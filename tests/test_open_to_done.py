"""이미 이뤄진 요구를 닫는 길 (REQ-20260907-044).

취소 21건 중 7건이 「다른 요청·커밋이 이미 이뤘다」였다 — 취소는 「안 했다」는
뜻인데 이룬 것을 안 했다고 적고 있었다. 그 자리는 done 이고, 어디서 이뤘는지는
`derived_from` 이 말한다.

고정하는 계약 넷.
1. open→done 이 열린다.
2. 그 길에는 **근거 지목**이 붙는다 — 무엇이 이뤘는지 적지 않으면 이 전이는
   취소를 done 이라고 적는 도구가 된다.
3. 지목한 문서는 `derived_from` 에 자동으로 적힌다(blocked→blocked_by 와 같은 패턴).
4. 화면에는 내지 않는다 — 표가 곧 버튼의 원천이라, 그냥 넣으면 모든 open 카드에
   「완료」가 생겨 일하지 않고 닫는 길을 화면에 내는 셈이 된다.

실행: python3 tests/ open_to_done
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9-o2d-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_o2d", importlib.machinery.SourceFileLoader("s9_mod_o2d", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class TableAndScreenAreNotTheSame(unittest.TestCase):
    def test_open_can_reach_done(self):
        self.assertIn("done", mod.TRANSITIONS["open"])

    def test_screen_does_not_offer_it(self):
        # 표가 곧 버튼의 원천이다 — 화면용 표에서는 빠져야 한다
        self.assertNotIn("done", mod.screen_transitions()["open"])

    def test_screen_keeps_the_other_branches(self):
        for br in ("in-progress", "blocked", "cancelled"):
            self.assertIn(br, mod.screen_transitions()["open"], br)

    def test_other_states_are_untouched_on_screen(self):
        self.assertEqual(sorted(mod.TRANSITIONS["in-progress"]),
                         mod.screen_transitions()["in-progress"])


class WhatCountsAsAReference(unittest.TestCase):
    def test_doc_id(self):
        ids, sha = mod.already_done_refs("REQ-20260906-017-62x6 로 흡수됐다")
        self.assertEqual(ids, ["REQ-20260906-017-62x6"])
        self.assertFalse(sha)

    def test_commit_sha(self):
        # 실제 마감 문장이 쓰는 꼴 — 「062 의 commit 2fd1d99 가 이미 고쳤다」
        ids, sha = mod.already_done_refs("commit 2fd1d99 가 이미 고쳤다")
        self.assertEqual(ids, [])
        self.assertTrue(sha)

    def test_self_reference_is_not_a_reference(self):
        # 「이 요청이 이 요청을 이뤘다」는 아무 말도 하지 않는다
        me = "REQ-20260907-044-62x6"
        ids, sha = mod.already_done_refs(f"{me} 은 이미 끝났다", me)
        self.assertEqual(ids, [])
        self.assertFalse(sha)

    def test_plain_sentence_is_not_a_reference(self):
        ids, sha = mod.already_done_refs("이미 다 되어 있었다")
        self.assertEqual((ids, sha), ([], False))


class Transition(unittest.TestCase):
    """CLI 를 실제로 돌린다 — 가드는 do_transition 안에 있다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-o2d-root-")
        self.env = dict(os.environ, S9_ROOT=self.root, S9_MACHINE="testbox",
                        S9_USER="tester")

    def _s9(self, *argv, inp=None):
        return subprocess.run([sys.executable, S9, *argv], input=inp,
                              capture_output=True, encoding="utf-8",
                              errors="replace", env=self.env, timeout=60)

    def _new(self, title="이미 된 요청"):
        out = self._s9("new", "request", "--title", title, "--summary", "s",
                       "--goal", "g", "--size", "S", inp="원문")
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.split()[0]

    def test_open_to_done_with_a_reference(self):
        other = self._new("먼저 한 요청")
        did = self._new()
        r = self._s9("status", did, "done", "--note", f"{other} 가 이미 이뤘다")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("open -> done", r.stdout)
        # 지목한 문서가 derived_from 에 적힌다
        self.assertIn(other, self._s9("show", did, "--meta").stdout)

    def test_open_to_done_without_a_reference_is_refused(self):
        did = self._new()
        r = self._s9("status", did, "done", "--note", "이미 다 되어 있었다")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("지목", r.stdout + r.stderr)

    def test_open_to_done_without_any_note_is_refused(self):
        did = self._new()
        r = self._s9("status", did, "done")
        self.assertNotEqual(r.returncode, 0)

    def test_the_old_path_still_needs_no_reference(self):
        # in-progress→done 은 종전 그대로다
        did = self._new()
        self.assertEqual(self._s9("status", did, "in-progress",
                                  "--note", "착수").returncode, 0)
        r = self._s9("status", did, "done", "--note", "끝냈다")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
