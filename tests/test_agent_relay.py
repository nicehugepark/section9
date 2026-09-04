"""에이전트 지목 전송 (REQ-20260825-095).

터미널에서 특정 서브에이전트를 지목해 보낸 메시지는 리드가 답하지 않고
그 에이전트에게 중계한다. 서버는 **살아 있는 대상만** 받아들인다 —
죽은 에이전트에게 보낸 메시지는 조용히 사라지기 때문이다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ agent_relay
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
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-session")
WEB = index_path()


# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402


class TestAgentRelay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9relay-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)

        def cli(*argv, env_extra=None):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env={**cls.env, **(env_extra or {})},
                               timeout=20, stdin=subprocess.DEVNULL)
            if r.returncode != 0:
                raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
            return r
        cls.cli = staticmethod(cli)
        cli("init")
        cli("user", "add", "tester")

        cls.sid = "relaysess"
        env_s = {"S9_SESSION": cls.sid}
        cli("log", "session start", env_extra=env_s)
        cli("bind", "attach_pid", "1", env_extra=env_s)

        # 위임 에이전트 2종을 세션 transcript 에 심는다: 살아있는 것 + 멈춘 것
        cls.live_out = os.path.join(cls.tmp, "agent-live.jsonl")
        cls.dead_out = os.path.join(cls.tmp, "agent-dead.jsonl")
        for p in (cls.live_out, cls.dead_out):
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"type": "assistant", "message": {
                    "content": [{"type": "text", "text": "작업 중"}]}}) + "\n")
        os.utime(cls.dead_out, (time.time() - 600, time.time() - 600))

        os.makedirs(os.path.join(cls.tmp, "streams"), exist_ok=True)
        cls.stream = os.path.join(cls.tmp, "streams", f"{cls.sid}-full.jsonl")
        rows = []
        for tu, aid, atype, out in (("tu1", "agentlive", "designer", cls.live_out),
                                    ("tu2", "agentdead", "staff-engineer",
                                     cls.dead_out)):
            rows.append({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": tu, "name": "Agent",
                 "input": {"subagent_type": atype, "description": "위임"}}]}})
            rows.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": tu,
                 "content": f"agentId: {aid}\noutput_file: {out}"}]}})
        with open(cls.stream, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**cls.env, "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)

    @classmethod
    def api(cls, path, payload=None):
        url = f"http://127.0.0.1:{cls.port}{path}"
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"}) if payload else \
            urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def inbox(self):
        p = os.path.join(self.tmp, "state", "terminal", f"inbox-{self.sid}.jsonl")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(x) for x in f.read().splitlines() if x.strip()]

    def touch(self):
        os.utime(self.stream, None)
        os.utime(self.live_out, None)

    # A1. 정상 전송: 지목한 에이전트 id·타입이 수신함 줄에 실린다
    def test_test_agent_relay(self):
        """TestAgentRelay 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("a1_targeted_line"):
                self.touch()
                code, res = self.api("/api/chat", {"text": "그 스킨 먼저 봐줘",
                                                   "agent": "agentlive"})
                self.assertEqual(code, 200, res)
                line = self.inbox()[-1]
                self.assertEqual(line["kind"], "chat")
                self.assertEqual(line["agent"], "agentlive")
                self.assertEqual(line["agent_type"], "designer")

            # A2. 대상 검증: 없는 id·멈춘 에이전트는 409, 수신함은 그대로
        with self.subTest("a2_unavailable_refused"):
                self.touch()
                before = len(self.inbox())
                for bad in ("nosuchagent", "agentdead"):
                    code, res = self.api("/api/chat", {"text": "여보세요", "agent": bad})
                    self.assertEqual(code, 409, (bad, res))
                    self.assertEqual(res.get("error"), "agent-unavailable", res)
                    self.assertIn("리드", res.get("reason", ""))   # 폴백 안내
                self.assertEqual(len(self.inbox()), before)

            # A3. 회귀: agent 없는 메시지는 기존대로 리드로 (필드도 없다)
        with self.subTest("a3_plain_message_regression"):
                self.touch()
                code, res = self.api("/api/chat", {"text": "리드에게 보내는 메시지"})
                self.assertEqual(code, 200, res)
                line = self.inbox()[-1]
                self.assertNotIn("agent", line)

            # A5. 감사: 지목 전송도 REQ로 기록된다 — 무기록 통로를 만들지 않는다
        with self.subTest("a5_audited"):
                self.touch()
                code, res = self.api("/api/chat", {
                    "text": "지목 전송도 요청으로 남아야 한다. 스킨 대비를 조정해줘",
                    "agent": "agentlive"})
                self.assertEqual(code, 200, res)
                self.assertTrue(res.get("req"), res)
                self.assertEqual(self.inbox()[-1].get("req"), res["req"])

            # A4. 중계 규율: 세션 훅 안내에 중계·규율·폴백·감사 지시가 들어간다
        with self.subTest("a4_hook_relay_directive"):
                r = subprocess.run(
                    [HOOK, "start"],
                    input=json.dumps({"session_id": "relayhook-full-session-id",
                                      "source": "startup"}),
                    capture_output=True, text=True,
                    env={**self.env, "S9_PORT": "1"}, timeout=20)
                out = r.stdout
                self.assertIn("agent 필드", out)
                self.assertIn("SendMessage", out)
                self.assertIn("하던 작업", out)     # 진행 중 작업 보호 규율
                self.assertIn("종료", out)          # 대상 부재 안내
                self.assertIn("--label response", out)   # 감사 기록

            # A6. 화면 계약: 전송 대상 칩과 해제 컨트롤이 존재한다
        with self.subTest("a6_composer_target_ui"):
                with open(WEB, encoding="utf-8") as f:
                    html = f.read()
                self.assertIn("cctarget", html)      # 대상 칩
                self.assertIn("termTargetClear", html)   # 해제 컨트롤

            # A7. 회귀: 지목(→ 버튼)과 열람(행 클릭)이 같은 스트립에서 서로를 삼키지
            # 않는다 — 지목 처리가 행 열람보다 먼저 걸리고 전파를 멈춰야 한다.
        with self.subTest("a7_target_and_viewer_coexist"):
            with open(WEB, encoding="utf-8") as f:
                html = f.read()
            i_t = html.find('closest("[data-target]")')
            i_r = html.find('closest(".ccagrow")')
            self.assertNotEqual(i_t, -1, "지목 버튼 핸들러가 없다")
            self.assertNotEqual(i_r, -1, "에이전트 행 열람 핸들러가 없다")
            self.assertLess(i_t, i_r, "지목이 열람보다 뒤면 → 클릭이 뷰어를 연다")
            self.assertIn("stopPropagation", html[i_t:i_r])
            # 대상이 활성 목록에서 사라지면 자동 해제 (칩이 유령으로 남지 않는다)
            self.assertIn("termTargetClear(T,", html)

if __name__ == "__main__":
    unittest.main(verbosity=2)
