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

    def test_t3_status_note_warns_too(self):
        """T3. s9 status --note 의 글도 검사한다 — 전이 노트도 기록이다."""
        r = subprocess.run([S9, "new", "request", "--title", "t", "--summary", "s", "--size", "S",
                            "--goal", "g", "--body", "b"], env=self.env, capture_output=True, text=True)
        doc = [t for t in r.stdout.split() if t.startswith("REQ-")][0]
        r = subprocess.run([S9, "status", doc, "in-progress", "--note", "전체가 붉었다 — 붉은 파일 둘"],
                           env=self.env, capture_output=True, text=True)
        self.assertIn("in-progress", r.stdout)
        self.assertIn("「붉었」→「실패했」", r.stderr)

    def test_t4_colors_on_screen_are_not_metaphors(self):
        """T4. 「붉은 글자」「초록 점」은 화면의 색이다 — 같은 줄의 비유만 잡는다."""
        hits = self.m.banned_terms_in("전체가 붉었습니다. 멈춤은 붉은 글자로, 실행 중은 초록 점으로 보인다. 초록이면 지나간다")
        self.assertEqual([a for a, _ in hits], ["붉었", "초록"])
        self.assertEqual(self.m.banned_terms_in("주황 글자와 붉은 글자, 초록 점멸"), [])

    def test_t5_response_hook_records_and_prompt_hook_reflects(self):
        """T5. 응답의 용어는 Stop 훅이 기록하고 다음 프롬프트 훅이 한 줄로 되비춘다 — 한 번만."""
        import json
        env = {**self.env, "S9_SESSION": "termsess"}
        r = subprocess.run([S9, "terms", "check", "--record"], input="원격 전체가 붉었습니다",
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        path = os.path.join(self.root, "state", "terms-warn-termsess.json")
        self.assertTrue(os.path.exists(path))
        self.assertEqual(json.load(open(path, encoding="utf-8"))["hits"][0][0], "붉었")
        r = subprocess.run([S9, "terms", "pending"], env=env, capture_output=True, text=True)
        self.assertIn("직전 응답의 용어 1건", r.stdout)
        self.assertIn("「붉었」→「실패했」", r.stdout)
        self.assertFalse(os.path.exists(path), "읽고 지우지 않았다 — 매 턴 되풀이된다")
        r = subprocess.run([S9, "terms", "pending"], env=env, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "")
        # 프롬프트 훅의 additionalContext 에 실린다
        PHOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")
        subprocess.run([S9, "terms", "check", "--record"], input="붉음이 남았다", env=env,
                       capture_output=True, text=True)
        r = subprocess.run([PHOOK], input=json.dumps({"prompt": "고마워", "session_id": "termsess-full"}),
                           env={**env, "S9_PORT": "1"}, capture_output=True, text=True, timeout=60)
        self.assertIn("직전 응답의 용어", r.stdout)
        # Stop 훅: transcript 의 마지막 응답을 읽어 기록한다
        RHOOK = os.path.join(HERE, "..", "bin", "s9-audit-response")
        tp = os.path.join(self.root, "state", "t.jsonl")
        with open(tp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "m",
                                "content": [{"type": "text", "text": "판정 묶음이 붉었고 이제 초록이다"}]}},
                               ensure_ascii=False) + "\n")
        r = subprocess.run([RHOOK], input=json.dumps({"transcript_path": tp, "session_id": "termsess-full",
                                                       "cwd": self.root}),
                           env={**env, "S9_PORT": "1"}, capture_output=True, text=True, timeout=60)
        self.assertTrue(os.path.exists(path), r.stdout + r.stderr)

    def test_t6_commit_message_hook_warns(self):
        """T6. commit-msg 훅은 메시지의 용어를 경고한다 — 막지는 않는다."""
        GUARD = os.path.join(HERE, "..", "bin", "s9-guard")
        msg = os.path.join(self.root, "COMMIT_EDITMSG")
        with open(msg, "w", encoding="utf-8") as f:
            f.write("ee223fa 의 붉음 셋을 고친다\n# 주석 줄은 보지 않는다: 초록\n")
        r = subprocess.run([GUARD, "commit-msg", msg], env=self.env, capture_output=True, text=True,
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("「붉음」→「실패」", r.stderr)
        self.assertNotIn("초록", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
