"""s9-audit-prompt classify 휴리스틱 테스트 (REQ-20260823-075).

실행: python3 tests/test_audit_prompt.py
"""
import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")

spec = importlib.util.spec_from_loader(
    "s9_audit_prompt",
    importlib.machinery.SourceFileLoader("s9_audit_prompt", HOOK))
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

# 격리: 무인(auto-resume) 워커 세션에서 스위트를 돌리면 상속된 S9_AUTO_RESUME=1이
# hook.main()을 auto-resume 분기로 보내 일반 분류 테스트가 전부 깨진다.
# auto-resume 경로 테스트는 mock.patch.dict로 명시 주입한다 (TestAutoResumeTurn).
os.environ.pop("S9_AUTO_RESUME", None)


class TestClassify(unittest.TestCase):
    # S1. 파편 차단: 짧은 무의미 단문은 REQ를 만들지 않는다
    def test_test_classify(self):
        """TestClassify 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("s1_fragment_single_word"):
                self.assertEqual(hook.classify("logout"), "fragment")

            # S2. 짧은 영어/한글 명사 파편
        with self.subTest("s2_fragments"):
                for t in ("test", "로그아웃", "asdf", "ㅁㄴㅇㄹ", "dashboard"):
                    self.assertEqual(hook.classify(t), "fragment", t)

            # S3. 짧아도 명령형이면 request 유지
        with self.subTest("s3_short_imperative_is_request"):
                self.assertEqual(hook.classify("로그아웃 만들어줘"), "request")
                self.assertEqual(hook.classify("로그인 고쳐"), "request")

            # S4. 짧은 질문은 question 유지
        with self.subTest("s4_short_question"):
                self.assertEqual(hook.classify("로그아웃 왜 안돼?"), "question")
                self.assertEqual(hook.classify("왜"), "question")

            # S5. 회귀: 기존 분류 불변
        with self.subTest("s5_regressions"):
            self.assertEqual(hook.classify("ㅇㅋ"), "nothing")
            self.assertEqual(hook.classify("073 이어서 진행해라"), "nothing")
            self.assertEqual(hook.classify("REQ-20260823-073 이어서"), "nothing")
            self.assertEqual(
                hook.classify("대시보드에서 프로젝트 멤버를 관리할 수 있는 화면이 필요하다. "
                              "추가와 제거, 역할 변경을 지원해야 한다."),
                "request")
            self.assertEqual(hook.classify("멤버 역할은 어디서 바꾸나요"), "question")
            # 긴 명사구(>20자)는 여전히 기본값 request
            self.assertEqual(
                hook.classify("프로젝트 멤버관리 대시보드 신규 구축 건"), "request")

class TestFragmentBranch(unittest.TestCase):
    # S6. 파편도 정정 경로 컨텍스트를 주입한다 (REQ는 미생성)
    def test_s6_fragment_emits_correction_context(self):
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append(argv)
            return mock.Mock(returncode=0, stdout="")

        payload = json.dumps({"prompt": "logout", "session_id": "b6556c6d00"})
        with mock.patch.object(hook, "run", fake_run), \
             mock.patch.object(sys, "stdin", io.StringIO(payload)), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            hook.main()
        printed = out.getvalue()
        # REQ 생성(new request) 호출이 없어야 한다
        self.assertFalse(any(a[:2] == ("new", "request") for a in calls), calls)
        # 세션 로그는 남는다
        self.assertTrue(any(a[0] == "log" for a in calls), calls)
        # 정정 경로 컨텍스트가 emit된다
        self.assertIn("s9 new request", printed)
        self.assertIn("additionalContext", printed)


class TestSystemNotificationTurn(unittest.TestCase):
    # S8. 시스템 통지(task-notification 등) 턴은 REQ 카드를 만들지 않는다
    def test_s8_notification_no_card(self):
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append(argv)
            return mock.Mock(returncode=0, stdout="")

        for body in ("<task-notification>\n<task-id>x</task-id>...",
                     "<system-reminder>\n[SYSTEM NOTIFICATION - NOT USER INPUT]...",
                     "[SYSTEM NOTIFICATION - NOT USER INPUT]\nThis is automated"):
            calls.clear()
            payload = json.dumps({"prompt": body, "session_id": "eeee5555xx"})
            with mock.patch.object(hook, "run", fake_run), \
                 mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                 mock.patch.object(sys, "stdout", io.StringIO()):
                hook.main()
            self.assertFalse(any(a[0] == "new" for a in calls), (body[:30], calls))


class TestAutoResumeTurn(unittest.TestCase):
    # S7. auto-resume 스폰 턴(S9_AUTO_RESUME=1)은 REQ 카드를 만들지 않는다
    def test_s7_auto_resume_no_card(self):
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append(argv)
            return mock.Mock(returncode=0, stdout="")

        payload = json.dumps({
            "prompt": "[section9 자동 재작업] REQ REQ-20260823-078 재작업하라 해줘",
            "session_id": "eeee5555xx"})
        with mock.patch.object(hook, "run", fake_run), \
             mock.patch.dict(hook.os.environ, {"S9_AUTO_RESUME": "1"}), \
             mock.patch.object(sys, "stdin", io.StringIO(payload)), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            hook.main()
        self.assertFalse(any(a[0] == "new" for a in calls), calls)
        self.assertTrue(any(a[0] == "log" for a in calls), calls)
        # 스폰 세션이 클레임할 수 있도록 sid + 대상 REQ 클레임 지시를 주입한다
        # (REQ-20260824-004: 이게 없으면 워처가 중복 스폰)
        printed = out.getvalue()
        # allowlist(s9 시작 명령만 허용)와 정합: env 접두가 아니라 --session 플래그 지시
        self.assertIn("s9 last REQ-20260823-078 --add --session eeee5555", printed)


class TestInteraction(unittest.TestCase):
    # N1. 즉석 인터랙션 (REQ-20260825-028): 응답으로 완결 — 카드 없음(question)
    def test_n1_interactions_no_card(self):
        for t in ("스피너 확인용 프롬프트다", "지금 상태 출력해줘",
                  "10초만 대기해줘", "웨이팅 텍스트 테스트용이다",
                  "현재 모델 알려줘"):
            self.assertEqual(hook.classify(t), "question", t)

    # N2. 지속 산출물 동사가 섞이면 request 유지 (애매하면 카드가 안전)
    def test_n2_produce_still_request(self):
        for t in ("이 화면 보여줘 그리고 정렬 고쳐줘",
                  "상태 출력 기능을 추가해줘"):
            self.assertEqual(hook.classify(t), "request", t)
        # 길이가 길면(설명 동반) 인터랙션 단서만으로 카드 생략하지 않는다
        long = "지금 대시보드 터미널의 웨이팅 스피너와 텍스트가 어떤 상태로 출력되는지 각 항목별로 알려줘"
        self.assertEqual(hook.classify(long), "request")


class TestIsCommand(unittest.TestCase):
    # I1. 커맨드 판별 정밀화 (REQ-20260825-014): /이름 토큰만 커맨드
    def test_i1_commands_vs_paths(self):
        self.assertTrue(hook.is_command("/compact"))
        self.assertTrue(hook.is_command("/rc"))
        self.assertTrue(hook.is_command("/code-review high"))
        # 절대경로로 시작하는 실메시지 — 커맨드가 아니다 (audit 누락 실사고)
        self.assertFalse(hook.is_command(
            "/home/tester/section9/state/terminal/uploads 이 경로도 문제가 있다"))
        self.assertFalse(hook.is_command("/etc/hosts 좀 봐줘"))
        self.assertFalse(hook.is_command("일반 텍스트"))


class TestAttachments(unittest.TestCase):
    # A1. 프롬프트의 [Image #N] → 이미지 캐시 실경로 매핑 (REQ-20260825-002:
    #     첨부도 요청 원문 — REQ body에 경로가 보존돼야 한다)
    def test_a1_image_refs_resolved(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            sid_full = "abcd1234-aaaa-bbbb"
            cache = os.path.join(home, ".claude", "image-cache", sid_full)
            os.makedirs(cache)
            p1 = os.path.join(cache, "1.png")
            open(p1, "wb").close()
            got = hook.attachment_paths("[Image #1] 이 화면 고쳐줘", sid_full,
                                        home=home)
            self.assertEqual(got, [p1])
            # 캐시에 없는 번호·참조 없는 프롬프트는 빈 목록
            self.assertEqual(
                hook.attachment_paths("[Image #2] x", sid_full, home=home), [])
            self.assertEqual(
                hook.attachment_paths("그냥 텍스트", sid_full, home=home), [])

    # A2. request 분류 시 REQ body에 첨부 경로가 덧붙는다
    def test_a2_request_body_carries_attachments(self):
        import tempfile
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append((argv, inp))
            return mock.Mock(returncode=0, stdout="REQ-20990101-001 x")

        with tempfile.TemporaryDirectory() as home:
            sid_full = "ffff0000-1111-2222"
            cache = os.path.join(home, ".claude", "image-cache", sid_full)
            os.makedirs(cache)
            open(os.path.join(cache, "1.png"), "wb").close()
            payload = json.dumps({
                "prompt": "[Image #1] 대시보드 헤더 정렬 고쳐줘",
                "session_id": sid_full})
            with mock.patch.object(hook, "run", fake_run), \
                 mock.patch.dict(hook.os.environ, {"HOME": home}), \
                 mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                 mock.patch.object(sys, "stdout", io.StringIO()):
                hook.main()
        new_calls = [(a, i) for a, i in calls if a[:2] == ("new", "request")]
        self.assertTrue(new_calls, calls)
        body = new_calls[0][1] or ""
        self.assertIn("[첨부]", body)
        self.assertIn("1.png", body)


class TestUserPrefs(unittest.TestCase):
    """개인 선호 자동 반영 (REQ-20260824-006)."""

    def _run_hook(self, prompt, cfg_json):
        calls, printed = [], io.StringIO()

        def fake_run(env, *argv, inp=None):
            calls.append(argv)
            out = ""
            if argv[:2] == ("user", "current"):
                out = "sjpark1 [source: binding X/y]"
            elif argv[:2] == ("user", "config"):
                out = cfg_json
            elif argv[0] == "new":
                out = "REQ-20260824-999  vault/..."
            elif argv[0] == "approvals":
                out = ("- REQ-20260824-025 신원 자동 파생 검토 — 승인 메모: "
                       "자동으로 다음 요청이 생성되고 진행이 된다는건가")
            elif argv[0] == "blocked":
                out = ("- REQ-20260823-078 그래프 (sjpark1, updated ...)\n"
                       "    사유: 패치 적용 대기(리드)")
            return mock.Mock(returncode=0, stdout=out)

        payload = json.dumps({"prompt": prompt, "session_id": "eeee5555xx"})
        with mock.patch.object(hook, "run", fake_run), \
             mock.patch.object(sys, "stdin", io.StringIO(payload)), \
             mock.patch.object(sys, "stdout", printed):
            hook.main()
        return printed.getvalue()

    # P1. pref_* 있으면 request/question 컨텍스트에 주입
    def test_test_user_prefs(self):
        """개인 선호 자동 반영 (REQ-20260824-006)."""
        with self.subTest("p1_prefs_injected"):
                cfg = json.dumps({"timezone": "Asia/Seoul",
                                  "pref_말투": "짧고 단정하게", "pref_보고": "결론 먼저"})
                out_req = self._run_hook("대시보드에 위젯 만들어줘", cfg)
                self.assertIn("개인 설정", out_req)
                self.assertIn("말투: 짧고 단정하게", out_req)
                out_q = self._run_hook("이건 왜 이래?", cfg)
                self.assertIn("보고: 결론 먼저", out_q)

            # P2 (016 개정). pref 없으면 '없음 + 기본 복귀·관성 금지'를 명시 주입 —
            # 삭제가 침묵이 아니라 지시가 되어야 설정이 항상 먹는다
        with self.subTest("p2_no_prefs_explicit_default"):
                out = self._run_hook("대시보드에 위젯 만들어줘",
                                     json.dumps({"timezone": "Asia/Seoul"}))
                self.assertIn("◈ 개인 설정: 없음", out)
                self.assertIn("관성을 따르지 마라", out)

            # P3. 저장 규약 지시가 request 규약에 포함
        with self.subTest("p3_save_instruction_present"):
                out = self._run_hook("대시보드에 위젯 만들어줘", "{}")
                self.assertIn("pref_<주제>", out)

            # B5 (REQ-20260824-028). 미확인 승인 메모가 주입되고 후속 착수 지시 포함
        with self.subTest("b5_approval_memo_injected"):
                out = self._run_hook("대시보드에 위젯 만들어줘", "{}")
                self.assertIn("🆗 방금 승인 처리된 요청의 메모", out)
                self.assertIn("자동으로 다음 요청이 생성되고", out)
                self.assertIn("구현 착수 신호", out)

            # B4 (REQ-20260824-011). blocked '패치 적용 대기'가 리드 프롬프트에 주입된다
        with self.subTest("b4_blocked_warning_injected"):
            out = self._run_hook("대시보드에 위젯 만들어줘", "{}")
            self.assertIn("⛔ 대기(blocked) 요청", out)
            self.assertIn("패치 적용 대기(리드)", out)
            self.assertIn("블락을 풀어라", out)

if __name__ == "__main__":
    unittest.main(verbosity=2)
