"""묶음이 말하는 줄을 **조각의 줄**로 되돌린다 (REQ-20260829-039).

조각 마흔둘을 `/app/all.js` 한 장으로 묶으면서 잃은 것이 하나 더 있다: 콘솔이
말하는 자리다. 낱개일 때 지킴이는 "app/ccrender.js:41 SyntaxError" 라고 말했는데,
묶은 뒤에는 같은 오류가 "app/all.js:1834" 가 된다 — 사람이 열 파일이 없어진다.
되돌리기(낱개로 다시 걸기)는 묶음이 **한 줄도 못 돌았을 때만** 발동하므로, 일부가
돌다 죽은 경우에는 그 이름을 되찾아 줄 사람이 지킴이뿐이다.

서버는 이미 묶음 맨 앞에 표를 낸다 — `window.__S9_BUNDLE = [[조각, 시작 줄], …]`
(bin/s9 `web_bundle`, 계약은 test_web_split 의 s7c). 여기서 묻는 것은 그 다음
한 걸음이다: **화면이 그 표를 실제로 쓰는가.**

판정을 정규식으로 짐작하지 않는다 — `remap()` 을 그대로 떼어 node 로 돌린다.
node 가 없으면 실행 검증만 건너뛰고 소스 계약은 그대로 본다.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest
import webasset

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
S9 = os.path.join(ROOT, "bin", "s9")


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


def grab(src, pattern, what):
    m = re.search(pattern, src, re.S | re.M)
    assert m, f"{what} 를 못 찾았다 — 이름이 바뀌었으면 이 시험도 따라가야 한다"
    return m.group(0)


class Remap(unittest.TestCase):
    """표를 손에 쥐여 주고 되돌리게 한다."""

    @classmethod
    def setUpClass(cls):
        cls.oops = webasset.part("app/oops.js")
        cls.fn = grab(cls.oops, r"^  function remap\(.*?^  \}", "remap()")

    def where(self, table, file, line):
        if not NODE:
            self.skipTest("node 없음 — 실행 검증 생략 (소스 계약은 별도 검사)")
        script = "\n".join([
            "global.window = {__S9_BUNDLE: %s};" % json.dumps(table),
            self.fn,
            "console.log(JSON.stringify(remap(%s, %s)));"
            % (json.dumps(file), json.dumps(line)),
        ])
        p = subprocess.run([NODE, "-e", script], capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(p.returncode, 0, f"node 실행 실패:\n{p.stderr[-2000:]}")
        return json.loads(p.stdout.strip().splitlines()[-1])

    TABLE = [["app/oops.js", 5], ["app/const.js", 191], ["app/card.js", 402]]

    # B1 — 이 요청의 전부: 묶음의 줄이 조각의 이름과 줄이 된다
    def test_remap(self):
        """표를 손에 쥐여 주고 되돌리게 한다."""
        with self.subTest("b1_a_bundle_line_becomes_a_part_line"):
            w = self.where(self.TABLE, "app/all.js", 200)
            self.assertEqual(w["file"], "app/const.js",
                             "표가 있는데도 어느 조각인지 말하지 못한다")
            self.assertEqual(w["line"], 9,
                             "조각 안에서의 줄이 아니라 통째 파일의 줄을 말한다")
        with self.subTest("b1b_the_last_part_reaches_to_the_end"):
                w = self.where(self.TABLE, "app/all.js", 9999)
                self.assertEqual(w["file"], "app/card.js")
                self.assertEqual(w["line"], 9999 - 402)

            # B2 — 표보다 앞(머리말·표 자신)은 묶음의 자리다
        with self.subTest("b2_the_header_is_not_anyones_part"):
                w = self.where(self.TABLE, "app/all.js", 3)
                self.assertEqual(w["file"], "app/all.js",
                                 "머리말에서 난 오류를 남의 조각 탓으로 돌린다")
                self.assertEqual(w["line"], 3)

            # B3 — 낱개로 되돌린 뒤의 오류는 이미 조각 이름이다. 건드리면 거짓이 된다
        with self.subTest("b3_a_real_part_is_left_alone"):
                w = self.where(self.TABLE, "app/card.js", 12)
                self.assertEqual(w["file"], "app/card.js")
                self.assertEqual(w["line"], 12)

            # B4 — 표가 없어도 죽지 않는다 (옛 서버가 내준 묶음, 또는 표가 망가진 경우)
        with self.subTest("b4_no_table_no_lie"):
                for table in (None, [], "망가짐", [["app/card.js"]], [[None, "x"]]):
                    w = self.where(table, "app/all.js", 1234)
                    self.assertEqual(w["file"], "app/all.js",
                                     f"표가 {table!r} 인데 조각 이름을 지어낸다")
                    self.assertEqual(w["line"], 1234)

            # B5 — 줄 번호가 없는 오류(자원 실패)는 되돌릴 근거가 없다
        with self.subTest("b5_without_a_line_there_is_nothing_to_undo"):
                w = self.where(self.TABLE, "app/all.js", 0)
                self.assertEqual(w["file"], "app/all.js",
                                 "묶음을 통째로 못 받은 것을 첫 조각 탓으로 돌린다")

            # B6 — 되돌린 것을 실제로 쓰는가. 떼어 낸 함수만 맞고 화면은 그대로면 헛일이다
        with self.subTest("b6_the_guard_actually_uses_it"):
            m = re.search(r"remap\(base\(e\.filename\), e\.lineno \|\| 0\)", self.oops)
            self.assertTrue(m, "remap() 이 있으나 오류를 그리는 자리에서 부르지 않는다 — "
                               "그러면 붉은 상자는 여전히 app/all.js 를 말한다")
            self.assertIn("__S9_BUNDLE", self.oops,
                          "지킴이가 서버의 표를 읽지 않는다")

class AgainstTheRealBundle(unittest.TestCase):
    """짐작한 표가 아니라 **서버가 지금 내는 표**로 되돌려 본다.

    표를 내는 쪽(bin/s9)과 읽는 쪽(app/oops.js)이 각자 맞고 둘의 규약만 어긋나는
    실패가 가장 찾기 어렵다 — 시작 줄을 하나씩 밀어 세는 것으로 충분하다.
    그래서 되돌린 (조각, 줄) 을 **조각 원문의 그 줄**과 글자로 맞춰 본다.
    """

    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        spec = importlib.util.spec_from_loader(
            "s9_bundle_ln",
            importlib.machinery.SourceFileLoader("s9_bundle_ln", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        cls.body = cls.m.web_bundle(
            "app", os.path.join(WEB, "index.html"), root=ROOT).decode("utf-8")
        cls.lines = cls.body.split("\n")
        mt = re.search(r"window\.__S9_BUNDLE = (\[.*?\]);\n", cls.body, re.S)
        assert mt, "묶음에 표가 없다 — test_web_split s7c 가 먼저 빨개져야 한다"
        cls.table = json.loads(mt.group(1))
        cls.fn = grab(webasset.part("app/oops.js"),
                      r"^  function remap\(.*?^  \}", "remap()")

    def test_b7_every_line_lands_on_the_same_text(self):
        if not NODE:
            self.skipTest("node 없음 — 실행 검증 생략")
        # 조각마다 첫 줄·중간·끝 언저리를 골라 묻는다. 전 줄을 묻는 것은
        # node 를 수천 번 띄우는 일이라, 한 번에 모아 묻는다.
        asks = []
        for i, (name, start) in enumerate(self.table):
            end = (self.table[i + 1][1] - 1 if i + 1 < len(self.table)
                   else len(self.lines))
            for ln in (start + 1, (start + 1 + end) // 2, end):
                if start < ln <= end:
                    asks.append(ln)
        script = "\n".join([
            "global.window = {__S9_BUNDLE: %s};" % json.dumps(self.table),
            self.fn,
            "const out = %s.map(l => remap('app/all.js', l));" % json.dumps(asks),
            "console.log(JSON.stringify(out));",
        ])
        p = subprocess.run([NODE, "-e", script], capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(p.returncode, 0, f"node 실행 실패:\n{p.stderr[-2000:]}")
        got = json.loads(p.stdout.strip().splitlines()[-1])
        for ln, w in zip(asks, got):
            src = webasset.part(w["file"]).split("\n")
            self.assertTrue(1 <= w["line"] <= len(src) + 1,
                            f"묶음 {ln}줄 → {w['file']}:{w['line']} — 그 조각에 "
                            f"없는 줄이다 (조각은 {len(src)}줄)")
            if w["line"] <= len(src):
                self.assertEqual(src[w["line"] - 1], self.lines[ln - 1],
                                 f"묶음 {ln}줄과 {w['file']}:{w['line']} 의 "
                                 "글자가 다르다 — 표와 읽는 쪽이 한 줄씩 어긋났다")


if __name__ == "__main__":
    unittest.main()
