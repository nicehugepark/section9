"""임시 신원의 승격 자리 (REQ-20260921-012-62x6).

부모 REQ-20260921-004-62x6 의 4단계다. 몫이 셋이고, 그 셋이 한 뿌리에서 나온다 —
**section9 이 박아 둔 값은 사람이 정한 값과 다르게 다뤄야 한다.**

  ① 표(`[section9] identity = auto`)를 남겨 그 둘을 가른다
  ② 우리가 박은 값만, 재료가 늘어난 순간(등록·프로필 수정) 다시 잰다
  ③ 우리가 박은 값을 우리가 「이 사람의 증거」로 되읽지 않는다

③ 이 이 요청의 핵심이다. architect 와 security-engineer 가 부모 요청에서 서로 모르는
채 같은 고리를 짚었다: `_user_by_git_identity` 와 `user_name_from_src` 는 git 신원을
사람의 증거로 읽는데, 그 값이 우리가 지어낸 것이면 증거가 아니라 메아리다.

실행: python3 tests/ identity_upgrade
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
FIRSTRUN = os.path.join(HERE, "..", "bin", "s9_firstrun.py")
S9 = os.path.join(HERE, "..", "bin", "s9")

spec = importlib.util.spec_from_loader("s9fr_up", SourceFileLoader("s9fr_up", FIRSTRUN))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)

# git 은 설정보다 이 환경변수를 먼저 본다 — 커밋 검사 안에서 시험이 돌면 이미 채워져
# 있어 임시 저장소에 무엇을 넣든 그 값이 읽힌다.
GIT_IDENT_ENV = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                 "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL")


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9ident-up-")
        self.home = os.path.join(self.root, "home")
        os.makedirs(self.home)
        with open(os.path.join(self.home, ".gitconfig"), "w", encoding="utf-8") as f:
            f.write("[init]\n\tdefaultBranch = main\n")      # 신원은 없는 컴퓨터
        self.env = {k: v for k, v in os.environ.items() if k not in GIT_IDENT_ENV}
        self.env["HOME"] = self.home
        subprocess.run(["git", "init", "-q", "-b", "main", self.root],
                       env=self.env, check=True, capture_output=True)
        self.git = fr._git_runner(self.root, env=self.env)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def local(self, key):
        return self.git("config", "--local", "--get", key, check=False).stdout.strip()


class TheMark(Base):
    """N1~N3. 표를 남기고, 그 표로 갈라 읽는다."""

    # N1. 박을 때 표가 함께 선다
    def test_n1_writing_identity_leaves_the_mark(self):
        res = fr.ensure_identity(self.root, env=self.env, account="sjpark1")
        self.assertTrue(res["set"])
        self.assertEqual(self.local("section9.identity"), "auto")
        self.assertTrue(fr.is_auto_identity(self.git))

    # N1b. 사람이 정해 둔 자리에는 표가 서지 않는다
    def test_n1b_human_identity_gets_no_mark(self):
        self.git("config", "user.name", "hong")
        self.git("config", "user.email", "hong@example.com")
        res = fr.ensure_identity(self.root, env=self.env, account="sjpark1")
        self.assertFalse(res["set"])
        self.assertEqual(self.local("section9.identity"), "")
        self.assertFalse(fr.is_auto_identity(self.git))

    # N2·N3. 표가 있으면 그 파일의 user 절을 사람의 증거로 세지 않는다.
    #        전역은 표와 무관하게 그대로 읽는다.
    def test_n2_marked_identity_is_not_evidence(self):
        body = ("[user]\n\tname = s9 sjpark1\n\temail = sjpark1@local\n"
                "[section9]\n\tidentity = auto\n")
        self.assertEqual(self._read_ident(body), {})
        plain = "[user]\n\tname = hong\n\temail = hong@example.com\n"
        self.assertEqual(self._read_ident(plain),
                         {"name": "hong", "email": "hong@example.com"})

    def _read_ident(self, git_config_body):
        """`_git_identity` 를 그 저장소 하나로 재현한다 — s9.py 를 통째로 싣지 않고,
        읽는 규칙만 같은 입력으로 확인한다(그 함수는 ROOT 에 묶여 있다)."""
        found, section, auto = {}, "", False
        for ln in git_config_body.splitlines():
            t = ln.strip()
            if t.startswith("["):
                section = t.lower().replace(" ", "").strip("[]")
                continue
            if "=" not in t or t.startswith(("#", ";")):
                continue
            k, _, v = t.partition("=")
            k, v = k.strip().lower(), v.strip().strip('"')
            if section == "user" and k in ("name", "email"):
                found.setdefault(k, v)
            elif section == "section9" and k == "identity" and v == "auto":
                auto = True
        return {} if auto else found


class TheUpgrade(Base):
    """N4~N6·B1~B2. 재료가 늘어난 순간 다시 잰다 — 우리가 박은 값만."""

    # N4. 임시값으로 섰던 자리가 프로필이 생기자 올라선다
    def test_n4_temp_rises_when_the_profile_arrives(self):
        first = fr.ensure_identity(self.root, env=self.env, account="sjpark1")
        self.assertEqual(first["source"], "temp")
        self.assertEqual(self.local("user.email"), "sjpark1@local")

        prof = {"github": "nicehugepark", "emails": []}
        again = fr.ensure_identity(self.root, env=self.env, account="sjpark1",
                                   profile=prof, user="tester", upgrade=True)
        self.assertTrue(again["set"])
        self.assertEqual(again["source"], "noreply")
        self.assertEqual(self.local("user.email"),
                         "nicehugepark@users.noreply.github.com")

    # N5. 사람이 손으로 정한 값은 upgrade 로도 덮지 않는다
    def test_n5_human_identity_survives_upgrade(self):
        self.git("config", "user.name", "hong")
        self.git("config", "user.email", "hong@example.com")
        res = fr.ensure_identity(self.root, env=self.env, account="sjpark1",
                                 profile={"emails": ["other@company.com"]},
                                 user="tester", upgrade=True)
        self.assertFalse(res["set"])
        self.assertEqual(self.local("user.email"), "hong@example.com")

    # N6. 같은 칸이 다시 나오면 아무것도 쓰지 않는다
    def test_n6_same_rung_writes_nothing(self):
        prof = {"emails": ["me@company.com"]}
        fr.ensure_identity(self.root, env=self.env, account="sjpark1",
                           profile=prof, user="tester")
        res = fr.ensure_identity(self.root, env=self.env, account="sjpark1",
                                 profile=prof, user="tester", upgrade=True)
        self.assertFalse(res["set"])
        self.assertEqual(res["skipped"], "same")

    # B1. 표만 남고 값이 지워진 자리에서도 멎지 않는다
    def test_b1_mark_without_value_still_writes(self):
        fr.ensure_identity(self.root, env=self.env, account="sjpark1")
        self.git("config", "--unset", "user.name", check=False)
        self.git("config", "--unset", "user.email", check=False)
        res = fr.ensure_identity(self.root, env=self.env, account="sjpark1",
                                 upgrade=True)
        self.assertTrue(res["set"])
        self.assertEqual(self.local("user.email"), "sjpark1@local")

    # B2. .git 이 없는 자리는 그대로 물러난다
    def test_b2_no_repo_is_unchanged(self):
        empty = tempfile.mkdtemp(prefix="s9ident-none-")
        try:
            res = fr.ensure_identity(empty, env=self.env, account="sjpark1",
                                     upgrade=True)
            self.assertEqual(res["skipped"], "no-repo")
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class RegisteringRaisesTheIdentity(unittest.TestCase):
    """N4 를 명령 자리에서 — `s9 user add` 가 실제로 다시 잰다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9ident-cmd-")
        self.home = os.path.join(self.root, "home")
        os.makedirs(self.home)
        with open(os.path.join(self.home, ".gitconfig"), "w", encoding="utf-8") as f:
            f.write("[init]\n\tdefaultBranch = main\n")
        self.env = {k: v for k, v in os.environ.items() if k not in GIT_IDENT_ENV}
        self.env.update(HOME=self.home, S9_ROOT=self.root, S9_SESSION="dddd4444")
        # `s9 init` 은 vault 뼈대만 세운다 — 저장소는 s9 code·s9-install 이 만든다.
        # 이 시험이 보는 것은 등록 뒤의 신원이라 저장소만 있으면 된다.
        subprocess.run(["git", "init", "-q", "-b", "main", self.root],
                       env=self.env, check=True, capture_output=True)
        subprocess.run([sys.executable, S9, "init"], env=self.env,
                       capture_output=True, timeout=120)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_user_add_with_github_raises_the_identity(self):
        git = fr._git_runner(self.root, env=self.env)
        fr.ensure_identity(self.root, env=self.env, account="sjpark1")
        self.assertEqual(
            git("config", "--local", "--get", "user.email").stdout.strip(),
            "sjpark1@local")
        r = subprocess.run([sys.executable, S9, "user", "add", "tester",
                            "--github", "nicehugepark"],
                           env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            git("config", "--local", "--get", "user.email").stdout.strip(),
            "nicehugepark@users.noreply.github.com",
            "등록하며 적은 github 로 신원이 올라서지 않았습니다:\n" + r.stdout + r.stderr)


class GoingRemoteSpeaksOnce(unittest.TestCase):
    """F1·F2. 바깥과 오가기 **시작하는 그 순간** 한 번 알린다 — 막지는 않는다.

    security-engineer 가 부모 요청에서 짚은 자리다: 신원을 박을 때는 origin 이 없어
    「로컬에만 남는 값」이었는데, 나중에 origin 이 생기면 그때까지 쌓인 commit 전부가
    아무 확인 없이 밖으로 나간다."""

    def setUp(self):
        with open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8") as f:
            self.src = f.read()

    # F1. 승격하는 그 자리가 이 함수를 부른다 — 함수만 있고 아무도 안 부르면
    #     사람 화면에는 한 글자도 안 나온다
    def test_f1_autoraise_calls_the_notice(self):
        body = self.src.split("def sync_autoraise(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("warn_auto_identity_going_remote()", body)

    # F2. 사람이 정한 신원이거나 사다리가 이어지는 주소를 골랐으면 조용하다
    def test_f2_only_the_temp_rung_speaks(self):
        body = self.src.split("def warn_auto_identity_going_remote(", 1)[1] \
                       .split("\ndef ", 1)[0]
        self.assertIn('res.get("auto")', body)
        self.assertIn('("", "temp")', body)
        # 한 번만 말한다
        self.assertIn("_IDENT_REMOTE_WARNED", body)
        # 막지 않는다 — 이 자리에 die 나 sys.exit 이 있으면 안 된다
        self.assertNotIn("die(", body)
        self.assertNotIn("sys.exit", body)


class TheIdentityDoesNotTravelByCopy(Base):
    """N1~N3·B1~B3·F1. 디렉토리를 통째로 복사해 받은 자리 (REQ-20260921-018-62x6).

    `.git/config` 의 로컬 신원은 clone 으로는 따라가지 않지만 디렉토리 복사에는
    그대로 간다. 받은 사람은 제 전역 신원이 있어도 만든 사람의 메일로 commit 한다 —
    git 이 로컬을 전역보다 앞세우기 때문이다."""

    def host_mark(self):
        return self.local(fr.IDENT_HOST_KEY)

    # N1. 박을 때 이 컴퓨터의 자국이 함께 남는다
    def test_n1_the_mark_carries_this_machine(self):
        fr.ensure_identity(self.root, env=self.env, account="maker")
        self.assertTrue(self.host_mark())
        self.assertIn("/maker", self.host_mark())

    # N2. 같은 컴퓨터에서 다시 부르면 남의 것이 아니므로 그대로 둔다
    def test_n2_same_machine_is_left_alone(self):
        fr.ensure_identity(self.root, env=self.env, account="maker")
        res = fr.ensure_identity(self.root, env=self.env, account="maker")
        self.assertFalse(res["set"])
        self.assertFalse(res["foreign"])
        self.assertEqual(self.local("user.email"), "maker@local")

    # N3. 다른 컴퓨터에서 부르면 다시 재라고 하지 않아도 사다리가 다시 고른다
    def test_n3_another_machine_re_picks(self):
        fr.ensure_identity(self.root, env=self.env, account="maker",
                           profile={"emails": ["maker@company.com"]}, user="maker")
        self.assertEqual(self.local("user.email"), "maker@company.com")
        # 받은 사람의 컴퓨터를 흉내 낸다 — 자국을 남의 것으로 바꿔 둔다
        self.git("config", fr.IDENT_HOST_KEY, "other-box/someone")
        res = fr.ensure_identity(self.root, env=self.env, account="taker",
                                 profile={"emails": ["taker@company.com"]},
                                 user="taker")
        self.assertTrue(res["foreign"])
        self.assertTrue(res["set"])
        self.assertEqual(self.local("user.email"), "taker@company.com")
        self.assertIn("/taker", self.host_mark())

    # N3b. 받은 사람에게 아무 재료가 없으면 그 사람의 임시값으로 내려간다 —
    #      만든 사람의 값이 그대로 남지는 않는다
    def test_n3b_without_material_it_still_leaves_the_maker(self):
        fr.ensure_identity(self.root, env=self.env, account="maker",
                           profile={"emails": ["maker@company.com"]}, user="maker")
        self.git("config", fr.IDENT_HOST_KEY, "other-box/someone")
        fr.ensure_identity(self.root, env=self.env, account="taker")
        self.assertEqual(self.local("user.email"), "taker@local")

    # B1. 사람이 손으로 정한 값은 어느 컴퓨터에서도 덮지 않는다 — 표가 없다
    def test_b1_human_value_is_never_foreign(self):
        self.git("config", "user.name", "hong")
        self.git("config", "user.email", "hong@example.com")
        res = fr.ensure_identity(self.root, env=self.env, account="taker")
        self.assertFalse(res["foreign"])
        self.assertFalse(res["set"])
        self.assertEqual(self.local("user.email"), "hong@example.com")

    # B3. 자국이 없는 옛 표는 남의 것으로 보지 않는다
    def test_b3_a_mark_without_a_machine_is_not_foreign(self):
        fr.ensure_identity(self.root, env=self.env, account="maker")
        self.git("config", "--unset", fr.IDENT_HOST_KEY, check=False)
        res = fr.ensure_identity(self.root, env=self.env, account="taker")
        self.assertFalse(res["foreign"])
        self.assertFalse(res["set"])

    # F1. 자국을 읽지 못해도 예외를 밖으로 내지 않는다
    def test_f1_unreadable_mark_does_not_raise(self):
        fr.ensure_identity(self.root, env=self.env, account="maker")
        self.git("config", fr.IDENT_HOST_KEY, "")
        res = fr.ensure_identity(self.root, env=self.env, account="taker")
        self.assertEqual(res["error"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
