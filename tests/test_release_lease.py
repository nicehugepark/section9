"""클레임을 풀면 리스도 풀리는가 (REQ-20260912-002).

실사고 2026-09-12 09:23. 주인이 REQ-20260911-016 의 담당 컴퓨터를 맥으로 옮겼는데
(09:08) 맥이 한 시간이 되도록 시작하지 않았다. 「맥에서 왜 시작을 안하는거야?」

까닭: 옮긴 것은 `needs_machine` 뿐이고, 문서의 `lease` 에는 앞 컴퓨터(WSL)가 그대로
남아 매 턴 갱신되고 있었다. 다른 컴퓨터의 `exec_verdict` 는 신선한 남의 리스를
busy-elsewhere 로 거부한다(30분). `s9 claim --release` 는 **세션 도장과 바인딩만**
걷고 리스는 두고 갔다 — 절반만 풀린 것이다.

계약: 클레임을 풀면 **그 세션이 쥔 리스**도 함께 풀린다. 남의 컴퓨터가 쥔 리스는
건드리지 않는다.

실행: python3 tests/ release_lease
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class ReleasingAClaimReleasesTheLease(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9rel-")
        self._prev = {k: os.environ.get(k) for k in
                      ("S9_ROOT", "S9_MACHINE", "S9_USER", "S9_SESSION",
                       "S9_REWORK_WATCH", "S9_SYNC")}
        os.environ.update({"S9_ROOT": self.tmp, "S9_MACHINE": "boxA",
                           "S9_USER": "tester", "S9_REWORK_WATCH": "off",
                           "S9_SYNC": "off"})
        os.environ.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, text=True, timeout=20,
                       stdin=subprocess.DEVNULL)
        subprocess.run([S9, "user", "add", "tester"], capture_output=True,
                       text=True, timeout=20, stdin=subprocess.DEVNULL)
        name = "s9rel_" + os.path.basename(self.tmp)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _req(self):
        r = subprocess.run(
            [S9, "new", "request", "--title", "리스 시험", "--summary", "시험",
             "--goal", "리스가 풀린다", "--size", "S", "--body", "시험"],
            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        rid = next((w for w in (r.stdout or "").split() if w.startswith("REQ-")), "")
        self.assertTrue(rid, f"{r.stdout} {r.stderr}")
        return rid

    def _lease(self, rid):
        meta, _ = self.m.read_doc(self.m.locate(rid))
        return meta.get("lease") or {}

    # R1 — 내가 쥔 리스는 클레임을 풀 때 함께 풀린다
    def test_r1_my_lease_goes_with_the_claim(self):
        rid = self._req()
        ok, code, why = self.m.doc_lease_acquire(
            rid, "claim", session="aaaabbbb",
            local={"user": "tester", "machine": "boxA", "session": "aaaabbbb"})
        self.assertTrue(ok, (code, why))
        self.assertEqual(self._lease(rid).get("machine"), "boxA")
        self.m.release_doc_session(rid, "aaaabbbb", user="tester", reason="시험")
        self.assertEqual(self._lease(rid), {},
                         "클레임은 풀렸는데 리스가 남았다 — 다른 컴퓨터가 "
                         "30분 동안 이 요청을 집지 못한다")

    # R2 — 푼 사실이 History 에 남는다 (지우는 것이 아니라 옮기는 것이다)
    def test_r2_the_release_is_written_down(self):
        rid = self._req()
        self.m.doc_lease_acquire(
            rid, "claim", session="aaaabbbb",
            local={"user": "tester", "machine": "boxA", "session": "aaaabbbb"})
        self.m.release_doc_session(rid, "aaaabbbb", user="tester", reason="시험")
        _, body = self.m.read_doc(self.m.locate(rid))
        self.assertIn("lease release", body)
        self.assertIn("boxA", body)

    # R3 — 남의 컴퓨터가 쥔 리스는 건드리지 않는다
    def test_r3_someone_elses_lease_is_left_alone(self):
        rid = self._req()
        path = self.m.locate(rid)
        meta, body = self.m.read_doc(path)
        meta["sessions"] = ["aaaabbbb"]
        meta["lease"] = {"user": "tester", "machine": "boxB",
                         "session": "ccccdddd", "since": self.m.now_iso(),
                         "renewed": self.m.now_iso()}
        self.m.write_doc(path, meta, body)
        self.m.release_doc_session(rid, "aaaabbbb", user="tester", reason="시험")
        self.assertEqual(self._lease(rid).get("machine"), "boxB",
                         "남의 컴퓨터가 쥔 리스를 풀었다 — 저쪽이 일하는 중일 수 있다")


if __name__ == "__main__":
    unittest.main()
