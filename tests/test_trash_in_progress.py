"""진행 중인 것을 버리면 진행 중인 채로 남지 않는다 (REQ-20260915-074-62x6).

실측 2026-09-16: 휴지통 137건 중 셋이 `in-progress` 였다(REQ-20260829-020 ·
REQ-20260828-038 · REQ-20260829-022, 전부 8월의 시험용 문서). 보드는 「하는
중」이라 하고 휴지통은 「버렸다」고 한다 — 한 문서에 대한 두 말이다.

가르는 선: **`open` 은 그대로 둔다**(휴지통 124건). 시작한 적 없는 것을 버리는
것은 모순이 아니다. 모순은 `in-progress` 뿐이었다.

그리고 사람은 **누르기 전에** 안다 — 누른 뒤에 아는 것은 통보다.

실행: python3 tests/ trash_in_progress
"""
import contextlib
import importlib.machinery
import importlib.util
import io as _io
import os
import re
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
TIDY = os.path.join(HERE, "..", "web", "app", "tidy.js")


class ThrowingAwayLiveWorkCancelsIt(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9trash-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.environ["S9_ROOT"] = self.root
        self.addCleanup(os.environ.pop, "S9_ROOT", None)
        spec = importlib.util.spec_from_loader(
            "s9_trash", importlib.machinery.SourceFileLoader("s9_trash", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        with contextlib.redirect_stdout(_io.StringIO()):
            self.m.cmd_init(type("A", (), {})())

    def mk(self, status):
        import types
        args = types.SimpleNamespace(
            doc_type="request", title="버릴 것", summary="s", goal="g",
            status="open", size="S", priority=None, user=None, assignee=None,
            tag_list=[], parent=None, derived_from=None, relates=None, why="",
            ref_doc=None, ref_link=None, ref_file=None, needs_os=None,
            needs_machine="", any_machine=True, from_chat="", project=None,
            project_tag=None, body="x", body_file=None, origin="human",
            agent="", root=True)
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        rid = out.getvalue().split()[0].rstrip(":")
        if status != "open":
            with contextlib.redirect_stdout(_io.StringIO()):
                self.m.do_transition(rid, status, note="착수")
        return rid

    def status_of(self, rid):
        for dp, _d, fns in os.walk(os.path.join(self.root, "vault")):
            for fn in fns:
                if fn.startswith(rid):
                    meta, _b = self.m.read_doc(os.path.join(dp, fn))
                    return meta.get("status"), dp
        return None, ""

    # 사고의 본체 — 진행 중인 것을 버리면 취소로 적힌다
    def test_an_in_progress_request_becomes_cancelled(self):
        rid = self.mk("in-progress")
        with contextlib.redirect_stdout(_io.StringIO()):
            self.m.do_rm(rid, "치운다")
        st, where = self.status_of(rid)
        self.assertIn(".trash", where, "휴지통으로 안 갔다")
        self.assertEqual("cancelled", st,
                         "휴지통에 in-progress 로 남았다 — 보드와 휴지통이 서로 "
                         "다른 말을 한다")

    # 경계 — open 은 그대로다 (시작한 적 없는 것을 버리는 것은 모순이 아니다)
    def test_an_open_request_keeps_its_status(self):
        rid = self.mk("open")
        with contextlib.redirect_stdout(_io.StringIO()):
            self.m.do_rm(rid, "치운다")
        st, where = self.status_of(rid)
        self.assertIn(".trash", where)
        self.assertEqual("open", st, "안 건드려도 되는 것을 건드렸다")

    # 정상 — 왜 취소됐는지가 문서에 남는다
    def test_the_document_says_why_it_was_cancelled(self):
        rid = self.mk("in-progress")
        with contextlib.redirect_stdout(_io.StringIO()):
            self.m.do_rm(rid, "치운다")
        _st, dp = self.status_of(rid)
        with open(os.path.join(dp, [f for f in os.listdir(dp)
                                    if f.startswith(rid)][0]),
                  encoding="utf-8") as f:
            body = f.read()
        self.assertIn("버려서 그만둔다", body,
                      "취소된 까닭이 문서에 없다 — 나중에 아무도 판정 못 한다")

    # 회귀 — 버린 사실(언제·누가·어디서)은 그대로 적힌다
    def test_the_trashed_facts_are_still_written(self):
        rid = self.mk("in-progress")
        with contextlib.redirect_stdout(_io.StringIO()):
            self.m.do_rm(rid, "치운다")
        _st, dp = self.status_of(rid)
        meta, _b = self.m.read_doc(os.path.join(dp, [
            f for f in os.listdir(dp) if f.startswith(rid)][0]))
        for k in ("trashed", "trashed_by", "trashed_how"):
            self.assertTrue(str(meta.get(k) or "").strip(), k)


class TheScreenSaysItFirst(unittest.TestCase):
    """누르기 전에 말한다 — 누른 뒤에 아는 것은 통보다."""

    def setUp(self):
        with open(TIDY, encoding="utf-8") as f:
            self.src = f.read()

    def test_the_confirm_dialog_warns_about_live_work(self):
        self.assertIn("tidyInProgressWarn", self.src)
        i = self.src.index("function tidyInProgressWarn")
        seg = self.src[i:i + 900]
        self.assertIn('status === "in-progress"', seg, "무엇을 보는지가 없다")
        self.assertIn("취소", seg, "버리면 무엇이 되는지 말하지 않는다")

    def test_the_warning_is_inside_the_trash_confirm(self):
        i = self.src.index("function tidyConfirmRm")
        seg = self.src[i:i + 1200]
        self.assertIn("tidyInProgressWarn(ids)", seg,
                      "확인 창이 그 경고를 부르지 않는다")
        # 되돌리기 안내보다 **먼저** 말한다 — 판정에 필요한 것이 앞이다
        self.assertLess(seg.index("tidyInProgressWarn"), seg.index("되돌릴 수"),
                        "되돌리기 안내 뒤에 말한다 — 판정이 그 아래 묻힌다")


if __name__ == "__main__":
    unittest.main()
