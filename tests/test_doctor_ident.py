"""s9 doctor 의 「git 이름」 항목 (REQ-20260920-001-2n7g).

배경: 2026-09-20, 한 컴퓨터에 git 의 user.name·user.email 이 없어 git 이 OS
계정과 호스트명으로 지어낸 값(`<계정>@<호스트>.local`)으로 commit 했다. 그
주소는 어느 GitHub 계정에도 등록할 수 없어 같은 사람이 목록에서 둘로 갈려
보였고, commit 166건이 쌓인 뒤에야 사람이 눈으로 알아챘다 —
REQ-20260920-001-62x6. git 은 이 경우 오류를 내지 않으므로 증상이 없다.
그래서 판정이 선다: 정해 두지 않았으면 경고하고, 정해 뒀어도 이 컴퓨터
안에서만 닿는 주소면 경고한다.

판정은 순수 함수(입력 dict → 등급)이라 이 컴퓨터의 실제 설정에 기대지 않는다.
수집기만 임시 저장소 하나로 확인한다.

실행: python3 tests/ doctor_ident
"""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
DOCTOR = os.path.join(HERE, "..", "bin", "s9-doctor")

spec = importlib.util.spec_from_loader(
    "s9doctor_ident", SourceFileLoader("s9doctor_ident", DOCTOR))
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def _d(name="", email="", used_name="", used_email="", resolved=True):
    return {"name": name, "email": email, "used_name": used_name,
            "used_email": used_email, "resolved": resolved}


class IdentVerdict(unittest.TestCase):
    """G1~G5. 등급과, 그 줄이 사람에게 말해 주는 것."""

    # G1. 제대로 정해 둔 컴퓨터는 ok 한 줄로 지나간다
    def test_configured_is_ok(self):
        v = doctor.ident_verdict(_d("hong", "me@example.com",
                                    "hong", "me@example.com"))
        self.assertEqual(v["level"], "ok")
        self.assertIn("hong", v["line"])
        self.assertIn("me@example.com", v["line"])
        self.assertIsNone(v["advice"])

    # G2. 아무것도 정해 두지 않았으면 warn — 지금 찍히는 값과 고치는 명령
    def test_unset_warns_and_shows_what_is_used(self):
        v = doctor.ident_verdict(
            _d("", "", "Hong Gildong", "hong@some-host.local"))
        self.assertEqual(v["level"], "warn")
        self.assertIn("이름과 메일", v["line"])
        self.assertIn("Hong Gildong", v["line"])
        self.assertIn("hong@some-host.local", v["line"])
        self.assertIn("git config --global user.name", v["advice"])
        self.assertIn("git config --global user.email", v["advice"])

    # G3. 한쪽만 빠져도 warn 이고, 빠진 쪽을 지목한다
    def test_half_configured_names_the_missing_half(self):
        v = doctor.ident_verdict(_d("hong", "",
                                    "hong", "x@host.local"))
        self.assertEqual(v["level"], "warn")
        self.assertIn("메일을", v["line"])
        self.assertNotIn("이름과 메일", v["line"])
        v = doctor.ident_verdict(_d("", "me@example.com",
                                    "hong", "me@example.com"))
        self.assertEqual(v["level"], "warn")
        self.assertIn("이름을", v["line"])

    # G4. git 이 누구로 commit 할지 전혀 못 정하면 critical — commit 이 거부된다
    def test_unresolved_is_critical(self):
        v = doctor.ident_verdict(_d(resolved=False))
        self.assertEqual(v["level"], "critical")
        self.assertIn("commit", v["line"])
        self.assertTrue(v["advice"])

    # G5. 정해 뒀어도 이 컴퓨터 안에서만 닿는 주소면 warn
    def test_unreachable_mail_warns(self):
        for mail in ("me@mac.local", "me@box.localdomain", "me@x.lan",
                     "me@x.home", "hong@(none)"):
            with self.subTest(mail=mail):
                v = doctor.ident_verdict(_d("hong", mail,
                                            "hong", mail))
                self.assertEqual(v["level"], "warn")
                self.assertIn("GitHub", v["line"])

    # G5b. 비슷하지만 멀쩡한 주소는 건드리지 않는다
    def test_normal_mail_is_not_flagged(self):
        for mail in ("me@gmail.com", "me@local.example.com", "me@lan.dev.io"):
            with self.subTest(mail=mail):
                self.assertEqual(
                    doctor.ident_verdict(_d("n", mail, "n", mail))["level"],
                    "ok")


# git 은 설정보다 이 환경변수를 먼저 본다. 커밋 검사(pre-commit 훅) 안에서
# 시험이 돌면 git 이 이미 채워 둔 값이 들어와, 임시 저장소에 무엇을 설정하든
# 그 값이 읽힌다 — 실제로 이 시험이 단독으로는 통과하고 커밋할 때만 실패했다.
GIT_IDENT_ENV = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                 "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL")


class IdentInfo(unittest.TestCase):
    """G6. 수집기가 실제 저장소에서 다섯 키를 채운다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9ident-")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "tester")
        self.git("config", "user.email", "tester@example.com")
        self.saved = {k: os.environ.pop(k, None) for k in GIT_IDENT_ENV}

    def tearDown(self):
        for k, v in self.saved.items():
            if v is not None:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True,
                       capture_output=True)

    def test_collects_configured_identity(self):
        d = doctor.ident_info(root=self.root)
        self.assertEqual(d["name"], "tester")
        self.assertEqual(d["email"], "tester@example.com")
        self.assertEqual(d["used_name"], "tester")
        self.assertEqual(d["used_email"], "tester@example.com")
        self.assertTrue(d["resolved"])
        self.assertEqual(doctor.ident_verdict(d)["level"], "ok")


class IdentIsOnTheBoard(unittest.TestCase):
    """G7. 항목이 진단 목록에 실제로 서 있어야 한다 — 함수만 있고 아무도
    부르지 않으면 사람 화면에는 한 글자도 안 나온다."""

    def test_ident_is_in_system_checks(self):
        src = open(DOCTOR, encoding="utf-8").read()
        body = src.split("def system_checks():", 1)[1].split("\ndef ", 1)[0]
        self.assertEqual(body.count("ident_verdict(ident_info())"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
