"""화면이 든 카탈로그로 "그 문서가 있는가"를 판정하지 않는다 (REQ-20260908-034).

`/api/catalog` 는 **화면이 그릴 것**을 준다 — 보드용 창(catalog_window)이 씌워져
저장소에 1380건이 있어도 손에 오는 것은 403건이다. 그런데 화면은 그 목록을
"이 문서가 존재하는가"의 사전으로도 읽었다(catFind·resolveShortRef). 그래서 답변에
적힌 **정식 id** 조차 창 밖이면 없는 문서로 판정돼 링크가 서지 않았다
(REQ-20260908-033 의 두 번째 원인).

존재를 묻는 자리를 따로 연다 — `/api/docindex` 는 전량의 [id, created] 만 준다.
링크 판정에 필요한 것이 그 둘뿐이라 실측 gzip 11KB 이고, 보드 카탈로그 응답
(gzip 56KB)의 1/5 이다. 판정 규칙은 새로 짜지 않는다: 화면은 `catalog` 를 잠깐
색인으로 바꿔 끼우고 **원래 그 함수**를 부른다 — 엔진은 한 벌이다.

실행: python3 tests/ doc_index
"""
import glob
import gzip
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
WEB = os.path.join(HERE, "..", "web", "app")

from portpool import free_port, wait_server  # noqa: E402


def find_node():
    """node 를 찾는다 — 없으면 화면쪽 시험은 건너뛴다."""
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


def _grab(path, pat):
    src = open(os.path.join(WEB, path), encoding="utf-8").read()
    m = re.search(pat, src, re.S | re.M)
    assert m, f"{path} 에서 {pat!r} 를 찾지 못했다"
    return m.group(0)


def js_engine():
    """판정에 쓰이는 조각만 떼어 온다 — 규칙이 바뀌면 이 시험이 함께 깨진다."""
    return "\n".join([
        _grab("state.js", r"^function catFind\(id\)\{.*?^\}"),
        _grab("refs.js", r"^function resolveShortRef\(kind, num, atMs\)\{.*?^\}"),
        _grab("refs.js", r"^const CC_SHORT_VECTORS = \[.*?^\];"),
        _grab("app.js", r"^let docIdx = null;.*?^let docIdxAt = 0;"),
        _grab("app.js", r"^function withDocIdx\(fn\)\{.*?^\}"),
        _grab("app.js", r"^function anyDoc\(id\)\{.*?\}$"),
        _grab("app.js", r"^function anyShortRef\(kind, num, atMs\)\{.*?^\}"),
    ])


def run_js(body):
    out = subprocess.run([find_node(), "-e", "let catalog = [];\n"
                          + js_engine() + "\n" + body],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


class DocIndexServer(unittest.TestCase):
    """서버: 창 밖의 문서도 색인에는 있다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9didx-")
        # 창을 1건으로 좁혀 둔다 — 닫힌 요청 400건을 만들지 않고도 같은 사고를 낸다
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_PORT_GUARD": "off", "S9_CATALOG_BOARD_CLOSED": "1"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env,
                       timeout=20)
        subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                       env=cls.env, timeout=20)
        cls.ids = [cls.mkdoc(f"doc{i}") for i in range(4)]
        for i in cls.ids:                       # 전부 닫아 창 밖으로 보낸다
            subprocess.run([S9, "status", i, "cancelled", "--note", "t"],
                           capture_output=True, env=cls.env, timeout=20)
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
    def mkdoc(cls, title):
        out = subprocess.run([S9, "new", "request", "--title", title,
                              "--summary", "t", "--goal", "t", "--size", "S",
                              "--user", "alice", "--body", "x" * 200],
                             capture_output=True, text=True, env=cls.env,
                             timeout=20)
        m = re.search(r"(REQ-\d{8}-\d+(?:-[0-9a-z]{4})?)", out.stdout)
        assert m, out.stdout + out.stderr
        return m.group(1)

    def get(self, path, headers=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_doc_index_server(self):
        # S1. 창이 자른 문서도 색인에는 전부 있다
        with self.subTest("s1_index_has_what_window_dropped"):
            _, _, cat = self.get("/api/catalog")
            _, _, idx = self.get("/api/docindex")
            board = {r["id"] for r in json.loads(cat)}
            index = {r[0] for r in json.loads(idx)}
            self.assertLess(len(board), len(self.ids),
                            "창이 아무것도 자르지 않았다 — 사고를 재현 못 한다")
            for i in self.ids:
                self.assertIn(i, index, f"{i} 가 색인에 없다")

        # S2. 계약: [id, created] 2칸 · ETag 재요청은 304 · gzip
        with self.subTest("s2_contract"):
            code, hdr, body = self.get("/api/docindex")
            self.assertEqual(code, 200)
            rows = json.loads(body)
            self.assertTrue(all(len(r) == 2 and r[0] and r[1] for r in rows))
            code2, _, body2 = self.get(
                "/api/docindex", {"If-None-Match": hdr["ETag"]})
            self.assertEqual(code2, 304)
            self.assertEqual(body2, b"")
            _, hz, bz = self.get("/api/docindex",
                                 {"Accept-Encoding": "gzip"})
            self.assertEqual(hz.get("Content-Encoding"), "gzip")
            self.assertEqual(json.loads(gzip.decompress(bz)), rows)

        # S4. 색인은 보드 카탈로그보다 가볍다 (gzip 기준)
        with self.subTest("s4_cheaper_than_catalog"):
            _, _, idx = self.get("/api/docindex", {"Accept-Encoding": "gzip"})
            _, _, cat = self.get("/api/catalog", {"Accept-Encoding": "gzip"})
            self.assertLess(len(idx), len(cat))

    # S3. 공개 범위 밖의 문서는 색인에도 없다
    def test_doc_index_respects_visibility(self):
        _, _, idx = self.get("/api/docindex")
        ids = {r[0] for r in json.loads(idx)}
        _, _, cat = self.get("/api/catalog?window=all")
        self.assertEqual(
            ids, {r["id"] for r in json.loads(cat)},
            "색인과 전량 카탈로그가 같은 문서를 봐야 한다 — 색인이 더 많이 "
            "보이면 공개 범위를 흘리는 것이다")


@unittest.skipUnless(find_node(), "node 없음")
class DocIndexScreen(unittest.TestCase):
    """화면: 카탈로그가 창에 잘려도 판정은 저장소 전체 기준이다."""

    NARROW = ('[{"id":"REQ-20260908-001-62x6","created":"2026-09-08T09:00:00+09:00"}]')
    FULL = ('[{"id":"REQ-20260828-021-62x6","created":"2026-08-28T09:00:00+09:00"},'
            '{"id":"REQ-20260908-001-62x6","created":"2026-09-08T09:00:00+09:00"}]')

    # S5. 창 밖의 정식 id 도 찾는다
    def test_s5_old_full_id_is_known(self):
        got = run_js(f"catalog = {self.NARROW}; docIdx = {self.FULL};"
                     'console.log(String((anyDoc("REQ-20260828-021-62x6")||{}).id));')
        self.assertEqual(got, "REQ-20260828-021-62x6")

    # S6. 저장소에 없는 id 에는 여전히 아무 약속도 하지 않는다
    def test_s6_unknown_id_stays_unknown(self):
        got = run_js(f"catalog = {self.NARROW}; docIdx = {self.FULL};"
                     'console.log(String(anyDoc("REQ-20990101-999-zzzz")));')
        self.assertEqual(got, "null")

    # S7. 축약 계약표가 색인 경로로도 그대로 통과한다 (두 벌 갈라짐 방지)
    def test_s7_short_ref_contract_holds_through_index(self):
        got = run_js(
            "catalog = [];"
            "docIdx = CC_SHORT_VECTORS.filter(v => v[2]).map(v => "
            "  ({id: v[2], created: v[1]}));"
            "const bad = CC_SHORT_VECTORS.filter(([ref, at, want]) => {"
            "  const [k, n] = ref.split('-');"
            "  const r = anyShortRef(k, n, Date.parse(at));"
            "  return (r ? r.id : null) !== want; });"
            "console.log(JSON.stringify(bad));")
        self.assertEqual(got, "[]")

    # S8. 색인을 못 받았으면 색인이 없던 때와 똑같이 동작한다
    def test_s8_without_index_nothing_changes(self):
        got = run_js(f"catalog = {self.FULL}; docIdx = null;"
                     'console.log(String((anyDoc("REQ-20260828-021-62x6")||{}).id)'
                     ' + " " + String(anyDoc("REQ-20990101-999-zzzz")));')
        self.assertEqual(got, "REQ-20260828-021-62x6 null")


if __name__ == "__main__":
    unittest.main()
