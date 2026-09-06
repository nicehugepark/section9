"""거부·충돌·장애는 다른 일이다 (REQ-20260902-022).

종전 sync_run 은 push 거부(non-fast-forward)·rebase 충돌·네트워크 장애를 전부
'네트워크 장애'로 취급해 60초 침묵했다. 거부는 남이 먼저 밀었다는 뜻이라 곧바로
다시 당겨 밀면 되고, 충돌은 물러나 봐야 같은 충돌이며, 장애만 백오프의 몫이다.
각 단계는 state/sync.jsonl 에 남아 `s9 sync --stats` 가 p50/p95·거부율을 낸다.

실행: python3 tests/ sync_classify
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


class CP:
    def __init__(self, rc=0, err="", out=""):
        self.returncode, self.stderr, self.stdout = rc, err, out


class SyncClassify(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9synccl-")
        os.makedirs(os.path.join(self.root, "state"))
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_synccl", importlib.machinery.SourceFileLoader("s9_synccl", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.calls = []

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(self.root, ignore_errors=True)

    def run_sync(self, script):
        """script: {"pull": [CP...], "push": [CP...]} — 호출 순서대로 꺼낸다."""
        q = {k: list(v) for k, v in script.items()}

        def fake(*argv, timeout=6):
            self.calls.append(argv)
            # 「당기기」는 fetch 뒤 rebase 다 — 대본의 "pull" 은 그 rebase 에 답한다
            op = "pull" if argv[:2] == ("rebase", "--autostash") else argv[0]
            if op == "diff":
                return CP(out="vault/x.md\n")
            if op in q and q[op]:
                return q[op].pop(0)
            return CP()
        with mock.patch.object(self.m, "_sync_git", fake), \
                mock.patch.object(self.m, "sync_mode", lambda: "remote"), \
                mock.patch("time.sleep", lambda s: None):
            return self.m.sync_run("t")

    def backoff(self):
        return os.path.exists(self.m._SYNC_FAIL_TS)

    def events(self):
        with open(self.m._SYNC_EVENTS, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    REJ = "! [rejected] main -> main (fetch first)\nerror: failed to push some refs\n"
    NET = "fatal: unable to access 'https://x/': Could not resolve host: x\n"
    CONF = "CONFLICT (content): Merge conflict in vault/x.md\nerror: could not apply abc\n"

    # C1. 거부 → 백오프 없이 다시 당겨 밀어 성공
    def test_c1_rejected_push_retries_immediately(self):
        r = self.run_sync({"push": [CP(1, self.REJ), CP(0)]})
        self.assertEqual(r, "ok")
        self.assertFalse(self.backoff(), "거부를 장애로 취급해 백오프를 걸었다")
        pushes = [e for e in self.events() if e["stage"] == "push"]
        self.assertEqual([e["attempt"] for e in pushes], [0, 1])
        self.assertEqual(pushes[0]["kind"], "rejected")
        # 재시도 사이에 pull 이 한 번 더 있었다
        self.assertEqual(sum(1 for c in self.calls if c[:2] == ("rebase", "--autostash")), 2)

    # C2. 거부가 이어져도 백오프는 없다 — 다음 이벤트가 다시 민다
    def test_c2_repeated_rejection_ends_without_backoff(self):
        n = self.m.SYNC_PUSH_RETRIES + 1
        r = self.run_sync({"push": [CP(1, self.REJ)] * n})
        self.assertEqual(r, "push-rejected")
        self.assertFalse(self.backoff())

    # C3. 네트워크 실패 → push-fail + 백오프
    def test_c3_network_failure_backs_off(self):
        r = self.run_sync({"push": [CP(1, self.NET)]})
        self.assertEqual(r, "push-fail")
        self.assertTrue(self.backoff())

    # C4. pull 충돌은 abort + 분류, 백오프 없음 / 네트워크는 백오프
    def test_c4_pull_conflict_vs_network(self):
        r = self.run_sync({"pull": [CP(1, self.CONF)]})
        self.assertEqual(r, "pull-conflict")
        self.assertIn(("rebase", "--abort"), self.calls)
        self.assertFalse(self.backoff())
        self.calls.clear()
        r = self.run_sync({"pull": [CP(1, self.NET)]})
        self.assertEqual(r, "pull-fail")
        self.assertTrue(self.backoff())

    # C5. 타임아웃 분기도 rebase 잔재를 치운다
    def test_c5_timeout_aborts_rebase(self):
        def fake(*argv, timeout=6):
            self.calls.append(argv)
            if argv[0] == "diff":
                return CP(out="vault/x.md\n")
            if argv[:2] == ("rebase", "--autostash"):
                raise subprocess.TimeoutExpired("git", timeout)
            return CP()
        with mock.patch.object(self.m, "_sync_git", fake), \
                mock.patch.object(self.m, "sync_mode", lambda: "remote"):
            r = self.m.sync_run("t")
        self.assertEqual(r, "timeout")
        self.assertIn(("rebase", "--abort"), self.calls)
        self.assertTrue(self.backoff())

    UNTRACKED = ("error: The following untracked working tree files would be overwritten by merge:\n"
                 "\tusers/sjpark/machines.json\n"
                 "Please move or remove them before you merge.\nAborting\n")

    # C10. 추적 안 되는 파일이 pull 을 막으면 비켜 세우고 한 번 더 당긴다 (원격 리눅스 실사고 2026-09-06)
    def test_c10_untracked_file_is_rescued_and_pull_retried(self):
        os.makedirs(os.path.join(self.root, "users", "sjpark"))
        with open(os.path.join(self.root, "users", "sjpark", "machines.json"), "w") as f:
            f.write("{}")
        r = self.run_sync({"pull": [CP(1, self.UNTRACKED), CP(0)]})
        self.assertEqual(r, "ok")
        pulls = [e for e in self.events() if e["stage"] == "pull"]
        self.assertEqual([e["attempt"] for e in pulls], [0, 1])
        self.assertEqual(pulls[0]["kind"], "untracked")
        self.assertFalse(os.path.exists(os.path.join(self.root, "users", "sjpark", "machines.json")),
                         "막던 파일이 제자리에 그대로다")
        rescued = [p for p, _, fs in os.walk(os.path.join(self.root, "state", "sync-rescue"))
                   if "machines.json" in fs]
        self.assertEqual(len(rescued), 1, "지운 것이 아니라 옮긴 것이어야 한다")
        self.assertFalse(self.backoff())

    # C11. rebase --abort 가 실패하면 --quit 뒤 가지를 orig-head 로 되돌린다 — 잔재를 남기지 않는다
    def test_c11_failed_abort_quits_and_restores_the_branch(self):
        rb = os.path.join(self.root, ".git", "rebase-merge")
        os.makedirs(rb)
        with open(os.path.join(rb, "orig-head"), "w") as f:
            f.write("bd8e852a5ad7714c714132385533c5a8985feb92\n")
        with open(os.path.join(rb, "head-name"), "w") as f:
            f.write("refs/heads/main\n")

        def fake(*argv, timeout=6):
            self.calls.append(argv)
            if argv[0] == "diff":
                return CP(out="vault/x.md\n")
            if argv[:2] == ("rebase", "--autostash"):
                return CP(1, self.CONF)
            if argv[:2] == ("rebase", "--abort"):
                return CP(128, "fatal: could not move back to bd8e852\n")
            return CP()
        with mock.patch.object(self.m, "_sync_git", fake), \
                mock.patch.object(self.m, "sync_mode", lambda: "remote"), \
                mock.patch("time.sleep", lambda s: None):
            r = self.m.sync_run("t")
        self.assertEqual(r, "pull-conflict")
        self.assertIn(("rebase", "--quit"), self.calls)
        self.assertIn(("checkout", "-q", "-B", "main", "bd8e852a5ad7714c714132385533c5a8985feb92"),
                      self.calls)

    # C12. 당기기는 pull 이 아니라 fetch → rebase @{u} — FETCH_HEAD 경합을 피한다 (실측 2026-09-06)
    def test_c12_pull_is_fetch_then_rebase_onto_upstream(self):
        r = self.run_sync({})
        self.assertEqual(r, "ok")
        verbs = [c[0] for c in self.calls]
        self.assertNotIn("pull", verbs, "pull 은 FETCH_HEAD 를 읽는다 — 겹친 fetch 에 선다")
        i_fetch = verbs.index("fetch")
        i_rebase = next(i for i, c in enumerate(self.calls) if c[:2] == ("rebase", "--autostash"))
        self.assertLess(i_fetch, i_rebase)
        self.assertEqual(self.calls[i_rebase], ("rebase", "--autostash", "-q", "@{u}"))
        self.assertFalse([c for c in self.calls if c[:1] == ("stash",)], "sync 가 제 보관함을 만든다 — 되돌리기 실패가 기록을 삼킨다(REQ-20260906-082)")

    # C13. 남이 담아 둔(git add) 변경은 pull 뒤 다시 담긴다 — autostash 가 index 를 풀어도
    #      (REQ-20260906-066); sync 제 경로는 되담지 않고, 직접 보관(stash)은 쓰지 않는다(082)
    def test_c13_staged_paths_are_restaged_after_the_pull(self):
        os.makedirs(os.path.join(self.root, "bin"), exist_ok=True)
        with open(os.path.join(self.root, "bin", "s9.py"), "w") as f:
            f.write("# staged\n")

        def fake(*argv, timeout=6):
            self.calls.append(argv)
            if argv[:3] == ("diff", "--cached", "--name-only") and "--" not in argv:
                return CP(out="bin/s9.py\nvault/x.md\n")
            if argv[0] == "diff":
                return CP(out="vault/x.md\n")
            return CP()
        with mock.patch.object(self.m, "_sync_git", fake), \
                mock.patch.object(self.m, "sync_mode", lambda: "remote"), \
                mock.patch("time.sleep", lambda s: None):
            r = self.m.sync_run("t")
        self.assertEqual(r, "ok")
        verbs = [c[:2] for c in self.calls]
        i_reb = verbs.index(("rebase", "--autostash"))
        i_add = next(i for i, c in enumerate(self.calls) if c[:2] == ("add", "--") and "bin/s9.py" in c)
        self.assertLess(i_reb, i_add, "되담기가 pull 앞에 있다")
        self.assertNotIn("vault/x.md", self.calls[i_add], "sync 제 경로까지 되담는다")
        self.assertFalse([c for c in self.calls if c[:1] == ("stash",)])

    # C6. 관측 — commit/pull/push 단계가 한 줄씩
    def test_c6_events_have_stage_ms_rc(self):
        self.run_sync({})
        ev = self.events()
        self.assertEqual([e["stage"] for e in ev], ["commit", "pull", "push"])
        for e in ev:
            self.assertIn("ms", e)
            self.assertEqual(e["rc"], 0)

    # C9. 보호 규칙 거부는 경합이 아니다 — 재시도도 백오프도 없이 표면화
    def test_c9_protected_branch_is_not_retried(self):
        PROT = ("remote: error: GH006: Protected branch update failed for refs/heads/main.\n"
                "remote: - Changes must be made through a pull request.\n"
                "! [remote rejected] main -> main (protected branch hook declined)\n")
        r = self.run_sync({"push": [CP(1, PROT), CP(0)]})
        self.assertEqual(r, "push-protected")
        self.assertFalse(self.backoff())
        self.assertEqual(sum(1 for c in self.calls if c[0] == "push"), 1)
        with open(os.path.join(self.root, "state", "sync.log"), encoding="utf-8") as f:
            self.assertIn("보호 규칙", f.read())

    # C7. 통계
    def test_c7_stats(self):
        self.run_sync({"push": [CP(1, self.REJ), CP(0)]})
        self.run_sync({})
        st = self.m.sync_stats()
        self.assertEqual(st["stages"]["push"]["n"], 3)
        self.assertEqual(st["stages"]["push"]["fail"], 1)
        self.assertAlmostEqual(st["push_rejected_rate"], 1 / 3, places=3)
        self.assertTrue(st["last_ok"])
        self.assertIn("p95_ms", st["stages"]["pull"])


if __name__ == "__main__":
    unittest.main()
