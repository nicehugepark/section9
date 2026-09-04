"""PDF 본문 추출 (REQ-20260826-001) — 실물 구조 픽스처로 검증.

REQ-054/-055 가 done 이었는데도 실물 한글 PDF가 0바이트로 추출된 이유는
테스트가 '(...) Tj' 만 있는 장난감 PDF를 봤기 때문이다. 그래서 이 스위트의
픽스처는 실물과 **같은 구조**로 만든다 — Identity-H CID 폰트 · hex 문자열 ·
TJ 커닝 배열 · ToUnicode CMap · FlateDecode · ObjStm + XRef 스트림.
실물 PDF(경로가 머신 종속)는 있으면 함께 검증하고 없으면 skip 한다.

실행: python3 tests/ pdf_text
"""
import importlib.machinery
import importlib.util
import os
import struct
import sys
import tempfile
import time
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
# S9_PDF_BIN 으로 다른 리비전의 s9 를 지목할 수 있다 — 이 스위트가 수정 전
# 리비전에서 실제로 red 였음을 재현하는 경로 (git show HEAD~:bin/s9 > /tmp/old_s9)
S9 = os.environ.get("S9_PDF_BIN") or os.path.join(HERE, "..", "bin", "s9")

# 실물 표본 1 — Chrome `--headless --print-to-pdf` 로 뽑은 한글 인쇄본(87KB).
# 스위트에 **함께 커밋**한다: vault/ 는 .gitignore 대상이라 문서 첨부로는 다른
# 머신에서 사라지고, 그러면 이 결함을 done 으로 통과시킨 "장난감 PDF만 검증"
# 상태로 되돌아간다. 우리가 생성한 파일이라 저작권 문제도 없다.
REAL_WEB = os.path.join(HERE, "fixtures", "web_print_ko.pdf")
# 실물 표본 2 — 1MB 한글 사용설명서(XRef 스트림 + ObjStm). 머신 종속이라 있으면 검증.
REAL_KO = "/mnt/c/User_guide/User_guide_korean.pdf"


def load_s9():
    spec = importlib.util.spec_from_loader(
        "s9mod", importlib.machinery.SourceFileLoader("s9mod", S9))
    mod = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = ["s9"]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


s9 = load_s9()


# ---- 픽스처 빌더 -----------------------------------------------------------
def cmap4(mapping):
    """unicode -> gid 를 담은 최소 TrueType cmap(format 4) 서브테이블."""
    segs = [(c, c, (g - c) & 0xFFFF) for c, g in sorted(mapping.items())]
    segs.append((0xFFFF, 0xFFFF, 1))
    n = len(segs)
    body = struct.pack(">%dH" % n, *[s[1] for s in segs]) + b"\x00\x00"
    body += struct.pack(">%dH" % n, *[s[0] for s in segs])
    body += struct.pack(">%dh" % n, *[s[2] - 0x10000 if s[2] > 0x7FFF else s[2]
                                      for s in segs])
    body += struct.pack(">%dH" % n, *([0] * n))
    head = struct.pack(">HHHHHHH", 4, 16 + len(body), 0, n * 2, 2, 1, 0)
    sub = head + body
    return struct.pack(">HHHHI", 0, 1, 3, 1, 12) + sub


def fake_ttf(mapping):
    """cmap(format 4) 은 진짜, 나머지는 이름만 있는 더미 — 실물 폰트처럼 테이블
    이름과 괄호 낀 ASCII 가 바이너리에 들어 있다(추출기가 이걸 본문으로 착각했다)."""
    cm = cmap4(mapping)
    junk = b"(Malgun Gothic Regular glyf head hmtx gasp loca name)" * 4
    tabs = [(b"cmap", cm), (b"name", junk), (b"glyf", b"\x00" * 32),
            (b"head", b"\x00" * 54), (b"hmtx", b"\x00" * 16),
            (b"gasp", b"\x00" * 8), (b"loca", b"\x00" * 16)]
    n = len(tabs)
    off = 12 + n * 16
    dirent, data = b"", b""
    for tag, blob in tabs:
        dirent += tag + struct.pack(">III", 0, off + len(data), len(blob))
        data += blob
    return (b"\x00\x01\x00\x00" + struct.pack(">HHHH", n, 0, 0, 0)
            + dirent + data)


def build(objs, compressed=(), path=None):
    """objs: {번호: bytes(딕셔너리) | (딕셔너리, 스트림바이트)}.
    compressed 에 든 번호는 ObjStm 에 담고 XRef 스트림으로 색인한다 (PDF 1.5+)."""
    nums = sorted(objs)
    stm_num, xref_num = max(nums) + 1, max(nums) + 2
    out = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n")
    offs, incomp = {}, {}
    if compressed:
        parts, hdr, off = [], [], 0
        for i, n in enumerate(sorted(compressed)):
            b = objs[n]
            parts.append(b)
            hdr.append(b"%d %d" % (n, off))
            incomp[n] = i
            off += len(b) + 1
        data = b" ".join(hdr) + b"\n" + b"\n".join(parts) + b"\n"
        first = len(b" ".join(hdr)) + 1
        packed = zlib.compress(data)
    for n in nums:
        if n in incomp:
            continue
        o = objs[n]
        offs[n] = len(out)
        out += b"%d 0 obj\n" % n
        if isinstance(o, tuple):
            out += o[0] + b"\nstream\n" + o[1] + b"\nendstream\nendobj\n"
        else:
            out += o + b"\nendobj\n"
    if compressed:
        offs[stm_num] = len(out)
        out += (b"%d 0 obj\n<< /Type /ObjStm /N %d /First %d /Length %d "
                b"/Filter /FlateDecode >>\nstream\n"
                % (stm_num, len(incomp), first, len(packed)))
        out += packed + b"\nendstream\nendobj\n"
    xstart = len(out)
    top = xref_num + 1
    rows = bytearray()
    for n in range(top):
        if n == 0:
            rows += struct.pack(">BIH", 0, 0, 0xFFFF)
        elif n in incomp:
            rows += struct.pack(">BIH", 2, stm_num, incomp[n])
        elif n in offs:
            rows += struct.pack(">BIH", 1, offs[n], 0)
        elif n == xref_num:
            rows += struct.pack(">BIH", 1, xstart, 0)
        else:
            rows += struct.pack(">BIH", 0, 0, 0xFFFF)
    xd = zlib.compress(bytes(rows))
    out += (b"%d 0 obj\n<< /Type /XRef /Size %d /W [1 4 2] /Root 1 0 R "
            b"/Filter /FlateDecode /Length %d >>\nstream\n" % (xref_num, top, len(xd)))
    out += xd + b"\nendstream\nendobj\n"
    out += b"startxref\n%d\n%%%%EOF\n" % xstart
    with open(path, "wb") as f:
        f.write(bytes(out))
    return path


def flate(b):
    return zlib.compress(b)


def word_like(path, tounicode=True, font_cmap=None):
    """Word/Chrome 출력과 같은 구조 — Identity-H + hex + TJ + ToUnicode + ObjStm."""
    content = (b"BT /F1 12 Tf 72 720 Td <00030004> Tj ET\n"
               b"BT /F1 12 Tf 72 700 Td [<0010> -3 <0011> -400 <00120013>] TJ ET\n"
               b"BT /F1 12 Tf 72 680 Td <0020> Tj ET\n")
    cs = flate(content)
    tu = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
          b"1 beginbfchar\n<0003> <D55C>\nendbfchar\n"
          b"2 beginbfrange\n<0004> <0005> [<AE00> <BCF4>]\n"
          b"<0010> <0013> <0041>\nendbfrange\n"
          b"1 beginbfchar\n<0020> <D83DDE00>\nendbfchar\n"
          b"endcmap end end\n")
    tud = flate(tu)
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
            b"<< /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"),
        4: (b"<< /Length %d /Filter /FlateDecode >>" % len(cs), cs),
        5: (b"<< /Type /Font /Subtype /Type0 /BaseFont /AAAAAA+Malgun "
            b"/Encoding /Identity-H /DescendantFonts [6 0 R]"
            + (b" /ToUnicode 7 0 R >>" if tounicode else b" >>")),
        6: (b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /AAAAAA+Malgun "
            b"/FontDescriptor 8 0 R /DW 1000 /CIDToGIDMap /Identity >>"),
        7: (b"<< /Length %d /Filter /FlateDecode >>" % len(tud), tud),
    }
    if font_cmap:
        ff = flate(fake_ttf(font_cmap))
        objs[8] = (b"<< /Type /FontDescriptor /FontName /AAAAAA+Malgun /Flags 4 "
                   b"/FontFile2 9 0 R >>")
        objs[9] = (b"<< /Length %d /Filter /FlateDecode /Length1 %d >>"
                   % (len(ff), len(ff)), ff)
    else:
        objs[8] = b"<< /Type /FontDescriptor /FontName /AAAAAA+Malgun /Flags 4 >>"
    return build(objs, compressed=[3, 5, 6, 8], path=path)


def literal_pdf(path, extra=b"", pad=b""):
    """REQ-054/-055 시절의 평문 (...) Tj PDF — 회귀 확인용."""
    content = (b"BT /F1 12 Tf 72 720 Td [(sec) -3 (tion9 ) 12 (dep) 5 (loy)] TJ ET\n"
               b"BT /F1 12 Tf 72 700 Td (deploy pipeline report) Tj ET\n")
    cs = flate(content)
    # 패딩(pad)·함정(extra) 객체는 본문보다 **앞** 번호를 쓴다 — build() 가 번호
    # 순으로 쓰므로 본문이 파일 뒤쪽(8MB 너머)에 놓인다.
    objs = {
        1: b"<< /Type /Catalog /Pages 6 0 R >>",
        6: b"<< /Type /Pages /Kids [7 0 R] /Count 1 >>",
        7: (b"<< /Type /Page /Parent 6 0 R /MediaBox [0 0 612 792] /Resources "
            b"<< /Font << /F1 9 0 R >> >> /Contents 8 0 R >>"),
        8: (b"<< /Length %d /Filter /FlateDecode >>" % len(cs), cs),
        9: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    if extra:
        objs[2] = (b"<< /Length %d >>" % len(extra), extra)
    if pad:
        objs[3] = (b"<< /Length %d >>" % len(pad), pad)
    return build(objs, path=path)


class TestPdfText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9pdf-")

    def p(self, name):
        return os.path.join(self.tmp, name)

    # S2/S3 — hex 문자열 + ToUnicode(bfchar·bfrange 구간형/배열형·surrogate)
    def test_test_pdf_text(self):
        """TestPdfText 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("s2_s3_hex_and_tounicode"):
                f = word_like(self.p("word.pdf"))
                raw = open(f, "rb").read()
                self.assertNotIn(b") Tj", raw, "리터럴 문자열이 없는 PDF여야 의미가 있다")
                t = s9.attach_text(f)
                self.assertIn("한글", t)          # bfchar + bfrange 배열형
                self.assertIn("AB CD", t)         # bfrange 구간형 + TJ 큰 음수 = 공백
                self.assertIn("\U0001F600", t)    # surrogate pair

            # S4 — ToUnicode 가 없으면 임베드 폰트 cmap 을 역매핑한다
        with self.subTest("s4_tounicode_absent_falls_back_to_font_cmap"):
                f = word_like(self.p("nocmap.pdf"), tounicode=False,
                              font_cmap={0xD55C: 3, 0xAE00: 4, 0xBCF4: 5,
                                         0x41: 0x10, 0x42: 0x11, 0x43: 0x12, 0x44: 0x13})
                t = s9.attach_text(f)
                self.assertIn("한글", t)
                self.assertIn("AB CD", t)

            # S4-b — 매핑이 아예 없으면 쓰레기를 뱉느니 침묵한다
        with self.subTest("s4b_no_map_no_garbage"):
                f = word_like(self.p("blind.pdf"), tounicode=False)
                t = s9.attach_text(f)
                self.assertEqual("", t.strip())

            # S5 — 스트림 바이너리에 endstream 바이트열이 있어도 본문이 살아남는다
        with self.subTest("s5_endstream_inside_binary"):
                trap = b"\x00\x01binary endstream\nmore\x00" * 8
                f = literal_pdf(self.p("trap.pdf"), extra=trap)
                t = s9.attach_text(f)
                self.assertIn("section9 deploy", t)
                self.assertIn("deploy pipeline report", t)

            # S6 — 8MB 하드코딩 제거: 상한은 첨부 상한(30MB)과 같다
        with self.subTest("s6_beyond_8mb"):
                self.assertGreaterEqual(s9.ATTACH_MAX_BYTES, 30 * 1024 * 1024)
                pad = b"A" * (9 * 1024 * 1024)
                f = literal_pdf(self.p("big.pdf"), pad=pad)
                self.assertGreater(os.path.getsize(f), 8 * 1024 * 1024)
                t = s9.attach_text(f)
                self.assertIn("deploy pipeline report", t)

            # S7 — TJ 커닝 배열에서 단어가 쪼개지지 않는다
        with self.subTest("s7_tj_kerning_keeps_words"):
                f = literal_pdf(self.p("kern.pdf"))
                t = s9.attach_text(f)
                self.assertIn("section9 deploy", t)
                self.assertNotIn("sec tion9", t)

            # S8 — 임베드 폰트 테이블 이름이 본문/태그로 새지 않는다
        with self.subTest("s8_no_font_table_names"):
                f = word_like(self.p("font.pdf"),
                              font_cmap={0xD55C: 3, 0xAE00: 4, 0xBCF4: 5})
                t = s9.attach_text(f)
                for junk in ("glyf", "head", "hmtx", "gasp", "loca", "cmap"):
                    self.assertNotIn(junk, t)
                self.assertNotIn("cmap", " ".join(s9.attach_tags([f])))

            # S9 — 스캔본(이미지만): 본문 없음이 정답, 이미지 바이너리는 새지 않는다
        with self.subTest("s9_scanned_image_only"):
                img = flate((b"(JFIF scanner artifact 2026) " + bytes(range(256))) * 60)
                content = b"q 200 0 0 200 72 500 cm /Im0 Do Q\n"
                cs = flate(content)
                objs = {
                    1: b"<< /Type /Catalog /Pages 2 0 R >>",
                    2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                    3: (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                        b"/Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>"),
                    4: (b"<< /Length %d /Filter /FlateDecode >>" % len(cs), cs),
                    5: (b"<< /Type /XObject /Subtype /Image /Width 100 /Height 100 "
                        b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Length %d "
                        b"/Filter /FlateDecode >>" % len(img), img),
                }
                f = build(objs, path=self.p("scan.pdf"))
                self.assertEqual("", s9.attach_text(f).strip())
                self.assertNotIn("scanner", " ".join(s9.attach_tags([f])))

            # S10 — 기존에 통과하던 평문 경로가 그대로 통과한다
        with self.subTest("s10_regression_literal"):
                f = literal_pdf(self.p("plain.pdf"))
                self.assertIn("deploy pipeline report", s9.attach_text(f))

            # S11 — 잘린 PDF · 암호화 · 빈 파일: 예외 없이 빈 문자열/부분 결과
        with self.subTest("s11_defensive"):
                good = open(literal_pdf(self.p("g.pdf")), "rb").read()
                cut = self.p("cut.pdf")
                with open(cut, "wb") as f:
                    f.write(good[:len(good) // 3])
                empty = self.p("empty.pdf")
                open(empty, "wb").close()
                enc = self.p("enc.pdf")
                with open(enc, "wb") as f:
                    f.write(good.replace(b"/Root 1 0 R", b"/Root 1 0 R /Encrypt 9 0 R"))
                for p in (cut, empty, enc):
                    self.assertIsInstance(s9.attach_text(p), str)
                self.assertEqual("", s9.attach_text(empty))

            # S1 — 실물 웹 인쇄본 (문서 첨부라 어느 머신에서나 돈다)
        with self.subTest("s1_real_web_print"):
                self.assertTrue(os.path.exists(REAL_WEB), "재현 자산이 사라졌다: " + REAL_WEB)
                t = s9.attach_text(REAL_WEB)
                self.assertIn("배포 파이프라인 점검 보고서", t)
                self.assertIn("deploy pipeline verification report", t)
                for junk in ("glyf", "hmtx", "gasp"):
                    self.assertNotIn(junk, t)

            # S1/S12 — 실물 한글 PDF 1MB (있는 머신에서만)
        with self.subTest("s1b_real_korean_manual"):
            t0 = time.time()
            t = s9.attach_text(REAL_KO)
            took = time.time() - t0
            hangul = sum(1 for c in t if "가" <= c <= "힣")
            self.assertGreater(hangul, 200, f"한글 {hangul}자: {t[:120]!r}")
            self.assertLess(took, 10, f"추출에 {took:.1f}s — 동기 인제스트 경로다")
            for junk in ("glyf", "hmtx", "gasp"):
                self.assertNotIn(junk, t)

if __name__ == "__main__":
    unittest.main()
