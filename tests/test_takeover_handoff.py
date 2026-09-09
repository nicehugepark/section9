"""가져오기 뒤 이 컴퓨터가 이어받게 (REQ-20260909-010).

실사고 2026-09-09 12:46~12:50: 맥 대시보드의 「이 컴퓨터로 가져오기」가 리스 한 줄만
옮겼다 — 이 컴퓨터의 세션은 아무 통지도 못 받았고 `s9 next` 에도 오르지 않았으며,
저쪽(WSL) 세션은 계속 일하다 다음 진전에서 리스를 도로 가져갔다. 주인이 두 번 누르고
「맥에서 처리 중인가?」라고 물었다.

계약(REQ-20260909-050 결정):
  ① 저쪽이 아직 진전을 내는 중(renewed 가 STALLED_WIN 안)이면 이관을 막는다 — 판정은
     doc_lease_acquire 한 곳.
  ② 멈춘 요청은 실제로 옮기고(lease.via=takeover) 이 컴퓨터의 실행 중인 세션 수신함에
     kind=event 한 줄을 넣는다; `s9 next`·`s9 handoff` 가 그 요청을 올린다.
  ③ 옛 세션은 `s9 handoff`(훅이 매 턴 싣는다)로 「이어받았다 — 마무리하고 release」를 받는다.
  ④ update_active_reqs 는 거부를 반환값으로 말한다.

실행: python3 tests/ takeover_handoff
임시 S9_ROOT · 함수 단위(tests/test_code_default_project.py 의 load 본보기) · 훅은
tests/test_cross_session_not_request.py 본보기(run 을 가로챈다).
"""
import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9.py")
HOOK = os.path.join(REPO, "bin", "s9-audit-prompt")

for _k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_JOB_REQ"):
    os.environ.pop(_k, None)


def _load_file(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load(root):
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        return _load_file("s9_tko_%d" % abs(hash(root)), S9)
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


def ago(sec):
    return (datetime.datetime.now().astimezone()
            - datetime.timedelta(seconds=sec)).isoformat(timespec="seconds")


HERE_M, THERE_M = "here-box", "there-box"
SID_LIVE = "aaaa1111"       # 이 컴퓨터의 실행 중인 리드 세션
SID_OLD = "bbbb2222"        # 리스를 잃은 옛 세션 (③)


class TakeoverHandoff(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9-tko-")
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = HERE_M
        os.environ["S9_USER"] = "me"
        cls.m = load(cls.root)
        with contextlib.redirect_stdout(io.StringIO()):
            cls.m.cmd_init(type("A", (), {})())
        cls.m.do_user_add("me", role="admin")
        cls.m.do_user_add("other")
        os.makedirs(cls.m.STATE, exist_ok=True)
        # 세션 생존·수신 대기는 프로세스 표를 보는 판정이다 — 임시 루트에서는
        # 바인딩이 있으면 살아 있는 것으로 둔다(재는 것은 이관의 동작이지 생존 판정이 아니다).
        cls.m.chat_live = lambda b, win=300: bool(b) and not b.get("ended")
        cls.m._inbox_watch_alive = lambda sid: bool(sid)

    @classmethod
    def tearDownClass(cls):
        for k in ("S9_ROOT", "S9_MACHINE", "S9_USER", "S9_SESSION"):
            os.environ.pop(k, None)
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        os.environ.pop("S9_SESSION", None)
        self.n = getattr(TakeoverHandoff, "_n", 0) + 1
        TakeoverHandoff._n = self.n

    # ---- 픽스처 ------------------------------------------------------------
    def doc(self, *, status="in-progress", lease=None, needs_os="", created_sec=3600):
        rid = f"REQ-20260909-{self.n:03d}-tk{self.n:02d}"
        path = os.path.join(self.m.VAULT, "requests", "2026", "09", rid + ".md")
        meta = {"id": rid, "type": "request", "title": f"t{self.n}", "summary": "s",
                "goal": "g", "status": status, "size": "S", "user": "me",
                "machine": THERE_M, "created": ago(created_sec), "updated": ago(60),
                "status_since": ago(created_sec), "priority": 50}
        if lease:
            meta["lease"] = lease
        if needs_os:
            meta["needs_os"] = needs_os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.m.write_doc(path, meta, "\n## Original\n\no\n\n## Notes\n\n## History\n")
        self.m.rebuild_index(quiet=True)
        return rid

    def lease_there(self, renewed_sec, user="me"):
        return {"user": user, "machine": THERE_M, "session": "s-th1",
                "since": ago(renewed_sec + 600), "renewed": ago(renewed_sec)}

    def binding(self, sid, reqs=(), user="me"):
        b = {"machine": HERE_M, "session": sid, "user": user, "history": [],
             "active_reqs": list(reqs), "claim_at": {r: ago(60) for r in reqs}}
        with open(os.path.join(self.m.STATE, f"{HERE_M}__{sid}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(b, f)
        return b

    def local(self, user="me", session=SID_LIVE):
        return {"user": user, "machine": HERE_M, "role": self.m.user_role(user),
                "session": session}

    def lease(self, rid):
        return self.m.doc_lease(self.m.read_doc(self.m.locate(rid))[0])

    def inbox_lines(self, sid):
        p = self.m.chat_inbox_path(sid)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    # ---- T1 저쪽이 실행 중이면 옮기지 않는다 --------------------------------
    def test_t1_a_working_lease_elsewhere_is_not_taken(self):
        win = self.m.STALLED_WIN
        for sec in (0, win - 120):
            rid = self.doc(lease=self.lease_there(sec))
            ok, code, why = self.m.doc_lease_acquire(
                rid, "claim", local=self.local(), takeover=True)
            self.assertEqual((ok, code), (False, "busy-elsewhere"), (sec, why))
            self.assertIn(f"{THERE_M} 에서 진행 중", why)
            self.assertIn("저쪽이 멈춘 뒤 가져올 수 있습니다", why)
            self.assertEqual(self.lease(rid)["machine"], THERE_M, sec)
            self.assertNotIn("via", self.lease(rid))
        # 화면이 부르는 경로도 같은 판정이고, 수신함에는 아무것도 가지 않는다
        self.binding(SID_LIVE)
        rid = self.doc(lease=self.lease_there(0))
        ok, code, why, sid = self.m.takeover_handoff(rid, "me", local=self.local())
        self.assertEqual((ok, code, sid), (False, "busy-elsewhere", ""))
        self.assertEqual(self.inbox_lines(SID_LIVE), [])
        self.assertEqual(self.lease(rid)["machine"], THERE_M)

    # ---- T2 멈춘 요청은 옮기고 이 컴퓨터의 세션에 알린다 --------------------
    def test_t2_a_stopped_lease_moves_and_the_live_session_hears_it(self):
        self.binding(SID_LIVE)
        rid = self.doc(lease=self.lease_there(self.m.STALLED_WIN + 60))
        ok, code, why, sid = self.m.takeover_handoff(rid, "me", local=self.local())
        self.assertEqual((ok, code, sid), (True, "takeover", SID_LIVE), why)
        l = self.lease(rid)
        self.assertEqual((l["user"], l["machine"], l["session"], l.get("via")),
                         ("me", HERE_M, SID_LIVE, "takeover"))
        body = self.m.read_doc(self.m.locate(rid))[1]
        self.assertIn(f"lease: takeover me@{THERE_M} -> me@{HERE_M}", body)
        lines = self.inbox_lines(SID_LIVE)
        self.assertEqual(len(lines), 1, lines)
        self.assertEqual(lines[0]["kind"], "event")
        self.assertIn(f"[이관] {rid} 를 이 컴퓨터가 이어받는다", lines[0]["text"])
        self.assertIn(f"s9 last {rid} --add", lines[0]["text"])
        # 두 번 눌러도 리스는 이미 이 컴퓨터라 renew 로 조용하고, 줄은 더 안 쌓인다
        ok2, code2, _w, sid2 = self.m.takeover_handoff(rid, "me", local=self.local())
        self.assertTrue(ok2, code2)
        self.assertEqual(len(self.inbox_lines(SID_LIVE)), 2 if sid2 else 1)

    # ---- T3 s9 next · handoff 에 오르고, 집으면 내려간다 ---------------------
    def test_t3_next_offers_it_until_a_session_here_claims_it(self):
        self.binding(SID_LIVE)
        rid = self.doc(lease=self.lease_there(self.m.STALLED_WIN + 60))
        ok, _c, _w, _s = self.m.takeover_handoff(rid, "me", local=self.local())
        self.assertTrue(ok)
        os.environ["S9_SESSION"] = SID_LIVE
        rows = self.m.handoff_rows(self.local())
        incoming = {r["id"]: r for r in rows["incoming"]}
        self.assertIn(rid, incoming)
        self.assertIn("아직 시작하지 않음", incoming[rid]["reason"])
        p = self.m.next_pickup(user="me")
        self.assertIsNotNone(p, "s9 next 가 옮겨진 요청을 올리지 않는다")
        # 앞 시험이 남긴 이관도 같은 자격이다 — 다음 한 건은 그 무리 안에서 온다
        self.assertIn(p["id"], incoming)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.m.cmd_handoff(type("A", (), {"quiet": True, "session": SID_LIVE})())
        self.assertIn(f"[이관] {rid} 를 이 컴퓨터가 이어받는다", out.getvalue())
        # 이 컴퓨터의 세션이 집는다 — 리스가 새로 지어져 표가 사라진다
        with contextlib.redirect_stderr(io.StringIO()):
            self.m._claim_req(HERE_M, SID_LIVE, rid)
        self.assertNotIn("via", self.lease(rid))
        self.assertEqual(self.lease(rid)["machine"], HERE_M)
        self.assertNotIn(rid, [r["id"] for r in self.m.handoff_rows(self.local())["incoming"]])
        self.assertNotEqual((self.m.next_pickup(user="me") or {}).get("id"), rid)

    # ---- T4 옛 세션은 「이어받았다」를 받는다 (훅 주입) ----------------------
    def test_t4_the_old_session_is_told_to_wrap_up_and_release(self):
        rid = self.doc(lease={"user": "me", "machine": "mac-box", "session": "s-mac",
                              "since": ago(30), "renewed": ago(30), "via": "takeover"})
        self.binding(SID_OLD, reqs=[rid])
        rows = self.m.handoff_rows(self.local(session=SID_OLD), session=SID_OLD)
        self.assertEqual([r["id"] for r in rows["outgoing"]], [rid])
        txt = rows["outgoing"][0]["text"]
        self.assertIn("me@mac-box 이 이어받았다", txt)
        self.assertIn(f"s9 claim {rid} --release", txt)
        self.assertNotIn(rid, [r["id"] for r in rows["incoming"]])   # 남의 머신 리스는 이어받을 것이 아니다
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.m.cmd_handoff(type("A", (), {"quiet": True, "session": SID_OLD})())
        line = out.getvalue().strip()
        self.assertIn("이어받았다", line)
        # 훅이 그 줄을 매 턴 싣는다 — run 을 가로채 `s9 handoff --quiet` 의 답만 준다
        hook = _load_file("s9_audit_prompt_tko", HOOK)
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append(argv)
            if argv and argv[0] == "handoff":
                return mock.Mock(returncode=0, stdout=line + "\n")
            if argv and argv[0] == "log":
                self.m.session_log_append(env["S9_SESSION"], argv[1])
            if argv and argv[0] == "new":
                return mock.Mock(returncode=0, stdout=f"{rid}: created\n")
            return mock.Mock(returncode=0, stdout="")

        payload = json.dumps({"prompt": "대시보드 헤더에 새로고침 버튼을 추가해줘",
                              "session_id": SID_OLD + "ffff", "cwd": self.root})
        with mock.patch.object(hook, "run", fake_run), \
                mock.patch.dict(os.environ, {"S9_ROOT": self.root}), \
                mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                mock.patch.object(sys, "stdout", io.StringIO()) as out:
            hook.main()
        emitted = out.getvalue()
        self.assertIn(("handoff", "--quiet"), calls)
        self.assertIn("me@mac-box 이 이어받았다", emitted)
        self.assertIn(f"s9 claim {rid} --release", emitted)

    # ---- T5 update_active_reqs 는 거부를 말한다 -----------------------------
    def test_t5_update_active_reqs_reports_a_refused_lease(self):
        os.environ["S9_SESSION"] = "cccc3333"
        rid = self.doc(lease=self.lease_there(0))
        with contextlib.redirect_stderr(io.StringIO()):
            res = self.m.update_active_reqs(rid, "in-progress")
        self.assertIsInstance(res, dict, "거부가 None 으로 사라진다")
        self.assertFalse(res["registered"])
        self.assertEqual(res["lease"], "busy-elsewhere")
        self.assertTrue(res["why"])
        b = self.m.read_binding(HERE_M, "cccc3333")
        self.assertNotIn(rid, (b or {}).get("active_reqs", []))
        # 자유로운 문서는 등록되고 리스 코드가 함께 온다
        rid2 = self.doc()
        with contextlib.redirect_stderr(io.StringIO()):
            res2 = self.m.update_active_reqs(rid2, "in-progress")
        self.assertTrue(res2["registered"], res2)
        self.assertIn(res2["lease"], ("free", "renew", "takeover-local"))
        self.assertIn(rid2, self.m.read_binding(HERE_M, "cccc3333")["active_reqs"])

    # ---- T6 회귀 -----------------------------------------------------------
    def test_t6_assign_and_expired_takeover_and_here_pickup_are_unchanged(self):
        # 담당 바꾸기(사람)는 그대로: 리스가 지워지고 History 한 줄
        rid = self.doc(lease=self.lease_there(0))
        res = self.m.do_assign(rid, "other", actor="me")
        self.assertTrue(res["ok"] and res["changed"], res)
        meta, body = self.m.read_doc(self.m.locate(rid))
        self.assertEqual(meta["user"], "other")
        self.assertNotIn("lease", meta)
        self.assertIn("assignee: me -> other", body)
        # 만료된 리스(TTL 밖)는 여전히 옮길 수 있다
        rid2 = self.doc(lease=self.lease_there(self.m.DOC_LEASE_TTL + 60))
        ok, code, why = self.m.doc_lease_acquire(rid2, "claim", local=self.local(),
                                                 takeover=True)
        self.assertEqual((ok, code), (True, "takeover"), why)
        self.assertEqual(self.lease(rid2)["machine"], HERE_M)
        # needs_os 자동 집기는 그대로 (REQ-20260909-012)
        self.m.do_user_config_set("me", "auto_resume", "on", actor="me")
        rid3 = self.doc(status="open", needs_os=self.m.os_platform(), created_sec=600)
        spawned = []
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            got = self.m.here_watch_tick(grace=0, _spawn=lambda did, m: spawned.append(did) or True)
        self.assertEqual(got, [rid3])
        self.assertEqual(self.m.read_doc(self.m.locate(rid3))[0]["status"], "in-progress")


if __name__ == "__main__":
    unittest.main()
