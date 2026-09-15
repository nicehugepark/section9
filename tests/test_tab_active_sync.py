"""탭 알약이 화면을 따라오는가 (REQ-20260829-007-62x6).

보드에서 `이어 말하기` 를 누르면 터미널이 뜨는데 상단 알약은 Board 에 그대로
남아 있었다. 화면과 표시가 갈린 것이다 — 사용자가 어디에 있는지 헤드가
거짓말을 한다.

원인은 사본이었다. `.active` 를 칠하는 코드가 네 자리에 손으로 적혀 있었고
(라우트 복원·탭 클릭·docOpen·그래프 노드 클릭), `tab` 을 옮기는 다섯 번째
길인 `docPick` 만 그 한 줄을 빠뜨렸다. 사본을 늘리는 한 다음 길이 또 빠진다.

그래서 이 시험은 "docPick 에 한 줄을 더했는가" 를 묻지 않는다. **자리를
하나로 모았는가** 를 묻는다 — `tabSync()` 가 `tab` 을 읽어 칠하고, 그리는
길목(render)이 매번 그것을 부른다. 그러면 화면을 옮기는 어떤 손도 표시를
따로 챙길 필요가 없다.

픽셀이 아니라 이 계약만 검사한다. 실제 클릭은 사람의 확인 몫이다.

실행: python3 tests/ tab_active_sync
"""
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

# 손으로 적은 사본의 모양 — `[data-tab]` 을 훑어 active 를 토글하는 줄.
# 헤더로 좁힌 꼴(REQ-20260915-085-62x6)도 같은 사본이므로 둘 다 센다.
HAND_COPY = re.compile(
    r'querySelectorAll\("(?:header )?\[data-tab\]"\)'
    r'[\s\S]{0,120}?classList\.toggle\("active"')


def find_node():
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


NODE = find_node()


class TabActiveSync(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.src = f.read()

    def tab_sync_src(self):
        m = re.search(r'function tabSync\(\)\{[\s\S]{0,900}?\n\}', self.src)
        self.assertIsNotNone(m, "tabSync() 가 없다 — 사본이 다시 흩어진다")
        return m.group(0)

    def run_sync(self, at, buttons):
        """tabSync() 를 **실제로 돌려** 무엇을 건드렸는지 센다. 가짜 화면은
        셋뿐이다 — 헤더 탭 둘과 헤더 밖의 버튼 하나."""
        js = self.tab_sync_src() + """
const els = [];
function mk(where, t){
  const o = {where, dataset: {tab: t}, touched: 0, active: null};
  o.classList = {toggle: (n, on) => { o.touched++; o.active = on; }};
  els.push(o);
  return o;
}
""" + "".join(f'mk({json.dumps(w)}, {json.dumps(t)});\n'
              for w, t in buttons) + """
globalThis.document = {querySelectorAll: sel =>
  sel.startsWith("header ") ? els.filter(e => e.where === "header") : els};
let tab = %s;
tabSync();
console.log(JSON.stringify(els.map(e =>
  ({where: e.where, tab: e.dataset.tab, touched: e.touched, active: e.active}))));
""" % json.dumps(at)
        d = tempfile.mkdtemp(prefix="s9tabsync-")
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        f = os.path.join(d, "run.js")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(js)
        r = subprocess.run([NODE, f], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_one_place_paints_the_pill(self):
        """T1. 칠하는 자리는 하나다 — tabSync() 가 tab 을 읽어 결정한다."""
        body = self.tab_sync_src()
        self.assertIn('querySelectorAll("header [data-tab]")', body,
                      "문서 전체를 돈다 — 화면 안 다른 부품이 같은 이름표를 "
                      "쓰면 그 표시를 이 함수가 매번 꺼 버린다 "
                      "(REQ-20260915-085-62x6)")
        self.assertIn('"active"', body)
        self.assertIn("dataset.tab === tab", body,
                      "인자로 받은 값이 아니라 상태(tab)를 읽어야 한다 — "
                      "부르는 쪽이 값을 챙기면 그게 다시 사본이다")

    def test_render_syncs_before_the_terminal_early_return(self):
        """T2. render() 가 매번 맞춘다 — 그것도 조기 반환보다 먼저.

        render() 는 살아있는 터미널 셸을 재빌드하지 않으려고 일찍 반환한다
        (REQ-040). 그 뒤에서 부르면 정작 이 결함이 난 자리에서 안 불린다.
        """
        m = re.search(r'\nfunction render\(\)\{([\s\S]*?)\n\}\n', self.src)
        self.assertIsNotNone(m, "render() 를 찾지 못했다")
        body = m.group(1)
        i_sync = body.find("tabSync()")
        i_ret = body.find('if (tab === "terminal" && TERM')
        self.assertGreaterEqual(i_sync, 0, "render() 가 tabSync() 를 부르지 않는다")
        self.assertGreaterEqual(i_ret, 0, "터미널 조기 반환을 찾지 못했다")
        self.assertLess(i_sync, i_ret,
                        "tabSync() 가 조기 반환 뒤에 있다 — 터미널로 옮겨갈 때 "
                        "정확히 안 불리는 자리다")

    def test_doc_pick_moves_the_tab_and_renders(self):
        """T3. 이어 말하기는 tab 을 옮기고 그린다 — 표시는 render 가 맡는다."""
        m = re.search(r'function docPick\(id, jump\)\{([\s\S]*?)\n\}\n',
                      self.src)
        self.assertIsNotNone(m, "docPick() 을 찾지 못했다")
        body = m.group(1)
        self.assertIn('tab = "terminal"', body)
        self.assertIn("render()", body)
        self.assertNotRegex(body, HAND_COPY,
                            "docPick 이 표시를 직접 칠한다 — 그러면 또 사본이다")

    def test_no_hand_written_copies_left(self):
        """T4. 손으로 적은 사본이 남아 있지 않다.

        넷이 흩어져 있었기에 다섯 번째 길이 빠졌다. tabSync() 안의 한 벌만
        남기고 전부 그 함수를 부르게 한다.
        """
        hits = HAND_COPY.findall(self.src)
        self.assertEqual(len(hits), 1,
                         f"[data-tab] active 토글이 {len(hits)} 곳에 있다 — "
                         "tabSync() 안의 한 벌만 남겨라")

    def test_the_paths_that_move_the_screen_call_it(self):
        """회귀: 화면을 옮기는 손들이 모두 tabSync() 를 지난다.

        render() 를 거치지 않는 길(라우트 복원의 doRender=false)도 있으므로
        부르는 자리가 하나로는 부족하다.
        """
        for fn, needle in (("applyRoute", "dlgCheckNav();   // 뒤로가기"),
                           ("docOpen", "function docOpen(id){")):
            self.assertIn(needle, self.src, f"{fn} 자리가 바뀌었다")
        # 라우트 복원은 doRender 가 꺼져 있어도 표시를 맞춰야 한다
        m = re.search(r'dlgCheckNav\(\);   // 뒤로가기[\s\S]{0,200}?'
                      r'if \(doRender\) render\(\);', self.src)
        self.assertIsNotNone(m, "라우트 복원 자리를 찾지 못했다")
        self.assertIn("tabSync()", m.group(0),
                      "라우트 복원이 tabSync() 를 부르지 않는다 — "
                      "doRender=false 면 표시가 안 맞는다")
        self.assertRegex(self.src,
                         r'function docOpen\(id\)\{[\s\S]{0,300}?tabSync\(\)')

    @unittest.skipIf(NODE is None, "node 가 없다")
    def test_it_leaves_alone_what_is_not_a_tab(self):
        """T5. 헤더 밖의 같은 이름표는 **건드리지 않는다**
        (REQ-20260915-085-62x6).

        「보관함 · 휴지통」 판의 하위 탭이 같은 `data-tab` 을 써서, 15초마다
        도는 이 함수가 그 버튼의 표시를 매번 꺼 버렸다. 탭 줄은 화면을 옮기는
        자리이고 그 자리는 헤더 하나뿐이다.
        """
        got = self.run_sync("docs", [("header", "board"), ("header", "docs"),
                                     ("panel", "trash")])
        by = {(e["where"], e["tab"]): e for e in got}
        self.assertEqual(by[("panel", "trash")]["touched"], 0,
                         "헤더 밖 버튼을 건드렸다 — 그 부품의 표시가 꺼진다")
        self.assertIs(by[("header", "docs")]["active"], True,
                      "고른 탭이 안 켜졌다")
        self.assertIs(by[("header", "board")]["active"], False,
                      "안 고른 탭이 안 꺼졌다")


if __name__ == "__main__":
    unittest.main()
