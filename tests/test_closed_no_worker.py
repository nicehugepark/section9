"""끝난 일에 작업자가 뜨지 않는다 (REQ-20260830-002).

실사고 2026-08-30 00:30. `REQ-20260829-019` 는 18:56 에 done 으로 닫혔는데
00:30 에 무인 작업자가 그 문서로 떴다. 리스로 `bin/s9`·`web/index.html`·시험
둘을 잡아 **대기 중이던 다른 작업들을 그만큼 더 막았다.**

경로를 되짚으니 승인 후속이었다: `rework_watch_tick` 이 승인(review→done)
메모를 보고 무인 작업자를 띄웠다(REQ-20260824-028). 반려 루프와 대칭이라고
썼지만 대칭이 아니다 — 반려는 아직 할 일이 남은 in-progress 로 가고, 승인
메모는 **언제나 done 으로** 간다. 게다가 이 저장소는 승인 전이에 근거 메모를
요구하므로 그 경로는 예외가 아니라 상시였다.

그리고 그 문서에는 **막다른 길**이 하나 더 있었다. 떠 버린 작업자를 세우려니
"먼저 `s9 last <id> --add` 로 집어라" 는데, `_claim_req` 는 끝난 문서를 등록
하지 않는다(REQ-20260828-036, 그것대로 옳다) — **시키는 명령이 성공할 수 없다.**
게다가 그 명령은 아무것도 안 하고도 `active_reqs += <id>` 를 찍었다.

여기서 못박는 계약 셋:
  ① 끝난 문서에는 **어떤 경로로도** 뜨지 않는다 — 판정은 디스크의 문서에서.
  ② 떠 버렸으면 **상태와 무관하게** 이유를 대고 세울 수 있다.
  ③ 거절을 성공처럼 찍지 않는다.

실행: python3 tests/ closed_no_worker
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def cli(env, *a, expect=0):
    r = subprocess.run([S9, *a], capture_output=True, text=True, env=env,
                       stdin=subprocess.DEVNULL, timeout=30)
    if expect is not None and r.returncode != expect:
        raise AssertionError(f"s9 {' '.join(a)}: rc={r.returncode}\n"
                             f"{r.stdout}{r.stderr}")
    return r


class Base(unittest.TestCase):
    """무인 워커를 **실제로 띄우지 않는다** — 임시 ROOT 라도 프로세스는 진짜 뜬다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9closed-")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_MACHINE": "testbox"}
        for k in ("S9_SESSION", "S9_AUTO_RESUME_DISABLE"):
            self.env.pop(k, None)
        cli(self.env, "init")
        cli(self.env, "user", "add", "alice")
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_MACHINE"] = "testbox"
        os.environ.pop("S9_AUTO_RESUME_DISABLE", None)
        spec = importlib.util.spec_from_loader(
            "s9_closed", importlib.machinery.SourceFileLoader("s9_closed", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        # 옵트인·머신·캡을 통과시킨다 — 여기서 재는 것은 **상태 문** 하나다.
        self.m.user_config = lambda o=None: {"auto_resume": True}
        self.m.current_machine = lambda: "testbox"
        self.spawned = []

    def tearDown(self):
        for k in ("S9_ROOT", "S9_MACHINE", "S9_AUTO_RESUME_DISABLE"):
            os.environ.pop(k, None)
        shutil.rmtree(self.root, ignore_errors=True)

    def mkreq(self, title="어떤 일"):
        return cli(self.env, "new", "request", "--title", title, "--summary",
                   "s", "--size", "S", "--user", "alice", "--goal", "g",
                   "--body", "x").stdout.split()[0]

    def spawn(self, doc_id, reason="wake"):
        """스폰 문을 지나 보되 Popen 자리는 지나기 전에 막힌다."""
        meta = self.m.read_doc(self.m.locate(doc_id))[0]
        real = subprocess.Popen

        def no_popen(*a, **kw):
            self.spawned.append(a[:1])
            raise AssertionError("무인 워커를 실제로 띄웠다")
        subprocess.Popen = no_popen
        out = {}
        try:
            ok = self.m._spawn_worker(doc_id, meta, "p", reason, out=out)
        finally:
            subprocess.Popen = real
        return ok, out


class ClosedNeverSpawns(Base):
    """① 끝난 문서에는 어떤 경로로도 뜨지 않는다."""

    def _closed(self, to):
        rid = self.mkreq()
        cli(self.env, "status", rid, "in-progress", "--note", "t")
        if to == "done":
            cli(self.env, "status", rid, "review", "--note", "확인해 주세요")
        cli(self.env, "status", rid, to, "--note", "근거")
        return rid

    def test_t1_done_is_refused_on_every_path(self):
        rid = self._closed("done")
        for reason in ("wake", "rework", "followup", "resume"):
            ok, out = self.spawn(rid, reason)
            self.assertFalse(ok, f"{reason} 경로가 끝난 문서에 워커를 띄운다")
            self.assertEqual(out.get("blocked"), "closed", out)
            self.assertIn("done", out.get("why", ""),
                          "왜 안 뜨는지가 사람 말로 안 나온다")

    def test_t2_cancelled_is_refused_too(self):
        rid = self._closed("cancelled")
        ok, out = self.spawn(rid, "wake")
        self.assertFalse(ok)
        self.assertEqual(out.get("blocked"), "closed", out)

    def test_t3_in_progress_still_passes_the_status_door(self):
        """회귀: 오늘 되던 것이 그대로 된다 — 문을 세우다 길을 막지 않는다."""
        rid = self.mkreq()
        cli(self.env, "status", rid, "in-progress", "--note", "t")
        ok, out = self.spawn(rid, "wake")
        self.assertNotEqual(out.get("blocked"), "closed",
                            "진행 중인 문서를 끝난 것으로 본다 — 이러면 "
                            "무인 이어받기가 통째로 죽는다")

    def test_t4_a_stale_index_does_not_open_the_door(self):
        """카탈로그가 낡아도 문은 안 열린다 — 판정은 디스크의 문서에서.

        사고의 다른 가설이 '낡은 색인' 이었다. 색인이 진실이면 색인이 낡는
        순간 문이 열린다. 그러니 색인을 일부러 낡게 만들어 두고 묻는다.
        """
        rid = self._closed("done")
        cat = self.m.CATALOG
        # 병합된 목록을 base 로 눌러 담는다 (REQ-20260902-035) — base 파일만
        # 읽으면 갓 쓴 행이 델타에 있어 손에 잡히지 않는다.
        rows = self.m.load_catalog()
        for r in rows:
            if r.get("id") == rid:
                r["status"] = "in-progress"      # 낡은 색인
        with open(cat, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        # 증분 카탈로그(REQ-20260902-035)에서는 델타가 base 를 덮는다 —
        # base 만 낡게 만들면 델타의 신선한 행이 이 시험을 무력하게 한다.
        open(self.m.CATALOG_DELTA, "w").close()
        self.assertEqual(self.m.doc_status(rid), "in-progress",
                         "색인을 낡게 만들지 못했다 — 이 시험이 아무것도 안 묻는다")
        ok, out = self.spawn(rid, "rework")
        self.assertFalse(ok, "낡은 색인 하나로 끝난 문서에 워커가 뜬다")
        self.assertEqual(out.get("blocked"), "closed", out)


class ApprovalFollowupIsNotAWorker(Base):
    """승인 메모는 사람이 붙은 자리로 간다 — 끝난 문서에 손을 붙이지 않는다."""

    def test_t5_the_watcher_spawns_nothing_for_an_approved_doc(self):
        rid = self.mkreq()
        cli(self.env, "status", rid, "in-progress", "--note", "t")
        cli(self.env, "status", rid, "review", "--note", "확인해 주세요")
        cli(self.env, "status", rid, "done", "--note",
            "충족 근거: 다 됐다. 그리고 다음엔 이것도 해 달라")
        seen = [r["id"] for r in self.m.approvals_unseen()]
        self.assertIn(rid, seen,
                      "승인 메모 자체가 사라지면 안 된다 — 사람이 받아야 한다")
        real = subprocess.Popen

        def no_popen(*a, **kw):
            raise AssertionError("승인 메모로 무인 워커를 띄웠다")
        subprocess.Popen = no_popen
        try:
            self.assertEqual(self.m.rework_watch_tick(grace=0), [],
                             "끝난 문서에 워커를 띄웠다")
        finally:
            subprocess.Popen = real
        self.assertIn(rid, [r["id"] for r in self.m.approvals_unseen()],
                      "메모를 소비해 버리면 사람도 못 본다 — 잃는 것이 생긴다")


class StoppableWhenClosed(Base):
    """② 떠 버렸으면 상태와 무관하게 이유를 대고 세울 수 있다."""

    def mark(self, rid, pid=424242):
        d = self.m._auto_dir()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, self.m.safe_name(rid) + ".json"), "w") as f:
            json.dump({"pid": pid, "last": time.time()}, f)

    def stop(self, rid, why="이유", session=""):
        killed = []
        return self.m.worker_stop(
            rid, session=session, why=why,
            kill=lambda p, s: killed.append((p, s)),
            alive=lambda p: False, wait=lambda s: None,
            note=lambda *a: None), killed

    def test_t6_a_worker_on_a_closed_doc_can_be_stopped_without_a_claim(self):
        rid = self.mkreq()
        cli(self.env, "status", rid, "in-progress", "--note", "t")
        cli(self.env, "status", rid, "review", "--note", "확인해 주세요")
        cli(self.env, "status", rid, "done", "--note", "근거")
        self.mark(rid)
        res, _k = self.stop(rid, why="끝난 문서에 떴다")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["pid"], 424242)
        self.assertNotIn("--add", res.get("message", ""),
                         "성공할 수 없는 명령을 다시 시키면 막다른 길이다")

    def test_t6b_the_reason_is_still_required(self):
        rid = self.mkreq()
        cli(self.env, "status", rid, "in-progress", "--note", "t")
        cli(self.env, "status", rid, "review", "--note", "확인해 주세요")
        cli(self.env, "status", rid, "done", "--note", "근거")
        self.mark(rid)
        res, _k = self.stop(rid, why="  ")
        self.assertFalse(res["ok"],
                         "이유 없는 중단은 나중에 아무도 판정할 수 없다")

    def test_t6c_an_open_doc_still_needs_a_claim(self):
        """회귀: 문을 여는 것이 아니라 **끝난 문서에서만** 면제다."""
        rid = self.mkreq()
        cli(self.env, "status", rid, "in-progress", "--note", "t")
        self.mark(rid)
        res, _k = self.stop(rid, why="남의 작업자")
        self.assertFalse(res["ok"],
                         "지나가는 세션이 남의 작업자를 끄게 되면 안 된다")
        self.assertIn("--add", res["message"],
                      "진행 중인 문서에서는 집으라는 안내가 맞다")


class NoDeadEnd(Base):
    """③ 거절을 성공처럼 찍지 않는다."""

    def test_t7_claiming_a_closed_doc_fails_out_loud(self):
        rid = self.mkreq()
        cli(self.env, "status", rid, "in-progress", "--note", "t")
        cli(self.env, "status", rid, "review", "--note", "확인해 주세요")
        cli(self.env, "status", rid, "done", "--note", "근거")
        env = {**self.env, "S9_SESSION": "abcd1234"}
        r = cli(env, "last", rid, "--add", expect=None)
        self.assertNotEqual(r.returncode, 0,
                            "끝난 문서를 집었다고 답한다 — 그 한 줄을 믿고 "
                            "다음 명령을 친 사람은 같은 거부를 다시 받는다")
        self.assertNotIn("active_reqs +=", r.stdout,
                         "아무것도 안 하고 성공 문장을 찍는다")

    def test_t7b_claiming_a_live_doc_still_works(self):
        rid = self.mkreq()
        cli(self.env, "status", rid, "in-progress", "--note", "t")
        env = {**self.env, "S9_SESSION": "abcd1234"}
        out = cli(env, "last", rid, "--add").stdout
        self.assertIn("active_reqs +=", out, "산 문서를 못 집으면 판이 선다")


class LeasesAreSwept(Base):
    """곁가지: 물러난 작업자의 리스가 남아 있었다 — 언제 거두는가."""

    def test_t8_the_watcher_sweeps_dead_leases(self):
        """스폰이 없어도 거둔다.

        종전엔 `lease_take` 안에서만 돌았다 — 즉 **다음 작업자가 뜰 때까지**
        죽은 손의 파일이 남았다. 판정은 죽은 pid 를 무시하므로 막지는 않지만,
        쌓인 파일은 조용하고 조용한 것은 다음 사람을 헷갈리게 한다.
        """
        self.m.lease_take("REQ-19000101-001", ["bin/s9"], pid=1)
        home = self.m.LEASE_HOME
        self.assertTrue(os.listdir(home), "리스를 못 만들었다")
        for fn in os.listdir(home):                 # 주인을 죽인다
            fp = os.path.join(home, fn)
            with open(fp, encoding="utf-8") as f:
                info = json.load(f)
            info["pid"] = 4000000                   # 없는 pid
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(info, f)
        self.m.rework_watch_tick(grace=0)
        self.assertEqual(os.listdir(home), [],
                         "죽은 손의 리스가 스폰이 있을 때까지 남는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
