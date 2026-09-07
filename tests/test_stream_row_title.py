"""Stream 목록의 행이 제 이름을 갖는가 (REQ-20260907-031-62x6).

Stream 탭 왼쪽 목록의 제목 자리에 「(SES 문서 없음)」이 열 줄 넘게 서 있었다.
문서가 없어서가 아니다 — **다른 이름으로 찾아서** 못 찾은 것이다:
`/api/streams` 는 파일 이름 그대로 36자 전체 세션 id 를 주는데, SES 문서의
`session` 앞머리 8자다(vault 의 194건 전부). 그래서 76행 중 75행이 빗나갔다.

이 시험이 지키는 계약은 넷이다.

  ① 찾을 때 8자 앞머리로 맞춘다 — 문서 쪽 키도, 스트림 쪽 조회도.
  ② 「SES 문서 없음」이라는 글자가 화면 소스에서 사라진다.
  ③ 행은 문서가 있든 없든 **같은 세 칸**으로 선다 — 세션 이름 8자 ·
     마지막으로 움직인 때 · 컴퓨터(모르면 「컴퓨터 모름」).
  ④ 고르기는 그대로다 — `data-stream` 은 자르지 않은 전체 세션 id 다.

실행: python3 tests/ stream_row_title
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = open(os.path.join(HERE, "..", "web", "app", "audit.js"),
           encoding="utf-8").read()
# renderStream 한 함수만 본다 — 이웃 함수의 글자가 판정에 섞이지 않게.
BLOCK = SRC[SRC.index("async function renderStream()"):
            SRC.index("async function loadStream(")]
# 주석은 화면에 안 나온다 — 옛 코드를 설명하는 주석이 「아직 남아 있다」로
# 잘못 걸리지 않게, 판정은 주석을 걷어 낸 코드에만 건다.
strip = lambda t: re.sub(r"//[^\n]*", "", re.sub(r"/\*[\s\S]*?\*/", "", t))
CODE = strip(BLOCK)
ROW = CODE.split("const list")[1].split("}).join")[0]


class TheRowFindsItsDocument(unittest.TestCase):
    def test_lookup_key_is_the_eight_char_prefix(self):
        """문서 쪽 키도, 스트림 쪽 조회도 8자 앞머리로 맞춘다."""
        self.assertIn('.slice(0, 8), r]', CODE,
                      "SES 문서를 8자 앞머리로 색인하지 않는다")
        self.assertIn('sesDocs[s.session.slice(0, 8)]', CODE,
                      "스트림을 8자 앞머리로 조회하지 않는다")
        self.assertNotIn("sesDocs[s.session]", CODE,
                         "36자 전체 id 로 찾는 옛 조회가 남아 있다")

    def test_the_missing_document_line_is_gone(self):
        """「SES 문서 없음」은 목록의 글자가 아니다."""
        self.assertNotIn("SES 문서 없음", strip(SRC),
                         "「SES 문서 없음」이 아직 화면에 그려진다")
        self.assertNotIn("SES", ROW, "행 안에 내부 문서종 약자가 남아 있다")


class TheRowsStandInOnePlace(unittest.TestCase):
    """문서가 있는 행과 없는 행이 같은 위계·같은 자리로 선다."""

    def test_three_slots_are_always_filled(self):
        # 이름 8자 · 시각 — 두 칸은 스트림 자신의 사실이라 늘 찬다.
        self.assertIn('<div class="id">${esc(s.session.slice(0, 8))}</div>', ROW)
        self.assertIn("<div>${esc(when)}</div>", ROW)
        # 컴퓨터 칸은 값이 갈릴 때만 서고, 모르는 행은 「모름」으로 자리를 지킨다.
        self.assertIn('${esc(where || "컴퓨터 모름")}', ROW)

    def test_one_machine_is_written_once_not_on_every_row(self):
        """76행이 한 컴퓨터면 이름을 76번 적지 않는다 (s9-design 표 절 8)."""
        self.assertIn("const wheres = [...new Set(rows.map(r => r.where))]", CODE)
        self.assertIn("const only = wheres.length === 1 ? wheres[0] : null", CODE)
        # 접었으면 그 값을 목록 밖 한 곳에 한 번 적는다.
        self.assertRegex(CODE, r'#count[\s\S]{0,240}only \|\| "어느 컴퓨터인지 모릅니다"')
        self.assertIn("only === null", ROW, "칸을 접는 판정이 행에 닿지 않는다")

    def test_time_uses_the_one_formatter_this_repo_has(self):
        """시각 서식은 한 벌이다 — fmtWhen 을 쓰고 두 번째를 만들지 않는다."""
        self.assertIn("fmtWhen(s.mtime)", CODE)
        self.assertNotIn('s.mtime.slice(0,16)', CODE,
                         "ISO 문자열을 잘라 쓰는 옛 서식이 남아 있다")

    def test_the_missing_fact_is_told_by_one_sentence(self):
        """문서가 없다는 사실은 툴팁 한 문장으로 내려간다 (s9-design R6)."""
        tip = re.search(r"const tip = [\s\S]*?;\n", CODE).group(0)
        self.assertIn("세션 문서가 없어 어느 컴퓨터인지 모릅니다", tip)
        for sentence in re.findall(r"`([^`]+)`", tip):
            self.assertLessEqual(sentence.count("."), 0,
                                 "툴팁이 두 문장이다: " + sentence)
            self.assertIn("니다", sentence, "툴팁이 존댓말이 아니다: " + sentence)
        self.assertIn('title="${esc(tip)}"', ROW, "툴팁이 행에 붙지 않았다")


class TheChoosingStillWorks(unittest.TestCase):
    def test_data_stream_keeps_the_whole_session_id(self):
        """보여주는 이름만 8자다 — 고르고 불러오는 값은 자르지 않는다."""
        self.assertIn('data-stream="${esc(s.session)}"', ROW)


if __name__ == "__main__":
    unittest.main()
