"""첨부 저장·서빙 테스트 (REQ-20260825-013 승인 → -050 구현, -023 렌더).

첨부는 문서의 일부 — 문서와 같은 월 디렉토리의 assets/<문서ID>/에 두고,
열람은 문서 가시성을 상속하는 /api/asset 라우트로만. rm은 첨부도 함께
tombstone. 격리: S9_ROOT=mktemp.

실행: python3 tests/ assets
"""
import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)   # 최소 더미 바이트


# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)


class TestAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9asset-")
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
        wait_server(cls.port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)

    @classmethod
    def cli(cls, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=20, stdin=subprocess.DEVNULL)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r.stdout

    def get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def upload_tmp(self, name="shot.png"):
        """업로드 임시본 흉내 — state/terminal/uploads/<계정>/<파일>"""
        d = os.path.join(self.tmp, "state", "terminal", "uploads", "tester")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(PNG)
        return p

    def new_req_with_image(self, title, img):
        return self.cli("new", "request", "--title", title, "--summary", "s",
                        "--size", "S", "--goal", "g",
                        "--body", f"화면 문제다\n[Image: {img}]").split()[0]

    def body_of(self, rid):
        import glob
        p = glob.glob(os.path.join(self.tmp, "vault", "**", rid + ".md"),
                      recursive=True)[0]
        with open(p, encoding="utf-8") as f:
            return f.read()

    # A1. ingest: 업로드 임시본이 문서 옆 assets/<id>/로 이동하고 본문이 상대경로로
    def test_test_assets(self):
        """TestAssets 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("a1_ingest_moves_and_rewrites"):
                src = self.upload_tmp("a1.png")
                rid = self.new_req_with_image("첨부 이전", src)
                self.cli("assets", "ingest", rid)
                body = self.body_of(rid)
                self.assertIn(f"[Image: assets/{rid}/a1.png]", body)
                self.assertNotIn(src, body)
                self.assertFalse(os.path.exists(src), "임시본이 남았다(이동 아님)")
                import glob
                moved = glob.glob(os.path.join(self.tmp, "vault", "**", "assets", rid,
                                               "a1.png"), recursive=True)
                self.assertEqual(len(moved), 1, "문서 옆 assets/에 없다")

            # A2. 서빙: 문서 가시성 상속 라우트로 바이트가 그대로 내려온다
        with self.subTest("a2_serving"):
                src = self.upload_tmp("a2.png")
                rid = self.new_req_with_image("첨부 서빙", src)
                self.cli("assets", "ingest", rid)
                code, data = self.get(f"/api/asset?doc={rid}&f=a2.png")
                self.assertEqual(code, 200)
                self.assertEqual(data, PNG)
                # 없는 파일·다른 문서·경로 탈출은 404 (존재 여부 누설 금지)
                self.assertEqual(self.get(f"/api/asset?doc={rid}&f=none.png")[0], 404)
                self.assertEqual(
                    self.get(f"/api/asset?doc={rid}&f=../../../etc/passwd")[0], 404)
                self.assertEqual(self.get("/api/asset?doc=REQ-9999-999&f=a2.png")[0], 404)

            # A2b. 글자 첨부는 charset 을 입고 나간다 (REQ-20260901-016) — charset 없는
            # text/* 를 받은 브라우저는 인코딩을 추측하고, 새 탭으로 연 소스 파일의
            # 한글 UTF-8 이 그 추측(레거시 인코딩)에서 전부 깨졌다(실캡처). 그림·이진은
            # 그대로다 — charset 은 글자에만 뜻이 있다.
        with self.subTest("a2b_text_asset_carries_charset"):
                d = os.path.join(self.tmp, "state", "terminal", "uploads", "tester")
                os.makedirs(d, exist_ok=True)
                p = os.path.join(d, "a2b.py")
                with open(p, "w", encoding="utf-8") as f:
                    f.write('print("한글")\n')
                rid = self.cli("new", "request", "--title", "글자 첨부", "--summary", "s",
                               "--size", "S", "--goal", "g",
                               "--body", f"소스다\n[File: {p}]").split()[0]
                self.cli("assets", "ingest", rid)
                url = f"http://127.0.0.1:{self.port}/api/asset?doc={rid}&f=a2b.py"
                with urllib.request.urlopen(url, timeout=5) as r:
                    self.assertEqual(r.status, 200)
                    ct = r.headers.get("Content-Type", "")
                    self.assertIn("charset=utf-8", ct,
                                  "글자 종류에 charset 이 없다: %r" % ct)
                    self.assertEqual(r.read().decode("utf-8"), 'print("한글")\n')
                src = self.upload_tmp("a2c.png")
                rid2 = self.new_req_with_image("그림 첨부", src)
                self.cli("assets", "ingest", rid2)
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/api/asset?doc={rid2}&f=a2c.png",
                        timeout=5) as r:
                    self.assertNotIn("charset", r.headers.get("Content-Type", ""),
                                     "그림에 charset 이 붙었다")

            # A3. rm: 첨부도 문서와 함께 tombstone(.trash)으로 — 고아 파일 없음
        with self.subTest("a3_rm_moves_assets"):
                src = self.upload_tmp("a3.png")
                rid = self.new_req_with_image("첨부 삭제", src)
                self.cli("assets", "ingest", rid)
                self.cli("rm", rid, "--reason", "test")
                import glob
                live = glob.glob(os.path.join(self.tmp, "vault", "requests", "*", "*",
                                              "assets", rid, "*"))
                self.assertEqual(live, [], "삭제 후에도 첨부가 남아 있다")
                trashed = glob.glob(os.path.join(self.tmp, "vault", "**", ".trash",
                                                 "assets-" + rid, "a3.png"),
                                    recursive=True)
                self.assertEqual(len(trashed), 1, "첨부가 tombstone으로 옮겨지지 않았다")
                self.assertEqual(self.get(f"/api/asset?doc={rid}&f=a3.png")[0], 404)

            # A4. migrate: 기존 문서들의 절대경로 첨부를 일괄 이전
        with self.subTest("a4_migrate"):
            src = self.upload_tmp("a4.png")
            rid = self.new_req_with_image("일괄 이전", src)
            out = self.cli("assets", "migrate")
            self.assertIn(rid, out)
            self.assertIn(f"[Image: assets/{rid}/a4.png]", self.body_of(rid))

class TestInlineRenderContract(unittest.TestCase):
    """문서 뷰 렌더 계약 (REQ-20260825-023): 첨부 HTML은 자리표시자로 보호돼
    linkifyIds가 src/href 속성 안 문서 id를 건드려 태그를 깨뜨리지 않는다."""
    def setUp(self):
        with open(index_path(),
                  encoding="utf-8") as f:
            self.html = f.read()

    def test_i1_img_route_used(self):
        self.assertIn("attimg", self.html)
        self.assertIn("/api/asset?doc=", self.html)

    def test_i2_placeholder_protection(self):
        # 창을 글자 수로 자르지 않는다 — 규칙이 하나 늘 때마다 계약이 창 밖으로
        # 밀려나 "없다"로 읽힌다(REQ-20260829-008 이 맨 경로 규칙을 더하며
        # 실제로 그랬다). 함수 시작점부터 앞뒤 관계만 본다.
        i = self.html.index("const inline = s =>")
        seg = self.html[i:]
        self.assertIn("held", seg[:1600])   # 자리표시자 보관
        self.assertIn("\\u0000", seg[:1600])  # 마커로 치환 후 복원
        self.assertLess(seg.index("hold("), seg.index("linkifyIds("),
                        "첨부 HTML이 linkifyIds보다 먼저 보호돼야 한다")


class TestFileAttachments(unittest.TestCase):
    """일반 파일 첨부 + 첨부 태깅 (REQ-20260825-053)."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9file-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "tester")

    @classmethod
    def cli(cls, *argv):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=20, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r.stdout

    def _tmpfile(self, name, content=b"x"):
        d = os.path.join(self.tmp, "state", "terminal", "uploads", "tester")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(content)
        return p

    def _doc(self, rid):
        import glob
        p = glob.glob(os.path.join(self.tmp, "vault", "**", rid + ".md"),
                      recursive=True)[0]
        with open(p, encoding="utf-8") as f:
            return f.read()

    # F1. [File: ...] 첨부도 문서 옆으로 이전되고 상대경로로 재작성
    def test_test_file_attachments(self):
        """일반 파일 첨부 + 첨부 태깅 (REQ-20260825-053)."""
        with self.subTest("f1_generic_file_ingest"):
                src = self._tmpfile("report.log", b"deploy failed at step 3\n")
                rid = self.cli("new", "request", "--title", "로그 첨부", "--summary", "s",
                               "--size", "S", "--goal", "g",
                               "--body", f"확인 바람\n[File: {src}]").split()[0]
                self.cli("assets", "ingest", rid)
                body = self._doc(rid)
                self.assertIn(f"[File: assets/{rid}/report.log]", body)
                self.assertFalse(os.path.exists(src))

            # F2. 첨부 문서에 attached 태그 + 내용 키워드가 붙는다
        with self.subTest("f2_attachment_tags"):
                src = self._tmpfile("notes.md",
                                    "깃 동기화 리모트 커밋 푸시 백업 계획".encode())
                rid = self.cli("new", "request", "--title", "무관한 제목", "--summary", "",
                               "--size", "S", "--goal", "g",
                               "--body", f"[File: {src}]").split()[0]
                self.cli("assets", "ingest", rid)
                meta = self._doc(rid).split("---")[1]
                tagline = [l for l in meta.splitlines() if l.startswith("tags:")][0]
                tags = json.loads(tagline.split(":", 1)[1].strip())
                self.assertIn("attached", tags)
                self.assertIn("sync", tags)        # 첨부 내용에서 파생된 주제 태그

            # F3. 바이너리는 내용 대신 파일명만 키워드로 (읽기 실패로 죽지 않는다)
        with self.subTest("f3_binary_safe"):
            src = self._tmpfile("screenshot-dashboard.png", PNG)
            rid = self.cli("new", "request", "--title", "바이너리", "--summary", "",
                           "--size", "S", "--goal", "g",
                           "--body", f"[Image: {src}]").split()[0]
            self.cli("assets", "ingest", rid)
            meta = self._doc(rid).split("---")[1]
            tags = json.loads([l for l in meta.splitlines()
                               if l.startswith("tags:")][0].split(":", 1)[1].strip())
            self.assertIn("attached", tags)
            self.assertIn("dashboard", tags)   # 파일명 키워드

class TestAttachExtraction(unittest.TestCase):
    """첨부 본문 추출·타입 태깅 (REQ-20260825-054) — 전부 stdlib."""
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        cls.tmp = tempfile.mkdtemp(prefix="s9ext-")
        prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_MACHINE"] = "testbox"
        try:
            spec = importlib.util.spec_from_loader(
                "s9_mod_ext",
                importlib.machinery.SourceFileLoader("s9_mod_ext", S9))
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def _write(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    # E1. PDF 본문 추출 (비압축 스트림)
    def test_test_attach_extraction(self):
        """첨부 본문 추출·타입 태깅 (REQ-20260825-054) — 전부 stdlib."""
        with self.subTest("e1_pdf_text"):
                body = (b"%PDF-1.4\n1 0 obj\n<< /Length 60 >>\nstream\n"
                        b"BT /F1 12 Tf (deploy pipeline commit push remote) Tj ET\n"
                        b"endstream\nendobj\n%%EOF\n")
                p = self._write("doc.pdf", body)
                txt = self.mod.attach_text(p)
                self.assertIn("commit", txt)
                self.assertIn("sync", self.mod.attach_tags([p]))

            # E1b. zlib 압축 스트림도 추출
        with self.subTest("e1b_pdf_flate"):
                import zlib
                inner = zlib.compress(b"BT (dashboard board render layout) Tj ET")
                p = self._write("z.pdf", b"%PDF-1.4\nstream\n" + inner
                                + b"\nendstream\n%%EOF")
                self.assertIn("dashboard", self.mod.attach_text(p))

            # E2. docx/xlsx 본문 추출 (zip+xml)
        with self.subTest("e2_ooxml_text"):
                import zipfile
                p = os.path.join(self.tmp, "a.docx")
                with zipfile.ZipFile(p, "w") as z:
                    z.writestr("word/document.xml",
                               "<w:document><w:t>세션 모델 재시작 계획</w:t></w:document>")
                self.assertIn("세션", self.mod.attach_text(p))
                x = os.path.join(self.tmp, "b.xlsx")
                with zipfile.ZipFile(x, "w") as z:
                    z.writestr("xl/sharedStrings.xml", "<sst><si><t>테스트 검증 회귀</t></si></sst>")
                self.assertIn("검증", self.mod.attach_text(x))

            # E3. 확장자·타입군 태그 + assets 제외(attached와 혼용 정리)
        with self.subTest("e3_type_tags"):
                p = self._write("plan.pdf", b"%PDF-1.4\n%%EOF")
                tags = self.mod.attach_tags([p])
                self.assertIn("attached", tags)
                self.assertIn("pdf", tags)          # 확장자
                self.assertIn("document", tags)     # 타입군
                self.assertNotIn("assets", tags)    # 주제 태그와 분리

            # E4. 손상 파일·미지원 형식은 조용히 빈 텍스트 (첨부 저장은 계속)
        with self.subTest("e4_robust"):
                bad = self._write("broken.pdf", b"not really a pdf")
                self.assertEqual(self.mod.attach_text(bad), "")
                z = self._write("x.zip", b"PK\x03\x04broken")
                self.assertEqual(self.mod.attach_text(z), "")
                self.assertIn("archive", self.mod.attach_tags([z]))

            # E5. 상한 30MB
        with self.subTest("e5_limit"):
            self.assertEqual(self.mod.ATTACH_MAX_BYTES, 30 * 1024 * 1024)

class TestFormatCoverage(unittest.TestCase):
    """포맷 전면 지원 (REQ-20260825-055) — 오피스·ODF·iWork·데이터·json/xml."""
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        cls.tmp = tempfile.mkdtemp(prefix="s9fmt-")
        prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_MACHINE"] = "testbox"
        try:
            spec = importlib.util.spec_from_loader(
                "s9_mod_fmt",
                importlib.machinery.SourceFileLoader("s9_mod_fmt", S9))
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def _zip(self, name, entries):
        import zipfile
        p = os.path.join(self.tmp, name)
        with zipfile.ZipFile(p, "w") as z:
            for n, data in entries.items():
                z.writestr(n, data)
        return p

    def _bin(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    # C1. ODF(odt/ods/odp) — content.xml
    def test_test_format_coverage(self):
        """포맷 전면 지원 (REQ-20260825-055) — 오피스·ODF·iWork·데이터·json/xml."""
        with self.subTest("c1_odf"):
                p = self._zip("a.odt", {"content.xml":
                                        "<office><text>동기화 리모트 커밋</text></office>"})
                self.assertIn("리모트", self.mod.attach_text(p))
                self.assertIn("document", self.mod.attach_tags([p]))

            # C2. 키노트(.key) — 구형 XML은 파싱, 신형 IWA는 문자열 폴백
        with self.subTest("c2_keynote"):
                old = self._zip("deck.key", {"index.apxl":
                                             "<slides><t>dashboard board layout</t></slides>"})
                self.assertIn("dashboard", self.mod.attach_text(old))
                new = self._zip("new.key", {"Index/Slide.iwa": b"\x00\x01binary",
                                            "preview.jpg": b"\xff\xd8"})
                self.mod.attach_text(new)          # 폴백 경로가 죽지 않는다
                self.assertIn("slides", self.mod.attach_tags([old]))

            # C3. 레거시 MS(doc/xls/ppt) — UTF-16LE/ASCII 문자열 스캔
        with self.subTest("c3_legacy_ms"):
                p = self._bin("legacy.doc",
                              b"\xd0\xcf\x11\xe0" + "배포 파이프라인 검증 계획".encode("utf-16-le")
                              + b"\x00" * 8 + b"deployment verify plan")
                txt = self.mod.attach_text(p)
                self.assertIn("verify", txt)
                tags = self.mod.attach_tags([p])
                self.assertIn("doc", tags)
                self.assertIn("document", tags)

            # C4. 컬럼 포맷(parquet/orc) — 스키마·평문 문자열
        with self.subTest("c4_columnar"):
                p = self._bin("events.parquet",
                              b"PAR1\x00\x00session_id\x00user_name\x00"
                              b"dashboard_click\x00" + b"\x00" * 16 + b"PAR1")
                txt = self.mod.attach_text(p)
                self.assertIn("session_id", txt)
                tags = self.mod.attach_tags([p])
                self.assertIn("parquet", tags)
                self.assertIn("data", tags)
                o = self._bin("t.orc", b"ORC\x00col_name customer_id\x00")
                self.assertIn("customer_id", self.mod.attach_text(o))

            # C5. json/xml (텍스트류) — 내용 그대로
        with self.subTest("c5_json_xml"):
                j = self._bin("cfg.json", b'{"sync": "remote", "commit": true}')
                self.assertIn("remote", self.mod.attach_text(j))
                x = self._bin("d.xml", "<root><item>테스트 검증</item></root>".encode())
                self.assertIn("검증", self.mod.attach_text(x))
                self.assertIn("json", self.mod.attach_tags([j]))

            # C6. rtf — 제어어 제거
        with self.subTest("c6_rtf"):
            p = self._bin("m.rtf", "{\\rtf1\\ansi 프로젝트 멤버십 계획\\par}".encode())
            self.assertIn("멤버십", self.mod.attach_text(p))

if __name__ == "__main__":
    unittest.main(verbosity=2)
