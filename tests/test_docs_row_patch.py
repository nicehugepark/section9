"""목록 재그리기는 **바뀐 줄만** 만지고, 사람이 기다린 시간은 숫자로 남는다
(REQ-20260913-034-62x6 · 부모 REQ-20260913-031-62x6).

실측 2026-09-13(주인 「카드를 눌러 문서로 넘어갈 때 상당히 오래 걸린다」):
서버의 `/api/doc` 은 5~10ms 로 상수인데, 실브라우저(Windows Chrome, CDP)로 잰
목록 줄 클릭→문서 표시는 기본 66줄에서 중앙값 61ms, 1,274줄을 편 목록에서
549ms, 전량(1,925줄)에서 675ms 였다. CPU 프로파일이 가리킨 자리는 셋이다 —
목록 전체 innerHTML 재파싱 143ms · `scrollIntoView` 79ms · 줄 전수의 속성
다시 쓰기. 그런데 그때 **실제로 달라지는 글자는 두 줄**뿐이다(고르기를 놓은
줄과 새로 고른 줄).

이 시험이 지키는 계약 넷:
  ① 조각의 차례가 같고 달라진 것이 줄뿐이면 그 줄만 갈아 끼운다.
  ② 차례·구성이 달라지면(무리를 폈다·걸렀다) 통째로 칠한다 — 반쯤 고친
     목록을 남기느니 한 번 더 파싱한다.
  ③ 여는 경로는 줄 전수를 돌지 않고, 이미 보이는 줄에는 스크롤하지 않는다.
  ④ 클릭→표시 ms 는 있는 길(perf 로그)에 kind=client 로 실려 `s9 perf` 에
     서고, 그 POST 는 폴링 지문을 굴리지 않는다(계측이 캐시를 깨면 계측이
     곧 병목이다).

실행: python3 tests/ docs_row_patch
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

from webasset import index_path

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"
sys.path.insert(0, HERE)

from portpool import free_port, wait_server  # noqa: E402

INDEX = index_path()
N_ROWS = 1270          # 실측에서 느림이 드러난 크기


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


def grab(src, pat, what):
    m = re.search(pat, src, re.S | re.M)
    assert m, "%s 를 찾지 못했다" % what
    return m.group(0)


class TheListRepaintsOnlyWhatChanged(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.patch = grab(cls.src, r"^const DOC_PATCH_MAX = .*?^\}$", "docPatchRows")
        cls.cssq = grab(cls.src, r"^const cssq = .*?;$", "cssq")

    # ---------------------------------------------------------------- 뼈대
    def node(self, body):
        """가짜 목록 판 위에서 docPatchRows 를 돌린다 → {ok, replaced, found}"""
        script = "\n".join([
            "globalThis.window = {};",   # cssq 가 CSS.escape 를 묻는다
            self.cssq, self.patch,
            """
function mkParts(n, selAt){
  const p = [{k: "head", h: "<div class=typebar></div>"}];
  for (let i = 0; i < n; i++)
    p.push({k: "row:REQ-" + i, h: "<div class=row" + (i === selAt ? " sel" : "") + "></div>"});
  p.push({k: "more:request", h: "<button class=more></button>"});
  return p;
}
function mkWrap(parts, missing){
  const seen = [];
  return {__s9parts: parts, __seen: seen, __html: null,
    set innerHTML(v){ this.__html = v; },
    querySelector(sel){
      const id = /data-doc="([^"]+)"/.exec(sel)[1];
      if (missing && missing.includes(id)) return null;
      return {set outerHTML(v){ seen.push([id, v]); }};
    }};
}
""" + body])
        p = subprocess.run([NODE, "-e", script], capture_output=True, text=True,
                           timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr[-800:])
        return json.loads(p.stdout.strip().splitlines()[-1])

    # ------------------------------------------------- ① 두 줄만 갈아 끼운다
    @unittest.skipUnless(NODE, "node 가 없다")
    def test_only_the_two_changed_rows_are_repainted(self):
        out = self.node("""
const before = mkParts(%d, 3), after = mkParts(%d, 900);
const wrap = mkWrap(before);
const ok = docPatchRows(wrap, after);
console.log(JSON.stringify({ok, replaced: wrap.__seen.map(s => s[0]),
                            full: wrap.__html !== null}));
""" % (N_ROWS, N_ROWS))
        self.assertTrue(out["ok"], "바뀐 줄만 갈아 끼우지 못했다")
        self.assertEqual(out["replaced"], ["REQ-3", "REQ-900"],
                         "%d줄에서 달라진 것은 두 줄인데 만진 줄이 다르다" % N_ROWS)
        self.assertFalse(out["full"],
                         "줄 두 개 때문에 목록 전체를 다시 파싱한다 "
                         "(실측 1,274줄에서 549ms)")

    # ----------------------------------------- ② 모양이 달라지면 통째로 칠한다
    @unittest.skipUnless(NODE, "node 가 없다")
    def test_a_changed_shape_falls_back_to_a_full_paint(self):
        n = 40
        cases = {
            # 줄이 늘었다(무리를 폈다)
            "grown": "mkParts(%d, 3), mkParts(%d, 3)" % (n, n + 5),
            # 차례가 달라졌다(걸렀다·정렬이 바뀌었다)
            "reordered": ("mkParts(%d, 3), (() => { const p = mkParts(%d, 3);"
                          " p[1].k = 'row:REQ-999'; return p })()" % (n, n)),
            # 줄이 아닌 조각이 달라졌다(타입 띠의 숫자)
            "head": ("mkParts(%d, 3), (() => { const p = mkParts(%d, 3);"
                     " p[0].h = '<div class=typebar>bar</div>'; return p })()" % (n, n)),
            # 한도를 넘게 바뀌었다 — 그때는 통째로가 싸다
            "many": ("mkParts(%d, 3), (() => { const p = mkParts(%d, 3);"
                     " for (let i = 1; i < 30; i++) p[i].h = 'x'; return p })()" % (n, n)),
        }
        for name, expr in cases.items():
            with self.subTest(name):
                out = self.node("""
const [a, b] = [%s];
const wrap = mkWrap(a);
console.log(JSON.stringify({ok: docPatchRows(wrap, b),
                            replaced: wrap.__seen.map(s => s[0])}));
""" % expr)
                self.assertFalse(out["ok"], "통째로 칠해야 하는데 부분 갱신했다")
                self.assertEqual(out["replaced"], [],
                                 "돌아설 거면서 목록을 반쯤 고쳤다")
        # 줄을 못 찾으면 **아무것도 만지지 않고** 돌아선다
        out = self.node("""
const wrap = mkWrap(mkParts(%d, 3), ["REQ-900"]);
console.log(JSON.stringify({ok: docPatchRows(wrap, mkParts(%d, 900)),
                            replaced: wrap.__seen.map(s => s[0])}));
""" % (N_ROWS, N_ROWS))
        self.assertFalse(out["ok"], "찾지 못한 줄이 있는데 고쳤다고 답한다")
        self.assertEqual(out["replaced"], [], "반쯤 고친 목록을 남긴다")

    # ------------------------------------- ③ 여는 경로가 줄 전수를 돌지 않는다
    def test_the_open_path_does_not_walk_every_row(self):
        load = grab(self.src, r"^async function loadDoc\(id, bg, force\)\{.*?\n\}$",
                    "loadDoc")
        self.assertNotIn('querySelectorAll(".doclist .row").forEach', load,
                         "문서를 열 때마다 줄 전수의 속성을 다시 쓴다")
        self.assertIn('.doclist .row.sel, .doclist .row[aria-current]', load,
                      "놓은 줄을 좁혀 찾지 않는다")
        rd = grab(self.src, r"^async function renderDocs\(rows\)\{.*?\n\}$",
                  "renderDocs")
        i = rd.index('scrollIntoView({block: "nearest"})')
        self.assertIn("docRowVisible", rd[max(0, i - 300):i],
                      "이미 보이는 줄에도 스크롤 사슬 전체를 계산한다")
        self.assertIn("requestAnimationFrame", rd[max(0, i - 300):i],
                      "재는 일이 그리기 앞을 막는다")
        self.assertIn("docMeasureSoon(", rd, "재는 일을 한 프레임에 모으지 않는다")
        self.assertNotIn("  sizeDocs();\n  requestAnimationFrame(sizeDocs);", rd,
                         "렌더마다 강제 레이아웃을 두 번 낸다")


@unittest.skipUnless(os.path.exists(S9), "s9 가 없다")
class TheClientMarkRidesThePerfLog(unittest.TestCase):
    """서버 기동은 클래스당 한 번."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9perfc-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "alice", "S9_PORT_GUARD": "off"}
        cls.env.pop("S9_SESSION", None)
        cls.env.pop("S9_PERF", None)
        cls.cli("init")
        cls.cli("user", "add", "alice", "--role", "admin")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def cli(cls, *a):
        r = subprocess.run([S9, *a], capture_output=True, env=cls.env, timeout=30)
        assert r.returncode == 0, (a, r.stderr.decode(errors="replace")[-400:])
        return r

    def post(self, path, obj):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(obj).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def etag(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/catalog?window=all")
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
            return r.headers.get("ETag")

    def test_the_client_mark_rides_the_perf_log(self):
        tag0 = self.etag()
        st, _ = self.post("/api/perf", {"marks": [
            {"name": "docopen", "ms": 412.5, "rows": N_ROWS, "retries": 1,
             "vis": "visible"},
            # 남의 말이라 잘라 낸다 — 이름의 쓰레기·범위 밖 ms·모르는 딸림값
            {"name": "doc open<script>", "ms": 9.0},
            {"name": "docopen", "ms": "느림"},
            {"name": "docopen", "ms": -3},
            {"name": "docopen", "ms": 1e9},
            {"name": "docopen", "ms": 7.0, "note": "x" * 5000},
        ]})
        self.assertEqual(st, 200, "계측 한 줄이 화면에 오류로 돌아온다")
        self.assertEqual(self.etag(), tag0,
                         "계측 POST 가 폴링 지문을 굴린다 — 문서를 열 때마다 "
                         "카탈로그 스냅샷이 깨진다")
        # 큐를 쓰는 스레드가 배치로 적는다 — 줄이 설 때까지 짧게 기다린다.
        lines = []
        for _ in range(40):
            out = subprocess.run([S9, "perf", "tail", "-n", "50"],
                                 capture_output=True, text=True, env=self.env,
                                 timeout=30).stdout
            lines = [json.loads(x) for x in out.splitlines() if x.startswith("{")]
            if any(r.get("kind") == "client" for r in lines):
                break
        cli = [r for r in lines if r.get("kind") == "client"]
        self.assertTrue(cli, "화면이 보낸 계측이 perf 로그에 서지 않는다")
        first = cli[0]
        self.assertEqual(first["name"], "docopen")
        self.assertAlmostEqual(first["ms"], 412.5, places=1)
        self.assertEqual((first.get("rows"), first.get("retries"),
                          first.get("vis")), (N_ROWS, 1, "visible"),
                         "행 수·재시도 수·창이 보이는지가 함께 실리지 않는다")
        self.assertEqual([r["ms"] for r in cli], [412.5, 9.0, 7.0],
                         "범위 밖 ms 나 수가 아닌 ms 가 그대로 들어갔다")
        self.assertNotIn("<", cli[1]["name"], "이름이 온 그대로 적힌다")
        self.assertNotIn("note", cli[2], "모르는 딸림값을 그대로 싣는다")


if __name__ == "__main__":
    unittest.main()
