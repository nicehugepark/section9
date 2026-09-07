"""문서 목록은 그림이 바뀔 때만 다시 그린다 (REQ-20260907-029-62x6).

15초 폴이 66줄을 통째로 갈아 끼웠다. 실브라우저(Playwright)로 50초·폴 3회를
관찰한 실측이 근거다 — 지어낸 목록 HTML 은 22,173자로 **세 번 모두 같았는데**
줄은 세 번 다 새 노드가 됐다. 새 노드는 hover·focus·고르기 눈금과 사람의 누름을
함께 떨어뜨린다(REQ-20260907-028 에서 Playwright 가 「element was detached,
retrying ×11」로 본 자리).

여기서 잠그는 것은 둘이다.
  ① `docListStale` — 같은 글자면 칠하지 않는다(docs.js).
  ② `roveSync` 의 쓰기 가드 — tabIndex 가 이미 맞으면 쓰지 않는다(input.js).
     `tabIndex =` 는 값이 같아도 setAttribute 를 거치므로 줄 수만큼 attribute
     갱신이 나갔다(66줄 × 폴마다 실측).

판정은 정규식으로 짐작하지 않고 두 조각을 떼어 node 로 **실행**한다.

실행: python3 tests/ docs_render_idle
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web", "app")


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


def grab(src, pattern, what):
    m = re.search(pattern, src, re.S | re.M)
    assert m, f"{what} 를 못 찾았다 — 이름이 바뀌었으면 이 시험도 따라가야 한다"
    return m.group(0)


def read(name):
    with open(os.path.join(WEB, name), encoding="utf-8") as f:
        return f.read()


class DocsRenderIdle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = read("docs.js")
        cls.input = read("input.js")
        cls.stale = grab(cls.docs, r"^function docListStale\([^\n]*$",
                         "docListStale")
        cls.rove = grab(cls.input, r"^function roveSync\(\)\{.*?^\}", "roveSync")

    def node(self, script):
        if not NODE:
            self.skipTest("node 없음 — 실행 검증 생략 (소스 계약은 별도 검사)")
        p = subprocess.run([NODE, "-e", script], capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(p.returncode, 0, f"node 실행 실패:\n{p.stderr[-2000:]}")
        return json.loads(p.stdout.strip().splitlines()[-1])

    # ------------------------------------------------ S1·S2·S3 — 칠하는 횟수
    def paints(self, sequence, fresh_panel=True):
        """폴이 준 그림들을 차례로 넣고 **몇 번 칠했는지** 센다."""
        script = "\n".join([
            self.stale,
            # 판 하나. 첫 폴 전에는 무엇을 그리고 있는지 표시가 없다.
            "const wrap = {};",
            "" if fresh_panel else "wrap.__s9list = %s;" % json.dumps(sequence[0]),
            "let paints = 0;",
            "for (const list of %s)" % json.dumps(sequence),
            "  if (docListStale(wrap, list)){ wrap.__s9list = list; paints++; }",
            "console.log(JSON.stringify(paints));",
        ])
        return self.node(script)

    def test_docs_render_idle(self):
        A = '<div class="typebar"></div><div class="row" data-doc="REQ-1"></div>'
        B = A + '<div class="row" data-doc="REQ-2"></div>'

        # S1 — 조용한 상태: 같은 그림이 세 번 와도 칠하는 것은 한 번뿐.
        with self.subTest("s1_same_html_paints_once"):
            self.assertEqual(self.paints([A, A, A]), 1,
                             "같은 그림인데 폴마다 다시 칠한다 — 줄이 매번 새 "
                             "노드가 되고 사람의 누름이 그 사이에서 떨어진다")

        # S2 — 한 글자라도 바뀌면 그 폴에서 다시 칠한다. 멈춘 화면은 더 나쁜 결함이다.
        with self.subTest("s2_changed_html_repaints"):
            self.assertEqual(self.paints([A, B, B, A]), 3,
                             "그림이 바뀌었는데 안 칠한다 — 화면이 멈춘다")

        # S3 — 판을 새로 세우면 표시가 없으므로 첫 폴에서 반드시 칠한다.
        with self.subTest("s3_new_panel_paints_first"):
            self.assertEqual(self.paints([A]), 1)
            self.assertEqual(self.paints([A], fresh_panel=False), 0,
                             "이미 그 그림을 그리고 있는 판을 또 칠한다")

    # ------------------------------------------------ S4 — roveSync 쓰기 횟수
    def test_rove_writes_only_when_needed(self):
        """짚어 둔 자리가 그대로면 tabIndex 를 한 번도 쓰지 않는다."""
        script = "\n".join([
            'const ROVE_ITEM = "[data-rove-item]";',
            # 66줄짜리 목록 하나. 쓰기만 센다 — 읽기는 값이 안 든다.
            "let writes = 0;",
            "const mk = i => { const o = {_t: i === 0 ? 0 : -1,",
            "  classList: {contains: () => false}};",
            "  Object.defineProperty(o, 'tabIndex', {get(){ return o._t; },",
            "    set(v){ writes++; o._t = v; }});",
            "  return o; };",
            "const rows = Array.from({length: 66}, (_, i) => mk(i));",
            "const cont = {querySelectorAll: () => rows};",
            "global.document = {querySelectorAll: () => [cont]};",
            self.rove,
            "roveSync(); roveSync(); roveSync();",
            "console.log(JSON.stringify(writes));",
        ])
        self.assertEqual(self.node(script), 0,
                         "짚어 둔 자리가 그대로인데 66줄의 tabIndex 를 다시 쓴다 — "
                         "폴마다 줄 수만큼 attribute 갱신이 나간다")

    # ------------------------------------------------ 회귀 — 계약이 소스에 남아 있나
    def test_swap_goes_through_the_guard(self):
        i = self.docs.index('const wrap = $(\'#view .docs[data-pane="docs"] .doclist\')')
        block = self.docs[i:i + 900]
        self.assertIn("docListStale(wrap, list)", block,
                      "목록 교체가 판정을 지나지 않는다")
        self.assertIn("wrap.__s9list = list", block,
                      "칠한 그림을 판에 적어 두지 않으면 다음 폴이 또 칠한다")


if __name__ == "__main__":
    unittest.main()
