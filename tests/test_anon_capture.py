"""?anon — 캡처에서 사람을 지우는 스위치 (REQ-20260918-013-62x6).

주인 판정 2026-09-18: 가이드에 실을 화면을 다시 찍는데 머리글에 계정 메일
(`claude01.pfe@…`)과 컴퓨터 이름(`DESKTOP-TEHV1KR`)이 그대로 선다. 가이드는
GitHub 릴리스로 나가는 공개 문서다 — 「가려서 찍는다」로 정했다.

가리는 자리는 **그림이 아니라 화면이다.** 찍은 PNG 의 화소를 덧칠하면 글자 수가
시각마다 달라져(사용량 칩의 퍼센트가 계속 바뀐다) 판을 낼 때마다 자를 다시
맞춰야 한다. 화면에서 지우고 찍으면 다음 판의 재촬영도 같은 한 줄이다.

가리는 것은 **메일과 컴퓨터 이름 둘뿐**이다. 사람 이름은 저장소 주소에 이미
공개돼 있어 그대로 둔다 — 주인이 고른 것이 그 둘이다.

실행: python3 tests/ anon_capture
"""
import importlib.util
import json
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FMT_SRC = open(os.path.join(ROOT, "web", "app", "format.js"), encoding="utf-8").read()
USAGE_SRC = open(os.path.join(ROOT, "web", "app", "usage.js"), encoding="utf-8").read()
NOTICE_SRC = open(os.path.join(ROOT, "web", "app", "notice.js"), encoding="utf-8").read()
MASK = "█" * 8


def _keeps():
    """node 찾기와 함수 잘라내기는 이미 있는 하네스를 쓴다 — 두 벌을 만들지 않는다."""
    p = os.path.join(HERE, "test_usage_chip_keeps.py")
    spec = importlib.util.spec_from_file_location("usage_chip_keeps_anon", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


K = _keeps()
NODE, STUBS, _fn = K.NODE, K.STUBS, K._fn


from webasset import anon_helper as helper_src   # 조각은 한 곳에서만 만든다


def run_js(body, search):
    """location.search 를 주고 조각을 돌린다. 마지막 줄의 출력을 돌려준다."""
    # STUBS 가 이미 `?anon` 조각을 들고 있다 — 두 번 실으면 const 재선언이다.
    src = (f'const location = {{search: {json.dumps(search)}}};\n'
           + STUBS + "\n" + body)
    r = subprocess.run([NODE, "-e", src], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError(r.stderr.strip()[:800])
    return r.stdout.strip()


@unittest.skipUnless(NODE, "node 가 없다")
class TheSwitchHidesOnlyTheTwo(unittest.TestCase):

    def chip(self, search):
        """사용량 칩의 계정 자리를 그린다 (usage.js renderUsageChip 의 그 줄)."""
        body = (_fn(USAGE_SRC, "renderUsageChip")
                + '\nlet usageLast = null;\n'
                + 'const el = mkEl();\n'
                + 'renderUsageChip(el, {email: "someone@example.com", limits: ['
                + '{scope:"session",percent:23},{scope:"weekly_all",percent:80}], ok: true});\n'
                + 'console.log(el.innerHTML);')
        return run_js(body, search)

    def who(self, search, machine="DESKTOP-TEHV1KR", user="nicehugepark"):
        """#whoami 의 신원 줄 (notice.js renderWhoami 가 세우는 innerHTML)."""
        body = ('const $ = () => el;\n'
                'const el = mkEl();\n'
                'const supplyLost = () => false;\n'
                'const asUser = "";\n'
                'const s9cmdq = () => "";\n'
                f'const window = {{__whoami: {{user: {json.dumps(user)}, '
                f'machine: {json.dumps(machine)}, os: "WSL", root: "/home/sjpark1/section9"}}}};\n'
                + _fn(NOTICE_SRC, "renderWhoami")
                + '\nrenderWhoami();\nconsole.log(el.innerHTML);')
        return run_js(body, search)

    def test_a1_without_the_switch_nothing_changes(self):
        """정상 ① — ?anon 이 없으면 지금과 한 글자도 다르지 않다."""
        chip = self.chip("")
        self.assertIn("someone@example.com", chip)
        self.assertNotIn(MASK, chip)
        who = self.who("")
        self.assertIn("DESKTOP-TEHV1KR", who)
        self.assertNotIn(MASK, who)

    def test_a2_the_account_mail_is_hidden(self):
        """정상 ② — ?anon 이면 계정 메일 자리가 가려진다."""
        chip = self.chip("?anon")
        self.assertNotIn("someone@example.com", chip)
        self.assertNotIn("example.com", chip)
        self.assertIn(MASK, chip)

    def test_a3_the_machine_name_is_hidden(self):
        """정상 ③ — ?anon 이면 컴퓨터 이름이 가려진다."""
        who = self.who("?anon")
        self.assertNotIn("DESKTOP-TEHV1KR", who)
        self.assertIn(MASK, who)

    def test_a4_the_person_stays(self):
        """경계 ④ — 사람 이름은 ?anon 에서도 그대로 남는다 (주인이 고른 것이 둘뿐이다)."""
        self.assertIn("nicehugepark", self.who("?anon"))

    def test_a5_the_home_path_does_not_leak_in_the_tooltip(self):
        """경계 ④' — 계정 폴더 이름이 든 경로(title)도 함께 지운다.

        화면에 안 보이지만 같은 것을 가리키는 값이다 — 하나만 지우면 반쪽이다."""
        self.assertNotIn("sjpark1", self.who("?anon"))
        self.assertIn("sjpark1", self.who(""), "?anon 이 없을 때는 종전 그대로여야 한다")

    def test_a6_the_mask_does_not_reveal_the_length(self):
        """경계 ⑤ — 가린 글자는 원래 길이를 드러내지 않는다. 길이가 곧 단서다."""
        short = self.who("?anon", machine="A")
        long = self.who("?anon", machine="A-VERY-LONG-COMPUTER-NAME-1234567890")
        m = re.compile(re.escape(MASK[0]) + "+")
        self.assertEqual([x.group(0) for x in m.finditer(short)],
                         [x.group(0) for x in m.finditer(long)])

    def test_a7_empty_values_do_not_blow_up(self):
        """경계 ⑥ — 값이 비어도 터지지 않는다."""
        self.assertIn(MASK, self.who("?anon", machine=""))
        self.assertIn(MASK, self.who("?anon", machine=None))

    def test_a8_it_rides_with_the_other_handles(self):
        """회귀 ⑦ — ?anon&skin=calm 처럼 다른 손잡이와 함께여도 듣는다."""
        for s in ("?anon&skin=calm", "?skin=calm&anon", "?noscroll&anon&skin=calm"):
            self.assertIn(MASK, self.chip(s), s)
        # 낱말 경계 — ?anonymous 는 이 스위치가 아니다
        self.assertNotIn(MASK, self.chip("?anonymous=1"))


class TheHandleIsWiredWhereItIsDrawn(unittest.TestCase):
    """node 없이도 서는 검사 — 가리는 자리가 코드에 남아 있는가."""

    def test_b1_both_drawing_sites_go_through_anonize(self):
        self.assertIn('esc(anonize(d.email, "?"))', USAGE_SRC,
                      "사용량 칩의 계정 자리가 anonize 를 지나지 않는다")
        self.assertIn("esc(anonize(w.machine))", NOTICE_SRC,
                      "#whoami 의 컴퓨터 이름이 anonize 를 지나지 않는다")

    def test_b2_the_helper_lives_before_its_callers(self):
        """format.js 는 notice.js·usage.js 보다 먼저 실린다 — 그 순서가 깨지면 터진다."""
        idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
        pos = {n: idx.index(f'<script src="app/{n}.js">') for n in ("format", "notice", "usage")}
        self.assertLess(pos["format"], pos["notice"])
        self.assertLess(pos["format"], pos["usage"])


if __name__ == "__main__":
    unittest.main()
