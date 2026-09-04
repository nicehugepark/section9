"""Terminal 탭 서버 API 테스트 (REQ-20260824-040 서버측: L1/L2/L3).

SSE 증분 푸시(/api/stream/sse), 첨부 업로드(/api/chat/upload),
명령 목록(/api/chat/commands).

격리: S9_ROOT=mktemp. 실행: python3 tests/test_terminal_api.py
"""
import base64
import http.client
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402


class TestTerminalApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9term-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester", "S9_REWORK_WATCH": "off"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env,
                       timeout=15)
        subprocess.run([S9, "user", "add", "tester", "--role", "admin"],
                       capture_output=True, env=cls.env, timeout=15)
        # 스트림 파일 준비 (transcript 미러 형식: jsonl)
        os.makedirs(os.path.join(cls.tmp, "streams"), exist_ok=True)
        cls.stream = os.path.join(cls.tmp, "streams",
                                  "ssetest1-0000-0000.jsonl")
        cls.write_event("첫 이벤트")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기

    @classmethod
    def write_event(cls, text):
        ev = {"type": "user", "timestamp": "2026-08-24T18:00:00.000Z",
              "message": {"role": "user", "content": text}}
        with open(cls.stream, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)

    def post(self, path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    # L1. SSE: 접속 후 새 이벤트 append → 1초 내 data 프레임 수신
    def test_test_terminal_api(self):
        """TestTerminalApi 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("l1_sse_incremental_push"):
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
                conn.request("GET", "/api/stream/sse?session=ssetest1&after=0")
                r = conn.getresponse()
                self.assertEqual(r.status, 200)
                self.assertIn("text/event-stream", r.getheader("Content-Type", ""))
                got = {"frames": []}

                def reader():
                    buf = b""
                    while len(got["frames"]) < 2:
                        chunk = r.read1(4096)
                        if not chunk:
                            return
                        buf += chunk
                        while b"\n\n" in buf:
                            frame, buf = buf.split(b"\n\n", 1)
                            if frame.startswith(b"data: "):
                                got["frames"].append(
                                    json.loads(frame[6:].decode()))
                t = threading.Thread(target=reader, daemon=True)
                t.start()
                # 기존 1건이 첫 프레임으로 와야 한다
                for _ in range(40):
                    if got["frames"]:
                        break
                    time.sleep(0.1)
                self.assertTrue(got["frames"], "초기 증분 미수신")
                # 새 이벤트 append → 1초 내 후속 프레임
                t0 = time.time()
                self.write_event("라이브 추가 이벤트")
                while len(got["frames"]) < 2 and time.time() - t0 < 3:
                    time.sleep(0.05)
                self.assertGreaterEqual(len(got["frames"]), 2, "증분 푸시 미수신")
                self.assertLess(time.time() - t0, 1.5, "푸시 지연 과다")
                texts = json.dumps(got["frames"][-1], ensure_ascii=False)
                self.assertIn("라이브 추가 이벤트", texts)
                conn.close()

            # L2. 업로드: base64 저장·절대경로 반환, 불량 입력 거부
        with self.subTest("l2_upload"):
                data = base64.b64encode(b"\x89PNG fakeimg").decode()
                code, res = self.post("/api/chat/upload",
                                      {"name": "shot.png", "data": data})
                self.assertEqual(code, 200, res)
                self.assertTrue(os.path.isabs(res["path"]))
                with open(res["path"], "rb") as f:
                    self.assertEqual(f.read(), b"\x89PNG fakeimg")
                self.assertIn(os.path.join("state", "terminal", "uploads"), res["path"])
                code, res = self.post("/api/chat/upload",
                                      {"name": "bad.bin", "data": "@@not-base64@@"})
                self.assertEqual(code, 400)
                code, res = self.post("/api/chat/upload", {"name": "e.png", "data": ""})
                self.assertEqual(code, 400)

            # L3. 명령 목록: 프로젝트 커맨드(.claude/commands) 노출
        with self.subTest("l3_commands"):
            cdir = os.path.join(self.tmp, ".claude", "commands")
            os.makedirs(cdir, exist_ok=True)
            with open(os.path.join(cdir, "deploy.md"), "w") as f:
                f.write("# deploy\n배포 절차 커맨드다\n")
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/api/chat/commands",
                    timeout=5) as r:
                d = json.loads(r.read().decode())
            names = {c["name"]: c for c in d["commands"]}
            self.assertIn("deploy", names)
            self.assertEqual(names["deploy"]["source"], "command")
            self.assertIn("배포 절차", names["deploy"]["desc"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
