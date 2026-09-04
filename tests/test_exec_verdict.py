"""실행 귀속은 한 함수가 판정한다 (REQ-20260902-016).

가드가 세 곳·세 기준(워처=만든 머신, next=user, 훅 목록=없음)이라 공유 리포에서
남의 반려 REQ 가 내 리드에게 "지금 이어서 하라"로 주입됐다. `exec_verdict` 하나가
담당자(user)·잠정 머신·역할·종결을 보고, 아홉 자리가 그것을 부른다.

실행: python3 tests/ exec_verdict
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class Verdict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9verdict-")
        env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "here"}
        env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=env)
        for u in ("me", "other", "watcher"):
            subprocess.run([S9, "user", "add", u], capture_output=True, env=env,
                           stdin=subprocess.DEVNULL)
        subprocess.run([S9, "user", "role", "watcher", "viewer"],
                       capture_output=True, env={**env, "S9_USER": "me"},
                       stdin=subprocess.DEVNULL)
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "here"
        spec = importlib.util.spec_from_loader(
            "s9_verdict", importlib.machinery.SourceFileLoader("s9_verdict", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        os.environ.pop("S9_MACHINE", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    def local(self, user="me", machine="here", role="member"):
        return {"user": user, "machine": machine, "role": role}

    def doc(self, **kv):
        d = {"type": "request", "status": "in-progress", "user": "me",
             "machine": "here"}
        d.update(kv)
        return d

    # V1. 내 문서 → free
    def test_verdict(self):
        """Verdict 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("v1_mine_is_free"):
                self.assertEqual(self.m.exec_verdict(self.doc(), self.local()),
                                 (True, "free", ""))

            # V2. 담당 타인 → not-mine (이름 포함)
        with self.subTest("v2_others_doc_is_not_mine"):
                ok, code, why = self.m.exec_verdict(self.doc(user="other"), self.local())
                self.assertFalse(ok)
                self.assertEqual(code, "not-mine")
                self.assertIn("other", why)

            # V3. 같은 사용자·다른 머신 — 만든 머신은 판정에 안 쓴다(D1): 리스가 없으면
            # 어느 컴퓨터든 free, 다른 컴퓨터의 신선한 리스가 있으면 busy-elsewhere
        with self.subTest("v3_same_user_other_machine"):
                d = self.doc(machine="there")
                self.assertEqual(self.m.exec_verdict(d, self.local())[1], "free")
                ts = self.m.now_iso()
                d["lease"] = {"user": "me", "machine": "there", "session": "s1",
                              "since": ts, "renewed": ts}
                for want in ("list", "spawn", "claim"):
                    self.assertEqual(self.m.exec_verdict(d, self.local(), want=want)[1],
                                     "busy-elsewhere", want)

            # V3b. 워처(spawn)는 담당자를 대신하는 자리 — 서버 계정과 담당자가 달라도
            # 이 머신의 문서면 띄운다 (잠정, 020 이 리스로 바꾼다)
        with self.subTest("v3b_spawn_is_on_behalf_of_owner"):
                d = self.doc(user="other", machine="here")
                self.assertTrue(self.m.exec_verdict(d, self.local(), want="spawn")[0])
                self.assertEqual(self.m.exec_verdict(d, self.local(), want="list")[1],
                                 "not-mine")

            # V4. 종결 → closed
        with self.subTest("v4_closed"):
                for st in ("done", "cancelled"):
                    ok, code, _ = self.m.exec_verdict(self.doc(status=st), self.local())
                    self.assertEqual((ok, code), (False, "closed"))

            # V5. 관찰 계정 → observer
        with self.subTest("v5_viewer_is_observer"):
                ok, code, _ = self.m.exec_verdict(self.doc(), self.local(role="viewer"))
                self.assertEqual((ok, code), (False, "observer"))
                # local_facts 가 profile 의 role 을 읽는다
                self.assertEqual(self.m.local_facts("watcher")["role"], "viewer")

            # V7. request 가 아니면 통과
        with self.subTest("v7_non_request_passes"):
                self.assertTrue(self.m.exec_verdict(self.doc(type="knowledge",
                                                             user="other"), self.local())[0])

            # V8. user 없는 옛 문서는 not-mine 이 아니다
        with self.subTest("v8_legacy_without_user"):
                self.assertTrue(self.m.exec_verdict(self.doc(user="", machine=""),
                                                    self.local())[0])
                # assignee 가 있으면 그것이 담당자다
                self.assertEqual(self.m.doc_owner({"user": "me", "assignee": "other"}),
                                 "other")

            # W1. 스폰 게이트가 판정 함수를 쓰고 spawn.log 에 사유가 남는다
        with self.subTest("w1_spawn_gate_uses_verdict_and_logs"):
                m = self.m
                env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "there",
                       "S9_USER": "other"}
                env.pop("S9_SESSION", None)
                out = subprocess.run([S9, "new", "request", "--title", "남의 일",
                                      "--summary", "s", "--size", "S", "--goal", "g",
                                      "--body", "b", "--user", "other"],
                                     capture_output=True, text=True, env=env,
                                     stdin=subprocess.DEVNULL)
                rid = out.stdout.split()[0]
                subprocess.run([S9, "status", rid, "in-progress", "--note", "t"],
                               capture_output=True, env=env, stdin=subprocess.DEVNULL)
                subprocess.run([S9, "user", "config", "other", "auto_resume", "on"],
                               capture_output=True, env=env, stdin=subprocess.DEVNULL)
                meta, _ = m.read_doc(m.locate(rid))
                # 다른 컴퓨터의 신선한 리스 — 워처는 벽시계만 보고 물러난다
                ts = m.now_iso()
                meta["lease"] = {"user": "other", "machine": "there", "session": "x1",
                                 "since": ts, "renewed": ts}
                m.write_doc(m.locate(rid), meta, m.read_doc(m.locate(rid))[1])
                logs, out = [], {}
                with mock.patch.object(m, "resolve_user", lambda *a, **k: "me"), \
                        mock.patch.object(m, "_auto_log", lambda s: logs.append(s)), \
                        mock.patch.object(m, "doc_status_live", lambda d: "in-progress"), \
                        mock.patch.object(m, "doc_commit_drift", lambda d: False):
                    r = m._spawn_worker(rid, meta, "p", "rework", out=out)
                self.assertFalse(r)
                self.assertEqual(out.get("blocked"), "busy-elsewhere")
                self.assertTrue(any("SKIP(busy-elsewhere)" in l for l in logs), logs)

            # W4. 드래그 착수 통지는 담당자의 세션에만
        with self.subTest("w4_chat_target_by_user"):
            m = self.m
            os.makedirs(m.STATE, exist_ok=True)
            for sid, u in (("aaaa0001", "me"), ("bbbb0002", "other")):
                with open(os.path.join(m.STATE, f"here__{sid}.json"), "w",
                          encoding="utf-8") as f:
                    json.dump({"machine": "here", "session": sid, "user": u,
                               "history": [], "attach_pid": os.getpid()}, f)
            with mock.patch.object(m, "chat_live", lambda b, **k: True):
                self.assertEqual(m.chat_target(None, user="other")["session"], "bbbb0002")
                self.assertEqual(m.chat_target(None, user="me")["session"], "aaaa0001")
                self.assertIsNone(m.chat_target(None, user="nobody"))

class ForeignBindings(unittest.TestCase):
    """B1~B4 (REQ-20260902-017) — 남의 머신 바인딩은 읽지도 쓰지도 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9fb-")
        env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "here"}
        env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=env)
        subprocess.run([S9, "user", "add", "me"], capture_output=True, env=env,
                       stdin=subprocess.DEVNULL)
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "here"
        spec = importlib.util.spec_from_loader(
            "s9_fb", importlib.machinery.SourceFileLoader("s9_fb", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        os.makedirs(cls.m.STATE, exist_ok=True)
        out = subprocess.run([S9, "new", "request", "--title", "내 일",
                              "--summary", "s", "--size", "S", "--goal", "g",
                              "--body", "b", "--user", "me"],
                             capture_output=True, text=True, env=env,
                             stdin=subprocess.DEVNULL)
        cls.rid = out.stdout.split()[0]

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        os.environ.pop("S9_MACHINE", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    def binding(self, machine, sid, **kv):
        b = {"machine": machine, "session": sid, "user": "me", "history": [],
             "attach_pid": os.getpid(), "active_reqs": [self.rid]}
        b.update(kv)
        p = os.path.join(self.m.STATE, f"{machine}__{sid}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f)
        return p

    def read(self, p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    # B1. 남의 바인딩은 채팅 대상이 아니다 (pid 가 내 것과 겹쳐도)
    def test_foreign_bindings(self):
        """B1~B4 (REQ-20260902-017) — 남의 머신 바인딩은 읽지도 쓰지도 않는다."""
        with self.subTest("b1_chat_target_skips_foreign"):
                self.binding("there", "ffff0001")
                with mock.patch.object(self.m, "chat_live", lambda b, **k: True):
                    self.assertIsNone(self.m.chat_target(None))
                    self.binding("here", "hhhh0001")
                    self.assertEqual(self.m.chat_target(None)["session"], "hhhh0001")

            # B2. 남의 바인딩은 클레임 생존 근거가 아니다
        with self.subTest("b2_rework_claimed_ignores_foreign"):
                for p in os.listdir(self.m.STATE):
                    os.remove(os.path.join(self.m.STATE, p))
                self.binding("there", "ffff0002")
                with mock.patch.object(self.m, "chat_live", lambda b, **k: True), \
                        mock.patch.object(self.m, "delegated_live", lambda r: False), \
                        mock.patch.object(self.m, "worker_running", lambda r, **k: False):
                    self.assertFalse(self.m.rework_claimed(self.rid))
                    self.binding("here", "hhhh0002")
                    self.assertTrue(self.m.rework_claimed(self.rid))

            # B3·B4. 떠나는 전이와 claim --release 가 남의 파일을 다시 쓰지 않는다
        with self.subTest("b3_b4_leave_and_release_do_not_touch_foreign"):
            fp = self.binding("there", "ffff0003")
            hp = self.binding("here", "hhhh0003")
            before = os.path.getmtime(fp)
            os.utime(fp, (before - 100, before - 100))
            stamp = os.path.getmtime(fp)
            self.m.update_active_reqs(self.rid, "review")
            self.assertEqual(os.path.getmtime(fp), stamp, "떠나는 전이가 남의 바인딩을 썼다")
            self.assertNotIn(self.rid, self.read(hp).get("active_reqs") or [])
            self.assertIn(self.rid, self.read(fp).get("active_reqs") or [])
            # release: 남의 세션 id 를 지목해도 그 파일은 그대로다
            self.m.acquire_lock()
            try:
                self.m._release_binding_claim(self.rid, "ffff0003")
            finally:
                self.m.release_lock()
            self.assertEqual(os.path.getmtime(fp), stamp, "release 가 남의 바인딩을 썼다")

if __name__ == "__main__":
    unittest.main()
