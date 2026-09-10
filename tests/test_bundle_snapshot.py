"""묶음은 일관된 스냅샷에서만 짓는다 (REQ-20260909-095).

`/app/all.js` 는 요청마다 `web/app/*.js` 를 그 자리에서 읽어 잇는다. 작업자가
조각을 쓰는 중에 요청이 오면 **반쯤 쓰인 조각**이 묶음에 실리고, 화면 껍데기가
아예 서지 않는다 — 실측 2026-09-09: `events.js` 의 `$(s)` 가 null, 그리고
"'usageLast' has already been declared".

그래서 규칙이 셋이다.
  ① 모든 조각이 1초 이상 조용할 때만 새 묶음을 짓는다. 어느 하나가 방금
     쓰였으면 마지막으로 내준 묶음(메모리)을 그대로 돌려준다 — 첫 요청이라
     돌려줄 것이 없으면 상한(2초) 안에서 기다렸다 다시 본다.
  ② 새 묶음을 짓기 전에 조각을 값싼 구문 검사로 본다. 실패한 조각은 싣지 않고
     직전 온전본을 그 자리에 세우며, 경고를 stderr 와 성능 기록에 남긴다.
  ③ ETag 는 **실제로 실린 조각들**의 지문이다 — 빠지거나 대체된 조각이 있으면
     온전할 때와 다른 값이다.

가장 큰 위험은 이 검사가 정상 조각을 떨어뜨리는 것이다(오탐이 곧 사고다).
S8 이 그 자리를 지킨다 — 지금 저장소의 조각 전부가 통과해야 한다.

실행: python3 tests/ bundle_snapshot
"""
import glob
import importlib.machinery
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")

OLD = 30.0        # 「조용한」 조각의 나이(초) — dwell 을 넉넉히 넘긴다
GOOD = "window.A = function () { return 1; };\n"
GOOD2 = "window.B = function () { return 2; };\n"
BROKEN = "window.A = function () { return 1;\n"      # 괄호가 안 닫혔다


def load():
    spec = importlib.util.spec_from_loader(
        "s9_bundle_snap", importlib.machinery.SourceFileLoader(
            "s9_bundle_snap", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class BundleSnapshot(unittest.TestCase):
    """web_bundle_response 를 가짜 저장소에 대고 직접 돌린다."""

    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def setUp(self):
        # dwell 을 줄여 시험이 초 단위로 늘어지지 않게 한다. 값은 모듈 전역이라
        # 여기서 바꾸면 호출 시점에 그대로 읽힌다.
        self.m.BUNDLE_DWELL_SEC = 0.3
        self.m.BUNDLE_WAIT_SEC = 2.0
        self.addCleanup(setattr, self.m, "BUNDLE_DWELL_SEC", 1.0)
        self.addCleanup(setattr, self.m, "BUNDLE_WAIT_SEC", 2.0)

    # -- 가짜 저장소 ------------------------------------------------------
    def fake(self, parts, quiet=True):
        """{이름: 내용} 으로 임시 저장소 하나 — (root, shell_path)."""
        root = tempfile.mkdtemp(prefix="s9snap-")
        self.addCleanup(shutil.rmtree, root, True)
        web = os.path.join(root, "web")
        os.makedirs(os.path.join(web, "app"))
        os.makedirs(os.path.join(web, "css"))
        for name, body in parts.items():
            self.write(root, name, body, quiet=quiet)
        lines = ['<template id="s9-parts-css">', "</template>",
                 '<template id="s9-parts-app">']
        lines += ['<script src="app/%s"></script>' % n for n in parts]
        lines += ["</template>", '<script src="/app/all.js"></script>']
        shell = os.path.join(web, "index.html")
        with open(shell, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        if quiet:
            self.age(shell)
        return root, shell

    def write(self, root, name, body, quiet=True):
        fp = os.path.join(root, "web", "app", name)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(body)
        if quiet:
            self.age(fp)
        return fp

    def age(self, fp, secs=OLD):
        """파일을 secs 만큼 과거로 — 「조용해졌다」를 기다리지 않고 만든다."""
        t = time.time() - secs
        os.utime(fp, (t, t))

    def body(self, ent):
        return ent["body"].decode()

    # -- S1 ---------------------------------------------------------------
    def test_s1_all_parts_quiet_yields_the_whole_bundle(self):
        """조용한 조각 셋은 그대로 다 실린다."""
        root, sh = self.fake({"a.js": GOOD, "b.js": GOOD2,
                              "c.js": "window.C = 3;\n"})
        ent = self.m.web_bundle_response("app", sh, root)
        out = self.body(ent)
        for n in ("a.js", "b.js", "c.js"):
            self.assertIn("app/" + n, out, "%s 가 묶음에 없다" % n)
        self.assertIn("window.C = 3;", out)
        self.assertNotIn("구문 오류", out)

    # -- S2 ---------------------------------------------------------------
    def test_s2_a_part_being_written_keeps_the_previous_bundle(self):
        """조각을 방금 썼으면 같은 body·같은 ETag 의 직전 묶음이 온다."""
        root, sh = self.fake({"a.js": GOOD, "b.js": GOOD2})
        first = self.m.web_bundle_response("app", sh, root)
        self.write(root, "a.js", "window.A = 99;\n", quiet=False)   # 쓰는 중
        again = self.m.web_bundle_response("app", sh, root)
        self.assertEqual(again["etag"], first["etag"],
                         "쓰는 중인 조각이 새 묶음을 짓게 했다")
        self.assertEqual(again["body"], first["body"])
        self.assertNotIn("window.A = 99;", self.body(again))

    # -- S3 ---------------------------------------------------------------
    def test_s3_after_the_dwell_the_bundle_is_rebuilt(self):
        """조용해지면 다음 요청이 새 내용을 싣는다 — 다른 ETag."""
        root, sh = self.fake({"a.js": GOOD, "b.js": GOOD2})
        first = self.m.web_bundle_response("app", sh, root)
        fp = self.write(root, "a.js", "window.A = 99;\n", quiet=False)
        self.age(fp)                       # mtime 을 dwell 밖으로
        after = self.m.web_bundle_response("app", sh, root)
        self.assertIn("window.A = 99;", self.body(after))
        self.assertNotEqual(after["etag"], first["etag"],
                            "내용이 바뀌었는데 ETag 가 같다")

    # -- S4 ---------------------------------------------------------------
    def test_s4_the_first_request_waits_for_quiet(self):
        """직전 묶음이 없으면 상한 안에서 기다렸다 짓는다."""
        root, sh = self.fake({"a.js": GOOD}, quiet=False)   # 방금 쓴 조각
        t0 = time.time()
        ent = self.m.web_bundle_response("app", sh, root)
        took = time.time() - t0
        self.assertIn("window.A = function", self.body(ent),
                      "기다린 뒤에도 조각을 안 실었다")
        self.assertGreater(took, self.m.BUNDLE_DWELL_SEC * 0.5,
                           "기다리지 않고 곧바로 지었다")
        self.assertLess(took, self.m.BUNDLE_WAIT_SEC + 1.0,
                        "상한을 넘겨 기다렸다")

    def test_s4b_the_wait_has_a_ceiling(self):
        """계속 쓰이는 조각이어도 상한에서 멈추고 낸다 — 무한 대기 금지."""
        root, sh = self.fake({"a.js": GOOD}, quiet=False)
        self.m.BUNDLE_DWELL_SEC = 30.0     # 절대 조용해지지 않는다
        self.m.BUNDLE_WAIT_SEC = 0.4
        t0 = time.time()
        ent = self.m.web_bundle_response("app", sh, root)
        took = time.time() - t0
        self.assertIsNotNone(ent)
        self.assertLess(took, 2.0, "상한을 안 지켰다 (%.1fs)" % took)

    # -- S5 ---------------------------------------------------------------
    def test_s5_a_broken_part_is_left_out_with_a_warning(self):
        """구문이 깨진 조각은 빠지고, 그 자리를 주석으로 말하며 경고가 남는다."""
        root, sh = self.fake({"a.js": BROKEN, "b.js": GOOD2})
        marks = []
        self.addCleanup(setattr, self.m, "perf_mark", self.m.perf_mark)
        self.m.perf_mark = lambda *a, **k: marks.append((a, k))
        err = io.StringIO()
        keep, sys.stderr = sys.stderr, err
        try:
            ent = self.m.web_bundle_response("app", sh, root)
        finally:
            sys.stderr = keep
        out = self.body(ent)
        self.assertNotIn("window.A = function", out, "깨진 조각이 실렸다")
        self.assertIn("app/a.js", out, "빠진 자리를 말하지 않는다")
        self.assertIn("구문 오류", out)
        self.assertIn("window.B = function", out, "나머지 조각까지 빠졌다")
        self.assertIn("a.js", err.getvalue(), "경고가 stderr 에 없다")
        self.assertTrue([m for m in marks if m[0][:2] == ("bundle", "skip")],
                        "경고가 성능 기록(perf_mark)에 없다: %r" % (marks,))

    # -- S6 ---------------------------------------------------------------
    def test_s6_a_part_that_breaks_falls_back_to_its_last_good_copy(self):
        """앞서 온전했던 조각이 깨지면 직전 온전본이 그 자리에 선다."""
        root, sh = self.fake({"a.js": GOOD, "b.js": GOOD2})
        self.m.web_bundle_response("app", sh, root)          # 온전본을 기억시킨다
        fp = self.write(root, "a.js", BROKEN, quiet=False)
        self.age(fp)                                         # 조용해졌다
        err = io.StringIO()
        keep, sys.stderr = sys.stderr, err
        try:
            ent = self.m.web_bundle_response("app", sh, root)
        finally:
            sys.stderr = keep
        out = self.body(ent)
        self.assertIn("window.A = function () { return 1; };", out,
                      "직전 온전본이 안 실렸다")
        self.assertIn("직전 온전본", out, "대체했다는 사실을 말하지 않는다")
        self.assertIn("a.js", err.getvalue())

    # -- S7 ---------------------------------------------------------------
    def test_s7_the_etag_follows_what_was_actually_served(self):
        """ETag 는 실린 조합의 지문 — 스킵이 있으면 온전할 때와 다르다."""
        root, sh = self.fake({"a.js": GOOD, "b.js": GOOD2})
        whole = self.m.web_bundle_response("app", sh, root)["etag"]
        again = self.m.web_bundle_response("app", sh, root)["etag"]
        self.assertEqual(whole, again, "안 바뀐 묶음의 ETag 가 흔들린다")

        root2, sh2 = self.fake({"a.js": BROKEN, "b.js": GOOD2})
        err = io.StringIO()
        keep, sys.stderr = sys.stderr, err
        try:
            skipped = self.m.web_bundle_response("app", sh2, root2)["etag"]
        finally:
            sys.stderr = keep
        self.assertNotEqual(whole, skipped,
                            "조각이 빠졌는데 온전할 때와 같은 ETag 다")

    # -- S8 ---------------------------------------------------------------
    def test_s8_the_cheap_check_does_not_reject_healthy_parts(self):
        """지금 저장소의 조각 전부가 통과한다 — 오탐이 곧 사고다."""
        bad = []
        for sub, pat in (("app", "web/app/*.js"), ("css", "web/css/*.css")):
            for fp in sorted(glob.glob(os.path.join(ROOT, pat))):
                with open(fp, "rb") as f:
                    why = self.m._balance_error(f.read(), sub)
                if why:
                    bad.append("%s: %s" % (os.path.relpath(fp, ROOT), why))
        self.assertEqual(bad, [], "정상 조각을 구문 오류로 판정했다:\n" +
                         "\n".join(bad))

    def test_s8b_a_truncated_part_is_caught(self):
        """잘린 조각은 잡힌다 — 이 검사가 막으려는 것이 그것이다."""
        missed = []
        for sub, pat in (("app", "web/app/*.js"), ("css", "web/css/*.css")):
            for fp in sorted(glob.glob(os.path.join(ROOT, pat))):
                with open(fp, "rb") as f:
                    raw = f.read()
                cut = raw[:len(raw) * 2 // 3]
                if self.m._balance_error(cut, sub) is None:
                    missed.append(os.path.relpath(fp, ROOT))
        self.assertEqual(missed, [], "잘린 조각을 못 잡았다:\n" +
                         "\n".join(missed))

    def test_s8c_a_cut_in_the_middle_of_a_line_is_always_caught(self):
        """줄 중간에서 잘린 조각은 예외 없이 잡힌다 (REQ-20260910-007).

        2/3 한 지점만 보면 그 지점이 우연히 구문상 온전한 파일을 놓친다 —
        실제로 const.js 가 그렇게 새 나갔다. 임의의 바이트에서 잘린 조각은
        낱말·문자열·줄 중간에서 끝나므로, **줄바꿈으로 끝나지 않는 절단은
        전부** 잡혀야 한다. 평평한 선언(const X = ...;)만 있는 조각이 이
        규율의 가장 약한 자리라 함께 본다.
        """
        missed = []
        for sub, pat in (("app", "web/app/*.js"), ("css", "web/css/*.css")):
            for fp in sorted(glob.glob(os.path.join(ROOT, pat))):
                with open(fp, "rb") as f:
                    raw = f.read()
                for k in range(1, 60):
                    cut = raw[:len(raw) * k // 60]
                    if not cut or cut.endswith(b"\n"):
                        continue      # 줄 경계는 구문상 온전할 수 있다
                    if self.m._balance_error(cut, sub) is None:
                        missed.append("%s @%d/60" %
                                      (os.path.relpath(fp, ROOT), k))
        self.assertEqual(missed, [], "줄 중간에서 잘렸는데 못 잡았다:\n" +
                         "\n".join(missed[:20]))

    def test_s8d_a_flat_declaration_part_is_caught_almost_everywhere(self):
        """평평한 선언만 있는 조각도 거의 어디서 잘리든 잡힌다.

        문장이 끝난 바로 그 자리(`;` 다음 줄바꿈)에서 잘린 조각은 균형도
        맞고 끝도 마무리돼 있어, 기대 바이트 수 없이는 구별할 길이 없다 —
        남는 구멍은 그 자리뿐이고 실측 1% 미만이다(옛 규율은 22%였다).
        """
        fp = os.path.join(ROOT, "web/app/const.js")
        with open(fp, "rb") as f:
            raw = f.read()
        pts = [raw[:len(raw) * k // 500] for k in range(1, 500)]
        missed = [c for c in pts if self.m._balance_error(c, "app") is None]
        rate = len(missed) / float(len(pts))
        self.assertLess(rate, 0.05,
                        "const.js 의 절단점 %d 중 %d 을 놓쳤다 (%.1f%%)"
                        % (len(pts), len(missed), rate * 100))

    # -- 회귀 -------------------------------------------------------------
    def test_s9_the_missing_part_path_still_works(self):
        """없는 조각은 옛 규율 그대로 — 나머지는 낸다 (test_web_split s8c)."""
        root, sh = self.fake({"a.js": GOOD, "gone.js": GOOD2})
        os.unlink(os.path.join(root, "web", "app", "gone.js"))
        out = self.body(self.m.web_bundle_response("app", sh, root))
        self.assertIn("window.A = function", out)
        self.assertIn("app/gone.js", out, "없는 자리를 말하지 않는다")
        self.assertIn("없다", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
