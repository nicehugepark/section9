"""문서 뷰어 review/blocked 판단 근거 callout (REQ-20260825-006 반려 재작업).

반려 사유: "리뷰나 블럭 판단 근거가 되는 내용, 사용자 판단을 위한 설명이나
선택지가 문서 내부에서 쉽게 확인이 어렵다" — 전이 사유가 본문 최하단 History
한 줄에만 있어 묻힌다. 뷰어가 최근 `-> review|blocked` 전이의 note를 상단
callout(.gate)으로 끌어올리는지, 그 파싱 정규식이 s9가 실제 생성하는 History
라인 형식과 일치하는지(형식 계약)를 검증한다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ review_gate
"""
import glob
import os
import re
import subprocess
import tempfile
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
INDEX = index_path()


class TestReviewGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.html = f.read()

    # --- S1~S3: 뷰어 구현 존재 (단일 파일 JS라 정적 계약으로 검증) ---

    def test_gate_markup_present(self):
        """S1/S2: .gate callout이 review·blocked 두 상태 모두에서 렌더된다."""
        self.assertIn('class="gate', self.html)
        self.assertIn('m.status === "review" || m.status === "blocked"', self.html)
        # 상태별 캡션 — review는 사용자 판단 요청임이 문구로 드러나야 한다
        self.assertIn("확인 요청", self.html)
        self.assertIn("대기 사유", self.html)

    def test_gate_css_ledger_language(self):
        """callout은 계기판 언어를 따른다 — 1px 보더, 라운드/그림자 금지."""
        m = re.search(r"\.gate\{([^}]*)\}", self.html)
        self.assertIsNotNone(m, ".gate CSS 규칙이 없다")
        css = m.group(1)
        self.assertIn("border:1px solid", css)
        self.assertNotIn("border-radius", css)
        self.assertNotIn("box-shadow", css)

    def test_gate_conditional_on_note(self):
        """S3: 전이 note가 없으면 회차로 세지 않는다 (t[5] 가드)."""
        self.assertIn("!t || !t[5]", self.html)

    def test_gate_round_history(self):
        """S5 (REQ-20260825-011 반려): 다회차 반려 시 이전 회차의 확인 포인트·
        반려 사유가 접힘 이력으로, 현재 회차가 메인 callout으로 구분 노출된다."""
        self.assertIn("gate-h", self.html)           # 이력 접힘 컨테이너
        self.assertIn("이전 판정 이력", self.html)
        self.assertIn('kind: "반려"', self.html)      # 반려 회차 수집

    # --- S4: 형식 계약 — JS 정규식이 s9 실제 출력과 일치 ---

    def _gate_re(self):
        m = re.search(r'GATE_RE_SRC\s*=\s*"([^"]+)"', self.html)
        self.assertIsNotNone(m, "GATE_RE_SRC 정의가 index.html에 없다")
        # JS 문자열 리터럴 이스케이프(\\S 등)를 실제 패턴으로 복원
        return m.group(1).replace("\\\\", "\\")

    def test_regex_matches_real_s9_history_line(self):
        tmp = tempfile.mkdtemp(prefix="s9gate-")
        env = {**os.environ, "S9_ROOT": tmp, "S9_MACHINE": "testbox",
               "S9_USER": "tester"}
        env.pop("S9_SESSION", None)

        def cli(*argv):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=env, timeout=15, stdin=subprocess.DEVNULL)
            self.assertEqual(r.returncode, 0,
                             f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
            return r

        cli("init")
        cli("user", "add", "tester")
        cli("new", "request", "--title", "gate 계약 검증", "--summary", "s",
            "--size", "S", "--body", "b")
        docs = glob.glob(os.path.join(tmp, "vault", "requests", "**", "REQ-*.md"),
                         recursive=True)
        self.assertEqual(len(docs), 1)
        rid = os.path.splitext(os.path.basename(docs[0]))[0]
        cli("status", rid, "in-progress", "--note", "착수")
        note1 = "확인 포인트 v1: (1) A안 채택 여부 — 예: 201 점프 허용?"
        cli("status", rid, "review", "--note", note1)
        cli("status", rid, "in-progress", "--note", "반려: 예시가 부족합니다")
        note2 = "확인 포인트 v2: 예시 보강판"
        cli("status", rid, "review", "--note", note2)
        with open(docs[0], encoding="utf-8") as f:
            body = f.read()

        # JS와 동일한 회차 수집 로직을 s9 실출력에 적용 (형식 계약 + 다회차)
        pat = re.compile(self._gate_re())
        rounds = []
        for ln in body.split("\n"):
            t = pat.match(ln)
            if not t or not t.group(5):
                continue
            if t.group(3) == "review":
                rounds.append(("확인 요청", t.group(4), t.group(5)))
            elif t.group(2) == "review" and t.group(3) == "in-progress":
                rounds.append(("반려", t.group(4), t.group(5)))
        self.assertEqual([r[0] for r in rounds], ["확인 요청", "반려", "확인 요청"])
        self.assertTrue(all(r[1] == "tester" for r in rounds))
        self.assertEqual(rounds[0][2], note1)   # 1차 확인 포인트 보존
        self.assertIn("반려:", rounds[1][2])     # 반려 사유 보존
        self.assertEqual(rounds[-1][2], note2)  # 현재(최신) 회차 = 메인 callout


if __name__ == "__main__":
    unittest.main(verbosity=2)
