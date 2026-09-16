"""뒤로가기는 판만 무른다 (REQ-20260915-012-2n7g).

맥 Safari 26.4 실측 2026-09-15: 「보관함 · 휴지통」 판을 연 뒤 뒤로가기를 누르면
판이 닫히면서 **보던 화면에서도 함께 나갔다**. 판이 이력에 아무 항목도 세우지
않아서, 뒤로가기가 무를 것이라고는 직전 화면밖에 없었던 것이다.

여기서 잠그는 계약은 셋이다.
  ① 판을 열면 이력 항목 하나가 선다 — 주소는 그대로다.
  ② 그 뒤로가기는 판만 닫는다 — 되물리지 않는다(되물리면 앞 화면까지 나간다).
  ③ 사람이 닫으면(ESC·닫기·판 밖) 그 항목을 되물린다 — 안 물리면 뒤로가기 한
     번이 아무 일도 하지 않는 빈 항목으로 남는다.

글자로 재지 않는다 — `tidyHistOpen` · `tidyHistDone` · `tidyClose` 와 뒤로가기를
받는 그 줄을 tidy.js 에서 떼어 node 로 **실행하고**, 가짜 이력에 몇 번 쌓이고
몇 번 되물렸는지를 읽는다.

실행: python3 tests/ tidy_back
"""
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TIDY = os.path.join(HERE, "..", "web", "app", "tidy.js")


def find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


NODE = find_node()
# 소스는 **한 번만** 읽는다 — 이 파일은 동작을 재는 시험이고, 읽은 본문은
# 떼어 낼 함수를 찾는 데 쓴다 (tests/test_test_budget.py 의 라쳇).
with open(TIDY, encoding="utf-8") as _f:
    SRC = _f.read()


def fn(name):
    """tidy.js 에서 함수 하나를 통째로 떼어 낸다 (async 도 같은 자리다)."""
    m = re.search(r"^(?:async )?function " + name + r"\([^)]*\)\{[\s\S]*?\n\}",
                  SRC, re.M)
    assert m, f"{name} 을 못 찾았다"
    return m.group(0)


# 뒤로가기를 받는 줄도 소스에서 그대로 가져온다 — 여기서 다시 적으면 규칙이
# 두 벌이 되고, 그중 하나만 고쳐지는 날이 온다.
POPLINE = re.search(r'^window\.addEventListener\("popstate",.*\);$', SRC, re.M)

FAKE = """
/* 가짜 이력 — 항목 하나가 곧 주소 하나다. 실제 브라우저는 뒤로가기의 popstate 를
   나중에 쏘지만, 여기서는 그 자리에서 쏜다(더 엄한 쪽이다: 되부름이 나면 잡힌다). */
const entries = ["#board"];
let at = 0, pushes = 0, backs = 0, onPop = null;
function goBack(){ if (at > 0) at--; if (onPop) onPop(); }
globalThis.location = {get href(){ return entries[at]; }};
globalThis.history = {
  pushState(st, _t, url){ entries.length = at + 1; entries.push(url);
                          at = entries.length - 1; pushes++; },
  back(){ backs++; goBack(); }};
globalThis.window = {addEventListener(k, f){ if (k === "popstate") onPop = f; }};
/* 판의 나머지는 이 시험의 관심 밖이다 — 여는 손잡이 표시와 목록 손질. */
let tidyType = "", tidyBox = null;
function tidyOpenersExpanded(){}
function tidyDecorate(){}
function openPanel(){ tidyBox = {remove(){ }}; tidyHistOpen(); }
"""


class BackUndoesOnlyThePanel(unittest.TestCase):

    def run_js(self, script):
        src = "\n".join([fn("tidyHistOpen"), fn("tidyHistDone"), fn("tidyClose"),
                         "let tidyHist = false;", FAKE, POPLINE.group(0), script])
        d = tempfile.mkdtemp(prefix="s9tidyback-")
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        f = os.path.join(d, "run.js")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(src)
        r = subprocess.run([NODE, f], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_the_popline_is_there(self):
        """뒤로가기를 받는 줄이 있다 — 없으면 아래 시험들이 잴 것이 없다."""
        self.assertIsNotNone(POPLINE, "popstate 를 받는 줄이 tidy.js 에 없다")
        self.assertIn("tidyClose(\"pop\")", POPLINE.group(0),
                      "뒤로가기가 판을 닫지 않는다")
        self.assertIn("if (tidyBox)", POPLINE.group(0),
                      "판이 없을 때도 이 줄이 일한다 — 남의 뒤로가기를 가로챈다")

    @unittest.skipIf(NODE is None, "node 가 없다")
    def test_opening_stands_one_entry_and_keeps_the_address(self):
        """① 판을 열면 이력 항목 하나, 주소는 그대로. ④ 다시 열어도 하나."""
        got = self.run_js("""
          openPanel();
          const first = {pushes, href: location.href};
          tidyHistOpen();   // 종류·탭을 바꿔 다시 여는 길
          console.log(JSON.stringify({first, pushes}));
        """)
        self.assertEqual(got["first"]["pushes"], 1, "이력 항목이 안 섰다")
        self.assertEqual(got["first"]["href"], "#board", "주소가 바뀌었다")
        self.assertEqual(got["pushes"], 1, "다시 여는 길에서 항목이 또 섰다")

    @unittest.skipIf(NODE is None, "node 가 없다")
    def test_back_closes_the_panel_and_stays_on_the_screen(self):
        """② 뒤로가기는 판만 닫는다 — 되물리지 않고 주소도 그대로."""
        got = self.run_js("""
          openPanel();
          goBack();
          console.log(JSON.stringify({open: !!tidyBox, backs, at,
                                      href: location.href}));
        """)
        self.assertFalse(got["open"], "뒤로가기가 판을 안 닫았다")
        self.assertEqual(got["backs"], 0,
                         "이미 쓰인 항목을 또 되물렸다 — 앞 화면까지 나간다")
        self.assertEqual(got["at"], 0, "이력 자리가 안 돌아왔다")
        self.assertEqual(got["href"], "#board", "화면이 함께 바뀌었다")

    @unittest.skipIf(NODE is None, "node 가 없다")
    def test_closing_by_hand_leaves_no_empty_entry(self):
        """③ ESC·닫기로 닫으면 그 항목을 되물린다 — 되부름 없이 한 번만."""
        got = self.run_js("""
          openPanel();
          tidyClose();            // ESC · 닫기 · 판 밖 — 사유 없는 자리
          const one = {open: !!tidyBox, backs, at};
          tidyClose();            // 두 번 눌러도 더 물리지 않는다
          console.log(JSON.stringify({one, backs}));
        """)
        self.assertFalse(got["one"]["open"], "판이 안 닫혔다")
        self.assertEqual(got["one"]["backs"], 1,
                         "사람이 닫았는데 항목이 남았다 — 뒤로가기 한 번이 빈다")
        self.assertEqual(got["one"]["at"], 0, "이력 자리가 안 돌아왔다")
        self.assertEqual(got["backs"], 1, "닫은 판을 또 닫으며 한 번 더 물렸다")

    @unittest.skipIf(NODE is None, "node 가 없다")
    def test_leaving_the_screen_does_not_undo_the_move(self):
        """⑤ 화면을 옮겨 닫히는 길에서는 되물리지 않는다."""
        got = self.run_js("""
          openPanel();
          tidyClose("nav");       // tidyNavAway 가 부르는 사유
          console.log(JSON.stringify({open: !!tidyBox, backs}));
        """)
        self.assertFalse(got["open"], "화면을 옮겼는데 판이 남았다")
        self.assertEqual(got["backs"], 0, "화면 이동 자체를 무르는 되물림이 났다")

    @unittest.skipIf(NODE is None, "node 가 없다")
    def test_back_without_a_panel_is_not_ours(self):
        """⑥ 판이 닫혀 있을 때의 뒤로가기는 건드리지 않는다."""
        got = self.run_js("""
          goBack();
          console.log(JSON.stringify({pushes, backs, at}));
        """)
        self.assertEqual([got["pushes"], got["backs"]], [0, 0],
                         "판도 없는데 이력을 건드렸다")

    def test_every_close_names_its_reason(self):
        """⑦⑧ 사유를 넘기는 자리와, 이력을 안 세우는 자리."""
        self.assertIn('tidyClose("nav")', SRC,
                      "화면을 떠나며 닫는 자리가 사유를 안 넘긴다")
        self.assertIn("tidyHistOpen()", fn("tidyOpen"),
                      "판을 열며 이력 항목을 안 세운다")
        self.assertNotIn("tidyHistOpen", fn("tidyPaneRender"),
                         "Settings 의 절이 이력 항목을 세운다 — 그 자리는 주소가 이미 하나다")


if __name__ == "__main__":
    unittest.main()
