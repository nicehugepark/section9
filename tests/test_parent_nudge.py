"""parent 없는 사람 요청을 짚는다 (REQ-20260909-073).

실측 2026-09-09: 9월 요청 476 중 parent 없음 204. 뿌리는 채팅 경로 — 훅이 세우는
요청은 parent 없이 서고, 리드는 착수 때 제목만 고치고 잇지 않는다. 규약(파생은
--parent)은 있었지만 그 경로에 그것을 짚는 손이 없었다. 여기서 재는 것 넷:
① `root: true` 표시와 parent 와의 배타, ② parent_nudge 의 판정과 후보(낱말 겹침),
③ 착수 전이가 경고를 내되 막지 않음, ④ `linkcheck --parents` 목록과 훅 주입 한 줄.

실행: python3 tests/ parent_nudge
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")
S9PY = os.path.join(ROOT, "bin", "s9.py")
HOOK = os.path.join(ROOT, "bin", "s9-audit-prompt")


def load(path, root, name):
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, path))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


class ParentNudge(unittest.TestCase):
    SID = "s1s1s1s1"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9pn-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_SESSION": cls.SID}
        cls.env.pop("S9_AUTO_RESUME", None)
        cls.cli("init")
        cls.cli("user", "add", "alice")
        # 이 세션이 다루는 요청 둘 — 후보의 재료
        cls.A = cls.mk("대시보드 카드 색 고침", "카드 색이 스킨을 따르지 않는다", "--tag", "dashboard")
        cls.B = cls.mk("Jira 토큰 만료 처리", "토큰이 만료되면 재발급한다", "--tag", "jira")
        cls.cli("status", cls.A, "in-progress", "--note", "착수")
        cls.cli("status", cls.B, "in-progress", "--note", "착수")
        # 사람이 채팅으로 낸(훅 경로와 같은 --origin human) parent 없는 요청
        cls.X = cls.mk("카드 색이 안 바뀐다", "대시보드 카드 색이 그대로다", "--origin", "human")
        cls.m = load(S9PY, cls.tmp, "s9_parent_nudge")

    @classmethod
    def cli(cls, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True, env=cls.env, timeout=30)
        if expect is not None:
            assert r.returncode == expect, f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}"
        return r

    @classmethod
    def mk(cls, title, summary, *extra):
        return cls.cli("new", "request", "--title", title, "--summary", summary,
                       "--goal", "g", "--size", "S", "--user", "alice",
                       "--body", "x", *extra).stdout.split()[0]

    def meta(self, doc_id):
        m, _ = self.m.read_doc(self.m.locate(doc_id))
        return m

    def row(self, doc_id):
        return next(r for r in self.m.load_catalog() if r["id"] == doc_id)

    # S1 -------------------------------------------------------------
    def test_s1_set_root_is_stored_and_indexed(self):
        r = self.mk("새 주제 하나", "아무것과도 잇지 않는다", "--origin", "human")
        self.assertFalse(self.m.doc_root(self.meta(r)))
        self.cli("set", r, "--root")
        self.assertTrue(self.m.doc_root(self.meta(r)))
        self.assertTrue(self.row(r)["root"], "catalog 행에 root 가 실리지 않았다")
        self.assertIn("root:", open(self.m.locate(r), encoding="utf-8").read().split("\n---", 1)[0])
        self.cli("set", r, "--no-root")
        self.assertFalse(self.m.doc_root(self.meta(r)))

    def test_s1b_new_request_root(self):
        r = self.mk("뿌리로 세운 요청", "s", "--root")
        self.assertTrue(self.m.doc_root(self.meta(r)))
        self.assertTrue(self.row(r)["root"])

    # S2 -------------------------------------------------------------
    def test_s2_root_and_parent_are_exclusive(self):
        child = self.mk("파생 요청", "s", "--parent", self.A)
        res = self.cli("set", child, "--root", expect=None)
        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(self.m.doc_root(self.meta(child)))
        self.assertEqual(self.meta(child).get("parent"), self.A)
        rooted = self.mk("뿌리 요청", "s", "--root")
        res = self.cli("link", rooted, "--parent", self.A, expect=None)
        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.meta(rooted).get("parent", ""), "")
        self.assertNotIn(rooted, self.meta(self.A).get("children") or [])
        res = self.cli("new", "request", "--title", "둘 다", "--summary", "s", "--goal", "g",
                       "--size", "S", "--user", "alice", "--body", "x",
                       "--root", "--parent", self.A, expect=None)
        self.assertNotEqual(res.returncode, 0)

    # S3 -------------------------------------------------------------
    def test_s3_nudge_only_for_human_without_parent_or_root(self):
        base = {"id": "REQ-20990101-001", "type": "request", "status": "in-progress",
                "title": "t", "summary": "s", "tags": []}
        self.assertIn("parent 가 없습니다", self.m.parent_nudge({**base, "origin": "human"}))
        self.assertEqual(self.m.parent_nudge({**base, "origin": "agent"}), "")
        self.assertEqual(self.m.parent_nudge({**base}), "", "origin 없는 옛 문서는 짚지 않는다")
        self.assertEqual(self.m.parent_nudge({**base, "origin": "human", "parent": self.A}), "")
        self.assertEqual(self.m.parent_nudge({**base, "origin": "human", "root": "true"}), "")
        self.assertEqual(self.m.parent_nudge({**base, "origin": "human", "status": "cancelled"}), "")

    # S4 -------------------------------------------------------------
    def test_s4_candidates_ranked_by_word_overlap(self):
        cands = self.m.parent_candidates(self.meta(self.X), session=self.SID)
        ids = [c[0] for c in cands]
        self.assertLessEqual(len(ids), 3)
        self.assertEqual(ids[0], self.A, f"낱말이 겹치는 {self.A} 가 먼저여야 한다: {cands}")
        self.assertIn(self.B, ids)
        self.assertNotIn(self.X, ids, "자기 자신은 후보가 아니다")
        self.assertEqual(self.m.parent_candidates(self.meta(self.X), session="zzzzzzzz"), [],
                         "다른 세션이 다룬 것은 후보가 아니다")
        nudge = self.m.parent_nudge(self.meta(self.X), session=self.SID)
        self.assertIn(self.A, nudge)
        self.assertIn("후보", nudge)

    # S5 -------------------------------------------------------------
    def test_s5_start_transition_warns_but_succeeds(self):
        y = self.mk("색 문제 이어서", "대시보드 카드 색", "--origin", "human")
        res = self.cli("status", y, "in-progress", "--note", "착수")
        self.assertEqual(self.meta(y).get("status"), "in-progress")
        out = res.stdout + res.stderr
        self.assertIn("parent 가 없습니다", out)
        self.assertIn(self.A, out)
        # parent 를 이으면 다음 전이에서는 말하지 않는다
        self.cli("link", y, "--parent", self.A)
        res = self.cli("status", y, "review", "--note", "확인", "--force")
        self.assertNotIn("parent 가 없습니다", res.stdout + res.stderr)

    # S6 -------------------------------------------------------------
    def test_s6_linkcheck_parents_lists_only_bare_human_requests(self):
        rooted = self.mk("뿌리 목록 시험", "s", "--root", "--origin", "human")
        child = self.mk("자식 목록 시험", "s", "--parent", self.A, "--origin", "human")
        gone = self.mk("취소 목록 시험", "s", "--origin", "human")
        self.cli("status", gone, "cancelled", "--note", "취소")
        out = self.cli("linkcheck", "--parents").stdout
        ids = [ln.split()[1] for ln in out.splitlines() if ln.startswith("- ")]
        self.assertIn(self.X, ids)
        for absent in (rooted, child, gone, self.A):
            self.assertNotIn(absent, ids, out)
        self.assertEqual(ids, sorted(ids, key=lambda i: self.meta(i)["created"]), "생성일 순이 아니다")
        far = self.cli("linkcheck", "--parents", "--since", "2999-01-01", "--quiet").stdout
        self.assertEqual(far.strip(), "")
        # 세션·착수 필터 — 훅 주입이 쓰는 모양
        mine = self.cli("linkcheck", "--parents", "--session", self.SID, "--started", "--quiet").stdout
        mine_ids = [ln.split()[1] for ln in mine.splitlines() if ln.startswith("- ")]
        self.assertNotIn(self.X, mine_ids, "open 인 것은 착수한 것이 아니다")


class HookInjectsParentless(unittest.TestCase):
    """S7. 매 턴 훅 주입에 「이 세션이 착수한 parent 없는 요청 N건」 한 줄."""

    def run_hook(self, parentless_out):
        hook = load(HOOK, tempfile.mkdtemp(prefix="s9pnh-"), "s9_audit_prompt_pn")
        calls, printed = [], io.StringIO()

        def fake_run(env, *argv, inp=None):
            calls.append(argv)
            out = ""
            if argv[:2] == ("user", "current"):
                out = "alice [source: binding X/y]"
            elif argv[0] == "new":
                out = "REQ-20260909-999  vault/..."
            elif argv[:2] == ("linkcheck", "--parents"):
                out = parentless_out
            return mock.Mock(returncode=0, stdout=out)

        payload = json.dumps({"prompt": "대시보드에 위젯 만들어줘", "session_id": "eeee5555xx"})
        with mock.patch.object(hook, "run", fake_run), \
             mock.patch.object(sys, "stdin", io.StringIO(payload)), \
             mock.patch.object(sys, "stdout", printed):
            hook.main()
        return calls, printed.getvalue()

    def test_s7_line_present_when_any_absent_when_none(self):
        calls, out = self.run_hook("- REQ-20260909-011 2026-09-09 [in-progress] a\n"
                                   "- REQ-20260909-012 2026-09-09 [review] b\n")
        pl = [a for a in calls if a[:2] == ("linkcheck", "--parents")]
        self.assertTrue(pl, calls)
        self.assertIn("--session", pl[0])
        self.assertIn("eeee5555", pl[0])
        self.assertIn("parent 없는 요청 2건: REQ-20260909-011, REQ-20260909-012", out)
        _calls, out = self.run_hook("")
        self.assertNotIn("parent 없는 요청", out)


if __name__ == "__main__":
    unittest.main()
