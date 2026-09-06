"""노트의 금지 용어를 기계가 거른다 (REQ-20260906-045).

에이전트가 규약 2조를 읽고도 「배경」을 썼다(2026-09-06). s9 note 가 용어표의 왼쪽 낱말을
찾아 경고 한 줄(대체어)을 내되 기록은 막지 않는다.

실행: python3 tests/ banned_terms
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class BannedTerms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9terms-")
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("S9_")}
        cls.env["S9_ROOT"] = cls.root
        subprocess.run([S9, "init"], env=cls.env, capture_output=True, check=True)
        spec = importlib.util.spec_from_loader(
            "s9_terms_t", importlib.machinery.SourceFileLoader("s9_terms_t", S9))
        cls.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.m)

    def test_t1_finds_banned_words_but_not_inside_code(self):
        """T1. 「배경에서」「작업 나무」는 잡고, 백틱 안의 코드·경로는 보지 않는다."""
        hits = self.m.banned_terms_in("전체 스위트가 배경에서 돈다 — `state/배경.log` 참고")
        self.assertEqual([a for a, _ in hits], ["배경에서", "전체 스위트"])
        self.assertEqual(self.m.banned_terms_in("백그라운드 전체 테스트가 통과했다"), [])

    def test_t2_note_warns_but_still_records(self):
        """T2. s9 note 는 경고 한 줄을 stderr 로 내고 노트는 그대로 남긴다."""
        r = subprocess.run([S9, "new", "request", "--title", "t", "--summary", "s", "--size", "S",
                            "--goal", "g", "--body", "b"], env=self.env, capture_output=True, text=True)
        doc = [t for t in r.stdout.split() if t.startswith("REQ-")][0]
        r = subprocess.run([S9, "note", doc, "작업 나무가 더럽다 — 배경에서 돌린다"], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("note appended", r.stdout)
        self.assertIn("용어", r.stderr)
        self.assertIn("「작업 나무」→「working tree」", r.stderr)
        r = subprocess.run([S9, "note", doc, "백그라운드 전체 테스트 통과"], env=self.env,
                           capture_output=True, text=True)
        self.assertNotIn("용어", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
