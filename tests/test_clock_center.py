"""경과 시각의 시계 그림은 숫자와 같은 높이에 선다 (REQ-20260910-042-62x6).

사용자가 본 것: 스킨 열 중 **soft 에서만** 시계 그림이 숫자보다 1px 위에 섰다.
나머지 아홉은 차가 0.00 이었다.

뿌리는 그림이 아니라 줄 상자였다. `.elapsed` 는 `inline-flex · align-items:
center` 라 11px 그림과 글자 줄 상자를 가운데로 맞추는데, soft 만
`line-height:1.4`(=14px)를 다시 적어 base 의 12px(=`--card-edge`)과 달랐다.
키 차가 1px 일 때와 3px 일 때는 그림이 화소 격자에 얹히는 자리가 갈리고,
그 어긋남이 잉크 1px 로 보였다.

**이 시험은 소스의 글자가 아니라 그려진 화소를 잰다.** 같은 결함을 CSS 쪽에서
막는 계약(어느 규칙도 이 줄의 줄높이를 `--card-edge` 밖에서 다시 적지 않는다)은
tests/test_card_corner.py 에 있다 — 둘은 같은 사고의 앞뒤다. 규칙을 지켜도 눈에
어긋나 보일 수 있으므로, 판정은 화면이 한다.

**두 번째 사고 — 배율 1.5 에서만 갈렸다** (REQ-20260910-022). 그림 잉크를
제 상자 한가운데에 두고서도 배율 1.5 에서 열 스킨 중 아홉이 0.67px(= 화소
하나)을 냈다. 뿌리는 숫자 쪽이었다: 줄 상자는 내림자 자리까지 품으므로 mono
10px 숫자의 잉크 중심은 줄 한가운데가 아니라 `L/2 − 0.5` 에 앉는다.
`align-items:center` 는 상자를 맞추니, 잉크가 상자 한가운데인 그림은 늘
0.5px 아래에 선다 — 배율 1 에서는 그 반 칸이 화소로 반올림돼 0.5 로,
1.5 에서는 화소 하나로 보였다. 그림을 반 칸 위(11칸 상자의 잉크 1..9)로
옮겨 걷었다(web/css/marks.css `--mk-clock-src`).

실행: python3 tests/ clock_center
"""
import time
import unittest

from _probe_marks import measure
from cdpreal import chrome_path

# 열 스킨 전부 — 어긋남은 한 스킨에서만 났고, 한 스킨만 재면 그것을 못 본다.
SKINS = ("ledger", "slate", "cork", "grid", "soft", "calm",
         "terminal", "glass", "field", "cobalt")
# 배율 셋 — 비정수 배율에서 획이 화소 경계에 걸리는 것이 이 화면의 단골 결함이라
# (규약 12조), 1 만 재고 넘기면 사람이 실제로 보는 자리를 안 본 것이 된다.
SCALES = (1.0, 1.25, 1.5)
# 화소 하나가 어긋나면 사람 눈에 보인다. 맞은 스킨들은 0.00 을 내므로 0.5px 은
# 넉넉한 폭이다.
TOLERANCE = 0.5


def _mid(part):
    """잉크 **경계**의 세로 한가운데.

    무게중심(`cy`)이 아니라 경계를 쓰는 까닭: 시계는 속이 빈 테라 잉크가 위아래
    가장자리에 몰리고, 숫자는 가운데가 무겁다. 무게중심으로 재면 자리가 맞아도
    열 스킨이 한결같이 0.7px 을 낸다 — 어긋남이 아니라 그림의 성질이다.
    앞선 재작업(REQ-20260910-009 5차)이 「그림 10.00 · 숫자 9.00」으로 1px 을
    지목하고 고친 자도 이 경계 한가운데였다. 같은 자를 이어 쓴다.
    """
    return (part["y0"] + part["y1"]) / 2


def _measure_or_retry(scale, tries=3):
    """한 배율을 재되, CDP 연결이 끊기면 다시 띄워 잰다.

    끊김은 결함이 아니라 **연결**의 사고다 — headless 크롬을 배율마다 새로
    띄우다 보면 몇 번에 한 번은 DevTools 소켓이 먼저 닫힌다(실측 2026-09-10:
    네 번 중 한 번). 그런데 종전에는 그 한 번이 `SkipTest` 로 나가 **화소를
    재지 않은 실행이 통과로 보였다** — 이 시험이 잡으라고 있는 어긋남이
    그대로 지나간 회차가 있었다(REQ-20260910-022). 그래서 끊김은 다시
    시도하고, 끝내 못 붙었을 때만 건너뛴다. 브라우저가 아예 없는 환경은
    위(`chrome_path`)에서 이미 갈렸다.
    """
    last = None
    for _ in range(tries):
        try:
            return measure(scale, list(SKINS), "clockcenter")
        except (ConnectionError, RuntimeError, OSError) as e:
            last = e
            time.sleep(1.5)
        except SystemExit as e:            # 크롬을 못 찾은 자리 — 재시도 무의미
            raise unittest.SkipTest("실측 불가: %s" % e)
    raise unittest.SkipTest("CDP 실측 불가(%d회): %s" % (tries, last))


class TheClockStandsWithTheNumber(unittest.TestCase):
    rows = None

    @classmethod
    def setUpClass(cls):
        if not chrome_path():
            raise unittest.SkipTest("브라우저 없음 — 실측 불가 환경")
        cls.rows = []
        for sc in SCALES:
            cls.rows += _measure_or_retry(sc)

    def test_the_clock_stands_with_the_number(self):
        """그림과 숫자의 잉크 세로 중심이 같은 자리에 있다."""
        self.maxDiff = None
        seen, bad = [], []
        for r in self.rows:
            # 한 스킨에 카드가 열 장 있지만 경과 칸은 전부 같은 줄이라
            # 첫 얼굴 하나면 족하다.
            if r["face"] != "on":
                continue
            where = "%s x%g" % (r["skin"], r["scale"])
            parts = r["parts"]
            if not parts or not parts["clock"] or not parts["num"]:
                bad.append("%s: 경과 칸에서 그림·숫자를 가르지 못했다" % where)
                continue
            seen.append(where)
            dy = _mid(parts["clock"]) - _mid(parts["num"])
            if abs(dy) > TOLERANCE:
                bad.append("%s: 그림이 숫자보다 %+.2fpx 어긋난다" % (where, dy))
        want = ["%s x%g" % (s, sc) for sc in SCALES for s in SKINS]
        self.assertEqual(sorted(seen), sorted(want),
                         "재지 못한 자리가 있다: %s"
                         % sorted(set(want) - set(seen)))
        self.assertEqual(bad, [],
                         "시계 그림과 숫자의 높이가 갈린다: %s" % bad)


if __name__ == "__main__":
    unittest.main()
