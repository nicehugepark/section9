"""머신·계정 이력 (REQ-20260827-066-62x6).

서버가 `/api/users` 의 사용자마다 `machine_accounts` 를 준다(커밋 5728cc3):
어느 머신에서 · 어떤 운영체제로 · 어떤 OS 계정으로 이 계정을 썼는지 +
처음 본 때 · 마지막 본 때.

화면의 일은 하나다 — **"지금도 쓰는 머신"과 "한 번 스쳐간 머신"을 가른다.**
그 둘을 가르는 값이 first/last 이고, 그래서 서버가 둘을 함께 준다.

계약은 여섯이다.

  ① 개인설정(Settings)의 내 계정 화면에 선다 — 머신·운영체제·계정·처음·마지막.
     열 이름은 `OS 계정` 이 아니다: 그 칸에는 머신의 OS 계정이 올 수도 있고
     사람이 정한 하네스 이름이 올 수도 있다(2026-08-27 반려).
  ② 마지막으로 본 때 순으로 세운다. 지금 쓰는 것이 맨 위다.
  ③ 하루가 넘은 줄은 **명도**로 뒤로 물린다 (색상도 색면도 아니다).
  ④ 처음과 마지막이 같으면 같은 시각을 두 번 적지 않고 "한 번뿐"이라 말한다.
  ⑤ 빈 사용자(옛 프로필)에서 표가 깨지지 않는다 — 표를 세우지 않고 **왜**
     비었는지 한 줄로 말한다. 빈 것은 고장이 아니다.
  ⑥ 넘치면 표만 가로로 스크롤한다 — 판이 통째로 밀리면 옆의 폼까지 어긋난다.

실행: python3 tests/ machine_history
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class MachineHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def test_machine_history(self):
        """MachineHistory 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("it_stands_in_my_account_screen"):
            self.assertIn("${machineHistoryHTML(u)}", self._fn("showUserForm"),
                          "프로필 화면에 이력을 세우지 않았다")
            fn = self._fn("machineHistoryHTML")
            for col in ("머신", "운영체제", "계정", "처음", "마지막"):
                self.assertIn(col, fn, "열이 없다: %s" % col)
            # 이 칸에는 OS 계정이 올 수도, 사람이 정한 하네스 이름이 올 수도 있다
            # (2026-08-27 반려). 둘 중 하나라고 이름 붙이면 절반은 거짓말이 된다.
            self.assertNotIn("<th>OS 계정</th>", fn,
                             "OS 계정이 아닌 이름까지 OS 계정이라 부른다")
            self.assertIn("machine_accounts", fn, "서버가 주는 값을 읽지 않는다")
        with self.subTest("most_recent_first"):
            fn = self._fn("machineHistoryHTML")
            self.assertRegex(fn, r"\.sort\(\(a, b\) => \(Date\.parse\(b\.last",
                             "마지막 본 때 내림차순으로 세우지 않는다")
        with self.subTest("stale_recedes_by_lightness_not_hue"):
            fn = self._fn("machineHistoryHTML")
            self.assertIn("MACHINE_FRESH_MS", fn, "산 것과 죽은 것을 가르는 잣대가 없다")
            css = self._css()
            m = re.search(r"\.mhtbl tr\.stale td[^{]*\{([^}]*)\}", css)
            self.assertIsNotNone(m, "오래된 줄의 규칙이 없다")
            self.assertIn("var(--faint)", m.group(1), "명도로 물리지 않는다")
            blk = ";".join(re.findall(r"\.mh[a-z]*[^{]*\{([^}]*)\}", css))
            websrc.no_hex(self, blk)
            self.assertNotRegex(blk, r"\bborder-left\b", "좌측 세로 띠 금지")
            for v in re.findall(r"background\s*:\s*([^;}\n]+)", blk):
                self.assertIn(v.strip(), ("none", "transparent", "var(--panel)"),
                              "색면을 깔지 않는다: %s" % v)
            # 경과를 함께 보여야 "얼마나 됐나"를 날짜에서 빼지 않아도 된다
            self.assertIn("fmtElapsed", fn, "얼마나 됐는지 말하지 않는다")
        with self.subTest("seen_once_says_so"):
            fn = self._fn("machineHistoryHTML")
            self.assertRegex(fn, r"const once = r\.first && r\.last && r\.first === r\.last",
                             "한 번만 보인 머신을 가려내지 않는다")
            self.assertIn("한 번뿐", fn, "무슨 뜻인지 말하지 않는다")
        with self.subTest("empty_does_not_break_the_table"):
            fn = self._fn("machineHistoryHTML")
            self.assertRegex(fn, r"if \(!rows\.length\)", "빈 경우를 따로 그리지 않는다")
            self.assertIn("이 계정으로 세션을 연 적이 없습니다", fn,
                          "왜 비었는지 말하지 않는다")
            # 빈 상태에서 <table> 을 그리면 머리만 있는 표가 남는다
            empty = fn[fn.index("if (!rows.length)"):fn.index("const body")]
            self.assertNotIn("<table", empty, "빈데도 표를 세운다")
        with self.subTest("wide_table_scrolls_inside_itself"):
            self.assertIn('<div class="mhwrap">', self._fn("machineHistoryHTML"),
                          "표를 감싸는 자리가 없다")
            self.assertIn("overflow-x:auto", self._css(), "표가 판을 밀어낸다")
        with self.subTest("it_can_be_opened_without_hands"):
                self.assertIn("mh=([a-z]+)", self.src, "진단 파라미터가 없다")
                demo = self._fn("machineDemo")
                self.assertIn("empty", demo, "빈 상태를 세울 길이 없다")
                # 자리표시자만 쓴다 — 이 저장소는 공개다
                self.assertNotRegex(demo, r"@[a-z0-9.]+\.(com|net|org)\b",
                                    "진단 데이터에 실제로 보이는 주소를 적었다")

            # ---------- helpers ----------

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _css(self):
        m = re.search(r"/\* -+ 머신·계정 이력 표[\s\S]*?\*/([\s\S]*?)\n\.cfg-h\{", self.src)
        self.assertIsNotNone(m, "이력 표 CSS 블록을 찾지 못했다")
        return m.group(1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
