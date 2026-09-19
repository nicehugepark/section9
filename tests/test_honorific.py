"""사람이 읽는 자리의 글이 존댓말인지 기계가 거른다 (REQ-20260919-003-62x6).

비유·용어는 표(BANNED_TERMS)와 훅과 시험이 함께 지키는데 존댓말은 규약의 문장 한 줄뿐이었다.
그래서 지켜지는 정도가 모델마다 갈렸다(실측 2026-09-19: 가이드 화면 93.5% · 요청 문서의 노트 6.1%).
`s9 speech check` 가 평서문의 종결을 보고 경고하되 기록은 막지 않는다.

실행: python3 tests/ honorific
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class Honorific(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9speech-")
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("S9_")}
        cls.env["S9_ROOT"] = cls.root
        subprocess.run([S9, "init"], env=cls.env, capture_output=True, check=True)
        spec = importlib.util.spec_from_loader(
            "s9_speech_t", importlib.machinery.SourceFileLoader("s9_speech_t", S9))
        cls.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.m)

    def _new_req(self):
        r = subprocess.run([S9, "new", "request", "--title", "t", "--summary", "s", "--size", "S",
                            "--goal", "g", "--body", "b"], env=self.env, capture_output=True, text=True)
        return [t for t in r.stdout.split() if t.startswith("REQ-")][0]

    # ── 정상
    def test_t1_plain_declarative_is_caught(self):
        """T1. 반말 평서문은 잡고, 합쇼체·해요체는 지나간다."""
        self.assertEqual(len(self.m.plain_speech_in("검사를 세웠다")), 1)
        self.assertEqual(self.m.plain_speech_in("검사를 세웠습니다"), [])
        self.assertEqual(self.m.plain_speech_in("그렇게 했어요"), [])
        self.assertEqual(self.m.plain_speech_in("무엇을 고쳐야 합니까"), [])

    def test_t2_counts_each_sentence(self):
        """T2. 한 줄에 여러 문장이면 반말인 것만 센다."""
        hits = self.m.plain_speech_in("검사를 세웠다. 시험도 붙였습니다. 훅이 되비친다")
        self.assertEqual(len(hits), 2, hits)

    # ── 경계
    def test_t3_code_and_quotes_are_skipped(self):
        """T3. 백틱 안의 코드와 「」·따옴표 안의 인용은 보지 않는다 — 코드거나 남의 말이다."""
        self.assertEqual(self.m.plain_speech_in("`s9 speech check` 로 확인했습니다"), [])
        self.assertEqual(self.m.plain_speech_in("주인 지적 「이게 뭐다」 를 받았습니다"), [])
        self.assertEqual(self.m.plain_speech_in('사용자가 "그렇게 한다" 고 적었습니다'), [])
        self.assertEqual(self.m.plain_speech_in("```\n검사를 세웠다\n```"), [])

    def test_t4_structure_lines_are_skipped(self):
        """T4. 제목·표·인용·체크박스 줄은 말이 아니라 구조다."""
        for line in ("## 검사를 세웠다", "| 검사 | 세웠다 |", "> 검사를 세웠다",
                     "- [ ] 검사를 세운다", "- [x] 검사를 세웠다"):
            self.assertEqual(self.m.plain_speech_in(line), [], line)

    def test_t5_imperative_is_not_plain_speech(self):
        """T5. 명령형 지시문은 세지 않는다 — 규약과 지시문의 말투다."""
        self.assertEqual(self.m.plain_speech_in("먼저 `s9 digest` 를 실행하라"), [])
        self.assertEqual(self.m.plain_speech_in("검사를 우회하지 마라"), [])
        self.assertEqual(self.m.plain_speech_in("판정할 것을 맨 앞에 두어라"), [])

    def test_t6_trailing_reference_does_not_hide_the_ending(self):
        """T6. 끝에 붙은 괄호 참조는 종결을 가리지 못한다."""
        hits = self.m.plain_speech_in("검사를 세웠다 (REQ-20260919-003-62x6)")
        self.assertEqual(len(hits), 1, hits)
        self.assertEqual(self.m.plain_speech_in("검사를 세웠습니다 (REQ-20260919-003-62x6)"), [])

    def test_t7_non_hangul_is_ignored(self):
        """T7. 한글이 아닌 문장은 이 검사의 대상이 아니다."""
        self.assertEqual(self.m.plain_speech_in("The check warns but never blocks."), [])
        self.assertEqual(self.m.plain_speech_in("state/speech-warn-<sid>.json"), [])

    # ── 실패
    def test_t8_check_never_blocks(self):
        """T8. 반말이 있어도 `s9 speech check` 는 0 으로 끝난다 — 막지 않는다."""
        r = subprocess.run([S9, "speech", "check"], input="검사를 세웠다",
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("존댓말", r.stderr)
        r = subprocess.run([S9, "speech", "check", "--json"], input="검사를 세웠다",
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(len(json.loads(r.stdout)), 1)

    def test_t9_note_warns_but_still_records(self):
        """T9. s9 note 는 경고를 stderr 로 내고 노트 본문은 그대로 남긴다."""
        doc = self._new_req()
        r = subprocess.run([S9, "note", doc, "검사를 세웠다. 시험도 붙였다"],
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("note appended", r.stdout)
        self.assertIn("존댓말", r.stderr)
        r = subprocess.run([S9, "show", doc], env=self.env, capture_output=True, text=True)
        self.assertIn("검사를 세웠다", r.stdout)
        r = subprocess.run([S9, "note", doc, "검사를 세웠습니다"],
                           env=self.env, capture_output=True, text=True)
        self.assertNotIn("존댓말", r.stderr)

    def test_t10_status_note_warns_too(self):
        """T10. 전이 노트(확인 포인트)도 같은 검사를 받는다 — 사람이 카드에서 읽는 자리다."""
        doc = self._new_req()
        r = subprocess.run([S9, "status", doc, "in-progress", "--note", "검사를 세웠다"],
                           env=self.env, capture_output=True, text=True)
        self.assertIn("in-progress", r.stdout)
        self.assertIn("존댓말", r.stderr)

    # ── 회귀
    def test_t11_record_and_pending_roundtrip(self):
        """T11. 기록한 것을 pending 이 한 줄로 내고 지운다 — 두 번째 호출은 비어 있다."""
        env = {**self.env, "S9_SESSION": "speechss"}
        r = subprocess.run([S9, "speech", "check", "--record"], input="검사를 세웠다",
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        path = os.path.join(self.root, "state", "speech-warn-speechss.json")
        self.assertTrue(os.path.exists(path))
        r = subprocess.run([S9, "speech", "pending"], env=env, capture_output=True, text=True)
        self.assertIn("직전 응답의 반말 1건", r.stdout)
        self.assertFalse(os.path.exists(path), "읽고 지우지 않았다 — 매 턴 되풀이된다")
        r = subprocess.run([S9, "speech", "pending"], env=env, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "")

    def test_t12_hooks_carry_it_to_the_next_turn(self):
        """T12. 응답 훅이 기록하고 프롬프트 훅이 되비춘다 — 훅을 실제로 이어 돌려 본다."""
        env = {**self.env, "S9_SESSION": "speechss", "S9_PORT": "1"}
        path = os.path.join(self.root, "state", "speech-warn-speechss.json")
        RHOOK = os.path.join(HERE, "..", "bin", "s9-audit-response")
        tp = os.path.join(self.root, "state", "speech.jsonl")
        with open(tp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "m",
                                "content": [{"type": "text", "text": "검사를 세웠다"}]}},
                               ensure_ascii=False) + "\n")
        r = subprocess.run([RHOOK], input=json.dumps({"transcript_path": tp,
                                                      "session_id": "speechss-full", "cwd": self.root}),
                           env=env, capture_output=True, text=True, timeout=90)
        self.assertTrue(os.path.exists(path), r.stdout + r.stderr)
        PHOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")
        r = subprocess.run([PHOOK], input=json.dumps({"prompt": "고맙습니다",
                                                      "session_id": "speechss-full"}),
                           env=env, capture_output=True, text=True, timeout=90)
        self.assertIn("직전 응답의 반말", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
