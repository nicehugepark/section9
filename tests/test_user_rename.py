"""계정 이름을 바꾸면 전부 따라온다 — 경로만 빼고 (REQ-20260827-060-62x6).

사용자 요청: "이 하네스의 모든 문서와 이력, 저장소 어디든 내 계정 hgpark을
hong으로 바꿔줘."

손으로 한 군데씩 고치면 반드시 어딘가 남는다. 남은 한 곳이 "누가 한 일인가"를
조용히 틀리게 만든다.

**바꾸지 않는 것이 둘 있다.**
- `/home/<이름>` · `-<이름>-section9` 같은 **경로**. 운영체제의 홈이고 Claude의
  프로젝트 폴더다 — 바꾸면 기록된 경로가 전부 거짓이 된다.
- `os_accounts`. 하네스의 이름과 로그인한 운영체제 계정은 원래 다른 층이고,
  그래서 이 필드가 따로 있다.

실행: python3 tests/ user_rename
"""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class UserRename(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9ren-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                    "S9_USER": "oldname"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "oldname")
        self.rid = self.cli("new", "request", "--title", "무엇인가",
                            "--summary", "s", "--goal", "g", "--size", "S",
                            "--user", "oldname", "--body", "x").split()[0]

    def cli(self, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=60)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def doc(self):
        for dp, _dn, fns in os.walk(os.path.join(self.root, "vault")):
            for fn in fns:
                if fn.startswith(self.rid):
                    return os.path.join(dp, fn)
        raise AssertionError("문서 없음")

    # N1. 디렉터리가 옮겨진다
    def test_n1_dir_moved(self):
        self.cli("user", "rename", "oldname", "newname")
        self.assertTrue(os.path.isdir(os.path.join(self.root, "users",
                                                   "newname")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "users",
                                                     "oldname")))

    # N2. 문서의 소유자가 따라온다
    def test_n2_doc_user_field(self):
        self.cli("user", "rename", "oldname", "newname")
        t = open(self.doc(), encoding="utf-8").read()
        self.assertIn("user: newname", t)
        self.assertNotIn("oldname", t)

    # B1. 경로는 그대로 둔다 — 바꾸면 기록된 경로가 거짓이 된다
    def test_b1_paths_untouched(self):
        p = self.doc()
        t = open(p, encoding="utf-8").read()
        t += ("\n캡처: /home/oldname/shot.png · "
              "~/.claude/projects/-home-oldname-section9/x.jsonl\n")
        open(p, "w", encoding="utf-8").write(t)
        self.cli("user", "rename", "oldname", "newname")
        t2 = open(p, encoding="utf-8").read()
        self.assertIn("/home/oldname/shot.png", t2)
        self.assertIn("-home-oldname-section9", t2)

    # B2. os_accounts 는 운영체제 계정이다 — 별개 층이라 그대로
    def test_b2_os_accounts_kept(self):
        prof = os.path.join(self.root, "users", "oldname", "profile.md")
        t = open(prof, encoding="utf-8").read()
        if "os_accounts:" not in t:
            t = t.replace("\n---\n", '\nos_accounts: ["oldname"]\n---\n', 1)
            open(prof, "w", encoding="utf-8").write(t)
        self.cli("user", "rename", "oldname", "newname")
        t2 = open(os.path.join(self.root, "users", "newname", "profile.md"),
                  encoding="utf-8").read()
        self.assertIn('os_accounts: ["oldname"]', t2)
        self.assertIn("name: newname", t2)

    # F1. 이미 있는 이름·없는 계정·이상한 이름은 거부한다
    def test_f1_guards(self):
        self.cli("user", "add", "other")
        self.cli("user", "rename", "oldname", "other", expect=1)
        self.cli("user", "rename", "ghost", "newname", expect=1)
        self.cli("user", "rename", "oldname", "bad name", expect=1)
        self.assertTrue(os.path.isdir(os.path.join(self.root, "users",
                                                   "oldname")))

    # R1. 다른 사람 이름은 건드리지 않는다
    def test_r1_other_users_intact(self):
        self.cli("user", "add", "other")
        rid2 = self.cli("new", "request", "--title", "남의 것", "--summary", "s",
                        "--goal", "g", "--size", "S", "--user", "other",
                        "--body", "x").split()[0]
        self.cli("user", "rename", "oldname", "newname")
        for dp, _dn, fns in os.walk(os.path.join(self.root, "vault")):
            for fn in fns:
                if fn.startswith(rid2):
                    self.assertIn("user: other",
                                  open(os.path.join(dp, fn),
                                       encoding="utf-8").read())
                    return
        raise AssertionError("남의 문서 없음")


if __name__ == "__main__":
    unittest.main()
