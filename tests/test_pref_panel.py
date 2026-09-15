"""개인 선호 — 제 판에 서고, 열고 저장만 해도 값이 안 바뀐다.

두 요청이 한 자리를 고쳤다.

REQ-20260915-054-62x6 (데이터 유실): 줄바꿈이 든 선호 값을 Settings 에서 열고
**아무것도 고치지 않은 채 「선호 저장」만 눌러도** 값이 한 줄로 덮여 썼다. 까닭은
행의 값 칸이 한 줄짜리 `<input>` 이라 브라우저가 값에서 줄바꿈을 지우고, 지워진
값이 저장값과 달라 보이므로 저장 로직이 「고쳤다」로 보아 POST 를 보낸 것이다.
CLI(`s9 user config <이름> pref_<주제>`)는 줄바꿈을 받아 저장하고 훅도 줄바꿈째
프롬프트에 넣으므로, 유실은 오직 화면을 지날 때만 일어났다.

REQ-20260915-052-62x6 (자리): 그 표는 「내 계정」 판의 아홉째 덩이였다 — 세로
2,120px 아래, 레일에는 이름조차 없었다. 「백그라운드 작업」을 같은 판에서 뽑아낸
근거(덩이 여덟·1,400px)를 같은 자로 재면 여기가 더 깊다.

이 시험이 지키는 계약:
  ① 값 칸은 `textarea` 다 — 줄바꿈이 살아남는 유일한 부품이다. `input` 으로
     되돌리면 D1 이 그대로 돌아온다.
  ② 열고 아무것도 안 고치고 저장하면 **보내는 것이 없다**(왕복 계약). 앞뒤 공백만
     다른 값도 「고쳤다」로 보지 않는다.
  ③ 정말 고친 값은 줄바꿈째 그대로 실린다 — ②를 「아무것도 안 보낸다」로 때우는
     우회를 막는다.
  ④ 지운 행은 빈 값으로(서버가 삭제), 새 행은 `pref_` 접두를 달고 나간다.
  ⑤ 레일에 「개인 선호」가 있고 자리는 「디스플레이」 다음·「백그라운드 작업」 앞이다.
  ⑥ 판이 이 값의 두 사실을 말한다 — 모든 대화 첫머리에서 읽힌다 / 저장소에 함께
     담겨 남이 읽을 수 있다.
  ⑦ 「내 계정」 판에는 그 표가 더 남아 있지 않다(같은 값을 고치는 자리가 둘이면 안 된다).
  ⑧ 주제 칸은 mono·uppercase·자간을 벗는다 — 열 머리가 아니라 사람이 지은
     낱말이라 그 조합이 한글을 음절로 흩는다(s9-design 「표」 1).

실행: python3 tests/ pref_panel
"""
import json
import os
import re
import subprocess
import unittest

from websrc import find_node

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")


def _read(*parts):
    with open(os.path.join(WEB, *parts), encoding="utf-8") as f:
        return f.read()


def _fn(src, name):
    """최상위 함수 하나를 중괄호를 세어 떼어 온다."""
    m = re.search(r"^function %s\s*\(" % re.escape(name), src, re.M)
    assert m, "%s 를 찾지 못했다" % name
    i = src.index("{", m.end() - 1)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
    raise AssertionError("%s 가 안 닫힌다" % name)


def run_sets(rows, cfg, new_key="", new_val=""):
    """prefSets 를 원본 그대로 node 로 실행한다 — 로직을 시험에 베끼지 않는다."""
    js = _fn(_read("app", "userform.js"), "prefSets") + "\n" + (
        "console.log(JSON.stringify(prefSets(%s, %s, %s, %s)));"
        % (json.dumps(rows), json.dumps(cfg), json.dumps(new_key), json.dumps(new_val)))
    out = subprocess.run([find_node(), "-e", js], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


TWO_LINES = "첫 줄\n둘째 줄"


class PrefValueSurvivesTheScreen(unittest.TestCase):
    """줄바꿈이 든 값은 화면을 지나도 그대로여야 한다 (REQ-20260915-054-62x6)."""

    @classmethod
    def setUpClass(cls):
        cls.js = _read("app", "userform.js")
        cls.form = _fn(cls.js, "showPrefForm")

    def test_value_cell_is_a_textarea(self):
        """① 값 칸은 textarea — input 은 브라우저가 줄바꿈을 지운다."""
        self.assertRegex(self.form, r"<textarea[^>]*class=\"uf pf-val\"",
                         "개인 선호의 값 칸이 textarea 가 아니다")
        self.assertNotRegex(
            self.form, r"<input[^>]*class=\"uf pf-val\"",
            "값 칸이 한 줄짜리 input 으로 되돌아갔다 — 열고 저장만 해도 값이 뭉개진다")

    def test_no_pref_table_left_in_account_panel(self):
        """⑦ 같은 값을 고치는 자리가 둘이면 어느 쪽이 참인지 화면이 말하지 못한다."""
        acct = _fn(self.js, "showUserForm")
        self.assertNotIn("pf-val", acct, "「내 계정」 판에 개인 선호 표가 남아 있다")
        self.assertNotIn("pf-save", acct, "「내 계정」 판에 선호 저장 버튼이 남아 있다")


@unittest.skipUnless(find_node(), "node 가 없다")
class SavingWithoutEditingSendsNothing(unittest.TestCase):
    """열고 저장만 누른 왕복 — 보내는 것이 없어야 한다."""

    def test_untouched_multiline_row_is_not_sent(self):
        """② D1 의 재현 경로 그대로: 고친 것이 없으면 POST 도 없다."""
        rows = [{"key": "pref_다줄", "value": TWO_LINES, "removed": False}]
        self.assertEqual(run_sets(rows, {"pref_다줄": TWO_LINES}), [])

    def test_surrounding_space_is_not_an_edit(self):
        """② 앞뒤 공백만 다른 값을 「고쳤다」로 보지 않는다."""
        rows = [{"key": "pref_말투", "value": "  짧게  ", "removed": False}]
        self.assertEqual(run_sets(rows, {"pref_말투": "짧게"}), [])

    def test_real_edit_keeps_the_newline(self):
        """③ 정말 고친 값은 줄바꿈째 실린다."""
        rows = [{"key": "pref_다줄", "value": TWO_LINES + "\n셋째 줄", "removed": False}]
        self.assertEqual(run_sets(rows, {"pref_다줄": TWO_LINES}),
                         [["pref_다줄", TWO_LINES + "\n셋째 줄"]])

    def test_removed_row_and_new_row(self):
        """④ 지운 행은 빈 값으로, 새 행은 pref_ 를 달고 나간다."""
        rows = [{"key": "pref_말투", "value": "짧게", "removed": True}]
        self.assertEqual(run_sets(rows, {"pref_말투": "짧게"}, "보고", "결론 먼저"),
                         [["pref_말투", ""], ["pref_보고", "결론 먼저"]])

    def test_new_row_prefix_is_not_doubled(self):
        """④ 사람이 pref_ 까지 쳐도 pref_pref_ 가 되지 않는다."""
        self.assertEqual(run_sets([], {}, "pref_말투", "짧게"),
                         [["pref_말투", "짧게"]])


class PrefHasItsOwnPanel(unittest.TestCase):
    """레일에 제 줄이 있고, 판이 이 값이 무엇을 하는지 말한다 (REQ-20260915-052-62x6)."""

    @classmethod
    def setUpClass(cls):
        cls.settings = _read("app", "settings.js")
        cls.form = _fn(_read("app", "userform.js"), "showPrefForm")

    def test_rail_order(self):
        """⑤ 「디스플레이」 다음·「백그라운드 작업」 앞 — 「나」 묶음 안이다."""
        keys = re.findall(r'^\s*\["([a-z]+)", "', self.settings, re.M)
        for k in ("display", "pref", "worker"):
            self.assertIn(k, keys, "레일에 %s 항목이 없다" % k)
        self.assertEqual(keys.index("display") + 1, keys.index("pref"))
        self.assertEqual(keys.index("pref") + 1, keys.index("worker"))
        self.assertIn('"개인 선호"', self.settings)

    def test_rail_subtitle_doubles_as_state(self):
        """⑤ 부제는 몇 개인지 말한다 — 레일만 봐도 상태가 보인다."""
        self.assertIn("prefNavSub(", self.settings)
        sub = _fn(_read("app", "userform.js"), "prefNavSub")
        self.assertIn("개 —", sub)
        self.assertIn("아직 저장한 값이 없습니다", sub)

    def test_panel_says_what_the_value_does(self):
        """⑥ 모든 대화 첫머리에서 읽힌다 / 저장소에 함께 담긴다."""
        self.assertIn("대화를 시작할 때마다 자동으로 전달되며", self.form)
        self.assertIn("이 저장소를 보는 사람도 함께 읽을 수 있습니다", self.form)

    def test_panel_has_no_internal_identifiers(self):
        """⑥ 화면 문장에 REQ id·내부 용어를 두지 않는다 (문구 규칙 R5)."""
        shown = re.sub(r"/\*.*?\*/", "", self.form, flags=re.S)
        shown = "\n".join(l for l in shown.splitlines()
                          if not l.strip().startswith("//"))
        self.assertNotRegex(shown, r"REQ-\d{8}")
        self.assertNotIn("리드 에이전트", shown)

    def test_row_has_a_delete_handle(self):
        """지우는 손잡이는 이메일 행의 그 부품 그대로다 — 새 부품을 만들지 않는다."""
        self.assertIn("em-rm pf-rm", self.form)
        css = _read("css", "density.css")
        self.assertRegex(css, r"(?m)^\.em-rm\{",
                         ".em-rm 이 자리(.emrow)에 묶여 있으면 선호 행이 못 쓴다")

    def test_topic_cell_drops_mono_uppercase(self):
        """⑧ 첫 칸은 사람이 지은 낱말이다 — mono·uppercase 를 이 표에서만 벗긴다."""
        css = _read("css", "docs.css")
        m = re.search(r"\.pftbl td:first-child\{([^}]*)\}", css)
        self.assertIsNotNone(m, ".pftbl 규칙이 없다")
        body = m.group(1)
        self.assertIn("font-family:inherit", body)
        self.assertIn("text-transform:none", body)
        self.assertIn("word-break:keep-all", body)


if __name__ == "__main__":
    unittest.main()
