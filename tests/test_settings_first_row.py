"""목록 머리가 첫 항목의 제목을 덮는다 (REQ-20260827-041-62x6).

사용자 지적: "좌측 내부 메뉴에서 디스플레이 라는 제목이 잘린것 아닌가?"

Settings 좌측 목록의 첫 항목만 제목 줄(`디스플레이`)이 사라지고 부제만 남았다.
문구가 빠진 게 아니라 **머리가 그 위에 올라타 가린 것**이다.

원인은 목록 머리 `.grp` 의 sticky 오프셋이다:

    .doclist .grp{position:sticky; top:var(--tbh,30px); background:var(--panel)}

`--tbh` 는 Docs 가 렌더 직후 타입바 실측 높이로 채운다. Settings 목록에는
타입바가 없어 변수가 없고, 폴백 30px 이 살아남는다. **sticky 는 문턱보다 위에
있는 상자를 아래로 밀어내면서 자리는 비워 두지 않는다** — 그래서 머리가 30px
내려가 불투명한 배경으로 첫 행의 제목 줄을 덮었다. 실측 가림: 스킨 10종에서
+19~+24px. Docs 가 멀쩡했던 건 타입바가 위쪽 30px 을 차지해 머리의 제자리가
이미 30px 이었기 때문이다.

처방은 **JS 가 변수를 채워 주기를 기다리지 않는 것**이다. 오프셋을 기본값에서
빼고, 선행 `.typebar` 가 실제로 있을 때만 주는 선택자로 옮긴다. 그러면 이
위젯을 타입바 없이 재사용하는 어떤 자리도 스스로 옳게 동작한다 — 지금 그런
자리가 둘(Settings 설정 머리 · Stream 빈 상태 줄)이고, 셋째가 생겨도 안전하다.

이 테스트가 지키는 계약:
  ① 기본 `.doclist .grp` 는 아래로 밀리지 않는다(문턱 0).
  ② 타입바 아래에 붙는 오프셋은 **선행 .typebar 를 요구하는 선택자**에만 있다.
  ③ 타입바 없이 `.doclist` 를 쓰는 자리(Settings·Stream)가 실제로 존재한다
     — 이 사실이 ①②를 필요하게 만든다. 사라지면 규칙의 근거가 사라진다.
  ④ 머리는 여전히 불투명하다(스크롤 중 글자가 겹쳐 읽히지 않게) — 배경을
     지워서 "안 가려 보이게" 때우는 우회를 막는다.

실행: python3 tests/ settings_first_row
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


def rules_for(src, needle):
    """선택자에 needle 이 들어간 CSS 규칙 [(선택자, 본문)] 을 모은다."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)   # 주석은 선택자가 아니다
    out = []
    for m in re.finditer(r"(?m)^([^\n{}@/][^{}]*)\{([^{}]*)\}", src):
        sel, body = m.group(1).strip(), m.group(2)
        if needle in sel:
            out.append((" ".join(sel.split()), body))
    return out


class SettingsFirstRow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.grp = rules_for(cls.src, ".grp")
        assert cls.grp, ".grp 규칙을 못 찾았다"

    # ① 기본 머리는 아래로 밀리지 않는다
    def test_settings_first_row(self):
        """SettingsFirstRow 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("base_grp_not_pushed_down"):
                base = [(s, b) for s, b in self.grp
                        if ".typebar" not in s and "top:" in b]
                self.assertTrue(base, ".doclist .grp 의 top 선언을 못 찾았다")
                for sel, body in base:
                    top = re.search(r"top:\s*([^;}]+)", body).group(1).strip()
                    self.assertIn(top, ("0", "0px"),
                                  f"타입바를 요구하지 않는 규칙이 머리를 {top} 밀어낸다 "
                                  f"— 첫 항목 제목이 그만큼 가려진다: {sel}")

            # ② 타입바 오프셋은 타입바를 요구하는 선택자에만
        with self.subTest("typebar_offset_is_scoped"):
                off = [(s, b) for s, b in self.grp if "--tbh" in b]
                self.assertTrue(off, "타입바 아래에 머리를 붙이는 규칙이 사라졌다 "
                                     "— Docs 에서 머리가 타입바 뒤로 숨는다")
                for sel, body in off:
                    self.assertIn(".typebar", sel,
                                  f"타입바가 없어도 적용되는 오프셋이다: {sel}")
                    self.assertRegex(sel, r"\.typebar\s*[~+]\s*",
                                     f"선행 형제로 요구해야 한다: {sel}")

            # ③ 타입바 없이 이 위젯을 쓰는 자리가 실제로 있다 (규칙의 근거)
        with self.subTest("grp_used_without_typebar"):
                # Settings 좌측 목록
                m = re.search(r'<div class="doclist"><div class="grp">설정</div>',
                              self.src)
                self.assertIsNotNone(m, "Settings 목록의 머리 markup 이 바뀌었다 "
                                        "— 이 테스트가 지키는 자리를 다시 확인하라")
                seg = self.src[m.start():m.start() + 400]
                self.assertNotIn("typebar", seg, "Settings 목록에 타입바가 생겼다")
                # Stream 빈 상태 줄
                self.assertIn('<div class="grp">no streams', self.src)

            # ④ 머리는 불투명해야 한다 — 배경을 지워 때우지 않는다
        with self.subTest("grp_stays_opaque"):
            base = [b for s, b in self.grp
                    if ".typebar" not in s and "position:sticky" in b]
            self.assertTrue(base, "머리의 sticky 선언을 못 찾았다")
            self.assertTrue(any("background:" in b for b in base),
                            "머리에서 배경을 지웠다 — 스크롤 중 글자가 겹친다. "
                            "가림은 위치로 풀어야지 투명도로 덮지 않는다")

if __name__ == "__main__":
    unittest.main()
