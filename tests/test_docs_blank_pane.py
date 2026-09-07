"""빈 오른쪽 판의 말은 고른 것이 있는지로 갈린다 (REQ-20260907-073-62x6).

사용자가 본 것: 목록의 한 줄은 고른 표시(닫기 손잡이·굵은 제목)를 달고 있는데
오른쪽 판은 「← 왼쪽 목록에서 문서를 골라 주세요」였다. 화면의 두 자리가 서로
다른 말을 한 것이다 — 고른 것이 있다는 왼쪽과, 아무것도 안 골랐다는 오른쪽.

판을 새로 세울 때(탭을 옮겼다 돌아올 때) 오른쪽은 빈 판으로 서고 `loadDoc` 이
그 뒤에 채운다. 그 사이가 길어지면(응답이 늦거나, 늦은 응답으로 판정돼 조용히
돌아가면) 그 한 순간이 화면에 남는다. 그래서 빈 판의 말을 갈랐다.

판정은 `docs.js` 의 `docBlankHTML` 을 떼어 node 로 실행한다 — 소스 글자를
대조하지 않는다.

실행: python3 tests/ docs_blank_pane
"""
import glob
import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web", "app")


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


def blank_src():
    src = open(os.path.join(WEB, "docs.js"), encoding="utf-8").read()
    out = []
    for name in ("docPickHTML", "docLoadingHTML", "docBlankHTML"):
        m = re.search(r"^const %s = \(\) =>.*?;$" % name, src, re.S | re.M)
        assert m, "docs.js 에서 %s 를 찾지 못했다" % name
        out.append(m.group(0))
    return "\n".join(out)


def blank(selected):
    js = ("let selectedDoc = %s;\n%s\nconsole.log(docBlankHTML());"
          % ("'REQ-20260907-073-62x6'" if selected else "null", blank_src()))
    out = subprocess.run([find_node(), "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@unittest.skipUnless(find_node(), "node 없음 — 화면 조각을 실행할 수 없다")
class TheBlankPaneSaysWhichStateItIsIn(unittest.TestCase):

    def test_nothing_selected_asks_you_to_pick(self):
        """정상 — 아무것도 안 골랐으면 고르라고 한다(종전 그대로)."""
        self.assertIn("골라 주세요", blank(False))

    def test_something_selected_never_says_pick_one(self):
        """실패 자리 — 고른 것이 있는데 「골라 주세요」가 서면 왼쪽과 어긋난다."""
        self.assertNotIn("골라 주세요", blank(True),
                         "목록은 고른 줄을 표시하는데 오른쪽은 안 골랐다고 말한다")

    def test_something_selected_says_it_is_loading(self):
        """정상 — 고른 것이 있으면 그것을 불러오는 중이라고 말한다."""
        self.assertIn("불러오는 중", blank(True))

    def test_the_two_states_are_different_words(self):
        """경계 — 두 자리가 같은 말이면 가른 뜻이 없다."""
        self.assertNotEqual(blank(True), blank(False))


if __name__ == "__main__":
    unittest.main()
