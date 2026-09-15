"""s9 가 보관함을 맡는다 (REQ-20260915-007-2n7g).

동기화의 pull 은 `rebase --autostash` 라 커밋하지 않은 작업을 잠시 보관함으로 걷어
간다. 되돌리지 못한 것을 비우는 길이 날 git 뿐이면 무인 작업자는 거기서 멈춘다 —
저장소의 s9-git-gate 는 `S9_GIT_OK=1` 을 요구하고, 하네스의 자동 승인 층은 명령 앞의
환경변수를 우회 시도로 보기 때문이다(2026-09-15, REQ-20260915-012-62x6).
사람의 확인을 대신하는 것은 「잃지 않았다」는 증거다: 담긴 자리가 없으면 먼저 뽑는다.

함수 단위로 잰다 — 임시 저장소를 만들고 stash_entries·stash_drop 을 직접 부른다.
실행: python3 tests/ stash_cmd
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9.py")


def load(root):
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        name = "s9_stash_%d" % abs(hash(root))
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


def git(root, *argv):
    return subprocess.run(["git", "-C", root, *argv], capture_output=True,
                          encoding="utf-8", errors="replace")


class StashCommand(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9stash-")
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@t")
        git(self.root, "config", "user.name", "t")
        self.write("a.txt", "처음\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "첫 commit")
        self.m = load(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        p = os.path.join(self.root, name)
        os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(p) else None
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def make_stash(self, text="치워 둘 것\n"):
        self.write("a.txt", text)
        git(self.root, "stash", "push", "-q", "-m", "autostash")
        return self.m.stash_entries()[0]

    def archive(self, entry, where="vault/requests/2026/09/assets/REQ-1"):
        d = os.path.join(self.root, where)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"autostash-20260915T000000-{entry['sha'][:8]}.patch")
        with open(p, "w", encoding="utf-8") as f:
            f.write("보관해 둔 patch\n")
        return p

    def test_s1_ls_shows_each_entry_and_where_it_is_archived(self):
        """정상: 목록이 항목마다 담긴 자리를 함께 말한다."""
        e = self.make_stash()
        self.assertEqual(self.m.stash_entries()[0]["archived"], "", "아직 담긴 자리가 없다")
        self.archive(e)
        got = self.m.stash_entries()[0]
        self.assertIn(f"autostash-20260915T000000-{e['sha'][:8]}.patch", got["archived"])

    def test_s2_drop_removes_an_archived_entry(self):
        """정상: 담긴 항목은 그대로 지워진다."""
        e = self.make_stash()
        self.archive(e)
        res = self.m.stash_drop(0)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["left"], 0)
        self.assertEqual(git(self.root, "stash", "list").stdout.strip(), "")

    def test_s3_an_unarchived_entry_is_pulled_out_first(self):
        """실패 갈래: 담긴 자리가 없으면 state/sync-rescue/ 로 먼저 뽑고 그 경로를 말한다."""
        self.make_stash("뽑아 둘 것\n")
        res = self.m.stash_drop(0)
        self.assertTrue(res["ok"], res)
        self.assertTrue(res["saved"].startswith("state/sync-rescue/"), res["saved"])
        saved = os.path.join(self.root, res["saved"])
        self.assertTrue(os.path.exists(saved))
        with open(saved, encoding="utf-8") as f:
            self.assertIn("뽑아 둘 것", f.read())

    def test_s4_an_unknown_number_drops_nothing(self):
        """경계: 없는 번호는 지우지 않고 무엇이 있는지 알려 준다."""
        self.make_stash()
        res = self.m.stash_drop(9)
        self.assertFalse(res["ok"])
        self.assertIn("stash@{0}", res["error"])
        self.assertEqual(len(self.m.stash_entries()), 1, "그대로 있다")

    def test_s5_the_last_drop_clears_the_orphan_marker(self):
        """회귀: 마지막 항목을 지우면 표식도 걷힌다 — 없는 보관함을 계속 세지 않는다."""
        e = self.make_stash()
        self.archive(e)
        os.makedirs(os.path.dirname(self.m.SYNC_ORPHAN_STASH), exist_ok=True)
        with open(self.m.SYNC_ORPHAN_STASH, "w", encoding="utf-8") as f:
            f.write(f"2026-09-15T00:00:00+09:00 {e['sha']}\n")
        self.assertEqual(self.m._sync_autostash_left()[0], 1)
        self.m.stash_drop(0)
        self.assertFalse(os.path.exists(self.m.SYNC_ORPHAN_STASH))
        self.assertEqual(self.m._sync_autostash_left()[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
