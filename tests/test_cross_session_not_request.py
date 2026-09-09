"""세션 간 메시지는 요청이 아니다 (REQ-20260909-037).

다른 Claude 세션이 SendMessage 로 보낸 프롬프트는 머리에 하네스가
`<cross-session-message from=… from-name=…>` 을 붙여 UserPromptSubmit 훅에 닿는다.
훅이 이것을 사람의 요청으로 audit 해 「<cross-session-message f…」 제목의 REQ 가
여섯 번 섰다(맥, 매번 휴지통행). 사람이 친 말이 아니니 REQ 를 만들지 않고 세션
문서(SES)에 받았다는 한 줄만 남긴다 — 부르는 이름 학습(REQ-20260908-019)은 그대로다.

실행: python3 tests/ test_cross_session_not_request
시험마다 임시 S9_ROOT 를 쓰고, s9 프로세스는 띄우지 않는다 — 훅의 `run` 을
가로채 `log` 만 모듈 함수(session_log_append)로 넘긴다.
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

os.environ.pop("S9_AUTO_RESUME", None)   # 무인 워커에서 물려받으면 분기가 바뀐다


def _load_file(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


hook = _load_file("s9_audit_prompt_xs", HOOK)


def load(root):
    """tests/test_code_default_project.py 의 본보기 — 임시 루트로 s9 모듈을 올린다."""
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        return _load_file("s9_xs_%d" % abs(hash(root)), S9)
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


SID = "eeee5555xx"
TAG = ('<cross-session-message from="bridge:session_MAC1" '
       'from-name="맥 리드" from-mode="prompting">')
CROSS = TAG + "\n037 의 진행 상황을 알려 주세요."
HUMAN = "대시보드 헤더에 새로고침 버튼을 추가해줘"


class CrossSessionMessagesAreNotRequests(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-xs-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.m = load(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.cmd_init(type("A", (), {})())
        self.calls = []

    def fake_run(self, env, *argv, inp=None):
        self.calls.append(argv)
        if argv and argv[0] == "log":
            self.m.session_log_append(env["S9_SESSION"], argv[1])
        if argv and argv[0] == "new":     # 훅은 첫 낱말을 문서 id 로 읽는다
            return mock.Mock(returncode=0, stdout="REQ-20260909-001-xxxx: created\n")
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

    # S1 정상 ─────────────────────────────────────────────────────────────
    def test_an_ordinary_prompt_still_becomes_a_request(self):
        self.run_hook(HUMAN)
        self.assertTrue(any(a[1] == "request" for a in self.new_calls()), self.calls)

    # S2 경계 ─────────────────────────────────────────────────────────────
    def test_a_cross_session_message_leaves_one_session_line_and_no_request(self):
        self.run_hook(CROSS)
        self.assertEqual(self.new_calls(), [], self.calls)
        hits = [ln for ln in self.session_history()
                if "cross-session 메시지 수신 (from 맥 리드)" in ln]
        self.assertEqual(len(hits), 1, self.session_history())

    # S3 회귀 — 앞 공백·줄바꿈 ───────────────────────────────────────────
    def test_leading_whitespace_does_not_change_the_verdict(self):
        self.run_hook("  \n\t" + CROSS)
        self.assertEqual(self.new_calls(), [], self.calls)
        self.assertTrue(any("cross-session 메시지 수신" in ln
                            for ln in self.session_history()))

    # S4 회귀 — 부르는 이름 학습은 그대로 (REQ-20260908-019) ────────────
    def test_the_call_name_is_still_learned(self):
        self.run_hook(CROSS)
        learn = [a for a in self.calls if a[:2] == ("callname", "learn")]
        self.assertEqual(len(learn), 1, self.calls)
        self.assertTrue(learn[0][3].startswith(TAG), learn[0])
        # 응답 캡처는 question 턴과 같이 멈춘다 — 에이전트의 말에 대한 답은 REQ 응답이 아니다
        self.assertIn(("last", "--pause"), self.calls)

    # S2' 경계 — from-name 이 없으면 from 으로 적는다 ───────────────────
    def test_without_a_call_name_the_sender_id_is_written(self):
        self.run_hook('<cross-session-message from="bridge:session_Z">\n안녕하세요')
        self.assertEqual(self.new_calls(), [])
        self.assertTrue(any("(from bridge:session_Z)" in ln
                            for ln in self.session_history()), self.session_history())


if __name__ == "__main__":
    unittest.main()
