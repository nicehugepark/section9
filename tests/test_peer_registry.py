"""다른 자리의 세션 이름은 한 번만 묻는다 (REQ-20260907-080-62x6).

vault 는 세션마다 `machine` 을 적어 두므로 「맥이 있다」는 사실은 이미 안다.
모르는 것은 **그 머신에서 도는 세션을 밖에서 무엇이라 부르는가**다 — Remote
Control 목록의 표시 이름은 하네스가 짓고 vault 는 모른다. 2026-09-07 에 리드가
맥 Safari 검증을 부탁하려다 「어느 세션이 맥이냐」를 사람에게 물어야 했고,
그 답은 어디에도 남지 않아 다음 세션이 또 물을 자리였다.

`s9 peer` 는 그 답을 적어 두는 자리다. 장치 이름은 코드가 아니라 `state/` 에
있고(projects/section9/CONTEXT.md), 그래서 이 시험도 이름을 인자로만 준다.

실행: python3 tests/ peer_registry
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s9cli  # noqa: E402  (윈도우에서 확장자 없는 bin/s9 를 부르게 한다)

s9cli.install()
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9")


class ThePeerRegistry(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-peer-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_SESSION": "test0000"}

    def run9(self, *args):
        return subprocess.run([S9, "peer", *args], capture_output=True,
                              encoding="utf-8", errors="replace", env=self.env)

    def test_nothing_known_says_how_to_write_it_down(self):
        """정상 — 빈 자리는 비었다고 말하고, 무엇을 하면 되는지 함께 말한다."""
        out = self.run9("ls")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("s9 peer set", out.stdout, "적어 두는 길을 안 알려 준다")

    def test_a_name_written_once_comes_back(self):
        """정상 — 한 번 적으면 다음에 그대로 나온다(다시 묻지 않는다)."""
        self.run9("set", "저쪽 세션", "--machine", "some-host",
                  "--os", "macOS", "--note", "화면 검증")
        out = self.run9("ls")
        self.assertIn("저쪽 세션", out.stdout)
        self.assertIn("some-host", out.stdout)
        self.assertIn("화면 검증", out.stdout)

    def test_it_narrows_by_os(self):
        """정상 — 찾는 물음은 대개 「맥이 어느 것이냐」다."""
        self.run9("set", "맥 쪽", "--machine", "h1", "--os", "macOS")
        self.run9("set", "리눅스 쪽", "--machine", "h2", "--os", "Linux")
        out = self.run9("ls", "--os", "mac")
        self.assertIn("맥 쪽", out.stdout)
        self.assertNotIn("리눅스 쪽", out.stdout, "좁히지 않았다")

    def test_setting_again_keeps_what_was_not_given(self):
        """경계 — 한 칸만 고치러 왔는데 나머지가 지워지면 안 된다."""
        self.run9("set", "저쪽", "--machine", "h1", "--os", "macOS")
        self.run9("set", "저쪽", "--note", "화면 검증")
        out = self.run9("ls")
        self.assertIn("h1", out.stdout)
        self.assertIn("화면 검증", out.stdout)

    def test_removing_an_unknown_name_fails_loudly(self):
        """실패 — 모르는 이름을 지우라면 조용히 성공하지 않는다."""
        out = self.run9("rm", "없는 이름")
        self.assertNotEqual(out.returncode, 0)

    def test_it_lives_in_state_not_in_the_vault(self):
        """회귀 — 장치 이름은 이 머신의 살림이다(커밋되지 않는 state/)."""
        self.run9("set", "저쪽", "--machine", "h1")
        p = os.path.join(self.root, "state", "peers.json")
        self.assertTrue(os.path.exists(p), "state/peers.json 에 안 적혔다")
        self.assertIn("저쪽", json.load(open(p, encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
