"""skin 이 density 축을 삼키지 않는가 (REQ-20260830-032-62x6).

사용자: "너무 카드 크기가 뚱뚱해져서 한 화면에 많은 카드를 보여주기 어려워지는
것 같다." 원인을 재 보니 버튼이 아니었다 — **compact 를 켜도 calm 스킨에서는
카드가 1px 도 줄지 않았다.**

    skin=calm  density=normal   멈춤 카드 197.1px
    skin=calm  density=compact  멈춤 카드 197.1px   ← 손잡이가 죽어 있다
    skin=ledger density=compact 멈춤 카드 134.1px

캐스케이드 사고다. 두 선언의 특이도가 같은데(둘 다 0,2,0) index.html 의 css
순서가 density → calm 이라 뒤에 실린 skin 이 이긴다:

    density.css:9  [data-density="compact"] .card{padding:5px 10px}
    calm.css:176   [data-skin="calm"]       .card{padding:14px 16px 13px}   ← 이긴다

설계 문서(s9-design)가 세운 규칙은 "밀도 변형은 skin 이 아니라 density 축"이다.
그 규칙이 지켜지려면 **skin 은 자기가 덮은 density 선언에 대해 짝을 가져야
한다** — `[data-skin="X"][data-density="compact"]`(특이도 0,3,0)는 순서와
무관하게 이긴다.

이 시험이 그 계약을 지킨다: density.css 가 compact 에서 어떤 선택자의 어떤
속성을 줄여 놓았는데 어떤 skin 이 같은 선택자의 같은 속성을 덮었다면, 그 skin
안에 compact 짝이 있어야 한다.

아직 짝이 없는 skin 은 KNOWN 에 적어 둔다 — **줄어들기만 하는 목록**이다.
새 skin 이나 새 override 가 여기에 붙으면 시험이 빨개져서, 다음 사람이 같은
사고를 반복하기 전에 알게 된다.

실행: python3 tests/ calm_density
"""
import os
import re
import unittest
from webasset import part

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
CSS = os.path.join(WEB, "css")

# 아직 density 짝이 없는 자리 (skin, 선택자). **줄어들기만 한다** —
# 새로 늘리려면 그 skin 을 고치는 편이 빠르다.
KNOWN = set()   # 비었다 — **어떤 skin 도 density 를 삼키지 않는다** (REQ-20260830-034)

RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
SKIN_RE = re.compile(r'^\[data-skin="(\w+)"\]\s+(.*)$')
COMPACT = '[data-density="compact"]'


def rules(text):
    """(선택자 목록, 선언한 속성 이름 집합) 들. 주석은 걷어낸다."""
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    out = []
    for m in RULE_RE.finditer(text):
        sels = [s.strip() for s in m.group(1).split(",") if s.strip()]
        props = {p.split(":")[0].strip() for p in m.group(2).split(";") if ":" in p}
        out.append((sels, props))
    return out


def compact_contract():
    """density.css 가 compact 에서 줄여 놓은 것 — {선택자: {속성…}}."""
    want = {}
    for sels, props in rules(part("css/density.css")):
        for s in sels:
            if s.startswith(COMPACT):
                want.setdefault(s[len(COMPACT):].strip(), set()).update(props)
    return want


class CalmDensityTest(unittest.TestCase):
    def test_skin_does_not_swallow_density(self):
        want = compact_contract()
        self.assertIn(".card", want, "density.css 가 카드 밀도를 더는 말하지 않는다")
        missing = {}
        for name in sorted(os.listdir(CSS)):
            if not name.endswith(".css") or name == "density.css":
                continue
            text = part("css/" + name)
            for sels, props in rules(text):
                for s in sels:
                    m = SKIN_RE.match(s)
                    if not m:
                        continue
                    skin, base = m.group(1), m.group(2).strip()
                    clash = props & want.get(base, set())
                    if not clash:
                        continue
                    pair = re.compile(
                        r'\[data-skin="%s"\]\[data-density="compact"\]\s+%s\s*[,{]'
                        % (skin, re.escape(base)))
                    if not pair.search(text):
                        missing.setdefault((skin, base), set()).update(clash)
        new = {k: sorted(v) for k, v in missing.items() if k not in KNOWN}
        self.assertEqual(new, {},
                         "이 skin 들이 density=compact 를 덮고 짝을 안 뒀다 — "
                         "[data-skin=…][data-density=\"compact\"] 로 compact 값을 세워라")
        fixed = sorted(KNOWN - set(missing))
        self.assertEqual(fixed, [],
                         "이미 고쳐진 자리가 KNOWN 에 남아 있다 — 목록에서 지워라")

    def test_calm_card_has_compact_pair(self):
        """calm 카드는 특히 짝이 있어야 한다 — 사용자가 신고한 그 화면이다."""
        text = part("css/calm.css")
        for base in (".card", ".card .t", ".card .m", ".acts button"):
            self.assertRegex(
                text,
                r'\[data-skin="calm"\]\[data-density="compact"\][^{,]*%s\s*[,{]'
                % re.escape(base),
                "calm 의 %s 에 compact 짝이 없다" % base)


if __name__ == "__main__":
    unittest.main()
