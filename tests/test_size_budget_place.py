"""크기(size)는 카드가 아니라 문서에서 읽는다 (REQ-20260909-074).

주인 지적 2026-09-09: 「크기의 기준을 모르겠고, 카드에 보여도 인사이트가 없으며
자리만 차지한다.」 소집한 셋의 판정이 같았다 — 이 값은 **리드의 처리 예산**
(규약 18조)이라 보드에서 내리는 판단 셋(다음에 무엇을 집을까 · 무엇이 막혔나 ·
무엇을 승인·반려할까) 중 무엇도 바꾸지 않는다. 게다가 카드에서는 축 이름 없는
값 한 글자(`S`)라 옆의 `보통`(우선순위)과 같은 척도로 읽혔고, S 가 최상급으로
오독됐다.

그래서 폐지가 아니라 **자리를 옮겼다**: 카드에서 내리고, 문서 메타 표의 `size`
행에서 값에 뜻을 붙인다. 라벨은 `size` 글자 그대로다 — 프론트매터 키이자 사람이
`--size` 로 직접 치는 이름이라 화면의 글자도 같아야 한다(규약 2조 ⑤).

이 파일이 고정하는 계약 넷:
  1. 뜻 문구는 한 곳(const.js `sizeText`)에서만 나온다 — 화면 둘이 각자 글자를
     가지면 한쪽만 고쳐진다.
  2. 값이 없어도 행은 선다 — 18조가 「없으면 S 로 본다」고 정했으므로 빈 칸은
     모르는 것이 아니라 아는 사실이다.
  3. 요청이 아닌 문서에는 이 축이 없다 — 행도 서지 않는다(우선순위와 같다).
  4. 카드는 이 값을 그리지 않는다 — 마크업도 그 클래스 규칙도 화면 한 장에 없다.

문구를 글자로 박아 재지 않는다: 실제 함수와 실제 표 항목을 node 로 **실행해**
나온 결과를 본다. 「예산」이라는 낱말만은 글자로 고정한다 — 그 낱말이 없으면
15분이 마감 약속으로 읽히기 때문이다(ux-writer 판정의 핵심).

실행: python3 tests/ size_budget_place
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest

from webasset import index_path

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web", "app")
CSS = os.path.join(os.path.dirname(HERE), "web", "css")


def find_node():
    """node 를 찾는다 — 없으면 이 시험은 건너뛴다.

    다른 시험 모듈에서 가져오지 않는다: 시험 파일은 표준 라이브러리 밖을
    import 하지 않는다(tests/test_stdlib_only.py)."""
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node",
                "/mnt/c/Temp/s9-webkit/node-*/node.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def _src(name):
    with open(os.path.join(WEB, name), encoding="utf-8") as f:
        return f.read()


def _size_dict():
    """const.js 의 사전과 sizeText() 를 그대로 떼어 온다."""
    src = _src("const.js")
    parts = []
    for pat in (r"^const SIZE_MEANING = \{.*?^\};$",
                r"^const SIZE_UNSET = .*?;$",
                r"^function sizeText\(v\)\{.*?^\}$"):
        m = re.search(pat, src, re.S | re.M)
        assert m, "const.js 에서 크기 사전 조각을 찾지 못했다: %s" % pat
        parts.append(m.group(0))
    return "\n".join(parts)


def _size_row():
    """docs.js 메타 표의 `["size", …]` 항목 하나."""
    src = _src("docs.js")
    m = re.search(r'^\s*\["size", (.*?)\],$', src, re.M)
    assert m, "docs.js 메타 표에서 size 행을 찾지 못했다"
    return m.group(1)


def _node(js):
    out = subprocess.run([find_node(), "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def size_text(v):
    js = ("%s\nconsole.log(sizeText(%s));"
          % (_size_dict(), json.dumps(v)))
    return _node(js)


def size_row(meta):
    """그 문서에 대해 메타 표의 size 칸이 무엇을 그리는가. 빈 문자열이면 행 없음."""
    js = ("const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');\n"
          "%s\nconst m = %s;\nconsole.log(String(%s ?? ''));"
          % (_size_dict(), json.dumps(meta), _size_row()))
    return _node(js)


@unittest.skipUnless(find_node(), "node 없음 — 화면 조각을 실행할 수 없다")
class TheValueTeachesItsOwnScale(unittest.TestCase):
    """① 값이 제 뜻을 데리고 선다 — 우선순위의 `보통 50/99` 와 같은 층."""

    def test_each_value_says_who_does_it_and_how_long(self):
        """정상 — 셋 다 값·주체·예산을 한 줄에서 말한다."""
        for v, must in (("S", ("S", "직접", "15분")),
                        ("M", ("M", "위임", "1시간")),
                        ("L", ("L", "파생"))):
            got = size_text(v)
            for word in must:
                self.assertIn(word, got, "%s 의 뜻에 「%s」가 없다: %s" % (v, word, got))

    def test_the_word_budget_is_not_optional(self):
        """실패 자리 — 「예산」이 빠지면 15분이 마감 약속으로 읽힌다."""
        for v in ("S", "M"):
            self.assertIn("예산", size_text(v),
                          "%s 의 시간이 예산이 아니라 마감으로 읽힌다" % v)

    def test_unset_says_it_is_read_as_S(self):
        """경계 — 값이 없으면 「S 로 봄 (미지정)」. 규약 18조가 그렇게 정했다."""
        got = size_text("")
        self.assertIn("S", got)
        self.assertIn("미지정", got, "값이 없는 것과 S 인 것을 가르지 않는다: %s" % got)

    def test_unknown_value_is_shown_as_it_is(self):
        """경계 — 사전에 없는 값도 삼키지 않는다(사람이 친 글자를 그대로 보여준다)."""
        self.assertEqual(size_text("XL"), "XL")

    def test_lowercase_is_the_same_value(self):
        """경계 — `--size s` 로 쳐도 같은 뜻이다."""
        self.assertEqual(size_text("s"), size_text("S"))


@unittest.skipUnless(find_node(), "node 없음 — 화면 조각을 실행할 수 없다")
class TheDocumentIsWhereItIsRead(unittest.TestCase):
    """② 읽는 자리는 문서 메타 표 하나다."""

    def test_request_row_carries_the_meaning(self):
        """정상 — 요청 문서의 size 행은 뜻이 붙은 값을 그린다."""
        got = size_row({"type": "request", "size": "M"})
        self.assertEqual(got, size_text("M"),
                         "표가 사전과 다른 글자를 그린다 — 문구가 두 벌이 됐다")

    def test_empty_size_still_stands(self):
        """경계 — 값이 비어도 행이 사라지지 않는다(빈 칸도 아는 사실이다)."""
        got = size_row({"type": "request"})
        self.assertTrue(got, "값이 없다고 행째 사라졌다 — 축이 있는지조차 안 보인다")
        self.assertIn("미지정", got)

    def test_non_request_has_no_such_axis(self):
        """경계 — knowledge·session 에는 이 축이 없다. 없는 축을 세우지 않는다."""
        for t in ("knowledge", "session", "question"):
            self.assertFalse(size_row({"type": t, "size": "S"}),
                             "%s 문서에 size 행이 섰다" % t)


class TheCardDoesNotDrawIt(unittest.TestCase):
    """③ 카드는 이 값을 그리지 않는다 — 마크업도, 그 클래스 규칙도 없다."""

    @classmethod
    def setUpClass(cls):
        with open(index_path(), encoding="utf-8") as f:
            cls.html = f.read()

    def test_no_size_chip_markup_anywhere_on_the_screen(self):
        """회귀 — 조각이 어디로 옮겨가도 화면 한 장에 그 마크업이 없어야 한다."""
        self.assertNotIn('class="size"', self.html,
                         "카드(또는 다른 화면)가 크기 칩을 다시 그린다")

    def test_no_dead_rule_for_that_chip(self):
        """회귀 — 규칙만 남으면 다음 사람이 「그 칩이 있다」고 읽는다."""
        hits = []
        for name in sorted(os.listdir(CSS)):
            if not name.endswith(".css"):
                continue
            with open(os.path.join(CSS, name), encoding="utf-8") as f:
                body = f.read()
            # 주석 속 언급(`.size·.tag 와 같은 급`)은 규칙이 아니다 — 선택자로
            # 서 있는 것(뒤에 `,` 또는 `{` 이 오는 것)만 센다.
            body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
            if re.search(r"(?:^|[\s,])\.size\s*[,{]", body, re.M):
                hits.append(name)
        self.assertEqual(hits, [], "카드용 .size 규칙이 남아 있다: %s" % hits)

    def test_the_card_no_longer_reads_the_value(self):
        """회귀 — 카드를 짓는 코드가 이 값을 읽지 않는다."""
        card = _src("card.js")
        card = re.sub(r"/\*.*?\*/", "", card, flags=re.S)
        self.assertNotRegex(card, r"\br\.size\b",
                            "카드가 다시 크기 값을 읽는다")


if __name__ == "__main__":
    unittest.main()
