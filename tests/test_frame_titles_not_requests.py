"""하네스가 붙인 틀로 시작하는 프롬프트는 요청이 아니다 (REQ-20260915-072).

실측(2026-09-16, vault 전수): 틀 제목 요청 84건이 **전부** 휴지통에 있다 —
`<cross-session-message` 48건(REQ-20260909-037 이 막은 뒤로 새 것 없음)과
`<agent-message` 36건(9/15 하루에만 31건, 아직 막히지 않았다). 훅의 목록은
손으로 세는 것이라 하네스가 틀을 새로 하나 만들 때마다 같은 구멍이 다시
열린다 — 그래서 이름만이 아니라 **생김새**(첫 줄 전체가 하이픈 있는 태그)로도
가른다. 사람이 붙여 넣은 HTML(`<div class=…>`)은 여전히 요청으로 선다.

실행: python3 tests/ test_frame_titles_not_requests
tests/test_cross_session_not_request.py 의 본보기 — 훅의 `run` 을 가로채
s9 프로세스를 띄우지 않는다.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9.py")
HOOK = os.path.join(REPO, "bin", "s9-audit-prompt")

os.environ.pop("S9_AUTO_RESUME", None)


def _load_file(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


hook = _load_file("s9_audit_prompt_frames", HOOK)


def load(root):
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        return _load_file("s9_frames_%d" % abs(hash(root)), S9)
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


SID = "ffff6666yy"
AGENT = ('<agent-message from="ae0ec8676bce1d66e">\n'
         '[Subagent hand-back] The text below is the final report of a subagent.\n'
         '  `[2026-09-15 13:38:39 KST - designer]`\n'
         '  REQ-20260915-015-62x6 화면 설계입니다.')
HUMAN = "대시보드 헤더에 새로고침 버튼을 추가해줘"


class FrameTitlesAreNotRequests(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-frames-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.m = load(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.cmd_init(type("A", (), {})())
        self.calls = []

    def fake_run(self, env, *argv, inp=None):
        self.calls.append(argv)
        if argv and argv[0] == "log":
            self.m.session_log_append(env["S9_SESSION"], argv[1])
        if argv and argv[0] == "new":
            return mock.Mock(returncode=0, stdout="REQ-20260916-001-xxxx: created\n")
        return mock.Mock(returncode=0, stdout="")

    def run_hook(self, prompt):
        payload = json.dumps({"prompt": prompt, "session_id": SID, "cwd": self.root})
        with mock.patch.object(hook, "run", self.fake_run), \
             mock.patch.dict(os.environ, {"S9_ROOT": self.root}), \
             mock.patch.object(sys, "stdin", io.StringIO(payload)), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            hook.main()
        return out.getvalue()

    def session_history(self):
        base = os.path.join(self.m.VAULT, "sessions")
        lines = []
        for dirpath, _d, files in os.walk(base):
            for fn in files:
                if fn.startswith("SES-") and fn.endswith(".md"):
                    with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                        lines.extend(f.read().splitlines())
        return lines

    def new_calls(self):
        return [a for a in self.calls if a and a[0] == "new"]

    def assert_request(self):
        self.assertTrue(any(a[1] == "request" for a in self.new_calls()), self.calls)

    def assert_no_request(self):
        self.assertEqual(self.new_calls(), [], self.calls)

    # 정상 ────────────────────────────────────────────────────────────────
    def test_n1_an_ordinary_prompt_still_becomes_a_request(self):
        self.run_hook(HUMAN)
        self.assert_request()

    def test_n2_a_subagent_hand_back_makes_no_request(self):
        self.run_hook(AGENT)
        self.assert_no_request()

    def test_n3_a_cross_session_message_still_leaves_its_one_line(self):
        self.run_hook('<cross-session-message from="bridge:session_MAC1" '
                      'from-name="맥 리드">\n072 진행 상황?')
        self.assert_no_request()
        self.assertTrue(any("cross-session 메시지 수신 (from 맥 리드)" in ln
                            for ln in self.session_history()), self.session_history())

    # 경계 ────────────────────────────────────────────────────────────────
    def test_b1_an_unknown_frame_is_skipped_and_named_in_the_session(self):
        self.run_hook('<future-frame kind="x">\n무언가')
        self.assert_no_request()
        self.assertTrue(any("하네스 틀 수신 (<future-frame kind=\"x\">)" in ln
                            for ln in self.session_history()), self.session_history())

    def test_b2_surrounding_whitespace_does_not_change_the_verdict(self):
        self.run_hook("  \n\t" + AGENT + "\n  ")
        self.assert_no_request()

    def test_b3_a_multiline_body_does_not_change_the_verdict(self):
        self.run_hook(AGENT + "\n\n" + ("한 줄 더\n" * 20))
        self.assert_no_request()

    # 실패 ────────────────────────────────────────────────────────────────
    def test_f1_pasted_html_without_a_hyphen_is_still_a_request(self):
        self.run_hook('<div class="card">\n이 마크업의 여백이 어긋난다 — 고쳐줘')
        self.assert_request()

    def test_f2_a_first_line_that_does_not_close_the_tag_is_recorded(self):
        # 사람이 그 이름을 입에 올린 말이다 — 틀이 아니므로 그대로 기록된다
        # (물음표로 끝나니 question 으로 서는 것이 맞다).
        self.run_hook("<agent-message 를 왜 못 막나?")
        self.assertTrue(self.new_calls(), self.calls)

    # 회귀 ────────────────────────────────────────────────────────────────
    def test_r1_the_older_marks_are_still_blocked(self):
        for p in ("<task-notification>\n<task-id>x</task-id>",
                  "<system-reminder>\n무언가",
                  "[SYSTEM NOTIFICATION - NOT USER INPUT]\n무언가"):
            with self.subTest(p=p.splitlines()[0]):
                self.calls = []
                self.run_hook(p)
                self.assert_no_request()

    def test_r2_the_detector_reports_the_frame_name(self):
        self.assertEqual(hook.harness_frame(AGENT),
                         '<agent-message from="ae0ec8676bce1d66e">')
        self.assertEqual(hook.harness_frame(HUMAN), "")


if __name__ == "__main__":
    unittest.main()
