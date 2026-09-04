"""문서 리스 — 담당자 + 처음 집은 머신 (REQ-20260902-020, DOC-20260902-001 D1).

리스는 문서 frontmatter 에 산다(바인딩은 머신별 파일이라 CAS 가 없다). 다른
머신의 리스는 벽시계만 본다. 만료(CLAIM_GRACE)·명시 이관(claim --takeover) 둘이
옛 머신이 꺼진 뒤 이어가는 길이다. 진전 쓰기(전이·노트)가 곧 하트비트다.

실행: python3 tests/ lease
"""
import datetime
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


class Lease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9lease-")
        cls.base = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "here"}
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_JOB_REQ", "S9_USER"):
            cls.base.pop(k, None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.base)
        for u in ("me", "other", "root"):
            subprocess.run([S9, "user", "add", u], capture_output=True,
                           env=cls.base, stdin=subprocess.DEVNULL)
        subprocess.run([S9, "user", "role", "root", "admin"], capture_output=True,
                       env={**cls.base, "S9_USER": "root"}, stdin=subprocess.DEVNULL)
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "here"
        spec = importlib.util.spec_from_loader(
            "s9_lease", importlib.machinery.SourceFileLoader("s9_lease", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        os.environ.pop("S9_MACHINE", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    def new(self, user="me"):
        r = subprocess.run([S9, "new", "request", "--title", "t", "--summary", "s",
                            "--size", "S", "--goal", "g", "--body", "b",
                            "--origin", "human", "--user", user],
                           capture_output=True, text=True, env=self.base,
                           stdin=subprocess.DEVNULL)
        rid = r.stdout.split()[0]
        subprocess.run([S9, "status", rid, "in-progress", "--note", "t"],
                       capture_output=True, env={**self.base, "S9_USER": user},
                       stdin=subprocess.DEVNULL)
        return rid

    def local(self, user="me", machine="here", session="s-me1"):
        return {"user": user, "machine": machine, "role": self.m.user_role(user),
                "session": session}

    def set_lease(self, rid, **kv):
        path = self.m.locate(rid)
        meta, body = self.m.read_doc(path)
        ts = self.m.now_iso()
        lease = {"user": "me", "machine": "there", "session": "s-th1",
                 "since": ts, "renewed": ts}
        lease.update(kv)
        meta["lease"] = lease
        self.m.write_doc(path, meta, body)
        return lease

    def lease(self, rid):
        return self.m.doc_lease(self.m.read_doc(self.m.locate(rid))[0])

    # L1. 리스 없는 내 문서 → 획득
    def test_lease(self):
        """Lease 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("l1_acquire_free"):
                rid = self.new()
                ok, code, why = self.m.doc_lease_acquire(rid, "claim", local=self.local())
                self.assertTrue(ok, (code, why))
                l = self.lease(rid)
                self.assertEqual((l["user"], l["machine"], l["session"]), ("me", "here", "s-me1"))
                self.assertTrue(l["since"] and l["renewed"])

            # L2. 다른 머신의 신선한 리스 → busy-elsewhere; --takeover 로 이관
        with self.subTest("l2_busy_elsewhere_and_takeover"):
                rid = self.new()
                self.set_lease(rid)
                for want in ("list", "spawn", "claim"):
                    ok, code, _ = self.m.doc_lease_acquire(rid, want, local=self.local())
                    self.assertEqual((ok, code), (False, "busy-elsewhere"), want)
                self.assertEqual(self.lease(rid)["machine"], "there")
                # 남(other)은 담당자가 아니라 takeover 도 못 한다
                ok, code, _ = self.m.doc_lease_acquire(rid, "claim", local=self.local("other"),
                                                       takeover=True)
                self.assertFalse(ok)
                # 담당자 본인은 옮긴다 — History 에 남는다
                ok, code, _ = self.m.doc_lease_acquire(rid, "claim", local=self.local(),
                                                       takeover=True)
                self.assertEqual((ok, code), (True, "takeover"))
                self.assertEqual(self.lease(rid)["machine"], "here")
                body = self.m.read_doc(self.m.locate(rid))[1]
                self.assertIn("lease: takeover me@there -> me@here", body)
                # CLI 도 같은 문
                rid2 = self.new()
                self.set_lease(rid2)
                r = subprocess.run([S9, "claim", rid2, "--takeover"], capture_output=True,
                                   text=True, env={**self.base, "S9_USER": "me",
                                                   "S9_SESSION": "s-me2"},
                                   stdin=subprocess.DEVNULL)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(self.lease(rid2)["machine"], "here")

            # L3. 만료된 리스 → free
        with self.subTest("l3_expired_is_free"):
                rid = self.new()
                old = (datetime.datetime.now().astimezone()
                       - datetime.timedelta(seconds=self.m.DOC_LEASE_TTL + 5)).isoformat()
                self.set_lease(rid, since=old, renewed=old)
                ok, code, _ = self.m.doc_lease_acquire(rid, "spawn", local=self.local())
                self.assertTrue(ok, code)
                self.assertEqual(self.lease(rid)["machine"], "here")

            # L4. 같은 머신·다른 세션 — 죽었으면 takeover-local, 살았으면 busy-local
        with self.subTest("l4_same_machine_other_session"):
                rid = self.new()
                self.set_lease(rid, machine="here", session="s-dead")
                with mock.patch.object(self.m, "_session_alive_here", lambda s: False):
                    ok, code, _ = self.m.doc_lease_acquire(rid, "claim", local=self.local())
                self.assertEqual((ok, code), (True, "takeover-local"))
                self.set_lease(rid, machine="here", session="s-live")
                with mock.patch.object(self.m, "_session_alive_here", lambda s: True):
                    ok, code, _ = self.m.doc_lease_acquire(rid, "claim", local=self.local())
                self.assertEqual((ok, code), (False, "busy-local"))
                # 내 세션이면 renew
                self.set_lease(rid, machine="here", session="s-me1")
                ok, code, _ = self.m.doc_lease_acquire(rid, "claim", local=self.local())
                self.assertEqual((ok, code), (True, "renew"))

            # L5. 전이·노트가 renewed 를 올린다 (하트비트)
        with self.subTest("l5_progress_writes_renew"):
                rid = self.new()
                old = (datetime.datetime.now().astimezone()
                       - datetime.timedelta(seconds=600)).isoformat()
                self.set_lease(rid, machine="here", session="s-me1", since=old, renewed=old)
                env = {**self.base, "S9_USER": "me", "S9_SESSION": "s-me1"}
                subprocess.run([S9, "note", rid, "진행", "--label", "response"],
                               capture_output=True, env=env, stdin=subprocess.DEVNULL)
                self.assertGreater(self.lease(rid)["renewed"], old)
                self.assertEqual(self.lease(rid)["since"], old)
                # 남의 리스는 내 쓰기가 갱신하지 않는다
                self.set_lease(rid, user="other", machine="here", since=old, renewed=old)
                subprocess.run([S9, "note", rid, "참견", "--label", "response"],
                               capture_output=True, env=env, stdin=subprocess.DEVNULL)
                self.assertEqual(self.lease(rid)["renewed"], old)

            # L6. 회수 — assign·종결
        with self.subTest("l6_release_on_assign_and_close"):
            rid = self.new()
            self.set_lease(rid, machine="here", session="s-me1")
            self.m.do_assign(rid, "other", actor="me")
            self.assertEqual(self.lease(rid), {})
            rid2 = self.new()
            self.set_lease(rid2, machine="here", session="s-me1")
            subprocess.run([S9, "status", rid2, "cancelled", "--note", "x", "--force"],
                           capture_output=True, env={**self.base, "S9_USER": "me"},
                           stdin=subprocess.DEVNULL)
            self.assertEqual(self.lease(rid2), {})

if __name__ == "__main__":
    unittest.main()
