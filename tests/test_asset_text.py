"""첨부 본문 보존 — 사이드카 + 검색 확장 (REQ-20260826-020).

추출한 첨부 본문은 문서가 아니라 파생물이다. 진실은 첨부 원본 하나뿐이고,
추출본은 `assets/<문서ID>/.text/<파일명>.txt` 사이드카에 캐시로 남는다.
`s9 assets reindex` 로 언제든 전량 재생성된다.

검색은 카탈로그를 부풀리지 않는다 — `search --body` 가 문서 파일을 여는 그
자리에서 사이드카도 읽는다. 카탈로그는 대시보드가 폴링마다 전량을 내려받는
인덱스라, 가끔 쓰는 본문을 상시 비용에 실을 수 없다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ asset_text
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
PDF_FIXTURE = os.path.join(HERE, "fixtures", "web_print_ko.pdf")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40

from portpool import free_port, wait_server  # noqa: E402

# 첨부 안에만 있는 문구 — 문서 본문 어디에도 쓰지 않는다
SECRET = "청령포유배지"


def s9_const(name):
    """bin/s9 에 선언된 정수 상수를 읽는다 — 테스트가 숫자를 중복 선언하지 않게."""
    with open(S9_SRC, encoding="utf-8") as f:
        m = re.search(rf"^{name}\s*=\s*([0-9_]+)", f.read(), re.M)
    assert m, f"{name} 상수가 bin/s9 에 없다"
    return int(m.group(1).replace("_", ""))


class TestAssetText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9atext-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "tester")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**cls.env, "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def cli(cls, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=120, stdin=subprocess.DEVNULL)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)} -> {r.returncode}\n"
                                 f"{r.stdout}{r.stderr}")
        return r.stdout

    # ---- 헬퍼 -------------------------------------------------------------
    def upload(self, name, data):
        """업로드 임시본 — state/terminal/uploads/<계정>/<파일>"""
        d = os.path.join(self.tmp, "state", "terminal", "uploads", "tester")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(p, mode, **({} if isinstance(data, bytes)
                              else {"encoding": "utf-8"})) as f:
            f.write(data)
        return p

    def new_with(self, title, paths, body_extra=""):
        refs = "\n".join(f"[File: {p}]" for p in paths)
        out = self.cli("new", "request", "--title", title, "--summary", "s",
                       "--size", "S", "--goal", "g",
                       "--body", f"{body_extra}\n{refs}")
        rid = out.split()[0]
        self.cli("assets", "ingest", rid)
        return rid

    def doc_path(self, rid):
        import glob
        return glob.glob(os.path.join(self.tmp, "vault", "**", rid + ".md"),
                         recursive=True)[0]

    def text_dir(self, rid):
        return os.path.join(os.path.dirname(self.doc_path(rid)), "assets",
                            rid, ".text")

    def sidecar(self, rid, name):
        p = os.path.join(self.text_dir(rid), name + ".txt")
        with open(p, encoding="utf-8") as f:
            return f.read()

    def get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    # ---- S1. 인제스트 → 사이드카 -----------------------------------------
    def test_test_asset_text(self):
        """TestAssetText 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("s1_ingest_writes_sidecar"):
            body = f"연산군은 {SECRET} 에서 죽었다.\n두 번째 줄."
            src = self.upload("s1.txt", body)
            rid = self.new_with("사이드카 생성", [src])
            self.assertEqual(self.sidecar(rid, "s1.txt").strip(), body.strip())
        with self.subTest("s1b_sidecar_from_real_pdf"):
                with open(PDF_FIXTURE, "rb") as f:
                    src = self.upload("s1b.pdf", f.read())
                rid = self.new_with("PDF 사이드카", [src])
                got = self.sidecar(rid, "s1b.pdf")
                self.assertGreater(len(got), 200, "PDF 추출본이 사이드카에 없다")
                word = [w for w in got.split() if len(w) >= 3][0]
                self.assertIn(rid, self.cli("search", word, "--body"))

            # ---- S2. 검색이 첨부 본문까지 본다 -----------------------------------
        with self.subTest("s2_search_body_finds_attachment_text"):
                src = self.upload("s2.txt", f"기록에 따르면 {SECRET} 은 강 가운데다.")
                rid = self.new_with("첨부 검색", [src], body_extra="본문에는 없는 낱말")
                out = self.cli("search", SECRET, "--body")
                self.assertIn(rid, out, "첨부 안에만 있는 문구로 문서가 잡히지 않는다")
                self.assertIn("s2.txt", out, "어느 첨부에서 나왔는지 안 보인다")
                # 첨부가 없는 문서는 여전히 안 잡힌다
                self.assertEqual(self.cli("search", SECRET).strip(), "",
                                 "메타 검색이 첨부 본문에 오염됐다")

            # ---- S3. 사이드카는 재생성 가능한 파생물 -----------------------------
        with self.subTest("s3_reindex_restores"):
                src = self.upload("s3.txt", f"{SECRET} 관련 조사 메모.")
                rid = self.new_with("재생성", [src])
                before = self.sidecar(rid, "s3.txt")
                shutil.rmtree(self.text_dir(rid))
                self.assertEqual(self.cli("search", SECRET, "--body").count(rid), 0,
                                 "사이드카를 지웠는데도 검색된다 — 다른 곳에 복제됐다")
                self.cli("assets", "reindex")
                self.assertEqual(self.sidecar(rid, "s3.txt"), before)
                self.assertIn(rid, self.cli("search", SECRET, "--body"))

            # ---- S4. 회귀: 문서 본문 검색은 그대로 -------------------------------
        with self.subTest("s4_doc_body_search_unchanged"):
                mark = "회귀확인문구ZX"
                out = self.cli("new", "request", "--title", "본문 검색", "--summary", "s",
                               "--size", "S", "--goal", "g", "--body", f"{mark} 있다")
                rid = out.split()[0]
                hit = self.cli("search", mark, "--body")
                self.assertIn(rid, hit)
                self.assertRegex(hit, rf"{rid}:\d+:", "라인 번호 표기가 사라졌다")

            # ---- S5. 회귀: 카탈로그 스키마·크기 불변 -----------------------------
        with self.subTest("s5_catalog_not_bloated"):
                src = self.upload("s5.txt", (SECRET + " ") * 500)
                rid = self.new_with("카탈로그 불변", [src])
                cat = os.path.join(self.tmp, "index", "catalog.jsonl")
                self.cli("index", "rebuild")
                import json
                rows = [json.loads(l) for l in open(cat, encoding="utf-8") if l.strip()]
                row = [r for r in rows if r["id"] == rid][0]
                for k, v in row.items():
                    self.assertNotIn(SECRET, str(v),
                                     f"카탈로그 '{k}' 에 첨부 본문이 실렸다")

            # ---- S6. 추출 0자면 사이드카를 만들지 않는다 -------------------------
        with self.subTest("s6_no_empty_sidecar"):
                src = self.upload("s6.png", PNG)
                rid = self.new_with("빈 추출", [src])
                d = self.text_dir(rid)
                self.assertFalse(os.path.exists(os.path.join(d, "s6.png.txt")),
                                 "추출 0자인데 빈 사이드카를 남겼다")

            # ---- S7. 이름 충돌·유니코드 ------------------------------------------
        with self.subTest("s7_name_collision_and_unicode"):
                a = self.upload("같은이름.txt", "텍스트쪽 고유낱말 알파일세")
                b = self.upload("같은이름.md", "마크다운쪽 고유낱말 베타일세")
                rid = self.new_with("이름 충돌", [a, b])
                self.assertIn("알파일세", self.sidecar(rid, "같은이름.txt"))
                self.assertIn("베타일세", self.sidecar(rid, "같은이름.md"))

            # ---- S8. 상한에서 자른다 ---------------------------------------------
        with self.subTest("s8_truncates_at_limit"):
                cap = s9_const("ATTACH_TEXT_MAX")
                big = "가나다라마바사아자차" * (cap // 10 + 500)
                src = self.upload("s8.txt", big)
                rid = self.new_with("상한", [src])
                got = self.sidecar(rid, "s8.txt")
                self.assertLessEqual(len(got), cap)
                self.assertGreater(len(got), cap // 2, "상한보다 훨씬 적게 저장됐다")
                self.assertTrue(big.startswith(got[:200]))

            # ---- S9. 첨부 하나가 실패해도 인제스트는 완주 ------------------------
        with self.subTest("s9_extraction_failure_isolated"):
                bad = self.upload("s9bad.pdf", b"%PDF-1.4\n<<garbage>>\n")
                good = self.upload("s9good.txt", f"{SECRET} 정상 추출")
                rid = self.new_with("실패 격리", [bad, good])
                with open(self.doc_path(rid), encoding="utf-8") as f:
                    body = f.read()
                self.assertIn(f"assets/{rid}/s9bad.pdf", body, "파일 이전이 중단됐다")
                self.assertIn(f"assets/{rid}/s9good.txt", body)
                self.assertIn("attached", body, "태깅이 중단됐다")
                self.assertIn(SECRET, self.sidecar(rid, "s9good.txt"))

            # ---- S10. 서버 검색도 같은 의미론 ------------------------------------
        with self.subTest("s10_server_search_matches_cli"):
                src = self.upload("s10.txt", f"서버쪽 {SECRET} 확인")
                rid = self.new_with("서버 검색", [src])
                code, body = self.get(f"/api/search?q={urllib.parse.quote(SECRET)}")
                self.assertEqual(code, 200)
                self.assertIn(rid, body, "대시보드 검색이 첨부 본문을 못 본다")

            # ---- S11. .text 가 첨부 경로로 새지 않는다 ---------------------------
        with self.subTest("s11_text_dir_not_served"):
            src = self.upload("s11.txt", f"{SECRET} 위생")
            rid = self.new_with("위생", [src])
            self.assertEqual(self.get(f"/api/asset?doc={rid}&f=.text")[0], 404)
            self.assertEqual(
                self.get(f"/api/asset?doc={rid}&f=.text/s11.txt.txt")[0], 404)

if __name__ == "__main__":
    unittest.main()
