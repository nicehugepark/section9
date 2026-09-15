"""헤더 알림이 화면을 얼마나 먹는가 (REQ-20260827-017-62x6).

REQ-20260826-018 이 서버 자동 복구 기록을 헤더 3행에 올렸다. 자리 판단 자체는
옳았지만 — 이 서버 자신에 대한 사실은 한 곳에 모여야 한다 — **줄의 값을 잘못
쳤다.** 코드 낡음 알림과 자동 복구 알림이 같이 뜨면 헤더가 4행이 되고, 그
아래로 밀린 보드가 정작 사람이 보러 온 것이다. 사용자 반응: "차지하는 구간이
커서 다른 기능의 시인성이 떨어진다."

여기서 정한 규칙은 하나다.

  **줄은 사람의 손을 요구하는 사실에만 준다.**

  - 자동 복구가 **성공**한 것은 이미 끝난 일이다. 읽고 나서 할 일이 없다.
    → 전용 줄을 주지 않는다. 툴바 행(hrow2)의 칩 한 자리로 말하고, 자세한
      것은 기록 패널이 답한다. 헤더 높이 증가 0.
  - 자동 복구가 **멈춘** 것과 서버가 **옛 코드로 도는** 것은 사람이 손을 대야
    끝난다. → 지금처럼 줄로 남는다. 이걸 같이 줄이면 그건 줄이는 게 아니라
      지우는 것이다.
  - **접기는 줄을 지운다.** 지금은 접어도 hrow3 한 줄이 그대로 남아 접는
    의미가 없었다. 접힌 알림은 칩으로 내려간다.

줄이는 것과 지우는 것은 다르다 — 그래서 이 파일의 절반은 "여전히 보이는가"를
지킨다(test_action_needed_still_gets_a_row, test_record_is_one_click_away).

픽셀은 단위 테스트가 볼 수 없다. 실제 면적은 사람의 캡처 검증이 맡는다
(test_serve_guard_ui.py·test_oldcode_banner.py 와 같은 계보).

실행: python3 tests/ header_notice_area
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class HeaderNoticeArea(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.src = f.read()

    # ---------- 줄은 사람의 손을 요구하는 사실에만 ----------

    def test_recovered_takes_no_header_row(self):
        """자동 복구 성공에 전용 줄을 주면, 아무 일도 할 게 없는 사실 때문에
        헤더가 매번 한 줄씩 눌린다. 오늘 하루만 세 번 복구된 서버라면 그 줄은
        상시 표시나 다름없다."""
        body = self._fn("renderGuard")
        self.assertRegex(
            body, r"const line\s*=[^\n;]*attention",
            "헤더 줄이 attention 에만 걸려 있지 않다 — 복구 성공까지 줄을 먹는다")
        self.assertRegex(
            body, r"el\.hidden\s*=\s*!line",
            "줄 표시가 line 판정을 따르지 않는다")

    def test_folded_notice_leaves_no_row(self):
        """접었는데 줄이 그대로 남으면 접는 버튼은 거짓말이다. 접힌 알림은
        자리를 비워야 한다.

        코드 낡음은 2026-09-15 에 알림 줄(.nrail)로 옮겼다 — 닫기의 규율은
        거기서도 같고, 그쪽 계약은 tests/test_notice_rail.py 가 본다."""
        self.assertFalse('id="gw-open"' in self.src,
            "접힌 자동 복구 알림이 아직 헤더 줄에 남아 있다")
        rail = self._fn("renderNotices")
        self.assertRegex(
            rail, r"if\s*\(!live\.length\)[\s\S]{0,220}?innerHTML\s*=\s*\"\"",
            "닫아 살아 있는 알림이 없어졌는데 줄이 비지 않는다")

    def test_action_needed_still_gets_a_row(self):
        """줄이는 것과 지우는 것은 다르다. 사람이 손을 대야 끝나는 두 사실은
        여전히 헤더 줄로 말한다 — 여기서 절약하면 기능이 존재할 이유가 없다."""
        self.assertRegex(self.src, r'<div class="nrail" id="notices"',
                         "알림 줄이 헤더 자리를 잃었다 — 코드 낡음은 여기로 옮겼다")
        self.assertRegex(self.src, r'<div class="hrow3" id="guard"',
                         "자동 복구 경고가 헤더 줄 자리를 잃었다")
        body = self._fn("renderGuard")
        self.assertIn("자동 복구가 멈췄습니다", body,
                      "복구가 멈춘 사실을 말하는 문장이 사라졌다")
        self.assertIn("다시 시작되지 않", body,
                      "다음에 무슨 일이 생기는지 말하지 않으면 행동으로 못 잇는다")
        self.assertIn("s9 serve --supervise", body,
                      "감시자를 다시 세울 명령이 사라졌다")

    # ---------- 칩은 새 행을 만들지 않는다 ----------

    def test_chip_sits_in_the_brand_row(self):
        """칩이 자기 행을 만들면 줄인 게 아니라 이름만 바꾼 것이다 — 이미 있는
        브랜드 행(hrow1) 안에 들어가야 한다. 툴바 행(hrow2)은 안 된다: 거기서는
        필터·신원 묶음과 폭을 다투다 좁은 화면에서 그 행을 두 줄로 밀어, 줄이려던
        높이를 도로 쓴다(실제 1340px 캡처에서 확인). 브랜드 행은 오른쪽이 늘 비어
        있고 탭 높이에 묻혀 한 픽셀도 더하지 않는다."""
        m = re.search(r'<div class="hrow1">[\s\S]*?\n  </div>', self.src)
        self.assertIsNotNone(m, "브랜드 행(hrow1)을 찾지 못했다")
        self.assertIn('id="sv-chip"', m.group(0),
                      "서버 상태 칩이 브랜드 행 안에 없다 — 새 행을 만들거나 툴바를 민다")

    def test_chip_vanishes_when_there_is_nothing_to_say(self):
        """사건이 없으면 칩도 없다. 빈 칩이 남으면 flex gap 만큼 자리를 먹고,
        상시 표시가 되면 곧 아무도 안 읽는다(018 이 세운 규칙)."""
        css = self._css()
        self.assertRegex(
            css, r"\.svchip:empty\s*\{[^}]*display\s*:\s*none",
            "빈 칩을 감추는 규칙이 없다 — 사건이 없어도 자리가 남는다")
        body = self._fn("renderSvChip")
        self.assertRegex(body, r'innerHTML\s*=\s*""',
                         "말할 것이 없을 때 칩을 비우는 경로가 없다")

    def test_chip_is_announced(self):
        """복구 성공은 이제 칩으로만 말한다 — 화면 낭독에도 실려야 한다."""
        m = re.search(r'<span[^>]*id="sv-chip"[^>]*>', self.src)
        self.assertIsNotNone(m, "서버 상태 칩 자리(#sv-chip)가 없다")
        self.assertIn('role="status"', m.group(0),
                      "동적으로 나타나는 상태는 변화를 알려야 한다")

    # ---------- 줄인 뒤에도 도달할 수 있는가 ----------

    def test_record_is_one_click_away(self):
        """줄을 없앤 대신 기록까지의 거리가 멀어지면 안 된다 — 칩 한 번에
        '왜 죽었나'의 답(기록 패널)이 열려야 한다."""
        body = self._fn("renderSvChip")
        self.assertIn("gwOpen", body,
                      "칩에서 기록 패널로 가는 경로가 없다")
        self.assertIn("renderGuard", body,
                      "칩을 눌러도 화면이 다시 그려지지 않는다")

    def test_folded_chip_can_be_unfolded(self):
        """접어 둔 경고는 칩을 눌러 되펼칠 수 있어야 한다 — 되돌릴 수 없는
        접기는 정보를 지우는 것과 같다."""
        body = self._fn("renderSvChip")
        self.assertIn("gwSetAck(null)", body,
                      "접어 둔 자동 복구 경고를 되펼치는 경로가 없다")
        # 알림 줄에서 닫은 것은 Settings › 디스플레이의 한 줄이 되돌린다 —
        # 전부 닫히면 줄째 사라지므로 되돌리는 손잡이를 줄 안에 둘 수 없다.
        self.assertIn("noticeUnpark", self._fn("renderNotices") + self.src,
                      "닫아 둔 알림을 되돌리는 길이 없다")

    # ---------- 시각 언어 ----------

    def test_chip_reads_without_colour(self):
        """색만으로 상태를 구분하지 않는다 — 마크와 문구가 같이 말한다."""
        body = self._fn("renderSvChip")
        # 마크는 폰트 글자가 아니라 사전(marks.css)에서 온다 (REQ-20260910-027) —
        # 고정할 성질은 「복구를 뜻하는 마크가 있다」이지 그 코드포인트가 아니다.
        self.assertRegex(body, r'[↻⟳]|mk\("redo"\)', "복구를 뜻하는 마크가 없다")
        # 마크는 사전에서 온다 (REQ-20260910-027)
        self.assertRegex(body, r'▲|mk\("warn"\)', "주의를 뜻하는 마크가 없다")
        self.assertIn("자동 복구", body, "칩이 무슨 사실인지 글자로 말하지 않는다")

    def test_chip_has_no_colour_fill(self):
        """색면 하이라이트·세로 띠 금지 — 색은 글자와 마크로."""
        css = self._css()
        blk = "".join(re.findall(r"\.svchip[^{]*\{[^}]*\}", css))
        self.assertTrue(blk, "칩 스타일이 없다")
        for bg in re.findall(r"background\s*:\s*([^;}]+)", blk):
            self.assertIn(bg.strip(), ("none", "transparent"),
                          "칩에 색면을 깔지 않는다: %s" % bg)
        self.assertNotIn("border-left", blk, "좌측 세로 띠 금지")
        websrc.no_hex(self, blk)
        self.assertNotRegex(blk, r"border-radius\s*:\s*(?!0)",
                            "라운드 금지 — 계기판/장부 언어")

    def test_chip_does_not_letterspace_korean(self):
        """한국어에 자간을 벌리면 글자가 흩어져 보인다 — 모노·자간은 시각·포트
        번호 같은 라틴/숫자 메타의 어휘다 (REQ-20260826-039)."""
        css = self._css()
        blk = "".join(re.findall(r"\.svchip[^{]*\{[^}]*\}", css))
        self.assertTrue(blk, "칩 스타일이 없다")
        self.assertNotIn("letter-spacing", blk,
                         "한글 문장이 들어가는 칩에 자간을 벌리지 않는다")
        self.assertNotIn("var(--mono)", blk,
                         "한글 문장에 모노 서체를 쓰지 않는다")

    # ---------- helpers ----------

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _css(self):
        return websrc.css_section(self, self.src, r"/\* ── 서버 자동 복구 기록")


if __name__ == "__main__":
    unittest.main(verbosity=2)
