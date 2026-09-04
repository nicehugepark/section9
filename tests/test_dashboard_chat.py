"""대시보드 채팅 테스트 (REQ-20260824-032 아키텍처 v3).

세션 간 메시징 없이 수신함 파일(state/terminal/inbox-<sid8>.jsonl) append로
세션을 깨운다. 서버 라우트(/api/chat*)·대상 자동 선택·전이 즉시 통지·훅의
arming 지시 주입을 검증한다.

격리: S9_ROOT=mktemp. 실행: python3 tests/test_dashboard_chat.py
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
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-session")
PHOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")


# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402


class TestDashboardChat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9chat-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)

        def cli(*argv, env_extra=None, expect=0):
            env = {**cls.env, **(env_extra or {})}
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=env, timeout=15, stdin=subprocess.DEVNULL)
            if expect is not None and r.returncode != expect:
                raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                     f"{r.stdout}{r.stderr}")
            return r
        cls.cli = staticmethod(cli)

        cli("init")
        cli("user", "add", "tester")

        # 라이브 세션 바인딩: attach_pid=1(항상 생존) + 신선한 스트림 활동
        cls.sid = "livesess"
        env_s = {"S9_SESSION": cls.sid}
        cli("log", "session start", env_extra=env_s)
        cli("bind", "attach_pid", "1", env_extra=env_s)
        os.makedirs(os.path.join(cls.tmp, "streams"), exist_ok=True)
        cls.stream = os.path.join(cls.tmp, "streams", f"{cls.sid}-full.jsonl")
        with open(cls.stream, "w") as f:
            f.write("{}\n")

        # 죽은 세션 바인딩(attach_pid 비생존) — 자동 대상에서 제외돼야 한다
        env_d = {"S9_SESSION": "deadsess"}
        cli("log", "session start", env_extra=env_d)
        cli("bind", "attach_pid", "999999999", env_extra=env_d)

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
        if payload is None:
            req = urllib.request.Request(url)
        else:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(), method="POST",
                headers={"Content-Type": "application/json"})
        # 붙자마자 끊기는 갈래가 낮은 비율로 있다 — 윈도우 쪽 중계가 그 자리를
        # 함께 듣는다(REQ-20260902-006). 되걸지 않으면 스위트가 길어질 때
        # `RemoteDisconnected` 로 넘어지고, 홀로는 늘 초록이라 원인이 안 보인다
        # (실측 2026-09-04, 전체 실행 중 1회). (REQ-20260903-012)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode())
            except (ConnectionError, urllib.error.URLError):
                if attempt == 2:
                    raise
                time.sleep(0.3)

    def inbox(self, sid):
        p = os.path.join(self.tmp, "state", "terminal", f"inbox-{sid}.jsonl")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(x) for x in f.read().splitlines() if x.strip()]

    def touch_stream(self):
        os.utime(self.stream, None)

    # C1. 수신함 기록: POST /api/chat → {ts,from,kind,text} 줄 append (from=whoami)
    def test_c1_chat_appends_inbox(self):
        self.touch_stream()
        code, res = self.api("/api/chat", {"text": "안녕 리드"})
        self.assertEqual(code, 200, res)
        self.assertEqual(res["sid"], self.sid)
        lines = self.inbox(self.sid)
        self.assertTrue(lines)
        last = lines[-1]
        self.assertEqual(last["text"], "안녕 리드")
        self.assertEqual(last["kind"], "chat")
        self.assertTrue(last["from"])   # 서버 파생 whoami
        self.assertTrue(last["ts"])

    # C2. 대상 자동 선택: 살아있는 attach 세션 — 죽은 세션은 제외. sid 명시 우선.
    def test_c2_target_selection(self):
        self.touch_stream()
        code, res = self.api("/api/chat/target")
        self.assertEqual(code, 200)
        self.assertEqual(res["sid"], self.sid)   # deadsess가 아니라 livesess
        self.assertTrue(res["live"])
        # sid 명시 시 그 세션 (죽어 있어도 명시 대상은 존중)
        code, res = self.api("/api/chat/target?sid=deadsess")
        self.assertEqual(res["sid"], "deadsess")
        self.assertFalse(res["live"])

    # C2b. attach_pid가 낡아 죽었어도 신선한 활동(스트림 mtime)이면 살아있다 —
    #      실세션 회귀(재개·프로세스 교체로 pid는 흔히 낡는다)
    def test_c2b_stale_pid_fresh_activity(self):
        env_s = {"S9_SESSION": "stalesess"}
        self.cli("log", "session start", env_extra=env_s)
        self.cli("bind", "attach_pid", "999999998", env_extra=env_s)
        with open(os.path.join(self.tmp, "streams",
                               "stalesess-full.jsonl"), "w") as f:
            f.write("{}\n")
        code, res = self.api("/api/chat/target?sid=stalesess")
        self.assertEqual(code, 200)
        self.assertTrue(res["live"])
        code, res = self.api("/api/chat", {"text": "핑", "sid": "stalesess"})
        self.assertEqual(code, 200, res)
        self.assertEqual(self.inbox("stalesess")[-1]["text"], "핑")

    # C2d. 종료된 세션을 sid로 지목해도 그 무덤에 append 하지 않는다.
    #      (REQ-20260826-023: 죽은 수신함에 넣고 ok를 돌려주면 메시지가
    #      사용자 눈앞에서 조용히 사라진다 — 살아 있는 대상으로 돌린다)
    def test_c2d_ended_target_rerouted(self):
        env_g = {"S9_SESSION": "gonesess"}
        self.cli("log", "session start", env_extra=env_g)
        self.cli("bind", "attach_pid", "1", env_extra=env_g)
        self.cli("bind", "ended", "1", env_extra=env_g)
        code, res = self.api("/api/chat", {"text": "무덤에 넣지 마라",
                                           "sid": "gonesess"})
        self.assertEqual(code, 200, res)
        self.assertNotEqual(res["sid"], "gonesess")
        self.assertFalse(os.path.exists(
            os.path.join(self.tmp, "state", "terminal",
                         "inbox-gonesess.jsonl")))

    # C2c. entry=code 세션은 더 오래된 활동이라도 임시 세션(서브에이전트 등)보다
    #      자동 대상에서 우선한다
    def test_c2c_entry_code_priority(self):
        env_c = {"S9_SESSION": "codesess"}
        self.cli("log", "session start", env_extra=env_c)
        self.cli("bind", "attach_pid", "1", env_extra=env_c)
        self.cli("bind", "entry", "code", env_extra=env_c)
        p = os.path.join(self.tmp, "streams", "codesess-full.jsonl")
        with open(p, "w") as f:
            f.write("{}\n")
        old = time.time() - 120           # livesess보다 오래된 활동
        os.utime(p, (old, old))
        self.touch_stream()               # livesess 활동 최신
        try:
            code, res = self.api("/api/chat/target")
            self.assertEqual(res["sid"], "codesess")
        finally:
            self.cli("bind", "entry", "", env_extra=env_c)
            self.cli("bind", "attach_pid", "999999999", env_extra=env_c)
            os.remove(p)

    # C2d. ended(SessionEnd) 세션은 자동 대상에서 제외
    def test_c2d_ended_excluded(self):
        env_e = {"S9_SESSION": "endsess"}
        self.cli("log", "session start", env_extra=env_e)
        self.cli("bind", "attach_pid", "1", env_extra=env_e)
        self.cli("bind", "entry", "code", env_extra=env_e)
        self.cli("bind", "ended", "1", env_extra=env_e)
        self.touch_stream()
        try:
            code, res = self.api("/api/chat/target")
            self.assertNotEqual(res["sid"], "endsess")
        finally:
            self.cli("bind", "entry", "", env_extra=env_e)
            self.cli("bind", "attach_pid", "999999999", env_extra=env_e)

    # C3. 라이브 세션 없음 → 400 + s9 code 안내
    def test_c3_no_live_session(self):
        # 별도 vault로 서버 하나 더 — 바인딩 없음
        tmp2 = tempfile.mkdtemp(prefix="s9chat2-")
        env2 = {**os.environ, "S9_ROOT": tmp2, "S9_USER": "tester"}
        env2.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=env2, timeout=15)
        port2 = free_port()
        srv2 = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(port2)],
            env={**env2, "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_server(port2)
            req = urllib.request.Request(
                f"http://127.0.0.1:{port2}/api/chat",
                data=json.dumps({"text": "hi"}).encode(), method="POST",
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    code, res = r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                code, res = e.code, json.loads(e.read().decode())
            self.assertEqual(code, 400)
            self.assertIn("s9 code", res.get("error", ""))
        finally:
            srv2.terminate()
            srv2.wait(timeout=5)

    # C4. 전이 즉시 통지: 반려(review→in-progress) → 클레임 세션 수신함에 event
    def test_c4_transition_event(self):
        r = self.cli("new", "request", "--title", "통지 대상",
                     "--summary", "x", "--goal", "g", "--size", "S",
                     "--body", "b", env_extra={"S9_SESSION": self.sid})
        rid = r.stdout.split()[0]
        self.cli("status", rid, "in-progress", "--note", "착수",
                 env_extra={"S9_SESSION": self.sid})
        self.cli("note", rid, "- [x] T1. ok", "--label", "tdd",
                 env_extra={"S9_SESSION": self.sid})
        self.cli("status", rid, "review", "--note", "완료",
                 env_extra={"S9_SESSION": self.sid})
        self.touch_stream()
        before = len(self.inbox(self.sid))
        code, res = self.api("/api/status",
                             {"id": rid, "to": "in-progress",
                              "note": "반려 사유: 다시"})
        self.assertEqual(code, 200, res)
        self.assertEqual(res.get("notified"), self.sid)
        lines = self.inbox(self.sid)[before:]
        ev = [x for x in lines if x["kind"] == "event"]
        self.assertTrue(ev, lines)
        self.assertIn(rid, ev[-1]["text"])
        self.assertIn("반려", ev[-1]["text"])
        self.assertIn("반려 사유: 다시", ev[-1]["text"])

    # C9. inbox tail(Monitor) 프로세스가 살아있으면 죽은 pid·무활동이어도 live
    #     (REQ-20260824-042: 프롬프트 무관 생존 신호)
    def test_c9_inbox_tail_signal(self):
        env_t = {"S9_SESSION": "tailsess"}
        self.cli("log", "session start", env_extra=env_t)
        self.cli("bind", "attach_pid", "999999996", env_extra=env_t)
        inbox = os.path.join(self.tmp, "state", "terminal", "inbox-tailsess.jsonl")
        os.makedirs(os.path.dirname(inbox), exist_ok=True)
        open(inbox, "a").close()
        tail = subprocess.Popen(["tail", "-f", inbox],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            time.sleep(0.2)
            code, res = self.api("/api/chat/target?sid=tailsess")
            self.assertTrue(res["live"], res)          # V1
        finally:
            tail.terminate()
            tail.wait(timeout=5)
        time.sleep(0.2)
        code, res = self.api("/api/chat/target?sid=tailsess")
        self.assertFalse(res["live"], res)             # V2

    # C8. 프롬프트 훅이 attach_pid를 매번 재바인딩 — 낡은 pid 자가 치유
    #     (REQ-20260824-041: 유휴 5분 후 no live session 오검출 회귀)
    def test_c8_prompt_hook_rebinds_attach(self):
        env_r = {"S9_SESSION": "rebindss"}
        self.cli("log", "session start", env_extra=env_r)
        self.cli("bind", "attach_pid", "999999997", env_extra=env_r)
        self.cli("bind", "ended", "1", env_extra=env_r)
        r = subprocess.run([PHOOK], input=json.dumps(
            {"session_id": "rebindss-full", "prompt": "실사용 프롬프트다"}),
            capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        b = json.loads(self.cli("bind", env_extra=env_r).stdout)
        # _claude_pid()는 조상 체인에서 claude/node를 찾는다(REQ-065) — 테스트
        # 환경에선 상위 하네스 pid일 수 있으므로 '살아있는 프로세스로 갱신됨'만 검증
        pid = int(b["attach_pid"])
        self.assertNotEqual(pid, 999999997)          # 낡은 값이 교체됨
        self.assertTrue(os.path.exists(f"/proc/{pid}"))
        self.assertFalse(b.get("ended"))

    # C5. 훅 주입: SessionStart 컨텍스트에 수신함 경로 + Monitor arming 지시
    def test_c5_hook_injects_arming(self):
        payload = {"session_id": "hooksess-full-id", "source": "startup"}
        r = subprocess.run([HOOK, "start"], input=json.dumps(payload),
                           capture_output=True, text=True,
                           env={**self.env, "S9_PORT": "1"}, timeout=20)
        self.assertIn("inbox-hooksess.jsonl", r.stdout)
        self.assertIn("Monitor", r.stdout)
        # 오프셋 arm (REQ-20260825-001): 빈 수신함이면 +1부터 follow
        self.assertIn("tail -c +1 -f", r.stdout)
        # 수신함 파일이 미리 생성됨
        self.assertTrue(os.path.exists(os.path.join(
            self.tmp, "state", "terminal", "inbox-hooksess.jsonl")))
        # resume에도 arming 지시는 주입된다 (Monitor는 재개 후 다시 arm 필요)
        r2 = subprocess.run([HOOK, "start"],
                            input=json.dumps({"session_id": "hooksess-full-id",
                                              "source": "resume"}),
                            capture_output=True, text=True,
                            env={**self.env, "S9_PORT": "1"}, timeout=20)
        self.assertIn("inbox-hooksess.jsonl", r2.stdout)

    # ---- REQ-20260825-001: 서버측 chat audit — 세션이 유휴여도 REQ 영속화 ----

    # C10. 명령형 채팅 → REQ 즉시 생성: 응답·inbox 줄에 req id, user=발신자
    def test_c10_chat_request_creates_req(self):
        self.touch_stream()
        code, res = self.api("/api/chat", {"text": "터미널 렌더러 색상 매핑 고쳐줘"})
        self.assertEqual(code, 200, res)
        req_id = res.get("req") or ""
        self.assertTrue(req_id.startswith("REQ-"), res)
        last = self.inbox(self.sid)[-1]
        self.assertEqual(last.get("req"), req_id)
        r = self.cli("show", req_id, "--meta")
        self.assertIn("user: tester", r.stdout)      # 발신자 귀속
        self.assertIn("auto-audit", r.stdout)
        self.assertIn(f"session: {self.sid}", r.stdout)

    # C11. 질문/파편/커맨드는 REQ 미생성 — 전송은 성공
    def test_c11_chat_question_no_req(self):
        self.touch_stream()
        for text in ("이 구조가 왜 이렇게 되어 있지?", "ㅇㅋ", "/compact"):
            code, res = self.api("/api/chat", {"text": text})
            self.assertEqual(code, 200, res)
            self.assertFalse(res.get("req"), (text, res))

    # C12. kind=interrupt (Esc 중단): 줄만 append, REQ 미생성. 미지 kind 거부.
    def test_c12_interrupt_kind(self):
        self.touch_stream()
        code, res = self.api("/api/chat", {"kind": "interrupt"})
        self.assertEqual(code, 200, res)
        self.assertFalse(res.get("req"))
        # 프로세스 신호 경로는 제거됐다 (REQ-20260830-047: SIGINT 1회가 세션을
        # 통째로 죽였다) — 응답에 signal 필드가 없어야 하고, 전달은 협조적
        # 큐잉(수신함) 하나뿐이다.
        self.assertNotIn("signal", res,
                         "signal 필드가 돌아왔다 — 프로세스 신호 경로 부활 의심")
        last = self.inbox(self.sid)[-1]
        self.assertEqual(last["kind"], "interrupt")
        self.assertTrue(last["text"])                # 기본 중단 문구
        code, _res = self.api("/api/chat", {"kind": "bogus", "text": "x"})
        self.assertNotEqual(code, 200)

    # C13. target 응답: listening(tail 실가동) + user 폴백(빈 바인딩 → whoami)
    def test_c13_target_listening_and_user(self):
        self.touch_stream()
        code, res = self.api("/api/chat/target")
        self.assertEqual(code, 200)
        self.assertIn("listening", res)
        self.assertFalse(res["listening"])           # 테스트 환경엔 tail 없음
        self.assertEqual(res["user"], "tester")      # binding user="" → whoami

    # C20. target 응답에 model 동봉 (REQ-20260825-037 재작업): 구버전 serve가
    #      키 자체를 안 줘 상태줄 모델 라벨이 통째로 실종되던 결함 — 실 HTTP
    #      왕복으로 키 존재와 트랜스크립트 파생 값을 고정한다.
    def test_c20_target_model_key(self):
        self.touch_stream()
        code, res = self.api("/api/chat/target")
        self.assertEqual(code, 200)
        self.assertIn("model", res)              # 키는 항상 존재 (빈 값 허용)
        # 트랜스크립트가 있으면 마지막 assistant의 model을 돌려준다
        tp = os.path.join(self.tmp, "modelsess-transcript.jsonl")
        with open(tp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {
                "model": "claude-fable-5", "stop_reason": "end_turn",
                "content": []}}) + "\n")
        env_s = {"S9_SESSION": "modelsess"}
        self.cli("log", "session start", env_extra=env_s)
        self.cli("bind", "transcript_path", tp, env_extra=env_s)
        code, res = self.api("/api/chat/target?sid=modelsess")
        self.assertEqual(code, 200)
        self.assertEqual(res.get("model"), "claude-fable-5")

    # C16. 선행 대화 보존 (REQ-20260825-007): Question 분류로 문서화되지 않은
    #      직전 메시지가, 이어진 Request의 REQ body에 [선행 대화]로 담긴다
    def test_c16_chat_context_carryover(self):
        self.touch_stream()
        code, res = self.api("/api/chat", {"text": "발번 구조가 왜 이렇게 되어 있지?"})
        self.assertEqual(code, 200, res)
        self.assertFalse(res.get("req"))             # 질문 — REQ 미생성
        code, res = self.api("/api/chat", {"text": "그 발번 구조를 개선해줘"})
        self.assertEqual(code, 200, res)
        req_id = res.get("req") or ""
        self.assertTrue(req_id.startswith("REQ-"), res)
        r = self.cli("show", req_id)
        self.assertIn("[선행 대화", r.stdout)
        self.assertIn("발번 구조가 왜 이렇게", r.stdout)   # 원안 메시지 보존
        self.assertIn("그 발번 구조를 개선해줘", r.stdout)

    # C17. 절대경로 시작 메시지도 REQ 기록 (REQ-20260825-014) — 커맨드(/이름)만 제외
    def test_c17_path_message_audited(self):
        self.touch_stream()
        code, res = self.api("/api/chat", {
            "text": "/home/tester/repo/state 이 경로 구조가 문제다. 재설계해줘"})
        self.assertEqual(code, 200, res)
        self.assertTrue((res.get("req") or "").startswith("REQ-"), res)

    # C18. 타깃 우선순위 (REQ-20260825-015): 수신 대기(tail) 세션이 활동
    #      신선도·워커보다 우선 — 리드가 타깃을 뺏기지 않는다
    def test_c18_listening_priority(self):
        import shutil
        tail = shutil.which("tail")
        if not tail:
            self.skipTest("tail 없음")
        inbox = os.path.join(self.tmp, "state", "terminal",
                             "inbox-livesess.jsonl")
        os.makedirs(os.path.dirname(inbox), exist_ok=True)
        open(inbox, "a").close()
        # 경쟁 세션: 더 신선한 활동 + entry=code (기존 규칙으로는 이쪽이 이김)
        env_w = {"S9_SESSION": "workerses"}
        self.cli("log", "session start", env_extra=env_w)
        self.cli("bind", "attach_pid", "1", env_extra=env_w)
        self.cli("bind", "entry", "code", env_extra=env_w)
        ws = os.path.join(self.tmp, "streams", "workerses-full.jsonl")
        with open(ws, "w") as f:
            f.write("{}\n")
        p = subprocess.Popen([tail, "-f", inbox],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        try:
            time.sleep(0.2)
            os.utime(ws, None)                     # 워커 활동이 더 신선해도
            code, res = self.api("/api/chat/target")
            self.assertEqual(code, 200)
            self.assertEqual(res["sid"], self.sid)  # tail 중인 livesess 유지
            self.assertTrue(res["listening"])
        finally:
            p.terminate()
            p.wait(timeout=5)
            self.cli("bind", "ended", "1", env_extra=env_w)

    # C19. 사람 판정 면제 (REQ-20260825-030): 대시보드 승인(review→done)은
    #      goal 미기재여도 성공 — 게이트는 에이전트용, CLI done은 여전히 거부
    def test_c19_dashboard_approve_bypasses_goal_gate(self):
        self.touch_stream()
        code, res = self.api("/api/chat", {"text": "게이트 면제 검증용 더미 요청 만들어줘"})
        self.assertEqual(code, 200, res)
        rid = res["req"]
        env_s = {"S9_SESSION": self.sid}
        # 제목 정리(042 게이트 통과) — goal은 일부러 비워 둔다(면제 검증 대상)
        self.cli("set", rid, "--title", "게이트 면제 검증", env_extra=env_s)
        self.cli("status", rid, "in-progress", env_extra=env_s)
        self.cli("status", rid, "review", "--note", "판정 요청", env_extra=env_s)
        # CLI done은 goal 게이트에 막힌다 (기존 규율 유지)
        r = self.cli("status", rid, "done", env_extra=env_s, expect=None)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("goal", r.stdout + r.stderr)
        # 대시보드 승인(judge 경로)은 통과
        code, res = self.api("/api/status", {"id": rid, "to": "done",
                                             "note": "승인"})
        self.assertEqual(code, 200, res)
        self.assertEqual(res.get("new"), "done")

    # C20. 드래그 착수 즉시 통지 (REQ-20260825-040): open→in-progress 대시보드
    #      전이가 수신 대기(tail) 리드 수신함에 착수 지시 이벤트로 즉시 도착
    def test_c20_drag_start_notifies_lead(self):
        import shutil
        tail = shutil.which("tail")
        if not tail:
            self.skipTest("tail 없음")
        inbox = os.path.join(self.tmp, "state", "terminal",
                             "inbox-livesess.jsonl")
        os.makedirs(os.path.dirname(inbox), exist_ok=True)
        open(inbox, "a").close()
        r = self.cli("new", "request", "--title", "드래그 통지 검증",
                     "--summary", "s", "--size", "S", "--body", "b",
                     env_extra={"S9_SESSION": self.sid, "S9_ORIGIN": "dgnt"})
        rid = r.stdout.split()[0]
        p = subprocess.Popen([tail, "-f", inbox],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        try:
            time.sleep(0.2)
            self.touch_stream()
            code, res = self.api("/api/status",
                                 {"id": rid, "to": "in-progress",
                                  "note": "drag 이동"})
            self.assertEqual(code, 200, res)
            last = self.inbox(self.sid)[-1]
            self.assertEqual(last["kind"], "event")
            self.assertIn("착수 지시", last["text"])
            self.assertIn(rid, last["text"])
        finally:
            p.terminate()
            p.wait(timeout=5)

    # C21. review 지목 감지 (REQ-20260825-041): 판정 대기 문서의 id·순번을
    #      언급한 채팅 줄에 review_refs 동봉 — 반려성 지적의 즉시 전이 근거
    def test_c21_review_refs_attached(self):
        self.touch_stream()
        r = self.cli("new", "request", "--title", "리뷰 지목 검증",
                     "--summary", "s", "--size", "S", "--goal", "g",
                     "--body", "b",
                     env_extra={"S9_SESSION": self.sid, "S9_ORIGIN": "rvrf"})
        rid = r.stdout.split()[0]
        env_s = {"S9_SESSION": self.sid}
        self.cli("status", rid, "in-progress", env_extra=env_s)
        self.cli("status", rid, "review", "--note", "확인 포인트", "--force",
                 env_extra=env_s)
        num = rid.split("-")[2]
        code, res = self.api("/api/chat",
                             {"text": f"{num} 리뷰를 내가 해야 하나? 다시 봐줘"})
        self.assertEqual(code, 200, res)
        last = self.inbox(self.sid)[-1]
        self.assertIn(rid, last.get("review_refs") or [], last)
        # review 아닌 문서 순번은 동봉되지 않는다 — done 전이 후 같은 언급
        self.cli("status", rid, "done", "--note", "닫음", "--force",
                 env_extra=env_s)
        code, res = self.api("/api/chat", {"text": f"{num} 어떻게 됐나?"})
        self.assertEqual(code, 200, res)
        last = self.inbox(self.sid)[-1]
        self.assertNotIn(rid, last.get("review_refs") or [], last)

    # C22. 원문 제목 게이트 (REQ-20260825-042): auto-audit 임시 제목 그대로면
    #      에이전트 전이 거부, 제목 정리 후 통과. 대시보드(judge) 전이는 허용.
    def test_c22_raw_title_gate(self):
        self.touch_stream()
        code, res = self.api("/api/chat", {
            "text": "게이트 검증용으로 아주 길게 쓴 요청 원문인데 제목이 이걸 그대로 잘라 쓰게 만들어줘"})
        self.assertEqual(code, 200, res)
        rid = res["req"]
        env_s = {"S9_SESSION": self.sid}
        r = self.cli("status", rid, "in-progress", env_extra=env_s, expect=None)
        self.assertNotEqual(r.returncode, 0)             # 원문 제목 → 거부
        self.assertIn("제목", r.stdout + r.stderr)
        # 대시보드 드래그(judge)는 사람 행위 — 게이트 미적용
        code, res = self.api("/api/status", {"id": rid, "to": "in-progress",
                                             "note": "drag"})
        self.assertEqual(code, 200, res)
        # 제목 정리 후 에이전트 전이 통과
        self.cli("set", rid, "--title", "게이트 검증", "--goal", "g",
                 env_extra=env_s)
        self.cli("status", rid, "review", "--note", "ok", env_extra=env_s)

    # C14. SessionStart: 유휴 중 쌓인 미처리 줄 주입 + EOF 오프셋 arm + seen 갱신
    def test_c14_hook_pending_injection(self):
        sid = "pendsess"
        inbox = os.path.join(self.tmp, "state", "terminal",
                             f"inbox-{sid}.jsonl")
        os.makedirs(os.path.dirname(inbox), exist_ok=True)
        with open(inbox, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "t1", "from": "tester", "kind": "chat",
                                "text": "밀린 대시보드 메시지"},
                               ensure_ascii=False) + "\n")
        payload = json.dumps({"session_id": sid + "-full", "source": "startup"})
        r = subprocess.run([HOOK, "start"], input=payload,
                           capture_output=True, text=True,
                           env={**self.env, "S9_PORT": "1"}, timeout=20)
        self.assertIn("밀린 대시보드 메시지", r.stdout)
        size = os.path.getsize(inbox)
        self.assertIn(f"tail -c +{size + 1} -f", r.stdout)
        with open(inbox + ".seen") as f:
            self.assertEqual(int(f.read().strip()), size)
        # 재시작: 신규 줄 없음 → 재주입 없음 (중복 처리 방지)
        r2 = subprocess.run([HOOK, "start"], input=payload,
                            capture_output=True, text=True,
                            env={**self.env, "S9_PORT": "1"}, timeout=20)
        self.assertNotIn("밀린 대시보드 메시지", r2.stdout)
        # 훅이 만든 바인딩이 다른 테스트의 자동 대상 선택을 오염시키지 않게 종료
        self.cli("bind", "ended", "1", env_extra={"S9_SESSION": sid})

    # C15. UserPromptSubmit: tail 미가동이면 미처리 줄을 컨텍스트로 주입
    #      ("ㅇㅋ" = nothing 분류라도 pending이 있으면 emit 되어야 한다)
    def test_c15_prompt_hook_pending(self):
        sid = "pdsess2x"   # 정확히 8자 — session_id[:8] 절단과 일치해야 한다
        inbox = os.path.join(self.tmp, "state", "terminal",
                             f"inbox-{sid}.jsonl")
        os.makedirs(os.path.dirname(inbox), exist_ok=True)
        with open(inbox, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "t1", "from": "tester", "kind": "chat",
                                "text": "유휴 중 온 채팅"},
                               ensure_ascii=False) + "\n")
        env = {**self.env, "S9_PORT": "1"}
        env.pop("S9_AUTO_RESUME", None)
        r = subprocess.run([PHOOK],
                           input=json.dumps({"session_id": sid + "-full",
                                             "prompt": "ㅇㅋ"}),
                           capture_output=True, text=True, env=env, timeout=20)
        self.assertIn("유휴 중 온 채팅", r.stdout)
        with open(inbox + ".seen") as f:
            self.assertEqual(int(f.read().strip()), os.path.getsize(inbox))
        self.cli("bind", "ended", "1", env_extra={"S9_SESSION": sid})


if __name__ == "__main__":
    unittest.main(verbosity=2)
