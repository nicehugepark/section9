"""이어 친 말의 자리는 맥락이 정한다 (REQ-20260918-017-62x6).

실제 사고 2026-09-18 두 번.
  ① 사람이 한 생각을 두 줄로 나눠 쳤는데 줄마다 요청이 섰다 — 18:51:45/18:52:01 이
     015·016 으로, 18:54:35/18:54:52 가 017·018 로 갈렸다.
  ② 그것을 「붙어 있으면 앞 요청에 붙인다」(2분 창 + 리드 응답 전)로 고쳤더니 주인이
     그것도 반려했다: 「이어서 친 말을 무조건 한 요청이 아니고 같은 맥락을 보고 하나로
     해야지. **몇개 건너띄더라도**」 (19:36).

그래서 일을 가른다 — **기계는 후보를 좁히고, 뜻은 리드가 읽는다.**

  C1 `_continuation_candidates` 는 기계가 아는 사실로만 후보를 좁힌다(사람이 낸 ·
     이 세션이 세운 · 아직 열린 · 창 안). **고르지 않는다** — 리드가 이미 답한
     요청도 후보로 남는다(사람은 답을 듣고 나서 그 얘기로 돌아온다).
  C2 보류 자리 — 훅이 붙들어 둔 초안 하나. 새 말이 오면 앞 것이 밀려나고, 밀려난
     사실이 부른 쪽에 돌아간다.
  C3 훅은 후보가 있으면 **요청을 세우지 않고** 붙들어 둔 뒤 후보를 리드에게 건넨다.
  C4 후보가 없으면 종전대로 요청이 선다.
  C5 리드가 자리를 안 정하면 턴 끝에 Stop 훅이 세운다 — 말이 사라지지는 않는다.
  C6 `--from-pending` 으로 세운 요청은 **사람의 것**이고, 그 명령은 stdin 을 안
     기다린다. 둘 다 모래상자 왕복(실제 훅 두 개를 실행)에서 드러난 결함이다:
     stdin 을 먼저 읽어 사람이 손으로 치는 자리에서 멎었고, origin 이 agent 로
     찍혀 그 요청이 **다음 말의 후보가 못 됐다** — 세 번째 줄부터 계보가 끊긴다.

실행: python3 tests/ continuation
"""
import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")
STOP = os.path.join(HERE, "..", "bin", "s9-audit-response")
S9SRC = os.path.join(HERE, "..", "bin", "s9.py")

# 격리: 무인 워커 세션에서 스위트를 돌리면 상속된 S9_AUTO_RESUME 이 hook.main() 을
# 다른 분기로 보낸다 (tests/test_audit_prompt.py 와 같은 이유).
os.environ.pop("S9_AUTO_RESUME", None)


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


hook = _load("s9_audit_prompt_cont", HOOK)
NOW = "2026-09-18T19:40:00+09:00"


def _ago(sec):
    return (datetime.datetime.fromisoformat(NOW)
            - datetime.timedelta(seconds=sec)).isoformat()


class TheMachineOnlyNarrowsTheCandidates(unittest.TestCase):
    """C1 — 후보를 좁히는 조건 넷. 그 밖의 것으로는 고르지 않는다."""

    def setUp(self):
        self.m = _load("s9_cont", S9SRC)

    def cands(self, docs, binding=None, catalog=None):
        b = {"last_req": "", "active_reqs": []}
        b.update(binding or {})
        cat = catalog if catalog is not None else [
            {"id": i, "type": "request"} for i in docs]

        def read_doc(path):
            return docs[path], ""

        with mock.patch.object(self.m, "read_binding", lambda *a: b), \
             mock.patch.object(self.m, "load_catalog", lambda *a, **k: list(reversed(cat))), \
             mock.patch.object(self.m, "locate", lambda i: i if i in docs else ""), \
             mock.patch.object(self.m, "read_doc", read_doc), \
             mock.patch.object(self.m, "now_iso", lambda: NOW):
            return self.m._continuation_candidates("m1", "983ee0e9")

    @staticmethod
    def doc(**kw):
        d = {"type": "request", "origin": "human", "status": "open",
             "session": "983ee0e9", "created": _ago(60), "title": "제목",
             "summary": "요약"}
        d.update(kw)
        return d

    def test_c1a_open_human_requests_of_this_session_are_candidates(self):
        """열린 · 사람이 낸 · 이 세션의 요청이 후보다 — 최신 것부터."""
        docs = {"REQ-20260918-015-62x6": self.doc(created=_ago(300), title="마크 눈"),
                "REQ-20260918-017-62x6": self.doc(created=_ago(60), title="이어 친 말")}
        got = self.cands(docs)
        self.assertEqual([r["id"] for r in got],
                         ["REQ-20260918-017-62x6", "REQ-20260918-015-62x6"])
        self.assertEqual(got[0]["title"], "이어 친 말")

    def test_c1b_an_answered_request_is_still_a_candidate(self):
        """**리드가 답했어도 후보다** — 주인 반려의 핵심이 이 줄이다.

        예전 규칙은 「리드가 답하기 전」만 자리로 봤다. 그러면 사람이 답을 듣고
        그 얘기로 돌아와 한 줄을 더 쳐도 그 말은 새 요청으로 선다.
        """
        docs = {"REQ-20260918-015-62x6": self.doc(created=_ago(600))}
        self.assertEqual([r["id"] for r in self.cands(docs)],
                         ["REQ-20260918-015-62x6"])

    def test_c1c_several_in_between_do_not_hide_an_older_one(self):
        """사이에 몇이 끼어도 앞선 것이 후보에서 빠지지 않는다 — 「몇개 건너띄더라도」."""
        docs = {"REQ-20260918-0%02d-62x6" % n: self.doc(created=_ago(600 - n * 10))
                for n in (15, 16, 17, 18)}
        got = [r["id"] for r in self.cands(docs)]
        self.assertIn("REQ-20260918-015-62x6", got)
        self.assertEqual(len(got), 4)

    def test_c1d_the_four_mechanical_filters(self):
        """사람이 낸 · 이 세션 · 열린 · 창 안 — 넷 중 하나라도 어긋나면 후보가 아니다."""
        for kw in ({"origin": "agent"}, {"session": "ffff0000"},
                   {"status": "done"}, {"status": "review"},
                   {"created": _ago(self.m.CONTINUATION_WINDOW_SEC + 1)},
                   {"type": "knowledge"}):
            docs = {"REQ-20260918-015-62x6": self.doc(**kw)}
            self.assertEqual(self.cands(docs), [], kw)

    def test_c1e_the_list_is_capped(self):
        """한 번에 보이는 후보 수에 상한이 있다 — 목록이 길면 아무도 안 읽는다."""
        docs = {"REQ-20260918-%03d-62x6" % n: self.doc(created=_ago(n))
                for n in range(1, 30)}
        self.assertEqual(len(self.cands(docs)), self.m.CONTINUATION_MAX)


class TheHeldWordWaitsForTheLead(unittest.TestCase):
    """C2 — 붙들어 둔 자리 하나. 새 말이 오면 앞 것이 밀려나고 그 사실이 돌아간다."""

    def setUp(self):
        self.m = _load("s9_cont2", S9SRC)
        self.store = {}

    def patched(self):
        return mock.patch.multiple(
            self.m,
            read_binding=mock.DEFAULT, write_binding=mock.DEFAULT,
            acquire_lock=mock.DEFAULT, release_lock=mock.DEFAULT)

    def test_c2_hold_read_and_clear(self):
        b = {"machine": "m1", "session": "983ee0e9"}
        with mock.patch.object(self.m, "read_binding", lambda *a: b), \
             mock.patch.object(self.m, "write_binding", lambda x: b.update(x)), \
             mock.patch.object(self.m, "acquire_lock", lambda *a, **k: None), \
             mock.patch.object(self.m, "release_lock", lambda *a, **k: None):
            self.assertEqual(self.m.read_pending("m1", "983ee0e9"), {})
            prev = self.m.write_pending("m1", "983ee0e9", {"title": "첫 말", "body": "본문"})
            self.assertEqual(prev, {})
            self.assertEqual(self.m.read_pending("m1", "983ee0e9")["title"], "첫 말")
            prev = self.m.write_pending("m1", "983ee0e9", {"title": "둘째 말", "body": "본문2"})
            self.assertEqual(prev["title"], "첫 말", "밀려난 말이 조용히 사라졌다")
            self.m.write_pending("m1", "983ee0e9", None)
            self.assertEqual(self.m.read_pending("m1", "983ee0e9"), {})


class TheHookHoldsInsteadOfFiling(unittest.TestCase):
    """C3·C4 — 훅은 고르지 않는다. 후보가 있으면 붙들고, 없으면 종전대로 세운다."""

    CANDS = ("REQ-20260918-015-62x6\topen\t300\t마크 눈 삼각형\t점 셋을 뒤집는다\n"
             "REQ-20260918-017-62x6\tin-progress\t60\t이어 친 말은 한 요청으로\t훅이 기계적이다\n")
    LINE = "검은 점이 조금 더 작고 서로 더 모여 있어야 한다. 지금은 너무 벌어져 있으니 좁혀줘"

    def turn(self, prompt, cands=CANDS):
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append(argv)
            if argv[:2] == ("last", "--continuation"):
                return mock.Mock(returncode=0, stdout=cands)
            if argv[:2] == ("last", "--pending-hold"):
                return mock.Mock(returncode=0, stdout="")
            if argv[0] == "new":
                return mock.Mock(returncode=0, stdout="REQ-20260918-019-62x6  x.md")
            if argv[0] == "user":
                return mock.Mock(returncode=0, stdout="nicehugepark")
            return mock.Mock(returncode=0, stdout="")

        payload = json.dumps({"prompt": prompt, "session_id": "983ee0e9aa"})
        with mock.patch.object(hook, "run", fake_run), \
             mock.patch.object(hook, "_session_belongs_here", lambda d: True), \
             mock.patch.object(hook, "_account_registered", lambda: True), \
             mock.patch.object(hook, "pending_context", lambda *a, **k: ""), \
             mock.patch.object(hook, "session_role", lambda e: "member"), \
             mock.patch.object(sys, "stdin", io.StringIO(payload)), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            hook.main()
        return calls, out.getvalue()

    def test_c3a_no_card_is_filed_when_candidates_exist(self):
        calls, _ = self.turn(self.LINE)
        self.assertFalse([a for a in calls if a[0] == "new"],
                         "후보가 있는데 요청을 세웠다 — 훅이 맥락을 안 읽고 고른 것이다")
        self.assertTrue([a for a in calls if a[:2] == ("last", "--pending-hold")],
                        "말을 붙들지 않았다")

    def test_c3b_the_lead_is_handed_every_candidate(self):
        _, out = self.turn(self.LINE)
        self.assertIn("REQ-20260918-015-62x6", out)
        self.assertIn("REQ-20260918-017-62x6", out, "앞선 후보가 목록에서 빠졌다")
        self.assertIn("--from-pending", out, "고른 뒤 무엇을 칠지 안 알려 준다")

    def test_c3c_a_project_tagged_line_is_not_held(self):
        """프로젝트를 스스로 지목한 말은 새 요청을 세우겠다는 표시다."""
        calls, _ = self.turn("[프로젝트: section9]\n" + self.LINE)
        self.assertTrue([a for a in calls if a[0] == "new"])
        self.assertFalse([a for a in calls if a[:2] == ("last", "--pending-hold")])

    def test_c4_without_candidates_a_request_is_filed_as_before(self):
        calls, _ = self.turn(self.LINE, cands="")
        self.assertTrue([a for a in calls if a[0] == "new"],
                        "후보가 없는데도 말을 붙들었다 — 그 말은 어디에도 안 선다")


class TheTurnEndDoesNotDropIt(unittest.TestCase):
    """C5 — 리드가 자리를 안 정했으면 Stop 훅이 세운다."""

    def setUp(self):
        self.stop = _load("s9_audit_response_cont", STOP)

    def flush(self, pending):
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append(argv)
            if argv[:2] == ("last", "--pending"):
                return mock.Mock(returncode=0, stdout=pending)
            return mock.Mock(returncode=0, stdout="")

        with mock.patch.object(self.stop, "run", fake_run):
            self.stop.flush_pending({})
        return calls

    def test_c5a_a_held_word_becomes_a_request(self):
        calls = self.flush("2026-09-18T19:40:00+09:00\t마크 눈 크기와 간격\n")
        made = [a for a in calls if a[0] == "new"]
        self.assertTrue(made, "붙들고 있던 말이 턴 끝에 사라졌다")
        self.assertIn("--from-pending", made[0])
        self.assertIn("마크 눈 크기와 간격", made[0])

    def test_c5b_nothing_held_nothing_filed(self):
        self.assertFalse([a for a in self.flush("") if a[0] == "new"])

class TheLeadsOwnHandDoesNotBreakTheChain(unittest.TestCase):
    """C6 — `s9 new request --from-pending` 의 두 자리. 진짜 s9 를 돌려 잰다."""

    @classmethod
    def setUpClass(cls):
        import shutil
        import subprocess
        import tempfile
        cls.root = tempfile.mkdtemp(prefix="s9cont-")
        cls.s9 = os.path.normpath(os.path.join(HERE, "..", "bin", "s9"))
        cls.env = dict(os.environ)
        cls.env["S9_ROOT"] = cls.root
        cls.env["S9_SESSION"] = "cccc3333"
        cls._rm = lambda: shutil.rmtree(cls.root, ignore_errors=True)
        for argv in (["init"], ["user", "add", "tester"]):
            subprocess.run([sys.executable, cls.s9, *argv], env=cls.env,
                           capture_output=True, timeout=120)

    @classmethod
    def tearDownClass(cls):
        cls._rm()

    def test_c6_from_pending_is_human_and_never_waits_on_stdin(self):
        import json as _json
        import subprocess
        subprocess.run([sys.executable, self.s9, "last", "--pending-hold"],
                       input=_json.dumps({"title": "붙들린 말", "body": "사람이 친 말"}),
                       env=self.env, capture_output=True, text=True, timeout=120)
        # stdin 을 **열어 둔 채** 부른다 — 사람이 터미널에서 치는 모양이다.
        # 본문을 stdin 에서 읽으려 들면 여기서 영영 멎는다.
        p = subprocess.Popen(
            [sys.executable, self.s9, "new", "request", "--from-pending",
             "--title", "붙들린 말 세우기", "--summary", "요약",
             "--size", "S", "--goal", "판별 가능한 한 문장", "--user", "tester"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=self.env, text=True)
        try:
            out, _err = p.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            p.kill()
            self.fail("--from-pending 이 stdin 을 기다린다 — 사람이 손으로 치면 멎는다")
        rid = (out or "").split()[0] if out.strip() else ""
        self.assertTrue(rid.startswith("REQ-"), out)
        doc = subprocess.run([sys.executable, self.s9, "show", rid, "--meta"],
                             env=self.env, capture_output=True, text=True,
                             timeout=120).stdout
        self.assertIn("origin: human", doc,
                      "리드의 손을 거쳤다고 사람의 말이 아니게 되면 그 요청은 "
                      "다음 말의 후보가 못 된다 — 세 번째 줄부터 계보가 끊긴다")


if __name__ == "__main__":
    unittest.main()
