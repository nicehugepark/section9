"""pre-commit 이 관련 시험을 찾아 함께 돌리는가 (REQ-20260909-059-62x6).

나흘 전체 테스트 실패 34건 중 14건은 계약을 바꾼 커밋이 그 계약을 재는 시험을
안 담은 것이었다(REQ-20260909-053, quality-assurance 실측). 8ce0dcc5 는 `s9 next`
의 문구 한 줄(`s9 claim` → `s9 last … --add`)을 bin/s9.py 에서 바꿨는데, 그 문구를
재는 test_boot_pickup.py 는 담기지 않았고 검사(담긴 시험 ∪ 스모크)는 그 시험을
볼 길이 없었다 — 130초 뒤 원격에서 실패했다(66b927f3 에서 고침).

그래서 guard 가 담긴 diff 의 -/+ 줄에서 바뀐 식별자·따옴표 문자열을 뽑아 그것을
참조하는 시험을 고르고(`select_related_tests`), 담긴 소스 파일의 이름을 글자로 담은
시험도 고른다. 상한 15파일·90초. 여기서는 임시 tests/ 와 가짜 diff 로 함수 단위로
재고, 마지막 하나는 저장소의 실제 tests/ 에 8ce0dcc5 의 diff 를 대 본다.

실행: python3 tests/ related_tests
"""
import importlib.machinery
import importlib.util
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
GUARD = os.path.join(ROOT, "bin", "s9-guard")


def _load(name=None):
    name = name or "s9guard_related"
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, GUARD))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _diff(path, minus=(), plus=(), ctx=""):
    """-U0 꼴의 가짜 diff 한 파일분."""
    out = [f"diff --git a/{path} b/{path}", f"--- a/{path}", f"+++ b/{path}",
           f"@@ -1,{len(minus)} +1,{len(plus)} @@ {ctx}".rstrip()]
    out += [f"-{ln}" for ln in minus] + [f"+{ln}" for ln in plus]
    return "\n".join(out) + "\n"


class SelectRelated(unittest.TestCase):
    """임시 tests/ 와 가짜 diff — 함수 단위."""

    @classmethod
    def setUpClass(cls):
        cls.g = _load()
        cls.tmp = tempfile.mkdtemp(prefix="s9related-")
        cls.tdir = os.path.join(cls.tmp, "tests")
        os.makedirs(cls.tdir)
        cls.files = {
            "test_uses_ident.py": "from s9 import jira_summary_of\nassert jira_summary_of(x)\n",
            "test_uses_ident_prefix.py": "y = jira_summary_of_x(1)\nz = my_jira_summary_of\n",
            "test_uses_string.py": 'self.assertIn("s9 last", out)\n',
            "test_uses_fstring_tail.py": 'self.assertIn(f"s9 last {rid} --add", out)\n',
            "test_reads_card.py": 'src = open(os.path.join(ROOT, "web", "app", "card.js")).read()\n',
            "test_reads_s9py.py": 'src = open("bin/s9.py").read()\n',
            "test_unrelated.py": "def test_x(self): self.assertTrue(True)\n",
            "test_only_short_string.py": 'self.assertIn("s9 la", out)\n',
        }
        for fn, body in cls.files.items():
            with open(os.path.join(cls.tdir, fn), "w", encoding="utf-8") as f:
                f.write(body)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def select(self, staged, diff, **kw):
        kw.setdefault("times", {})
        return self.g.select_related_tests(staged, diff, tests_dir=self.tdir, **kw)

    def picked(self, sel):
        return {fn for fn, _ in sel["picked"]}

    def test_s1_changed_identifier_picks_the_test_that_names_it(self):
        """S1. `+def jira_summary_of(` → 그 이름을 단어로 담은 시험, 이유에 이름."""
        d = _diff("bin/s9.py", plus=["def jira_summary_of(doc):"])
        sel = self.select(["bin/s9.py"], d)
        self.assertEqual(self.picked(sel), {"test_uses_ident.py"})
        why = dict(sel["picked"])["test_uses_ident.py"]
        self.assertIn("jira_summary_of", why)
        self.assertIn("식별자", why)
        with self.subTest("removed_def_counts_too"):
            d = _diff("bin/s9.py", minus=["def jira_summary_of(doc):"])
            self.assertIn("test_uses_ident.py", self.picked(self.select(["bin/s9.py"], d)))
        with self.subTest("hunk_header_function_counts"):
            d = _diff("bin/s9.py", minus=["    x = 1"], plus=["    x = 2"],
                      ctx="def jira_summary_of(doc):")
            self.assertIn("test_uses_ident.py", self.picked(self.select(["bin/s9.py"], d)))

    def test_s2_changed_string_picks_the_test_that_asserts_it(self):
        """S2. -/+ 줄의 따옴표 문자열(≥6자, f-string 의 글자 조각 포함)."""
        d = _diff("bin/s9.py",
                  minus=["    print(f\"  이어받기: s9 claim {p['id']}\")"],
                  plus=["    print(f\"  이어받기: s9 last {p['id']} --add\")"])
        sel = self.select(["bin/s9.py"], d)
        self.assertIn("s9 last", sel["strings"])
        self.assertIn("s9 claim", sel["strings"])
        self.assertNotIn("--add", sel["strings"], "5자는 조각이 아니다")
        self.assertEqual(self.picked(sel), {"test_uses_string.py", "test_uses_fstring_tail.py"})
        self.assertIn("「s9 last」", dict(sel["picked"])["test_uses_string.py"])

    def test_s3_source_file_name_picks_the_test_that_reads_it(self):
        """S3. 담긴 `web/app/card.js` 의 이름 `card.js` 를 글자로 담은 시험 — 넓은 파일은 뺀다."""
        sel = self.select(["web/app/card.js"], _diff("web/app/card.js", plus=["x = 1;"]))
        self.assertEqual(self.picked(sel), {"test_reads_card.py"})
        self.assertIn("파일 이름 card.js", dict(sel["picked"])["test_reads_card.py"])
        with self.subTest("wide_file_name_is_not_evidence"):
            sel = self.select(["bin/s9.py"], _diff("bin/s9.py", plus=["x = 1"]))
            self.assertEqual(sel["names"], [])
            self.assertNotIn("test_reads_s9py.py", self.picked(sel))

    def test_s4_cap_and_budget_keep_the_short_ones(self):
        """S4. 후보 16개 이상·시간 합 90초 초과 → 짧은 것부터 cap 개, 나머지 dropped."""
        tdir = os.path.join(self.tmp, "tests_many")
        os.makedirs(tdir, exist_ok=True)
        for i in range(20):
            with open(os.path.join(tdir, f"test_m{i:02d}.py"), "w", encoding="utf-8") as f:
                f.write("from s9 import contract_fn\n")
        times = {f"test_m{i:02d}.py": i * 0.5 for i in range(20)}    # 0..9.5초, 15개 합 52.5초
        d = _diff("bin/tool.py", plus=["def contract_fn():"])
        sel = self.g.select_related_tests(["bin/tool.py"], d, tests_dir=tdir, times=times)
        self.assertEqual(len(sel["picked"]), 15)
        self.assertEqual(self.picked(sel), {f"test_m{i:02d}.py" for i in range(15)},
                         "짧은 것부터 15개")
        self.assertEqual([fn for fn, _ in sel["dropped"]],
                         [f"test_m{i:02d}.py" for i in range(15, 20)])
        with self.subTest("budget_binds_before_cap"):
            times = {f"test_m{i:02d}.py": 10.0 for i in range(20)}    # 9개 = 90초
            sel = self.g.select_related_tests(["bin/tool.py"], d, tests_dir=tdir, times=times)
            self.assertEqual(len(sel["picked"]), 9)
            self.assertEqual(len(sel["dropped"]), 11)
            self.assertLessEqual(sel["seconds"], self.g.RELATED_BUDGET_SEC)
        with self.subTest("unknown_time_is_weighted_not_free"):
            sel = self.g.select_related_tests(["bin/tool.py"], d, tests_dir=tdir, times={})
            self.assertAlmostEqual(sel["seconds"], 15 * self.g.RELATED_UNKNOWN_SEC)

    def test_s5_unrelated_and_partial_matches_are_not_picked(self):
        """S5. 회귀(오탐): 무관한 시험·부분 일치 식별자·짧은 문자열은 안 뽑힌다."""
        d = _diff("bin/s9.py", plus=["def jira_summary_of(doc):",
                                     "    print(f\"  이어받기: s9 last {p['id']} --add\")"])
        sel = self.select(["bin/s9.py"], d)
        self.assertNotIn("test_unrelated.py", self.picked(sel))
        self.assertNotIn("test_uses_ident_prefix.py", self.picked(sel),
                         "jira_summary_of_x · my_jira_summary_of 는 단어 경계 밖")
        self.assertNotIn("test_only_short_string.py", self.picked(sel))
        with self.subTest("staged_test_diff_is_not_evidence"):
            d = _diff("tests/test_new.py", plus=["def test_a(self):", '    x = "s9 last"'])
            sel = self.select(["tests/test_new.py"], d)
            self.assertEqual(sel["idents"], [])
            self.assertEqual(sel["strings"], [])
            self.assertEqual(sel["picked"], [])
        with self.subTest("staged_test_itself_is_not_a_candidate"):
            d = _diff("bin/s9.py", plus=["def jira_summary_of(doc):"])
            sel = self.select(["bin/s9.py", "tests/test_uses_ident.py"], d)
            self.assertEqual(sel["picked"], [], "담긴 시험은 이미 가는 길이 있다")
        with self.subTest("common_fragment_is_boilerplate"):
            d = _diff("bin/s9.py", plus=["def jira_summary_of(doc):"])
            sel = self.select(["bin/s9.py"], d, common=0)
            self.assertEqual(sel["picked"], [])
            self.assertIn("식별자 jira_summary_of", sel["common"])
        with self.subTest("weak_single_word_and_stop_idents"):
            d = _diff("bin/s9.py", plus=['ROOT = "x"', 'HERE = 1', 'y = "option"', 'z = "--quiet"'])
            sel = self.select(["bin/s9.py"], d)
            self.assertEqual(sel["idents"], [])
            self.assertEqual(sel["strings"], [])


class RealRepo(unittest.TestCase):
    """S6. 실측 재현 — 8ce0dcc5 의 diff 를 저장소의 실제 tests/ 에 대면 test_boot_pickup 이 뽑힌다."""

    def test_s6_8ce0dcc5_picks_test_boot_pickup(self):
        if not shutil.which("git"):
            self.skipTest("git 없음")
        r = subprocess.run(["git", "show", "--format=", "-U0", "8ce0dcc5", "--", "bin/s9.py"],
                           capture_output=True, encoding="utf-8", errors="replace", cwd=ROOT)
        if r.returncode != 0 or "s9 last" not in r.stdout:
            self.skipTest("8ce0dcc5 를 이 저장소에서 읽을 수 없다")
        g = _load("s9guard_related_real")
        sel = g.select_related_tests(["bin/s9.py"], r.stdout)
        picked = {fn for fn, _ in sel["picked"]}
        self.assertIn("test_boot_pickup.py", picked,
                      f"뽑힘: {sorted(picked)} / 밖: {sel['dropped']}")
        self.assertIn("s9 last", dict(sel["picked"])["test_boot_pickup.py"])
        self.assertLessEqual(len(picked), g.RELATED_CAP)
        self.assertLessEqual(sel["seconds"], g.RELATED_BUDGET_SEC)


class GateWiring(unittest.TestCase):
    """S7. staged_tests_gate 가 뽑힌 시험을 스모크·담긴 시험과 한 번의 러너 호출에 넘긴다."""

    def setUp(self):
        self.g = _load("s9guard_related_gate")

    def test_s7_gate_passes_related_to_one_runner_call_and_says_why(self):
        calls = []

        def fake_run(argv, **kw):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")
        fake_sel = {"picked": [("test_boot_pickup.py", "문자열 「s9 last」"),
                               ("test_staged_one.py", "식별자 foo")],
                    "dropped": [("test_slow.py", 40.0)], "seconds": 2.5,
                    "idents": [], "strings": ["s9 last"], "names": [], "common": []}
        err = io.StringIO()
        with mock.patch.object(self.g.subprocess, "run", fake_run), \
                mock.patch.object(self.g, "select_related_tests", return_value=fake_sel), \
                redirect_stderr(err):
            self.g.staged_tests_gate(["bin/s9.py", "tests/test_staged_one.py"],
                                     diff_text="+x\n")
        self.assertEqual(len(calls), 1, calls)
        argv = calls[0]
        self.assertIn("--smoke", argv)
        self.assertIn("--jobs", argv)
        self.assertIn("test_boot_pickup.py", argv)
        self.assertEqual(argv.count("test_staged_one.py"), 1, "담긴 시험은 한 번만")
        text = err.getvalue()
        self.assertIn("관련 시험 1개", text)
        self.assertIn("test_boot_pickup.py ← 문자열 「s9 last」", text)
        self.assertIn("test_slow.py", text)
        self.assertIn("전체가 뒤에서", text)

    def test_s7b_without_diff_the_gate_is_the_old_gate(self):
        """diff 를 안 받으면 고르지 않는다 — 기존 시험(test_commit_gate G12: 호출 1회)의 계약."""
        calls = []

        def fake_run(argv, **kw):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")
        with mock.patch.object(self.g.subprocess, "run", fake_run), \
                mock.patch.object(self.g, "select_related_tests",
                                  side_effect=AssertionError("diff 없이 골랐다")):
            self.g.staged_tests_gate(["bin/s9"])
        self.assertEqual(len(calls), 1)

    def test_s7c_pre_commit_reads_the_diff_once_and_hands_it_over(self):
        with open(GUARD, encoding="utf-8") as f:
            src = f.read()
        body = src[src.index("def _pre_commit_gates"):]
        ends = [i for i in (body.find("\ndef "), body.find("\nif __name__")) if i > 0]
        body = body[:min(ends)] if ends else body
        self.assertIn("diff_text = staged_diff_text(staged)", body)
        # 인자 목록은 계약이 아니다 — 고정할 성질은 「읽은 diff 를 그대로
        # 넘긴다」이지 인자의 수가 아니다 (REQ-20260910-012 가 지운 시험 목록을
        # 셋째 인자로 더했다).
        self.assertIn("staged_tests_gate(staged, diff_text", body)
        self.assertIn("role_change_hits(staged, diff_text)", body)
        self.assertEqual(body.count("git\", \"diff"), 0, "diff 는 staged_diff_text 한 곳에서")


if __name__ == "__main__":
    unittest.main()
