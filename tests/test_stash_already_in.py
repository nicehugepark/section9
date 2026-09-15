"""이미 담긴 것은 「치워 둔 작업」이 아니다 (REQ-20260915-060-62x6).

주인 물음 2026-09-15 18:14: 「「동기화 치워 둔 작업 — 동기화가 잠시 치워 둔 1건이
아직 남아 있습니다.」 이 메시지는 내가 뭘 해야하는거지? 정말 의미가 있는 경고인가?」

실측: 그때 보관함이 들고 있던 것은 파일 하나였고, 그 내용은 이미 commit 으로
담겨 있었다(HEAD 의 그 파일과 한 글자도 다르지 않았다). 동기화가 커밋 **직전**의
파일을 잠시 치웠고, 커밋된 뒤에도 보관함에 남아 경고가 계속 떴다.

**사람이 할 일이 없는 경고는 다음 경고까지 함께 못 믿게 만든다.** 그래서 세는
자리에서 가른다: 그 patch 를 거꾸로 적용해 보아 깨끗이 맞으면 지금 트리에 이미
있는 것이다. 모르는 것은 「남아 있음」으로 센다 — 되돌리지 못한 작업을 조용히
잃는 쪽이 헛경고보다 나쁘다.

격리: S9_ROOT=mktemp 에 git 저장소를 따로 세운다.
실행: python3 tests/ stash_already_in
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


class StashAlreadyIn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9-stashin-")
        cls._prev = os.environ.get("S9_ROOT")
        os.environ["S9_ROOT"] = cls.root
        cls.git("init", "-q", "-b", "main")
        cls.git("config", "user.name", "t")
        cls.git("config", "user.email", "t@t")
        cls.write("a.txt", "one\n")
        cls.git("add", "-A")
        cls.git("commit", "-q", "-m", "base")
        spec = importlib.util.spec_from_loader(
            "s9_stash_in", importlib.machinery.SourceFileLoader("s9_stash_in", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        if cls._prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = cls._prev
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def git(cls, *a):
        env = {**os.environ, **GIT_ENV}
        r = subprocess.run(["git", "-C", cls.root, *a], capture_output=True,
                           text=True, env=env, timeout=30)
        if r.returncode != 0 and a[0] not in ("stash",):
            raise AssertionError("git %s: %s" % (" ".join(a), r.stderr))
        return r.stdout

    @classmethod
    def write(cls, rel, text):
        p = os.path.join(cls.root, rel)
        os.makedirs(os.path.dirname(p) or cls.root, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def _make_autostash(self, rel, text):
        """치워 둔 작업 하나를 만든다 — 이름은 동기화가 쓰는 그 꼴(autostash)."""
        self.write(rel, text)
        self.git("add", "-A")
        self.git("stash", "push", "-q", "-m", "autostash")

    def test_a_stash_whose_content_is_already_committed_is_not_counted(self):
        """치운 뒤 같은 내용이 커밋되면 그 보관함은 남은 것이 아니다."""
        self._make_autostash("b.txt", "two\n")
        # 그 사이 같은 내용이 커밋됐다 (커밋 직전에 치워졌던 그 파일)
        self.write("b.txt", "two\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "b 를 담았다")
        n, _oldest = self.m._sync_autostash_left()
        self.assertEqual(n, 0, "이미 담긴 내용인데 「남아 있음」으로 셌다")

    def test_a_stash_with_real_unreturned_work_is_counted(self):
        """돌려놓지 못한 진짜 작업은 그대로 센다 — 여기서 덜 세면 사람이 잃는다."""
        self._make_autostash("c.txt", "three\n")
        n, oldest = self.m._sync_autostash_left()
        self.assertGreaterEqual(n, 1, "되돌리지 못한 작업을 안 셌다")
        self.assertTrue(oldest, "가장 오래된 시각이 비었다")

    def test_the_judgement_itself(self):
        """판정 함수 — 모르는 것은 「담겼다」로 세지 않는다."""
        self.assertFalse(self.m._stash_already_in_tree(""))
        self.assertFalse(self.m._stash_already_in_tree("stash@{99}"))


if __name__ == "__main__":
    unittest.main()
