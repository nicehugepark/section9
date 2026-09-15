"""문장 안의 명령은 한 곳에서 짓고 한 곳에서 표기한다 (REQ-20260915-023·024-62x6).

주인 지적 2026-09-15: 「화면의 가이드에 명령어 부분이 코드 구간으로 표시가 되면
좋겠다. 문장인지 명령어인지 구분이 되지 않는다.」 안내 문구의 s9 명령이 본문과 같은
흐름으로 흘러 어디까지가 붙여 넣을 글자인지 경계가 없었다.

그 자리를 고치며 **더 깊은 것**이 드러났다: 서버는 여는 길을 `{"kind":"cmd","text":…}`
로 싣는데 화면의 `nGoOf` 는 `cmd`·`command` 두 이름만 읽어, 알림 줄의 명령 버튼이
한 번도 서지 않았다. 오른쪽 묶음에 시각만 남아 문구 끝과 시각 사이가 천 화소가 된
것이 「시간 위치가 이상하다」의 실체였다.

지키는 것 셋. 셋 다 조금만 손대면 조용히 무너지고, 무너져도 화면은 멀쩡해 보인다.

  ① **표기를 손으로 감싸지 않는다.** 호출부가 제각기 `<code>` 를 두르면 두른 자리와
     안 두른 자리가 갈린다 — 글자는 `s9cmd`, 표기는 `s9code`(마크업이 못 드는
     자리는 `s9cmdq`) 한 곳에서 난다.
  ② **화면이 서버가 쓰는 이름을 읽는다.** 서버가 싣는 `kind:"cmd"` 의 `text` 를
     화면이 명령으로 읽지 않으면 버튼은 영영 서지 않는다.
  ③ **얼굴은 한 규칙이다.** `.cmd` 를 칠하는 자리는 control.css 한 곳이고, 색면이
     아니라 경계로 가른다(계기판 언어 — 색면 하이라이트는 이 제품의 금지 목록이다).

화소는 단위 시험이 볼 수 없다 — 열 맞춤·배율·좁은 폭은 사람의 캡처 검증이 맡는다.

실행: python3 tests/ cmd_code
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WEB = os.path.join(REPO, "web")
APP = os.path.join(WEB, "app")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def strip_comments(src):
    """코드만 본다 — 주석 안의 `<code>`·`kind` 는 설명이지 표기도 계약도 아니다."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


class TheCommandIsWrittenInOnePlace(unittest.TestCase):
    """① 표기를 손으로 감싸지 않는다."""

    def setUp(self):
        self.files = {n: strip_comments(read(os.path.join(APP, n)))
                      for n in sorted(os.listdir(APP)) if n.endswith(".js")}
        self.shell = strip_comments(read(os.path.join(WEB, "index.html")))

    def test_the_makers_stand_together(self):
        state = self.files["state.js"]
        for name in ("const s9cmd =", "const s9code =", "const s9cmdq ="):
            self.assertIn(name, state, f"짓는 자리 「{name}」가 state.js 에 없다")
        self.assertIn("esc(s9cmd(", state, "s9code 가 이스케이프를 제 안에서 하지 않는다")

    def test_no_call_site_wraps_it_by_hand(self):
        """`<code>…s9cmd…</code>` 를 손으로 두른 자리가 없다 — 두르는 것은 s9code 다."""
        bad = []
        for name, src in self.files.items():
            if name == "state.js":
                continue
            for m in re.finditer(r"<code[^>]*>[^<]*s9cmd\(", src):
                bad.append(f"{name}:{src[:m.start()].count(chr(10)) + 1}")
        self.assertEqual(bad, [], "명령을 손으로 <code> 로 둘렀다 — s9code 를 써라: "
                                  + ", ".join(bad))

    def test_the_literal_command_is_not_typed_into_the_screen(self):
        """화면 문구에 `s9 …` 를 글자로 박지 않는다 — Windows 꼴이 안 나온다.

        예외 하나: 「s9 digest / ls / search …」처럼 **이름을 늘어놓은 목록**은
        붙여 넣을 명령이 아니라 이 도구가 무엇을 하는지의 안내다(Settings 의
        저장소 판). 가르는 표는 `/` 로 이어진 목록인가이다."""
        bad = []
        for name, src in self.files.items():
            for m in re.finditer(r"<code[^>]*>\s*s9 ([^<]*)", src):
                if " / " in m.group(1):
                    continue
                bad.append(f"{name}:{src[:m.start()].count(chr(10)) + 1}")
        self.assertEqual(bad, [], "명령을 글자로 박았다 — s9code 를 지나야 "
                                  "이 컴퓨터의 꼴이 된다: " + ", ".join(bad))


class TheScreenReadsWhatTheServerSends(unittest.TestCase):
    """② 화면이 서버가 쓰는 이름을 읽는다 (REQ-20260915-024-62x6 의 뿌리)."""

    def setUp(self):
        self.js = strip_comments(read(os.path.join(APP, "notice.js")))
        self.py = read(os.path.join(REPO, "bin", "s9.py"))

    def test_the_server_still_sends_that_shape(self):
        """서버가 이 꼴로 싣는다 — 이것이 바뀌면 아래 계약도 함께 고쳐야 한다."""
        self.assertRegex(self.py, r'\{"kind":\s*"cmd",\s*"text"',
                         '서버가 여는 길을 {"kind":"cmd","text":…} 로 싣지 않는다')

    def test_the_screen_reads_the_kind_and_the_text(self):
        i = self.js.index("function nGoOf(")
        body = self.js[i:i + 1200]
        self.assertIn("kind", body, "화면이 kind 를 안 읽는다 — 명령 버튼이 서지 않는다")
        self.assertRegex(body, r'kind\s*===\s*["\']cmd["\']',
                         'kind 가 "cmd" 인 줄을 명령으로 읽지 않는다')
        self.assertRegex(body, r'go\.text',
                         "kind:cmd 의 text 를 명령으로 읽지 않는다")

    def test_the_command_text_does_not_leak_into_the_handle_label(self):
        """같은 글자가 손잡이 이름으로 다시 나오면 버튼에 명령이 두 번 적힌다."""
        i = self.js.index("function nGoOf(")
        body = self.js[i:i + 1200]
        m = re.search(r"const label\s*=.*", body)
        self.assertIsNotNone(m, "손잡이 이름을 짓는 줄이 없다")
        self.assertIn("kind", m.group(0),
                      "kind:cmd 일 때 text 를 손잡이 이름으로도 집는다")


class TheFaceIsOneRule(unittest.TestCase):
    """③ 얼굴은 한 규칙 — 색면이 아니라 경계."""

    def setUp(self):
        self.css = read(os.path.join(WEB, "css", "control.css"))
        self.skins = read(os.path.join(WEB, "css", "skins.css"))

    def test_the_rule_lives_in_one_file(self):
        self.assertIsNotNone(re.search(r"^\.cmd\{", self.css, flags=re.M),
                             "control.css 에 .cmd 규칙이 없다")
        rules = strip_comments(self.skins)
        self.assertNotIn(".cmd", rules,
                         "스킨이 .cmd 를 다시 칠한다 — 열 스킨으로 번진다")

    def test_it_gives_a_boundary_not_a_colour_field(self):
        rule = re.search(r"^\.cmd\{[^}]*\}", self.css, flags=re.M).group(0)
        self.assertIn("border", rule, ".cmd 에 경계가 없다 — 문장과 안 갈린다")
        self.assertNotIn("background", rule,
                         ".cmd 를 색면으로 칠했다 — 이 제품의 금지 목록이다")

    def test_it_does_not_fix_the_type_size(self):
        """자리마다 정한 글자 크기가 이긴다 — 이 규칙이 주는 것은 경계다."""
        rule = re.search(r"^\.cmd\{[^}]*\}", self.css, flags=re.M).group(0)
        self.assertRegex(rule, r"font-size:\s*\.?\d*\.?\d+em",
                         ".cmd 의 글자 크기가 px 로 못박혀 자리마다의 크기를 덮는다")


if __name__ == "__main__":
    unittest.main()
