"""색인은 HEAD 를 따라온다 — 어느 경로로 움직였든 (REQ-20260908-017-62x6).

사용자가 본 것: 목록에 줄이 있는데 열면 「문서를 찾을 수 없습니다」. 그 문서는
다른 컴퓨터가 지운 것이고 이 머신에는 pull 로 그 삭제가 들어와 있었다.

색인 쪽은 지운 문서를 다룰 줄 안다 — `index_upsert` 는 그 자리에 파일이 없으면
묘비를 세운다. 빠진 것은 **그 길을 타지 않는 pull** 이었다: HEAD 를 움직이는
자리가 넷인데(수신 폴 · 판정 직전 당김 · 전송 루프의 rebase · 사람이 손으로 친
`git pull`) 색인을 부르는 것은 앞의 둘뿐이었다.

그래서 부르는 자리마다 잇지 않고 **표와 HEAD 를 견주는 자리**를 하나 뒀다.

실행: python3 tests/ index_catch_up
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9.py")

TMP = tempfile.mkdtemp(prefix="s9-idxhead-")
_prev = os.environ.get("S9_ROOT")
os.environ["S9_ROOT"] = TMP
try:
    spec = importlib.util.spec_from_loader(
        "s9_idxhead", importlib.machinery.SourceFileLoader("s9_idxhead", S9))
    s9 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(s9)
finally:
    if _prev is None:
        os.environ.pop("S9_ROOT", None)
    else:
        os.environ["S9_ROOT"] = _prev


class TheHeadIsReadFromFiles(unittest.TestCase):
    """서브프로세스 없이 읽는다 — 서버 루프가 매 틱 묻는 값이다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-idxhead-root-")
        os.makedirs(os.path.join(self.root, ".git", "refs", "heads"))

    def _head(self, text, ref=None, sha=None):
        with open(os.path.join(self.root, ".git", "HEAD"), "w", encoding="utf-8") as f:
            f.write(text)
        if ref and sha is not None:
            p = os.path.join(self.root, ".git", ref)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(sha + "\n")
        with mock.patch.object(s9, "ROOT", self.root):
            return s9.repo_head_sha()

    def test_a_branch_head_comes_from_its_ref_file(self):
        """정상 — 흔한 자리(loose ref)는 파일 두 번 읽기로 끝난다."""
        self.assertEqual(
            self._head("ref: refs/heads/main\n", "refs/heads/main", "a" * 40),
            "a" * 40)

    def test_a_detached_head_is_the_sha_itself(self):
        """경계 — 분리된 HEAD 는 그 자리에 sha 가 있다."""
        self.assertEqual(self._head("b" * 40 + "\n"), "b" * 40)

    def test_no_git_is_an_empty_answer(self):
        """경계 — .git 이 없으면 빈 값이다(모른다). 예외를 올리지 않는다."""
        empty = tempfile.mkdtemp(prefix="s9-idxhead-bare-")
        with mock.patch.object(s9, "ROOT", empty):
            self.assertEqual(s9.repo_head_sha(), "")

    def test_a_packed_ref_falls_back_to_git(self):
        """경계 — ref 파일이 없는 판(packed-refs)에서만 git 에게 묻는다."""
        with mock.patch.object(s9, "ROOT", self.root), \
                mock.patch.object(s9, "_sync_git") as g:
            g.return_value = type("R", (), {"returncode": 0, "stdout": "c" * 40})()
            with open(os.path.join(self.root, ".git", "HEAD"), "w", encoding="utf-8") as f:
                f.write("ref: refs/heads/main\n")
            self.assertEqual(s9.repo_head_sha(), "c" * 40)
            g.assert_called_once()


class TheCatalogFollowsTheHead(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-idxhead-c-")
        os.makedirs(os.path.join(self.root, "state"))
        self.mark = os.path.join(self.root, "state", ".index-head")

    def _run(self, head, mark=None):
        if mark is not None:
            with open(self.mark, "w", encoding="utf-8") as f:
                f.write(mark)
        with mock.patch.object(s9, "ROOT", self.root), \
                mock.patch.object(s9, "_INDEX_HEAD", self.mark), \
                mock.patch.object(s9, "repo_head_sha", lambda: head), \
                mock.patch.object(s9, "index_sync_range") as rng, \
                mock.patch.object(s9, "rebuild_index") as full:
            n = s9.index_catch_up()
        return n, rng, full

    def test_the_same_head_does_nothing(self):
        """정상 — 같으면 아무 일도 하지 않는다(매 틱 불러도 값이 없다)."""
        n, rng, full = self._run("a" * 40, mark="a" * 40)
        self.assertEqual(n, 0)
        rng.assert_not_called()
        full.assert_not_called()

    def test_a_moved_head_syncs_only_that_range(self):
        """실패 자리 — 표와 다르면 그 사이만 반영한다. 손으로 친 pull 도 여기서 잡힌다."""
        n, rng, full = self._run("b" * 40, mark="a" * 40)
        rng.assert_called_once_with("a" * 40, "b" * 40, quiet=True)
        full.assert_not_called()
        self.assertEqual(open(self.mark, encoding="utf-8").read().strip(), "b" * 40)

    def test_no_mark_rebuilds_everything(self):
        """경계 — 표가 없으면 기준이 없다. 전량으로 물러난다."""
        n, rng, full = self._run("b" * 40)
        full.assert_called_once()
        rng.assert_not_called()
        self.assertEqual(n, -1)

    def test_an_unknown_head_is_not_an_error(self):
        """경계 — HEAD 를 못 읽으면(.git 없음) 조용히 0. 색인을 건드리지 않는다."""
        n, rng, full = self._run("", mark="a" * 40)
        self.assertEqual(n, 0)
        rng.assert_not_called()
        full.assert_not_called()


if __name__ == "__main__":
    unittest.main()
