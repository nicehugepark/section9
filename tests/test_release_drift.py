"""나간 판과 지금 코드의 거리는 늘 보인다 (REQ-20260918-006-62x6).

실제 사고 2026-09-18: 주인이 GitHub 릴리스의 윈도우 zip 을 받아 풀었는데
`section9.cmd` 가 없었다. 태그 v0.9.1 은 2026-09-14 에 땄고 그 파일은 다음 날
들어왔다 — 그 뒤 나흘 동안 코드 commit 147 개가 태그 뒤에 쌓이는 동안 VERSION 은
0.9.1 그대로였다.

앞선 시험 `test_release_guide_match.py` 는 **가이드가 이름을 댄 파일**이 그 판에
있는지 본다. 그것만으로는 좁다 — 가이드가 이름을 대지 않는 변화(화면·동작·고침)가
쌓이는 것은 못 잡는다. 이 시험이 보는 것은 그 밑의 것이다: **판을 낼 때를 사람의
기억에 맡기지 않는다.** `s9 doctor` 가 거리를 세어 말하므로, 9/15 에 그 파일이
들어온 날부터 「나간 판 v0.9.1 뒤로 코드 commit N개」가 화면에 있었을 것이다.

실행: python3 tests/ release_drift
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCTOR = os.path.join(ROOT, "bin", "s9-doctor")


def load_doctor():
    loader = importlib.machinery.SourceFileLoader("s9doctor_drift", DOCTOR)
    spec = importlib.util.spec_from_loader("s9doctor_drift", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


D = load_doctor()


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, check=True)


class TheVerdictReadsTheDistance(unittest.TestCase):
    """판정은 순수 함수다 — git 없이 네 갈래를 전부 잰다."""

    def test_a1_a_fresh_install_has_never_cut_a_release(self):
        """정상 ①: 받아서 쓰는 설치에는 태그가 없다 — 조용히 ok."""
        v = D.release_verdict({"tag": None, "version": "0.9.2"})
        self.assertEqual(v["level"], "ok")
        self.assertIn("판을 낸 적이 없다", v["line"])

    def test_a2_code_matching_the_released_version_is_ok(self):
        """정상 ②: 나간 판과 코드가 같으면 ok 이고, 그 판의 이름을 적는다."""
        v = D.release_verdict({"tag": "v0.9.2", "version": "0.9.2",
                               "commits": 0, "days": 0.0, "tagged": True})
        self.assertEqual(v["level"], "ok")
        self.assertIn("v0.9.2", v["line"])

    def test_a3_the_accident_of_2026_09_18_is_caught(self):
        """실패 ③: 그날의 수를 그대로 넣으면 warn 이 되고 받는 사람을 말한다.

        이 한 줄이 9/15 부터 화면에 있었으면 사람이 받기 전에 보였다."""
        v = D.release_verdict({"tag": "v0.9.1", "version": "0.9.1",
                               "commits": 147, "days": 4.0, "tagged": True})
        self.assertEqual(v["level"], "warn")
        self.assertIn("v0.9.1", v["line"])
        self.assertIn("147", v["line"])
        self.assertIn("받는 사람", v["line"])

    def test_a4_bumping_the_version_without_a_tag_is_caught(self):
        """실패 ④: VERSION 만 올리고 태그를 안 따면 배포판은 만들어지지 않는다.

        워크플로는 태그 push 로만 돈다 — 판을 올린 commit 만으로는 아무것도 안 나간다."""
        v = D.release_verdict({"tag": "v0.9.1", "version": "0.9.2",
                               "commits": 3, "days": 1.0, "tagged": False})
        self.assertEqual(v["level"], "warn")
        self.assertIn("v0.9.2", v["line"])
        self.assertIn("v0.9.2", v["advice"])

    def test_a5_a_few_commits_on_a_fresh_tag_are_not_noise(self):
        """경계 ⑤: 선 안이면 ok 다 — 태그를 딴 다음 날의 commit 세 건까지 붙잡지 않는다."""
        v = D.release_verdict({"tag": "v0.9.2", "version": "0.9.2",
                               "commits": 3, "days": 1.0, "tagged": True})
        self.assertEqual(v["level"], "ok")
        self.assertIn("3개", v["line"])

    def test_a6_either_threshold_alone_is_enough(self):
        """경계 ⑥: 수만 넘어도, 날수만 넘어도 말한다 — 둘 다여야 하는 것이 아니다."""
        many = D.release_verdict({"tag": "v1.0.0", "version": "1.0.0",
                                  "commits": D.RELEASE_DRIFT_N, "days": 0.5, "tagged": True})
        old = D.release_verdict({"tag": "v1.0.0", "version": "1.0.0",
                                 "commits": 1, "days": D.RELEASE_DRIFT_DAYS, "tagged": True})
        self.assertEqual(many["level"], "warn")
        self.assertEqual(old["level"], "warn")

    def test_a7_an_old_tag_with_no_code_since_is_not_a_warning(self):
        """경계 ⑦: 오래된 판이라도 그 뒤 코드가 없으면 낼 것이 없다 — ok."""
        v = D.release_verdict({"tag": "v1.0.0", "version": "1.0.0",
                               "commits": 0, "days": 90.0, "tagged": True})
        self.assertEqual(v["level"], "ok")

    def test_a8_unreadable_state_says_so(self):
        v = D.release_verdict(None)
        self.assertEqual(v["level"], "unknown")


class TheInfoReadsTheRepository(unittest.TestCase):
    """실제 git 저장소를 하나 지어 재는 것 — 세는 자리가 맞는지."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9drift-")
        r = cls.tmp
        git(r, "init", "-q", "-b", "main")
        git(r, "config", "user.email", "t@example.com")
        git(r, "config", "user.name", "t")
        os.makedirs(os.path.join(r, "bin"))
        os.makedirs(os.path.join(r, "vault"))
        with open(os.path.join(r, "VERSION"), "w") as f:
            f.write("0.9.1\n")
        with open(os.path.join(r, "bin", "s9"), "w") as f:
            f.write("code\n")
        git(r, "add", "-A")
        git(r, "commit", "-qm", "첫 판")
        git(r, "tag", "-a", "v0.9.1", "-m", "0.9.1")
        # 코드 두 건 · 데이터 한 건 — 데이터는 세지 않아야 한다
        for i, (path, text) in enumerate([("bin/s9", "code2\n"), ("bin/s9", "code3\n"),
                                          ("vault/doc.md", "문서\n")]):
            with open(os.path.join(r, path), "w") as f:
                f.write(text)
            git(r, "add", "-A")
            git(r, "commit", "-qm", f"c{i}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_b1_it_counts_code_commits_since_the_tag(self):
        i = D.release_info(root=self.tmp)
        self.assertEqual(i["tag"], "v0.9.1")
        self.assertEqual(i["version"], "0.9.1")
        self.assertTrue(i["tagged"])
        self.assertEqual(i["commits"], 2, "vault/ 만 바꾼 commit 이 거리로 세어졌다")

    def test_b2_bumping_the_version_flips_tagged(self):
        with open(os.path.join(self.tmp, "VERSION"), "w") as f:
            f.write("0.9.2\n")
        try:
            i = D.release_info(root=self.tmp)
            self.assertFalse(i["tagged"])
            self.assertEqual(i["tag"], "v0.9.1", "나간 판은 아직 v0.9.1 이다")
        finally:
            with open(os.path.join(self.tmp, "VERSION"), "w") as f:
                f.write("0.9.1\n")

    def test_b3_versions_sort_by_number_not_by_letter(self):
        """v0.10.0 은 v0.9.1 보다 뒤다 — 글자 순서로 고르면 옛 판을 나간 판으로 본다."""
        git(self.tmp, "tag", "-a", "v0.10.0", "-m", "0.10.0")
        try:
            self.assertEqual(D.release_info(root=self.tmp)["tag"], "v0.10.0")
        finally:
            git(self.tmp, "tag", "-d", "v0.10.0")

    def test_b4_a_repository_without_tags_is_quiet(self):
        """받아서 쓰는 설치 — 첫 실행이 git init 으로 세운 저장소에는 태그가 없다."""
        plain = tempfile.mkdtemp(prefix="s9drift-plain-")
        try:
            git(plain, "init", "-q", "-b", "main")
            i = D.release_info(root=plain)
            self.assertIsNone(i["tag"])
            self.assertEqual(D.release_verdict(i)["level"], "ok")
        finally:
            shutil.rmtree(plain, ignore_errors=True)


class ItStandsInTheReport(unittest.TestCase):

    def test_c1_doctor_lists_the_release_line(self):
        """회귀: 검사 목록에 들어 있어야 화면에 선다 — 함수만 있고 안 부르면 뜻이 없다."""
        keys = [v["key"] for v in D.system_checks()]
        self.assertIn("release", keys)


if __name__ == "__main__":
    unittest.main()
