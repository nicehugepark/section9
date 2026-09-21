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


def _d(name="", email="", used_name="", used_email="", resolved=True,
       auto=False):
    return {"name": name, "email": email, "used_name": used_name,
            "used_email": used_email, "resolved": resolved, "auto": auto}


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
        self.assertIn("메일이", v["line"])
        self.assertNotIn("이름과 메일", v["line"])
        v = doctor.ident_verdict(_d("", "me@example.com",
                                    "hong", "me@example.com"))
        self.assertEqual(v["level"], "warn")
        self.assertIn("이름이", v["line"])

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

    # G5a. 닿지 않는 까닭이 다르면 말도 다르다 (REQ-20260921-020-62x6) — `.local` 은
    # 이 컴퓨터 안에서만 닿고, RFC 2606 이 예약한 도메인은 어디에도 닿지 않는다.
    def test_reserved_mail_warns_with_its_own_wording(self):
        for mail in ("me@x.invalid", "me@corp.example", "me@x.test", "me@box.localhost"):
            with self.subTest(mail=mail):
                v = doctor.ident_verdict(_d("hong", mail, "hong", mail))
                self.assertEqual(v["level"], "warn")
                self.assertIn("어디에도 닿지 않는", v["line"])
                self.assertNotIn("이 컴퓨터 안에서만", v["line"])
        local = doctor.ident_verdict(_d("hong", "me@mac.local", "hong", "me@mac.local"))
        self.assertIn("이 컴퓨터 안에서만", local["line"])

    # G5b. 비슷하지만 멀쩡한 주소는 건드리지 않는다
    def test_normal_mail_is_not_flagged(self):
        for mail in ("me@gmail.com", "me@local.example.com", "me@lan.dev.io"):
            with self.subTest(mail=mail):
                self.assertEqual(
                    doctor.ident_verdict(_d("n", mail, "n", mail))["level"],
                    "ok")

    # G6. 죽은 메일 목록의 자리는 하나다 (REQ-20260921-011-62x6) — 신원을 세우는 쪽
    # (bin/s9_firstrun.py)이 그 자리이고 doctor 는 그것을 읽는다. 두 벌로 두면 한쪽에
    # 꼬리를 더한 날 다른 쪽이 그 주소를 멀쩡한 것으로 읽는다 — 사다리는 걸러 낸
    # 주소를 doctor 는 ✓ 로 통과시키는 식이다.
    def test_the_dead_mail_list_has_one_home(self):
        firstrun = importlib.util.module_from_spec(importlib.util.spec_from_loader(
            "s9_firstrun_for_doctor_test",
            SourceFileLoader("s9_firstrun_for_doctor_test",
                             os.path.join(HERE, "..", "bin", "s9_firstrun.py"))))
        firstrun.__loader__.exec_module(firstrun)
        self.assertEqual(tuple(doctor.IDENT_DEAD_MAIL), tuple(firstrun.IDENT_DEAD_MAIL))
        self.assertEqual(doctor.is_dead_mail.__module__, "s9_firstrun_for_doctor",
                         "doctor 가 제 목록을 따로 들고 있다")


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


class S9TempIdentity(unittest.TestCase):
    """N1·N2·B1·B2. section9 이 제 손으로 박은 임시 신원은 사람이 잘못 둔 값과
    다르게 말해야 한다 (REQ-20260921-006-62x6).

    실제 사고 2026-09-20 의 값은 macOS 가 지어낸 것이었고, 그것과 우리가 박는
    `s9 <계정> <계정@local>` 은 고칠 사람도 할 말도 다르다 — 앞은 사람이 정해
    두지 않아 난 것이고 뒤는 우리가 넣은 것이다."""

    def _temp(self, **kw):
        return _d("s9 hgpark", "hgpark@local",
                  "s9 hgpark", "hgpark@local", **kw)

    # N1. 전용 갈래 — 오류가 아니라 알림이고, 누가 넣었는지 밝힌다
    def test_s9_written_identity_is_its_own_branch(self):
        v = doctor.ident_verdict(self._temp(auto=True))
        self.assertEqual(v["level"], "warn")
        self.assertNotEqual(v["level"], "critical")
        self.assertIn("section9 이 임시로", v["line"])
        self.assertIn("s9 hgpark", v["line"])

    # N2. 먼저 안심시키고, 시한을 사건으로 못박는다
    def test_temp_advice_reassures_then_sets_a_deadline(self):
        a = doctor.ident_verdict(self._temp(auto=True))["advice"]
        self.assertIn("잃는 것은 없습니다", a)
        self.assertIn("GitHub 에 잇기 전에", a)
        self.assertNotIn("나중에", a)

    # B1. 사람이 손으로 넣은 .local 은 이 갈래로 오지 않는다
    def test_human_local_mail_keeps_the_dead_mail_branch(self):
        v = doctor.ident_verdict(_d("hong", "me@mac.local",
                                    "hong", "me@mac.local"))
        self.assertEqual(v["level"], "warn")
        self.assertNotIn("section9 이 임시로", v["line"])
        self.assertIn("이어지지 않습니다", v["line"])

    # B2. 값의 모양이 아니라 표로도 가른다 — 4단계가 세울 자리를 미리 읽는다.
    #     다만 표만으로는 「임시」가 아니다 (REQ-20260921-019-62x6): 표는 우리가
    #     골랐다는 사실만 적고, 프로필 메일로 선 값을 임시라 부르면 거짓말이 된다.
    def test_auto_flag_alone_is_enough(self):
        v = doctor.ident_verdict(_d("Hong", "hong@example.com",
                                    "Hong", "hong@example.com", auto=True))
        self.assertIn("section9", v["line"])
        self.assertNotIn("임시", v["line"])

    # B2b. 모양 판정은 이름과 메일 둘 다 맞아야 선다
    def test_shape_needs_both_halves(self):
        self.assertTrue(doctor.is_s9_identity("s9 hgpark", "hgpark@local"))
        self.assertFalse(doctor.is_s9_identity("s9 hgpark", "me@example.com"))
        self.assertFalse(doctor.is_s9_identity("hong", "hong@local"))
        self.assertFalse(doctor.is_s9_identity("", ""))


class IdentLadderRung(unittest.TestCase):
    """L1~L6. 사다리의 어느 칸으로 선 값인지를 진단이 갈라 말한다
    (REQ-20260921-019-62x6).

    실제 결함 2026-09-21: clone 한 자리에서 사다리가 프로필 메일을 골라
    `hong <agent01.pfe@example.invalid>` 를 박았는데, 진단은 「section9 이
    임시로 지은 이름」이라고 말했다. 그 값은 임시가 아니라 그 사람이 프로필에 적어
    둔 주소이고, 고칠 까닭도 다르다 — 사람에게 거짓을 말하는 자리였다."""

    def _auto(self, name, mail, source=""):
        d = _d(name, mail, name, mail, auto=True)
        if source:
            d["source"] = source
        return d

    # L1. 프로필 메일로 선 값은 임시가 아니다 — 출처를 말하고 등급은 ok
    def test_profile_rung_names_its_source(self):
        v = doctor.ident_verdict(self._auto("hong-gildong", "hong@example.com"))
        self.assertEqual(v["level"], "ok")
        self.assertNotIn("임시", v["line"])
        self.assertIn("프로필", v["line"])
        self.assertIn("hong@example.com", v["line"])

    # L2. GitHub 이 내주는 주소로 선 값도 임시가 아니다
    def test_noreply_rung_names_github(self):
        mail = "hong-gildong@users.noreply.github.com"
        v = doctor.ident_verdict(self._auto("hong-gildong", mail))
        self.assertEqual(v["level"], "ok")
        self.assertNotIn("임시", v["line"])
        self.assertIn("GitHub", v["line"])

    # L3. 임시 칸은 지금 그대로 — warn 이고 안심시키는 advice 가 붙는다
    def test_temp_rung_keeps_its_warning(self):
        v = doctor.ident_verdict(self._auto("s9 hgpark", "hgpark@local"))
        self.assertEqual(v["level"], "warn")
        self.assertIn("section9 이 임시로", v["line"])
        self.assertIn("잃는 것은 없습니다", v["advice"])

    # L4. 표에 칸이 적혀 있으면 값의 모양보다 표가 이긴다 — 세우는 쪽이 칸을 적기
    #     시작해도 진단은 고칠 것이 없다
    def test_the_mark_beats_the_shape(self):
        v = doctor.ident_verdict(self._auto("hong", "hong@example.com",
                                            source="temp"))
        self.assertIn("section9 이 임시로", v["line"])
        v = doctor.ident_verdict(self._auto("s9 hgpark", "hgpark@local",
                                            source="profile"))
        self.assertNotIn("임시", v["line"])

    # L5. 표를 읽는 쪽은 `auto` 도 `auto:<칸>` 도 같은 뜻으로 읽는다
    def test_mark_with_and_without_a_rung(self):
        for mark in ("auto", "auto:profile", "auto:noreply", "auto:temp"):
            self.assertTrue(doctor.is_auto_mark(mark), mark)
        for mark in ("", "manual", "autopilot"):
            self.assertFalse(doctor.is_auto_mark(mark), mark)
        self.assertEqual(doctor.ident_source("auto:noreply", "hong",
                                             "hong@example.com"), "noreply")
        self.assertEqual(doctor.ident_source("auto:없는칸", "hong",
                                             "hong@example.com"), "profile")
        # 우리 값이 아니면 칸이 없다 — 사람이 정해 둔 값을 사다리의 것으로 읽지 않는다
        self.assertEqual(doctor.ident_source("", "hong", "hong@example.com"), "")

    # L6. 우리 값인데 닿지 않는 주소면 임시 칸으로 본다 — 사다리는 그런 주소를 고르지
    #     않으므로, 사람을 탓하는 죽은 메일 갈래로 보내지 않는다
    def test_our_unreachable_mail_is_the_temp_rung(self):
        v = doctor.ident_verdict(self._auto("s9 hgpark", "hgpark@box.local"))
        self.assertEqual(v["level"], "warn")
        self.assertIn("section9 이 임시로", v["line"])

    # L7. 수집기가 표의 칸을 실제 저장소에서 읽는다
    def test_info_reads_the_rung_from_the_repo(self):
        root = tempfile.mkdtemp(prefix="s9ident-rung-")
        saved = {k: os.environ.pop(k, None) for k in GIT_IDENT_ENV}
        try:
            def git(*args):
                subprocess.run(["git", *args], cwd=root, check=True,
                               capture_output=True)
            git("init", "-q", "-b", "main")
            git("config", "user.name", "hong-gildong")
            git("config", "user.email", "hong@example.com")
            git("config", "section9.identity", "auto:profile")
            d = doctor.ident_info(root=root)
            self.assertTrue(d["auto"])
            self.assertEqual(d["source"], "profile")
            self.assertEqual(doctor.ident_verdict(d)["level"], "ok")
            self.assertNotIn("임시", doctor.ident_verdict(d)["line"])
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
            shutil.rmtree(root, ignore_errors=True)


class IdentSpeech(unittest.TestCase):
    """B3·F1·F2. 사람이 읽는 자리의 말씨와 모양 (규약 2조 1 · ux-writer 판정)."""

    ALL = (
        _d(resolved=False),
        _d("", "", "Hong", "hong@x.local"),
        _d("hong", "", "hong", "x@host.local"),
        _d("hong", "me@mac.local", "hong", "me@mac.local"),
        _d("s9 a", "a@local", "s9 a", "a@local", auto=True),
        _d("hong", "me@example.com", "hong", "me@example.com"),
        _d("hong", "hong@example.com", "hong", "hong@example.com", auto=True),
        _d("hong", "hong@users.noreply.github.com",
           "hong", "hong@users.noreply.github.com", auto=True),
    )

    # B3. 모든 줄과 advice 가 존댓말이다
    def test_every_line_is_polite(self):
        for d in self.ALL:
            v = doctor.ident_verdict(d)
            for text in (v["line"], v["advice"] or ""):
                for sent in text.split("\n"):
                    sent = sent.strip().rstrip(".")
                    if not sent or sent.startswith("git config"):
                        continue
                    self.assertFalse(
                        sent.endswith("한다") or sent.endswith("된다")
                        or sent.endswith("이다") or sent.endswith("는다"),
                        f"반말: {sent}")

    # F1. 신원이 없어 commit 이 거부되는 줄은 「무엇이 없는지 → 그래서 무엇이
    #     안 되는지」 순으로 말한다
    def test_unresolved_line_says_what_then_why(self):
        line = doctor.ident_verdict(_d(resolved=False))["line"]
        self.assertLess(line.index("없습니다"), line.index("거부됩니다"))
        self.assertIn("user.name", line)
        self.assertIn("user.email", line)

    # F2. 고치는 명령은 한 줄에 하나씩, 꺾쇠가 아니라 붙여 넣을 수 있는 예시로
    def test_fix_commands_stand_one_per_line(self):
        for advice in (doctor.IDENT_FIX, doctor.IDENT_TEMP_FIX,
                       doctor.IDENT_AUTO_FIX):
            cmds = [ln.strip() for ln in advice.split("\n")
                    if ln.strip().startswith("git config")]
            self.assertEqual(len(cmds), 2, advice)
            self.assertTrue(any("user.name" in c for c in cmds))
            self.assertTrue(any("user.email" in c for c in cmds))
            self.assertNotIn("<", advice)
            self.assertNotIn(">", advice)


class TheAccidentEndToEnd(unittest.TestCase):
    """L8. 사고 그대로 — 신원이 없는 컴퓨터에서 사다리가 값을 박고, 그 자리에서
    진단이 무엇이라 말하나 (REQ-20260921-019-62x6).

    단위 시험은 dict 를 손으로 지어 넣지만, 사고는 **세우는 쪽과 읽는 쪽 사이**에서
    났다 — 사다리는 프로필 메일을 골랐는데 진단은 임시라고 말했다. 그 이음매는
    이어 봐야 갈린다(규약 19조)."""

    def _run(self, profile):
        root = tempfile.mkdtemp(prefix="s9ident-e2e-")
        saved = {k: os.environ.pop(k, None) for k in GIT_IDENT_ENV}
        try:
            home = os.path.join(root, "home")
            os.makedirs(home)
            with open(os.path.join(home, ".gitconfig"), "w", encoding="utf-8") as f:
                f.write("[init]\n\tdefaultBranch = main\n")   # 신원은 없는 컴퓨터
            env = dict(os.environ, HOME=home)
            subprocess.run(["git", "init", "-q", "-b", "main", root],
                           env=env, check=True, capture_output=True)
            firstrun = importlib.util.module_from_spec(
                importlib.util.spec_from_loader(
                    "s9_firstrun_for_e2e",
                    SourceFileLoader("s9_firstrun_for_e2e",
                                     os.path.join(HERE, "..", "bin", "s9_firstrun.py"))))
            firstrun.__loader__.exec_module(firstrun)
            res = firstrun.ensure_identity(root, env=env, account="hgpark",
                                           profile=profile, user="hong")
            return res, doctor.ident_verdict(doctor.ident_info(root=root))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
            shutil.rmtree(root, ignore_errors=True)

    # L8a. 프로필 메일로 선 자리 — 진단이 임시라 말하지 않는다
    def test_profile_mail_is_not_called_temporary(self):
        res, v = self._run({"github": "hong-gildong",
                            "emails": ["hong@example.com"]})
        self.assertEqual(res["source"], "profile")
        self.assertNotIn("임시", v["line"])
        self.assertIn("hong@example.com", v["line"])

    # L8b. GitHub 주소로 선 자리도 마찬가지다
    def test_noreply_is_not_called_temporary(self):
        res, v = self._run({"github": "hong-gildong", "emails": []})
        self.assertEqual(res["source"], "noreply")
        self.assertNotIn("임시", v["line"])
        self.assertIn("GitHub", v["line"])

    # L8c. 재료가 없어 임시값으로 선 자리는 그대로 임시라고 말한다
    def test_temp_is_still_called_temporary(self):
        res, v = self._run({})
        self.assertEqual(res["source"], "temp")
        self.assertEqual(v["level"], "warn")
        self.assertIn("section9 이 임시로", v["line"])


class IdentIsOnTheBoard(unittest.TestCase):
    """G7. 항목이 진단 목록에 실제로 서 있어야 한다 — 함수만 있고 아무도
    부르지 않으면 사람 화면에는 한 글자도 안 나온다."""

    def test_ident_is_in_system_checks(self):
        src = open(DOCTOR, encoding="utf-8").read()
        body = src.split("def system_checks():", 1)[1].split("\ndef ", 1)[0]
        self.assertEqual(body.count("ident_verdict(ident_info())"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
