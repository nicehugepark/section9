"""자동 commit 실패를 사람이 보는 자리에 세운다 (REQ-20260910-052-62x6).

실제 발생 2026-09-10: eek-p620 의 작업 트리에 끝난 코드 46파일·3,600줄이 커밋되지
않은 채 있었다. `git stash pop` 이 남긴 충돌 표시 두 곳 때문에 s9-guard 가 「담기는
파이썬 소스가 컴파일되지 않습니다」로 모든 커밋을 거부했고, sync 의 자동 commit 은
698번 중 74번을 그렇게 졌다. 그런데 그 74회는 state/sync.log 한 줄씩으로만 쌓였다 —
대시보드 머리에도, 카드에도, 세션 수신함에도 없었다. 맥이 REQ-20260910-004-t8rc ·
005-t8rc 를 blocked 로 되돌린 사유가 이것이다: 화면에는 있고 HEAD 에는 없는 코드.

pull 실패에는 이미 연속 실패 알림이 있었다(REQ-20260907-005) — 그 장치가 commit
단계를 세지 않았을 뿐이다. 그래서 새 장치를 만들지 않고 SyncFailStreak 에 stage 를
더한다: 단계마다 따로 세고, 단계가 바뀌면 1 부터 다시 세고, 한 단계의 성공은 그
단계의 streak 만 지운다.

git·네트워크 없이 함수와 작은 상태 객체만 시험한다.

실행: python3 tests/ sync_commit_alert
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

# 사고 당일 state/sync.log 에 남은 stderr 그대로 (경로만 일반화)
GUARD_STDERR = (
    "s9-guard: 담기는 파이썬 소스가 컴파일되지 않습니다 — bin/s9.py:1204: "
    "SyntaxError: invalid syntax\n")
LOCK_STDERR = (
    "error: cannot lock ref 'HEAD': is at 8f385a7 but expected 2c91b0e\n")
INDEX_LOCK_STDERR = (
    "fatal: Unable to create '/x/section9/.git/index.lock': File exists.\n")
OTHER_STDERR = "error: pathspec 'vault/x.md' did not match any file(s) known to git\n"
CONFLICT_STDERR = (
    "CONFLICT (content): Merge conflict in vault/requests/2026/09/REQ-1.md\n")


def _evt(stage, rc, ts="2026-09-10T21:00:00+09:00"):
    return {"stage": stage, "rc": rc, "ms": 10, "ts": ts}


class SyncCommitAlert(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9synccommit-")
        os.makedirs(os.path.join(cls.root, "state"))
        os.environ["S9_ROOT"] = cls.root
        spec = importlib.util.spec_from_loader(
            "s9_synccommit",
            importlib.machinery.SourceFileLoader("s9_synccommit", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    # ---- S1: commit 실패를 갈래로 나눈다
    def test_commit_fail_kind_splits_hook_lock_other(self):
        k = self.m._sync_commit_fail_kind
        self.assertEqual(k(GUARD_STDERR), "hook")
        self.assertEqual(k(LOCK_STDERR), "lock")
        self.assertEqual(k(INDEX_LOCK_STDERR), "lock")
        self.assertEqual(k(OTHER_STDERR), "other")
        self.assertEqual(k(""), "other")
        # 잠금은 곧 풀리는 경합이라 훅 거부보다 먼저 갈린다 — 둘이 함께 있어도 lock
        self.assertEqual(k(LOCK_STDERR + GUARD_STDERR), "lock")

    # ---- S2: stage 를 함께 센다 — 3회 연속에 딱 한 번
    def test_commit_streak_alerts_once_with_stage(self):
        s = self.m.SyncFailStreak()
        self.assertIsNone(s.record("hook", GUARD_STDERR, threshold=3, stage="commit"))
        self.assertIsNone(s.record("hook", GUARD_STDERR, threshold=3, stage="commit"))
        a = s.record("hook", GUARD_STDERR, threshold=3, stage="commit")
        self.assertIsNotNone(a)
        self.assertEqual((a["stage"], a["kind"], a["count"]), ("commit", "hook", 3))
        for _ in range(4):
            self.assertIsNone(
                s.record("hook", GUARD_STDERR, threshold=3, stage="commit"))
        self.assertEqual(s.count, 7)

    # ---- S3: 알림 문장이 단계를 말한다
    def test_alert_text_names_the_stage(self):
        s = self.m.SyncFailStreak()
        a = None
        for _ in range(3):
            a = s.record("hook", GUARD_STDERR, threshold=3, stage="commit") or a
        text = self.m.sync_alert_text(a, pending=46)
        self.assertIn("sync commit 이 3회 연속 실패", text)
        self.assertIn("s9-guard", text)
        self.assertIn("commit 46개가 push 되지 않았습니다", text)
        # 비유로 상태를 말하지 않는다 (PROTOCOL 2조 ②)
        for bad in ("막혔", "섰다", "죽었", "멈췄", "붉"):
            self.assertNotIn(bad, text)
        # pull 은 종전 문장 그대로 — 회귀
        p = self.m.SyncFailStreak()
        pa = None
        for _ in range(3):
            pa = p.record("conflict", CONFLICT_STDERR, threshold=3) or pa
        self.assertIn("sync pull 이 3회 연속 실패", self.m.sync_alert_text(pa, pending=1))

    # ---- S4: 헤더 칩 사실의 label 이 단계를 말한다
    def test_chip_fact_label_names_the_stage(self):
        s = self.m.SyncFailStreak()
        for _ in range(3):
            s.record("hook", GUARD_STDERR, threshold=3, stage="commit")
        fact = self.m.sync_alert_fact(s, pending=46)
        self.assertEqual(fact["label"], "sync commit 실패 3회")
        self.assertEqual(fact["stage"], "commit")
        p = self.m.SyncFailStreak()
        for _ in range(3):
            p.record("conflict", CONFLICT_STDERR, threshold=3)
        self.assertEqual(self.m.sync_alert_fact(p, pending=1)["label"], "sync 실패 3회")

    # ---- S5: 단계가 바뀌면 1 부터 다시 센다
    def test_stage_change_restarts_the_count(self):
        s = self.m.SyncFailStreak()
        s.record("hook", GUARD_STDERR, threshold=3, stage="commit")
        s.record("hook", GUARD_STDERR, threshold=3, stage="commit")
        self.assertEqual(s.count, 2)
        s.record("conflict", CONFLICT_STDERR, threshold=3, stage="pull")
        self.assertEqual((s.stage, s.kind, s.count, s.told), ("pull", "conflict", 1, False))

    # ---- S6: 한 단계의 성공은 그 단계의 streak 만 지운다
    def test_success_clears_only_its_own_stage(self):
        s = self.m.SyncFailStreak()
        for _ in range(3):
            s.record("conflict", CONFLICT_STDERR, threshold=3, stage="pull")
        s.success("commit")                       # commit 이 성공해도 pull 계열은 남는다
        self.assertEqual((s.stage, s.count), ("pull", 3))
        s.success("pull")
        self.assertEqual((s.stage, s.kind, s.count, s.told), ("", "", 0, False))

    # ---- S7: 옛 상태 파일(stage 키 없음)을 읽으면 pull 로 본다
    def test_old_state_file_reads_as_pull(self):
        p = os.path.join(self.root, "state", "alert-old.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"kind": "conflict", "count": 2, "told": False,
                       "line": "CONFLICT", "since": "2026-09-07T10:36:00+09:00"}, f)
        s = self.m.SyncFailStreak.load(p)
        self.assertEqual((s.stage, s.kind, s.count), ("pull", "conflict", 2))
        # 그 상태에서 pull 실패가 이어지면 3 이지 1 이 아니다
        self.assertIsNotNone(s.record("conflict", CONFLICT_STDERR, threshold=3))
        # 저장·복원에 stage 와 requested 가 함께 간다
        s.save(p)
        self.assertEqual(self.m.SyncFailStreak.load(p).stage, "pull")

    # ---- S8: sync_stats 가 단계마다 끝에서 이어진 연속 실패 수를 낸다
    def test_stats_counts_trailing_streak_per_stage(self):
        ev = os.path.join(self.root, "state", "sync-stats.jsonl")
        rows = ([_evt("commit", 1)] * 5 + [_evt("pull", 0)] * 2
                + [_evt("commit", 1)] * 3)
        with open(ev, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        with mock.patch.object(self.m, "_SYNC_EVENTS", ev):
            st = self.m.sync_stats()
        self.assertEqual(st["stages"]["commit"]["streak"], 8)   # 사이에 성공이 없다
        self.assertEqual(st["stages"]["pull"]["streak"], 0)
        # 마지막 한 건이 성공이면 0
        with open(ev, "a", encoding="utf-8") as f:
            f.write(json.dumps(_evt("commit", 0)) + "\n")
        with mock.patch.object(self.m, "_SYNC_EVENTS", ev):
            st = self.m.sync_stats()
        self.assertEqual(st["stages"]["commit"]["streak"], 0)

    # ---- S9: `s9 sync --stats` 첫 줄에 경고가 선다
    def test_stats_screen_puts_warning_first(self):
        st = {"events": 10, "last_ok": "", "last_fail": "",
              "push_rejected_rate": None,
              "stages": {"commit": {"n": 8, "fail": 8, "p50_ms": 1, "p95_ms": 2,
                                    "streak": 8}}}
        w = self.m.sync_stats_warning(st, threshold=3)
        self.assertTrue(w.startswith("⚠"))
        self.assertIn("commit", w)
        self.assertIn("8회", w)
        st["stages"]["commit"]["streak"] = 0
        self.assertEqual(self.m.sync_stats_warning(st, threshold=3), "")

        args = mock.Mock(on=False, off=False, stats=True, json=False, action=None)
        st["stages"]["commit"]["streak"] = 8
        buf = io.StringIO()
        with mock.patch.object(self.m, "sync_stats", lambda *a, **k: st), \
                mock.patch.object(self.m, "sync_alert_after", lambda *a, **k: 3), \
                mock.patch("sys.stdout", buf):
            self.m.cmd_sync(args)
        self.assertTrue(buf.getvalue().splitlines()[0].startswith("⚠"))

    # ---- S10: 요청 임계를 넘기면 요청이 한 번 선다
    def test_request_stands_once_per_streak(self):
        self.assertEqual(self.m.sync_request_after({}), 10)
        self.assertEqual(self.m.sync_request_after({"sync_request_after": "4"}), 4)
        self.assertEqual(self.m.sync_request_after({"sync_request_after": "x"}), 10)

        s = self.m.SyncFailStreak()
        due = []
        for _ in range(12):
            s.record("hook", GUARD_STDERR, threshold=3, stage="commit")
            due.append(s.request_due(10))
        self.assertEqual(due.count(True), 1)
        self.assertTrue(due[9])                      # 10번째에 선다
        # 같은 streak 에서 두 번 서지 않는다 — 성공해야 다시 선다
        s.success("commit")
        for _ in range(10):
            s.record("hook", GUARD_STDERR, threshold=3, stage="commit")
        self.assertTrue(s.request_due(10))

    # ---- S11: 기존 pull 알림 시험이 그대로 통과한다 (호출 모양 회귀)
    def test_pull_call_shape_unchanged(self):
        s = self.m.SyncFailStreak()
        self.assertIsNone(s.record("hook", GUARD_STDERR, threshold=3))
        self.assertIsNone(s.record("hook", GUARD_STDERR, threshold=3))
        a = s.record("hook", GUARD_STDERR, threshold=3)
        self.assertIsNotNone(a)
        self.assertEqual(a["stage"], "pull")         # 인자 없는 record 는 pull
        s.success()                                  # 인자 없는 success 는 pull 을 지운다
        self.assertEqual(s.count, 0)

    # ---- S12: commit 이 실패해도 sync_run 은 예외 없이 error 를 돌려준다
    def test_commit_failure_returns_error_and_records_streak(self):
        m = self.m
        seen = []

        class R:
            def __init__(self, rc=0, err=""):
                self.returncode, self.stderr, self.stdout = rc, err, ""

        def fake_git(*a, **k):
            if a[0] == "commit":
                return R(1, GUARD_STDERR)
            if a[0] == "diff":
                return R(0)
            return R(0)
        fake_git_diff = R(0)
        fake_git_diff.stdout = "vault/requests/2026/09/REQ-1.md\0"

        def git(*a, **k):
            return fake_git_diff if a[0] == "diff" else fake_git(*a, **k)

        with mock.patch.object(m, "_sync_git", git), \
                mock.patch.object(m, "_sync_event", lambda *a, **k: None), \
                mock.patch.object(m, "_sync_log", lambda *a, **k: None), \
                mock.patch.object(m, "_sync_commit_busy", lambda: ""), \
                mock.patch.object(m, "machine_recv_beat", lambda *a, **k: None), \
                mock.patch.object(m, "_sync_streak_record",
                                  lambda *a, **k: seen.append((a, k))):
            try:
                rv = m.sync_run(reason="test", transport=False)
            except Exception as e:      # 원래 작업을 막지 않는다
                self.fail(f"sync_run 이 예외를 냈다: {e}")
        self.assertEqual(rv, "error")
        self.assertTrue(seen, "commit 실패가 streak 에 세어지지 않았다")
        self.assertEqual(seen[0][1].get("stage"), "commit")
        self.assertEqual(seen[0][0][0], "hook")


    # ---- S13: 요청을 세우는 자리가 조용히 지지 않는다
    def test_request_helper_builds_a_real_command_and_never_raises(self):
        """이 자리를 `except: pass` 로 지나가면 이 요청이 고치려던 그 실패를 그대로
        되풀이한다 — 그래서 argv 가 실제로 서는지, 실패해도 로그가 남는지 본다."""
        m = self.m
        calls, logs = [], []

        class Out:
            returncode, stdout, stderr = 0, "REQ-20260910-999-zzzz 세움\n", ""

        def fake_run(argv, **kw):
            calls.append((argv, kw))
            return Out()
        alert = {"stage": "commit", "kind": "hook", "count": 12,
                 "line": GUARD_STDERR.strip(), "since": "2026-09-10T21:00:00+09:00"}
        with mock.patch.object(m.subprocess, "run", fake_run), \
                mock.patch.object(m, "_sync_log", lambda s: logs.append(s)):
            rid = m._sync_streak_request(alert, pending=46)
        self.assertEqual(rid, "REQ-20260910-999-zzzz")
        argv, kw = calls[0]
        self.assertEqual(argv[1:3], ["new", "request"])
        self.assertIn("--goal", argv)            # goal 없는 request 는 done 이 거부된다
        self.assertIn("--summary", argv)
        self.assertLessEqual(len(argv[argv.index("--title") + 1]), 24)
        self.assertIn("commit 46개가 push 되지 않았습니다", kw["input"])
        self.assertIn("이 컴퓨터:", kw["input"])

        # 세우지 못해도 예외가 새지 않고, 못 세웠다는 사실이 로그에 남는다
        logs.clear()
        with mock.patch.object(m.subprocess, "run",
                               mock.Mock(side_effect=OSError("boom"))), \
                mock.patch.object(m, "_sync_log", lambda s: logs.append(s)):
            self.assertEqual(m._sync_streak_request(alert, pending=1), "")
        self.assertTrue(any("세우지 못했습니다" in s for s in logs))


if __name__ == "__main__":
    unittest.main()
