"""확인 포인트는 카드에서 읽히는 길이여야 한다 (REQ-20260829-009-62x6).

사용자 지적: "확인 메시지가 너무 기니까 잘린다. 잘리는게 맞나? 그리고 이렇게까지
길게 보여주는게 맞을까? 너무 길면 결국 가독성이 떨어져서 본문으로 들어가서
보게 되는데 말이야."

판정 카드에 실리는 것은 `-> review` 전이의 note 다. 그것이 원인·경위·자기검증
이력까지 다 담으면서 한 카드에 20줄 넘는 문단이 되었고, 사용자는 판정을 하러
왔다가 본문으로 들어가 읽어야 했다 — **판정 자리가 판정을 못 시킨다.**

숫자의 근거는 우리가 쓴 것에서 나왔다. 그때까지 쌓인 review 전이 260건의
중앙값이 231자, 60%가 이미 300자 이하였다. 300자는 새 규율이 아니라 다수가
이미 지키던 선이고, 사고 사례(982~1805자)는 전부 그 밖이다. 갈래 상한 3은
같은 자리에서 나온다 — 한 판정 요청은 한 결정을 청한다. ①②③④⑤ 를 한 문단에
욱여넣으면 그것은 판정 요청이 아니라 점검 목록이다.

이 시험이 지키는 것은 길이 규율 하나다. 이미 있는 두 규율은 그 아래 그대로다 —
확인 포인트는 사용자 언어로(현상 → 비유 → 재현 절차 순), review 는 눌러서
확인할 수 있는 것만. 길이는 그 위에 얹힌 층이지 대체가 아니다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ review_point_len
"""
import os
import re
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
PROTO = os.path.join(HERE, "..", "harness", "common", "PROTOCOL.md")
CLAUDE_MD = os.path.join(HERE, "..", "CLAUDE.md")
SKILL = os.path.join(HERE, "..", "harness", "claude", "skills",
                     "s9-protocol", "SKILL.md")

OK = ("멈춰 있던 카드에 깨우기 단추가 생겼습니다. 먼저 서버를 다시 띄우고 Board 탭 "
      "IN-PROGRESS 열에서 멈춤 줄이 붙은 카드를 눌러 보세요. 깨워지면 점이 주황으로 "
      "바뀌고 멈춤 줄이 사라집니다. 못 깨운 이유가 붉은 실패 창으로 뜨면 반려해 주세요.")


class ReviewPointLen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9rplen-")
        self.env = {**os.environ, "S9_ROOT": self.tmp, "S9_MACHINE": "testbox"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "alice")

    def cli(self, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=30)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def mk(self):
        doc = self.cli("new", "request", "--title", "확인 포인트 길이",
                       "--summary", "s", "--goal", "g", "--size", "S",
                       "--user", "alice", "--body", "x").split()[0]
        self.cli("status", doc, "in-progress")
        return doc

    def body(self, doc_id):
        for root, _d, files in os.walk(os.path.join(self.tmp, "vault")):
            for fn in files:
                if fn.startswith(doc_id) and fn.endswith(".md"):
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        return f.read()
        raise AssertionError(f"문서 없음: {doc_id}")

    # --- N. 규율대로 쓴 확인 포인트는 통과한다 ---

    def test_n1_within_limit_passes(self):
        """실제로 다시 쓴 확인 포인트(232자)가 막히지 않는다 — 상한은 쓸 수
        있는 선이어야 규율이지, 못 쓰는 선이면 --force 우회를 부른다."""
        doc = self.mk()
        self.assertLessEqual(len(OK), 300)
        self.cli("status", doc, "review", "--note", OK)
        self.assertIn("-> review", self.body(doc))

    def test_n2_three_branches_pass(self):
        """갈래 셋까지는 한 판정으로 본다."""
        doc = self.mk()
        self.cli("status", doc, "review", "--note",
                 "① 카드를 누른다 ② 점이 주황으로 바뀐다 ③ 안 바뀌면 반려")

    # --- B. 경계 ---

    def test_b1_exactly_at_limit_passes(self):
        """정확히 상한이면 통과 — 경계는 넘어야 걸린다."""
        doc = self.mk()
        self.cli("status", doc, "review", "--note", "가" * 300)

    def test_b2_over_limit_rejected(self):
        """한 자만 넘어도 거부."""
        doc = self.mk()
        out = self.cli("status", doc, "review", "--note", "가" * 301, expect=1)
        self.assertIn("301자", out)
        self.assertIn("300", out)
        self.assertNotIn("-> review", self.body(doc))

    def test_b3_whitespace_normalized_before_counting(self):
        """줄바꿈·연속 공백은 History 에서 한 칸으로 접히니, 세는 것도 접힌
        뒤여야 한다 — 안 그러면 개행만 넣어 상한을 우회한다."""
        doc = self.mk()
        self.cli("status", doc, "review", "--note", "가" * 300 + "\n\n   \n")

    # --- F. 실제 사고 재현 ---

    def test_f1_real_incident_rejected(self):
        """REQ-20260828-041 이 실제로 올린 982자 5갈래 확인 포인트가 막힌다."""
        doc = self.mk()
        note = ("멈춰 있는 카드에 깨우기 단추를 달았다. " + "경위와 근거를 길게 적는다. " * 40
                + " ① 하나 ② 둘 ③ 셋 ④ 넷 ⑤ 다섯")
        out = self.cli("status", doc, "review", "--note", note, expect=1)
        self.assertIn("확인 포인트", out)
        self.assertIn("갈래 5개", out)

    def test_f2_too_many_branches_rejected_even_when_short(self):
        """짧아도 갈래가 넷이면 그것은 판정 요청이 아니라 점검 목록이다."""
        doc = self.mk()
        out = self.cli("status", doc, "review", "--note",
                       "① 하나 ② 둘 ③ 셋 ④ 넷", expect=1)
        self.assertIn("갈래 4개", out)

    def test_f3_numeric_branches_counted(self):
        """`1) 2) 3) 4)` 도 같은 갈래다 — 기호만 바꿔 빠져나가지 못한다."""
        doc = self.mk()
        out = self.cli("status", doc, "review", "--note",
                       "확인은 넷이다. 1) 하나 2) 둘 3) 셋 4) 넷", expect=1)
        self.assertIn("갈래 4개", out)

    def test_f4_error_says_where_the_rest_goes(self):
        """거부는 '지워라'가 아니라 '옮겨라'여야 한다 — 근거를 버리게 하면
        문서가 얇아진다. 갈 자리(response 노트)를 문구가 지목한다."""
        doc = self.mk()
        out = self.cli("status", doc, "review", "--note", "가" * 400, expect=1)
        self.assertIn("--label response", out)
        self.assertIn("--force", out)

    # --- E. 예외 ---

    def test_e1_force_passes(self):
        """사람 판정만 남은 예외는 --force — 기존 게이트들과 같은 문 하나."""
        doc = self.mk()
        self.cli("status", doc, "review", "--note", "가" * 500, "--force")
        self.assertIn("-> review", self.body(doc))

    def test_e2_judge_memo_not_capped(self):
        """승인·반려 메모는 확인 포인트가 아니다 — review 에서 나가는 길에는
        이 상한이 걸리지 않는다."""
        doc = self.mk()
        self.cli("status", doc, "review", "--note", OK)
        self.cli("status", doc, "in-progress", "--note", "가" * 600)
        self.assertIn("review -> in-progress", self.body(doc))

    # --- C. 규칙이 글로만 남지 않는다 ---

    def test_c1_rule_is_written_where_the_lead_reads(self):
        """리드가 매 세션 읽는 두 자리(CLAUDE.md · PROTOCOL.md)에 숫자가 있다."""
        for path in (CLAUDE_MD, PROTO, SKILL):
            with open(path, encoding="utf-8") as f:
                txt = f.read()
            self.assertIn("300자", txt, f"{os.path.basename(path)} 에 상한이 없다")

    def test_c2_code_and_doc_agree(self):
        """문서의 숫자와 코드의 상수가 어긋나면 규율이 둘이 된다."""
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("REVIEW_POINT_MAX = 300", src)
        self.assertIn("REVIEW_POINT_BRANCHES = 3", src)

    def test_c3_existing_disciplines_survive(self):
        """길이 규율은 두 선행 규율 위에 얹히는 층이지 대체가 아니다."""
        with open(PROTO, encoding="utf-8") as f:
            txt = f.read()
        for phrase, why in (
                ("사용자 언어", "확인 포인트를 사용자 언어로 쓰라는 규율이 사라졌다"),
                ("현상", "현상 → 비유 → 재현 절차 순서가 사라졌다"),
                ("✓승인/↺반려", "눌러 답할 수 있는 것만 review 라는 규율이 사라졌다")):
            self.assertIn(phrase, txt, why)


if __name__ == "__main__":
    unittest.main()
