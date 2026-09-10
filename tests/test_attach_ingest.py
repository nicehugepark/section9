"""터미널 첨부가 vault 에 들어간다 (REQ-20260907-039).

프롬프트 훅은 `[첨부]` 아래 `- 경로` 목록으로 적었고, `ingest_assets` 가 찾는
것은 `[종류: 경로]` 꼴이었다 — 한 번도 걸리지 않았다. 그래서 터미널로 붙인
그림은 vault 에 들어간 적이 없고, 문서에는 `~/.claude/image-cache/…` 라는
이 머신·이 계정에만 있는 경로가 글자로 남았다. Claude Code 가 그 캐시를 치우면
그림은 사라진다 — QST-20260902-012 의 그림이 실제로 그렇게 없어졌다.

고정하는 계약 셋.
1. 훅은 `[Attach: 절대경로]` 로 적는다 — 종류는 안 가른다(확장자 목록을 두 벌로
   만들지 않기 위해).
2. ingest 가 종류를 갈라 준다(asset_mark) — Attach 든 잘못 적힌 Image 든.
3. 원본은 **복사**된다. CC 캐시는 남의 파일이라 지우지 않는다.

실행: python3 tests/ attach_ingest
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")

TMP = tempfile.mkdtemp(prefix="s9-attach-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    def _load(name, path):
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, path))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    mod = _load("s9_mod_attach", S9)
    hook = _load("s9_hook_attach", HOOK)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class HookMarks(unittest.TestCase):
    def test_writes_attach_marks_not_a_list(self):
        # 목록 꼴(`- 경로`)은 ASSET_RE 에 안 걸린다 — 그것이 이 결함이었다.
        out = hook.asset_marks(["/tmp/a.png", "/tmp/b.pdf"])
        self.assertEqual(out, "[Attach: /tmp/a.png]\n[Attach: /tmp/b.pdf]")
        self.assertNotIn("- /tmp/a.png", out)

    def test_marks_are_absolute(self):
        out = hook.asset_marks(["a.png"])
        self.assertTrue(out.startswith("[Attach: /"), out)

    def test_ingest_regex_matches_the_hook_output(self):
        # 두 쪽이 같은 글자를 보고 있는가 — 이 결함의 뿌리가 여기였다.
        marks = hook.asset_marks(["/tmp/a.png"])
        found = [m.group(2) for m in mod.ASSET_RE.finditer(marks)]
        self.assertEqual(found, ["/tmp/a.png"])


class KindIsDecidedAtIngest(unittest.TestCase):
    def test_image_extension(self):
        self.assertEqual(mod.asset_mark("assets/X/1.png"), "[Image: assets/X/1.png]")

    def test_non_image_extension(self):
        self.assertEqual(mod.asset_mark("assets/X/a.pdf"), "[File: assets/X/a.pdf]")

    def test_unknown_extension_is_not_claimed_as_image(self):
        self.assertEqual(mod.asset_mark("assets/X/a.bin"), "[File: assets/X/a.bin]")


class IngestCopiesAndRewrites(unittest.TestCase):
    """CLI 를 실제로 돌린다 — 훅이 부르는 것이 `s9 assets ingest` 이므로."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-attach-root-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.src_dir = tempfile.mkdtemp(prefix="s9-attach-src-")
        self.addCleanup(shutil.rmtree, self.src_dir, ignore_errors=True)
        self.env = dict(os.environ, S9_ROOT=self.root, S9_MACHINE="testbox",
                        S9_USER="tester")

    def _s9(self, *argv, inp=None):
        return subprocess.run([sys.executable, S9, *argv], input=inp,
                              capture_output=True, encoding="utf-8",
                              errors="replace", env=self.env, timeout=60)

    def test_attach_becomes_image_and_original_survives(self):
        src = os.path.join(self.src_dir, "1.png")
        with open(src, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        out = self._s9("new", "request", "--title", "첨부 시험",
                       "--summary", "s", "--goal", "g", "--size", "S",
                       inp=f"본문\n\n[Attach: {src}]")
        self.assertEqual(out.returncode, 0, out.stderr)
        did = out.stdout.split()[0]
        r = self._s9("assets", "ingest", did)
        self.assertEqual(r.returncode, 0, r.stderr)
        shown = self._s9("show", did).stdout
        # 훅이 적은 Attach 가 ingest 에서 Image 로 갈렸다
        self.assertIn(f"[Image: assets/{did}/1.png]", shown)
        self.assertNotIn("[Attach:", shown)
        # 남의 파일(CC 캐시)은 지우지 않는다 — 복사다
        self.assertTrue(os.path.exists(src), "원본이 사라졌다 — 복사여야 한다")

    def test_a_fresh_missing_original_is_left_alone(self):
        """갓 만든 문서는 경로를 지키다 — 파일이 아직 안 내려앉았을 수 있다."""
        gone = os.path.join(self.src_dir, "없다.png")
        out = self._s9("new", "request", "--title", "사라진 첨부",
                       "--summary", "s", "--goal", "g", "--size", "S",
                       inp=f"본문\n\n[Attach: {gone}]")
        self.assertEqual(out.returncode, 0, out.stderr)
        did = out.stdout.split()[0]
        r = self._s9("assets", "ingest", did)
        self.assertEqual(r.returncode, 0, r.stderr)   # 죽지 않는다
        self.assertIn("[Attach:", self._s9("show", did).stdout)

    def test_a_long_dead_original_becomes_a_sentence(self):
        """오래된 것은 되살아날 일이 없다 — 경로 대신 사실 한 줄을 세운다.

        사용자가 머신 로컬 경로 글자를 보고 「아직도 렌더링이 안 된다」고 읽었다
        (2026-09-07 15:53). 사람에게 그 경로는 아무 뜻이 없다.
        """
        gone = os.path.join(self.src_dir, "없다.png")
        out = self._s9("new", "request", "--title", "오래 전에 사라진 첨부",
                       "--summary", "s", "--goal", "g", "--size", "S",
                       inp=f"본문\n\n[Attach: {gone}]")
        did = out.stdout.split()[0]
        # 문서를 한 시간 넘게 묵힌 것으로 만든다
        path = subprocess.run(
            [sys.executable, S9, "show", did, "--meta"], capture_output=True,
            encoding="utf-8", env=self.env).stdout
        import glob as _g
        f = _g.glob(os.path.join(self.root, "vault", "**", did + ".md"),
                    recursive=True)[0]
        old = time.time() - 7200
        os.utime(f, (old, old))
        r = self._s9("assets", "ingest", did)
        self.assertEqual(r.returncode, 0, r.stderr)
        shown = self._s9("show", did).stdout
        self.assertNotIn("[Attach:", shown)
        self.assertIn("남아 있지 않습니다", shown)
        self.assertNotIn(gone, shown, "머신 로컬 경로가 사람에게 남았다")


class ExamplesInProseAreNotOverwritten(IngestCopiesAndRewrites):
    """형식을 설명하는 예시 경로는 덮어쓰지 않는다 (REQ-20260910-008-62x6).

    migrate 를 전수로 돌리면 설명문의 예시까지 문장으로 바뀌어 설명이
    망가진다 — 실측 2026-09-10: 죽은 절대경로 30개 중 12개가 예시였다.
    """

    def _aged_doc(self, body):
        import glob as _g
        out = self._s9("new", "request", "--title", "예시가 든 문서",
                       "--summary", "s", "--goal", "g", "--size", "S",
                       inp=body)
        self.assertEqual(out.returncode, 0, out.stderr)
        did = out.stdout.split()[0]
        f = _g.glob(os.path.join(self.root, "vault", "**", did + ".md"),
                    recursive=True)[0]
        old = time.time() - 7200
        os.utime(f, (old, old))
        return did

    def _survives(self, body, mark):
        did = self._aged_doc(body)
        r = self._s9("assets", "ingest", did)
        self.assertEqual(r.returncode, 0, r.stderr)
        shown = self._s9("show", did).stdout
        self.assertIn(mark, shown)
        self.assertNotIn("남아 있지 않습니다", shown)

    def test_an_inline_quoted_example_survives(self):
        self._survives("훅이 쓰는 꼴은 `[Image: /x/a.png]` 다.",
                       "[Image: /x/a.png]")

    def test_an_indented_example_survives(self):
        self._survives('확인:\n\n    "이 로그 왜 이래?\\n[File: /x/a.log]"',
                       "[File: /x/a.log]")

    def test_an_abbreviated_path_survives(self):
        self._survives("맥이 적은 것은 [Image: /Users/…/assets/R/x.png] 였다.",
                       "[Image: /Users/…/assets/R/x.png]")


if __name__ == "__main__":
    unittest.main()
