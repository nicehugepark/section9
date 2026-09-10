"""CDP 실브라우저 공용 헬퍼 — 브라우저 탐색·회수·stdlib WebSocket.

test_hover_realscale(REQ-20260831-019)에서 추출했다: 시험 파일끼리
`import test_*` 로 얽히면 stdlib-only 검사(커밋 스모크)가 막고, 실제로도
한 시험의 픽스처 변경이 남의 시험을 깨는 길이 된다 — 공용 기반은
webasset·portpool 처럼 제 이름의 헬퍼로 산다.
"""
import base64
import glob
import json
import os
import shutil
import re
import socket
import struct
import subprocess
import sys
import time

# ---- 실측 브라우저 탐색 (s9 shot 과 같은 후보 순서) ------------------------
#
# **화소 계약** (REQ-20260910-003). 마크의 획이 몇 번째 화소에 앉는지까지 재는
# 시험(test_hover_realscale 류)은 브라우저의 글자·도형 래스터라이저에 걸린다 —
# 같은 Chrome 이어도 운영체제가 다르면 값이 다르다. 실측 2026-09-10 맥 Chrome:
# 과녁이 27 대신 28, ⏸ 잉크 +0.5화소, ▶ -1.095화소. 지금 소스에 적힌 기대값은
# Windows Chrome 에서 잰 것이라, 맥 브라우저로 그 시험을 돌리면 코드가 옳아도
# 3항목이 실패한다.
#
# 그래서 물음을 둘로 가른다: **브라우저를 찾았나**, 그리고 **그 브라우저로
# 화소를 재도 되나.** 배치·스크롤·클릭만 재는 시험은
# `chrome_path(pixel_contract=False)` 로 불러 맥에서도 실측하고, 화소를 재는
# 시험은 기본값 그대로 두면 맥에서는 사유와 함께 건너뛴다. 맥의 기대값을 따로
# 두는 일은 그 시험 파일의 몫이지 여기가 아니다.
#
# 계약 밖이라고 표시한 것은 **재 본 것뿐**이다 — 맥 갈래를 더하는 이 변경이
# Windows·PATH 갈래의 선택을 바꾸지 않는다.

WIN_CANDIDATES = (
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
)
PATH_NAMES = ("google-chrome", "chromium", "chromium-browser")
MAC_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
# playwright 가 받아 둔 Chromium — 맥에서 브라우저를 따로 깔지 않은 자리의 마지막 후보.
MAC_PLAYWRIGHT_GLOB = (
    "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")

NO_BROWSER = "브라우저 없음 — 실측 불가 환경"
OFF_CONTRACT = (
    "맥 브라우저만 찾았다 — 화소 계약(기대값을 Windows Chrome 에서 쟀다) 밖이라 "
    "화소를 재는 시험은 건너뛴다 (REQ-20260910-003). 배치·스크롤만 재는 시험은 "
    "chrome_path(pixel_contract=False) 로 부르면 맥에서도 실측한다")

_said = set()


def _mac_playwright():
    """받아 둔 Chromium 을 build 번호 오름차순으로 — 뒤가 최신이다."""
    def build(p):
        m = re.search(r"chromium[-_](\d+)", p)
        return int(m.group(1)) if m else -1
    return sorted(glob.glob(os.path.expanduser(MAC_PLAYWRIGHT_GLOB)), key=build)


def found():
    """찾은 실측 브라우저를 (경로, 화소 계약 안인가) 로 — 앞에 있는 것이 우선."""
    out = []
    for base in WIN_CANDIDATES:
        if os.path.exists(base):
            out.append((base, True))
    for name in PATH_NAMES:
        p = shutil.which(name)
        if p:
            out.append((p, True))
    for base in MAC_CANDIDATES:
        if os.path.exists(base):
            out.append((base, False))
    for p in reversed(_mac_playwright()):
        out.append((p, False))
    return out


def skip_reason(pixel_contract=True):
    """chrome_path() 가 None 을 낸 까닭 한 줄 — 건너뜀 메시지에 그대로 쓴다."""
    got = found()
    if not got:
        return NO_BROWSER
    if pixel_contract and not any(on for _, on in got):
        return OFF_CONTRACT
    return ""


def chrome_path(pixel_contract=True):
    """실측 브라우저 경로 — 없으면 None. 까닭은 skip_reason() 이 말한다.

    pixel_contract 는 「이 시험이 화소를 재는가」다. 기본은 재는 쪽이라, 계약
    밖의 브라우저밖에 없으면 경로 대신 None 을 낸다 — 건너뜀 메시지를 제 손으로
    적어 둔 옛 시험도 사유를 알 수 있게, 물린 까닭을 실행마다 한 번 알린다.
    """
    for path, on_contract in found():
        if on_contract or not pixel_contract:
            return path
    why = skip_reason(pixel_contract)
    if why and why != NO_BROWSER and why not in _said:
        _said.add(why)
        print("[cdpreal] " + why, file=sys.stderr)
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
