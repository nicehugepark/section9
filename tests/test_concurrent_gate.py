"""빠져나가는 문은 증거를 받는다 (REQ-20260907-062).

작업자가 붙어 있는 중에 그 사이 바뀐 파일을 담으면 가드가 막는다. 그런데 그
문을 여는 값이 `1` 이었다 — 「읽었다」는 주장일 뿐이고 읽었는지는 아무도 안
봤다. 2026-09-07 18:26 에 리드가 그 문으로 남의 진행 중 변경 셋을 제 커밋에
쓸어 담았다. **사람이 규율을 안 지킨 것이 아니라 지키지 않아도 지나갈 수
있었다.**

고정하는 계약 넷.
1. 표(token)를 손에 넣는 유일한 길이 목록을 보는 것이다 — 가드가 막으면서
   목록과 함께 알려 준다.
2. 옛 방식(`=1`)으로는 못 지나간다.
3. 목록이 바뀌면 표도 바뀐다 — 그 사이 남이 또 고쳤으면 다시 봐야 한다.
4. 지나간 사실은 commit 메시지에 남는다 — 지나간 것을 **보이게** 만든다.

실행: python3 tests/ concurrent_gate
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")

TMP = tempfile.mkdtemp(prefix="s9-cgate-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT",)}
os.environ["S9_ROOT"] = TMP
try:
    spec = importlib.util.spec_from_loader(
        "s9_guard_cg", importlib.machinery.SourceFileLoader("s9_guard_cg", GUARD))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class TheToken(unittest.TestCase):
    def test_the_same_set_gives_the_same_token(self):
        a = g.concurrent_token([("b.py", 3), ("a.py", 9)])
        b = g.concurrent_token([("a.py", 1), ("b.py", 2)])
        self.assertEqual(a, b, "순서·나이가 표를 바꾸면 안 된다 — 집합이 재료다")

    def test_a_different_set_gives_a_different_token(self):
        a = g.concurrent_token([("a.py", 1)])
        b = g.concurrent_token([("a.py", 1), ("c.py", 1)])
        self.assertNotEqual(a, b, "목록이 바뀌었는데 옛 표로 지나갈 수 있다")

    def test_it_is_short_enough_to_type(self):
        self.assertLessEqual(len(g.concurrent_token([("a.py", 1)])), 8)


class TheGate(unittest.TestCase):
    """`concurrent_gate` 를 실제로 부른다 — 소스 글자를 대조하지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-cgate-root-")
        self.f = "tests/남의것.py"
        p = os.path.join(self.root, self.f)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").close()          # 방금 만든 파일 = 방금 바뀐 파일

    def _run(self, override=None, workers=("REQ-x (백그라운드 작업자 pid 1, 1분째)",)):
        env = {} if override is None else {g.OVERRIDE: override}
        with mock.patch.object(g, "ROOT", self.root), \
                mock.patch.object(g, "live_workers", lambda: list(workers)), \
                mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop(g.OVERRIDE, None) if override is None else None
            return g.concurrent_gate([self.f])

    def test_no_worker_no_gate(self):
        self.assertIsNone(self._run(workers=()))

    def test_it_blocks_without_a_token(self):
        with self.assertRaises(SystemExit):
            self._run()

    def test_the_old_way_no_longer_passes(self):
        """`=1` 은 목록을 봤다는 증거가 아니다 — 이것이 이 요청의 전부다."""
        with self.assertRaises(SystemExit):
            self._run("1")

    def test_the_right_token_passes(self):
        tok = g.concurrent_token([(self.f, 0)])
        self.assertIsNone(self._run(tok))

    def test_a_stale_token_does_not_pass(self):
        with self.assertRaises(SystemExit):
            self._run(g.concurrent_token([("다른것.py", 0)]))

    def test_passing_records_what_was_swept(self):
        tok = g.concurrent_token([(self.f, 0)])
        self._run(tok)
        mark = os.path.join(self.root, "state", "concurrent-swept.txt")
        self.assertTrue(os.path.exists(mark), "지나간 사실이 남지 않았다")
        self.assertIn(self.f, open(mark, encoding="utf-8").read())


class TheCommitMessageSaysIt(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-cgate-msg-")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        self.msg = os.path.join(self.root, "MSG")

    def _msg(self, text="고침 하나\n"):
        with open(self.msg, "w", encoding="utf-8") as f:
            f.write(text)
        with mock.patch.object(g, "ROOT", self.root):
            g.commit_msg_swept(self.msg)
        return open(self.msg, encoding="utf-8").read()

    def test_a_plain_commit_gets_no_tail(self):
        self.assertNotIn("S9_ALLOW_CONCURRENT", self._msg())

    def test_a_swept_commit_names_the_files(self):
        with open(os.path.join(self.root, "state", "concurrent-swept.txt"),
                  "w", encoding="utf-8") as f:
            f.write("tests/남의것.py\n")
        got = self._msg()
        self.assertIn("tests/남의것.py", got,
                      "쓸려 담긴 파일이 커밋 메시지에 없다 — 다음 사람이 까닭을 못 찾는다")

    def test_the_mark_is_used_once(self):
        # 표식이 남아 다음 커밋에도 붙으면 거짓말이 된다
        with open(os.path.join(self.root, "state", "concurrent-swept.txt"),
                  "w", encoding="utf-8") as f:
            f.write("tests/남의것.py\n")
        self._msg()
        self.assertNotIn("남의것", self._msg("다음 커밋\n"))


if __name__ == "__main__":
    unittest.main()
