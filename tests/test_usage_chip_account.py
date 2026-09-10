"""사용량 칩은 계정이 바뀌면 옛 계정의 값을 남기지 않는다 (REQ-20260910-008-2n7g).

실제 사고 2026-09-10 22:35: 세션을 claude04 계정으로 다시 띄운 뒤에도 화면
오른쪽 위 계정 줄은 claude01 의 메일과 숫자를 보였다 — 맥에서 프로필 계정은
Keychain 을 못 읽어 사용량 조회가 늘 실패하고, 「못 받으면 마지막 값을 시각
마크와 함께 둔다」(REQ-20260907-068)는 규칙이 **다른 계정의 값**까지 그대로
두었기 때문이다. 사람은 「여전히 바꾸기 전의 계정이 보인다. 제대로 바뀐 건지
알 길이 없다」고 읽었다.

서버는 실패 응답에도 그 세션의 계정(email)을 싣는다. 계정이 다르면 옛 숫자는
이 계정의 것이 아니다 — 버리고 새 계정을 빈 숫자로 세운다. 같은 계정이면 종전
규칙(마지막 값 + 마크)이 그대로다.

실행: python3 tests/ usage_chip_account
"""
import importlib.util
import json
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def _keeps():
    """같은 하네스로 같은 갈래를 잰다 — test_usage_chip_keeps 의 STUBS·_fn·_fail_branch.
    경로로 싣는다: 시험 파일끼리의 `import` 는 표준 라이브러리 검사가 바깥 의존으로 본다."""
    p = os.path.join(HERE, "test_usage_chip_keeps.py")
    spec = importlib.util.spec_from_file_location("usage_chip_keeps", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


K = _keeps()
NODE, STALE, STUBS, USAGE_SRC = K.NODE, K.STALE, K.STUBS, K.USAGE_SRC
_fail_branch, _fn = K._fail_branch, K._fn


@unittest.skipUnless(NODE, "node 가 없다")
class ChipFollowsTheAccount(unittest.TestCase):
    def _drive(self, last, d):
        driver = STUBS + _fn(USAGE_SRC, "renderUsageChip") + f"""
let usageLast = {json.dumps(last)};
const el = mkEl(); el.setAttribute("tabindex", "0");
const d = {json.dumps(d)};
(function(){{ """ + _fail_branch(USAGE_SRC) + """ })();
console.log(JSON.stringify({html: el.innerHTML, last: usageLast}));"""
        r = subprocess.run([NODE, "-e", driver], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip())

    def test_a1_another_account_replaces_the_old_one(self):
        """핵심 — 실패했어도 응답의 계정이 다르면 새 계정이 서고 옛 숫자는 사라진다."""
        got = self._drive(
            {"email": "old@x", "limits": [{"kind": "session", "percent": 29}]},
            {"ok": False, "email": "new@x", "cfg_dir": "/p/new",
             "error": "자격증명 없음 — 프로필은 Keychain 을 읽지 않는다"})
        self.assertIn("new@x", got["html"], "바꾼 계정이 화면에 서지 않는다")
        self.assertNotIn("old@x", got["html"], "옛 계정이 그대로 보인다 — 사고 그대로다")
        self.assertNotIn("29%", got["html"], "옛 계정의 숫자가 새 계정 것처럼 남았다")
        self.assertNotIn(STALE, got["html"], "새 계정의 빈 값에 「낡은 값」 마크를 달았다")
        self.assertEqual(got["last"]["email"], "new@x")
        self.assertIn("Keychain", got["last"]["error"], "왜 비었는지가 카드에 갈 수 없다")

    def test_a2_same_account_keeps_the_last_value(self):
        """경계 — 같은 계정의 실패는 종전 규칙: 마지막 값이 마크를 달고 남는다."""
        got = self._drive(
            {"email": "a@b", "limits": [{"kind": "session", "percent": 29}]},
            {"ok": False, "email": "a@b", "error": "usage 조회 실패"})
        self.assertIn("a@b", got["html"])
        self.assertIn("29%", got["html"], "같은 계정인데 마지막 값을 버렸다")
        self.assertIn(STALE, got["html"])

    def test_a3_no_email_in_the_failure_keeps_the_last_value(self):
        """경계 — 응답이 아예 없거나 계정을 안 실으면 바뀐 것으로 보지 않는다."""
        for d in (None, {"ok": False, "error": "서버 연결 실패"}):
            got = self._drive(
                {"email": "a@b", "limits": [{"kind": "session", "percent": 29}]}, d)
            self.assertIn("a@b", got["html"], d)
            self.assertIn(STALE, got["html"], d)

    def test_a5_first_failure_still_names_the_account(self):
        """경계 — 받은 적이 없어도(F5 직후) 응답이 계정을 알면 계정이 선다."""
        got = self._drive(None, {"ok": False, "email": "new@x",
                                 "error": "자격증명 없음"})
        self.assertIn("new@x", got["html"], "계정을 아는데 「받지 못했습니다」만 세웠다")
        self.assertNotIn(STALE, got["html"])

    def test_a4_hover_names_the_account_and_the_reason(self):
        """빈 숫자의 카드는 계정과 사유를 말한다 — 「아직 못 받았다」만으로는 왜인지 모른다."""
        src = _fn(USAGE_SRC, "showUsageHover")
        self.assertIn("d.error", src, "카드가 실패 사유를 말하지 않는다")
        self.assertIn("umail", src, "카드가 계정을 말하지 않는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
