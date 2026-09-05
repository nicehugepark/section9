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
