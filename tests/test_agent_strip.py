"""에이전트 스트립 서버 API 테스트 (REQ-20260824-044 G1~G5).

세션 transcript(streams 미러)에 Agent 스폰·결과를 심고, 에이전트 output
파일(jsonl)을 만들어 /api/agents·/api/agentstream 파싱을 검증한다.

격리: S9_ROOT=mktemp. 실행: python3 tests/test_agent_strip.py
"""
import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402


class TestAgentStrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9strip-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "boss", "S9_REWORK_WATCH": "off"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env,
                       timeout=15)
        subprocess.run([S9, "user", "add", "boss", "--role", "admin"],
                       capture_output=True, env=cls.env, timeout=15)

        # 에이전트 output(jsonl)
        cls.agout = os.path.join(cls.tmp, "agent-abc123.output")
        cls.ag_write(
            {"type": "assistant",
             "timestamp": "2026-08-24T10:00:00.000Z",
             "message": {"usage": {"output_tokens": 100},
                         "content": [{"type": "text",
                                      "text": "설계 검토를 시작한다"}]}})

        # 세션 transcript 미러: Agent 스폰 + 결과(agentId/output_file)
        os.makedirs(os.path.join(cls.tmp, "streams"), exist_ok=True)
        cls.stream = os.path.join(cls.tmp, "streams",
                                  "stripsess-0000.jsonl")
        with open(cls.stream, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "assistant", "timestamp": "2026-08-24T10:00:00.000Z",
                "message": {"content": [{
                    "type": "tool_use", "id": "toolu_ag1", "name": "Agent",
                    "input": {"subagent_type": "frontend-developer",
                              "description": "스트립 구현",
                              "prompt": "..."}}]}}) + "\n")
            f.write(json.dumps({
                "type": "user", "timestamp": "2026-08-24T10:00:01.000Z",
                "message": {"content": [{
                    "type": "tool_result", "tool_use_id": "toolu_ag1",
                    "content": [{"type": "text", "text":
                                 "Async agent launched successfully.\n"
                                 "agentId: abc123 (internal)\n"
                                 f"output_file: {cls.agout}\n"}]}]}}) + "\n")

        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기

    @classmethod
    def ag_write(cls, obj):
        with open(cls.agout, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)

    def get(self, path, expect_json=True):
        for attempt in range(3):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}{path}",
                        timeout=5) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode())
            except (ConnectionError, urllib.error.URLError):
                if attempt == 2:
                    raise
                time.sleep(0.3)

    # G1. 목록: type/desc/label/tokens/elapsed/active
    def test_test_agent_strip(self):
        """TestAgentStrip 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("g1_agents_list"):
                code, d = self.get("/api/agents?session=stripsess")
                self.assertEqual(code, 200, d)
                self.assertEqual(len(d["agents"]), 1, d)
                a = d["agents"][0]
                self.assertEqual(a["id"], "abc123")
                self.assertEqual(a["type"], "frontend-developer")
                self.assertEqual(a["desc"], "스트립 구현")
                self.assertEqual(a["label"], "설계 검토를 시작한다")
                self.assertEqual(a["tokens"], 100)
                self.assertTrue(a["active"])       # 방금 만든 파일 — mtime 신선
                self.assertGreater(a["elapsed"], 0)

            # G2. 라벨·토큰 갱신(증분): 새 활동 추가 → label 교체, tokens 합산
        with self.subTest("g2_label_updates"):
                self.get("/api/agents?session=stripsess")   # 캐시 적재
                self.ag_write(
                    {"type": "assistant",
                     "timestamp": "2026-08-24T10:01:00.000Z",
                     "message": {"usage": {"output_tokens": 50},
                                 "content": [{"type": "tool_use", "name": "Read",
                                              "id": "t2",
                                              "input": {"file_path":
                                                        "/tmp/mock-main.png"}}]}})
                code, d = self.get("/api/agents?session=stripsess")
                a = d["agents"][0]
                self.assertEqual(a["label"], "Read /tmp/mock-main.png")
                self.assertEqual(a["tokens"], 150)

            # G3. agentstream: 증분 열람 + 미존재 에이전트 404
        with self.subTest("g3_agentstream"):
                code, d = self.get("/api/agentstream?session=stripsess&agent=abc123")
                self.assertEqual(code, 200, d)
                self.assertTrue(d["events"])
                roles = {e["role"] for e in d["events"]}
                self.assertIn("assistant", roles)
                off = d["offset"]
                code, d2 = self.get(
                    f"/api/agentstream?session=stripsess&agent=abc123&after={off}")
                self.assertEqual(d2["events"], [])          # 증분 소진
                code, _ = self.get("/api/agentstream?session=stripsess&agent=nope")
                self.assertEqual(code, 404)

            # G4. 격리: 비멤버 시점 404 (admin as= 강등)
        with self.subTest("g4_isolation"):
                subprocess.run([S9, "user", "add", "stranger"], capture_output=True,
                               env=self.env, timeout=15)
                code, _ = self.get("/api/agents?session=stripsess&as=stranger")
                self.assertEqual(code, 404)
                code, _ = self.get(
                    "/api/agentstream?session=stripsess&agent=abc123&as=stranger")
                self.assertEqual(code, 404)

            # G5. 회귀: /api/stream 기존 동작(parse_stream_file 분리 후)
        with self.subTest("g5_stream_regression"):
            code, d = self.get("/api/stream?session=stripsess")
            self.assertEqual(code, 200)
            self.assertTrue(d["events"])
            self.assertIn("offset", d)
            self.assertIn("live", d)

if __name__ == "__main__":
    unittest.main(verbosity=2)
