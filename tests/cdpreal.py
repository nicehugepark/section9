"""CDP 실브라우저 공용 헬퍼 — Windows Chrome 탐색·회수·stdlib WebSocket.

test_hover_realscale(REQ-20260831-019)에서 추출했다: 시험 파일끼리
`import test_*` 로 얽히면 stdlib-only 게이트(커밋 스모크)가 막고, 실제로도
한 시험의 픽스처 변경이 남의 시험을 깨는 길이 된다 — 공용 기반은
webasset·portpool 처럼 제 이름의 헬퍼로 산다.
"""
import base64
import json
import os
import shutil
import re
import socket
import struct
import subprocess
import time

# ---- Windows Chrome (s9 shot 과 같은 후보 순서) ----------------------------

def chrome_path():
    for base in ("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
                 "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                 "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe"):
        if os.path.exists(base):
            return base
    for name in ("google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None


def reclaim(marker, win):
    """캡처 브라우저 회수 — 우리 프로필(marker)을 가진 것만 (s9 shot 위생 규칙)."""
    try:
        out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True,
                             text=True, timeout=10).stdout
        for line in out.splitlines()[1:]:
            pid, _, cmd = line.strip().partition(" ")
            if pid.isdigit() and marker in cmd and "--headless" in cmd:
                try:
                    os.kill(int(pid), 15)
                except OSError:
                    pass
    except Exception:
        pass
    if win:
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process -Filter "
                 "\"Name='chrome.exe' or Name='msedge.exe'\" | "
                 f"Where-Object {{ $_.CommandLine -like '*{marker}*' }} | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
                 "-ErrorAction SilentlyContinue }"],
                capture_output=True, timeout=30)
        except Exception:
            pass


# ---- CDP: stdlib 만으로 WebSocket (REQ-20260830-043 선례) -------------------

class WS:
    def __init__(self, url, timeout=30):
        m = re.match(r"ws://([^/:]+):(\d+)(/.*)$", url)
        host, port, path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
             "Upgrade: websocket\r\nConnection: Upgrade\r\n"
             f"Sec-WebSocket-Key: {key}\r\n"
             "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            d = self.sock.recv(4096)
            if not d:
                raise ConnectionError("CDP 핸드셰이크 중 끊김")
            buf += d
        head, _, rest = buf.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError("CDP 업그레이드 거절: %r" % head[:80])
        self.buf = rest
        self.next_id = 0

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def _read(self, n):
        while len(self.buf) < n:
            d = self.sock.recv(1 << 16)
            if not d:
                raise ConnectionError("CDP 소켓 끊김")
            self.buf += d
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _send_frame(self, op, payload):
        head = bytearray([0x80 | op])
        n = len(payload)
        if n < 126:
            head.append(0x80 | n)
        elif n < (1 << 16):
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        mask = os.urandom(4)
        head += mask
        self.sock.sendall(bytes(head)
                          + bytes(b ^ mask[i % 4]
                                  for i, b in enumerate(payload)))

    def _recv_msg(self):
        data = b""
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            op = b1 & 0x0F
            if op == 9:                       # ping → pong
                self._send_frame(10, payload)
                continue
            if op == 8:
                raise ConnectionError("CDP 닫힘")
            data += payload
            if b1 & 0x80:
                return data

    def call(self, method, **params):
        self.next_id += 1
        self._send_frame(1, json.dumps(
            {"id": self.next_id, "method": method,
             "params": params}).encode())
        while True:
            msg = json.loads(self._recv_msg())
            if msg.get("id") == self.next_id:
                if "error" in msg:
                    raise RuntimeError("%s → %s" % (method, msg["error"]))
                return msg.get("result", {})

    def eval(self, expr):
        r = self.call("Runtime.evaluate", expression=expr,
                      returnByValue=True)
        return r.get("result", {}).get("value")


# ---- 준비 신호 — 한 자리에서 짓는다 (REQ-20260907-057 · DOC-20260907-003) ----
#
# `__S9_APP_READY` 는 스크립트가 실린 시점에 서고, 화면이 서버에서 받아 오는
# 재료(신원·사용자 목록·프로젝트 목록·문서 목록)는 그 뒤 왕복으로 온다. 둘 사이
# 틈은 단독 실행에서 닫히고 병렬 실행에서 벌어져, **전체 실행에서만 나는 간헐
# 실패**가 됐다(REQ-20260907-055). 그래서 파일마다 신호를 손으로 짓지 않는다 —
# 여기 한 자리에서 짓고, 시험은 제가 읽을 재료의 이름만 댄다.
#
# 재료가 어디까지 왔나는 **화면에게 묻는다.** window 전역은 화면이 값을 놓아둔
# 자리일 뿐이라 이름도 모양도 화면 사정에 따라 바뀌지만, `supplyState(k)` 는
# 화면이 스스로 그 물음에 답하는 자리다(web/app/boot.js). 상태는 wait|ok|lost 이고
# 다 온 것은 ok 뿐이다. 전역 대입(`window.__whoami = d`)은 상태가 ok 로 선 바로
# 다음 마이크로태스크라, 다음 CDP 왕복(새 태스크)에서는 이미 서 있다.
#
# 화면은 **사실만** 낸다: 판이 섰나 · 재료가 어디까지 왔나 · 볼 자리가 있나.
# 판단은 여기 파이썬 쪽에 둔다 — 그래야 브라우저 없이도 그 판단을 잴 수 있다.
READY_FACTS = """(() => {
  const needs = %s, sels = %s, supply = {}, sel = {};
  const asks = (typeof supplyState === 'function');
  for (const k of needs) supply[k] = asks ? (supplyState(k) || '') : null;
  for (const s of sels) sel[s] = !!document.querySelector(s);
  return {ready: !!window.__S9_APP_READY, supply: supply, sel: sel};
})()"""

# 준비 신호를 제 손으로 짓는 것이 허용된 시험 — 파일 이름 → 사유. 지금은 비어
# 있다. 더하려면 사유를 적어라: 적으면서 「왜 이 파일만 달라야 하나」를 스스로
# 묻게 된다. (tests/test_test_budget.py 의 가드가 이 목록을 읽는다.)
HANDMADE_READY_OK = {}


def ready_missing(ws, needs=(), sels=()):
    """아직 안 선 것의 이름을 낸다 — 빈 목록이면 재도 된다.

    needs 는 화면이 서버에서 받아 오는 재료 이름(whoami·users·projects·catalog),
    sels 는 눈으로 볼 자리(CSS 선택자, 하나면 문자열로 줘도 된다). 재료 이름을
    하나도 안 주면 옛 신호와 뜻이 같다 — 판과 볼 자리만 본다.
    """
    if isinstance(sels, str):
        sels = (sels,)
    needs, sels = list(needs), list(sels)
    f = ws.eval(READY_FACTS % (json.dumps(needs, ensure_ascii=False),
                               json.dumps(sels, ensure_ascii=False)))
    if not isinstance(f, dict):
        raise ConnectionError("준비 상태를 못 읽었다 — %r" % (f,))
    miss = []
    if not f.get("ready"):
        miss.append("판(__S9_APP" + "_READY)")
    supply, sel = f.get("supply") or {}, f.get("sel") or {}
    for k in needs:
        st = supply.get(k)
        # `supplyState` 자체가 없는 옛 판은 「없음」으로 센다 — 못 묻는 것을
        # 「왔다」로 치면 조용히 통과한다.
        if st != "ok":
            miss.append("%s(%s)" % (k, st or ("없음(묻는 자리가 없다)"
                                              if st is None else "없음")))
    for s in sels:
        if not sel.get(s):
            miss.append("볼 자리 %s" % s)
    return miss


def wait_ready(ws, needs=(), sels=(), tries=200, gap=0.25):
    """판·재료·볼 자리가 다 설 때까지 기다린다 — 끝내 안 서면 이름을 대고 끊는다."""
    miss = ["아직 한 번도 못 물었다"]
    for _ in range(tries):
        miss = ready_missing(ws, needs, sels)
        if not miss:
            return
        time.sleep(gap)
    raise ConnectionError("판이 재료를 못 받았다 — 못 기다린 것: %s" % ", ".join(miss))
