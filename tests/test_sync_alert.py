"""sync 되풀이 실패를 알린다 (REQ-20260907-005).

실제 발생 2026-09-07 10:36~11:54: rebase 가 재생한 깨진 commit 을 훅이 컴파일하다 낸
stderr(SyntaxWarning·Traceback)가 「pull conflict」 로 분류돼 78분 동안 30여 회 실패했는데
세션 수신함에도 헤더 칩에도 아무 알림이 없었다. 여기서 지키는 것은 둘이다:
① `_sync_fail_kind` 가 훅 오류(hook)를 문서 충돌(conflict)과 가른다
② 같은 사유로 N회 연속 실패하면 딱 한 번 알림이 나고, 성공하면 0 으로 돌아온다.
git·네트워크 없이 함수와 작은 상태 객체만 시험한다.

실행: python3 tests/ sync_alert
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

# 사고 당일 state/sync.log 에 남은 stderr 그대로 (경로만 일반화)
HOOK_STDERR = (
    "/x/section9/bin/s9.py:20362: SyntaxWarning: invalid escape sequence '\\T'\n"
    '  """UI 검증용 스크린샷 — WSL이면 Windows Chrome을 headless로 구동해 PNG 생성.\n'
    "Traceback (most recent call last):\n"
    '  File "/x/section9/bin/s9-guard", line 12, in <module>\n'
    "SyntaxError: unterminated triple-quoted string literal\n")
GUARD_STDERR = "s9-guard: 담긴 본이 깨졌습니다 — bin/s9.py:20362: SyntaxError\n"
CONFLICT_STDERR = (
    "Auto-merging vault/requests/2026/09/REQ-1.md\n"
    "CONFLICT (content): Merge conflict in vault/requests/2026/09/REQ-1.md\n"
    "error: could not apply 8f385a7... s9 sync: note\n")
BOTH_STDERR = HOOK_STDERR + CONFLICT_STDERR
NET_STDERR = "fatal: unable to access 'https://example.invalid/': Could not resolve host\n"


class SyncAlert(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9syncalert-")
        os.makedirs(os.path.join(cls.root, "state"))
        os.environ["S9_ROOT"] = cls.root
        spec = importlib.util.spec_from_loader(
            "s9_syncalert", importlib.machinery.SourceFileLoader("s9_syncalert", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    # ---- S1 · S7: 분류
    def test_hook_stderr_is_hook(self):
        self.assertEqual(self.m._sync_fail_kind(HOOK_STDERR), "hook")
        self.assertEqual(self.m._sync_fail_kind(GUARD_STDERR), "hook")
        self.assertEqual(self.m._sync_fail_kind("SyntaxError: invalid syntax\n"), "hook")

    def test_conflict_wins_over_hook_and_plain_is_net(self):
        self.assertEqual(self.m._sync_fail_kind(CONFLICT_STDERR), "conflict")
        self.assertEqual(self.m._sync_fail_kind(BOTH_STDERR), "conflict")
        self.assertEqual(self.m._sync_fail_kind(NET_STDERR), "net")
        self.assertEqual(self.m._sync_fail_kind(""), "net")

    def test_hook_has_screen_word(self):
        self.assertIn("hook", self.m.SYNC_KIND_WORD)
        self.assertEqual(self.m._sync_pull_fail_label("hook"), "pull 실패(hook)")
        self.assertEqual(self.m._sync_pull_fail_label("conflict"), "pull conflict")

    # ---- S2 · S5: 카운터가 임계에 딱 한 번 알린다
    def test_alert_once_at_threshold(self):
        s = self.m.SyncFailStreak()
        self.assertIsNone(s.record("hook", HOOK_STDERR, threshold=3))
        self.assertIsNone(s.record("hook", HOOK_STDERR, threshold=3))
        a = s.record("hook", HOOK_STDERR, threshold=3)
        self.assertIsNotNone(a)
        self.assertEqual((a["kind"], a["count"]), ("hook", 3))
        self.assertTrue(a["line"].startswith("/x/section9/bin/s9.py:20362: SyntaxWarning"))
        for _ in range(5):
            self.assertIsNone(s.record("hook", HOOK_STDERR, threshold=3))
        self.assertEqual(s.count, 8)
        self.assertTrue(s.told)

    def test_success_resets_and_kind_change_restarts(self):
        s = self.m.SyncFailStreak()
        for _ in range(3):
            s.record("hook", HOOK_STDERR, threshold=3)
        s.success()
        self.assertEqual((s.count, s.kind, s.told), (0, "", False))
        self.assertIsNone(s.record("hook", HOOK_STDERR, threshold=3))
        self.assertIsNone(s.record("hook", HOOK_STDERR, threshold=3))
        self.assertIsNotNone(s.record("hook", HOOK_STDERR, threshold=3))
        # 사유가 바뀌면 1 부터 다시 센다
        self.assertIsNone(s.record("conflict", CONFLICT_STDERR, threshold=3))
        self.assertEqual((s.kind, s.count, s.told), ("conflict", 1, False))

    # ---- S4: 임계는 오너 config 를 따른다
    def test_threshold_from_owner_config(self):
        self.assertEqual(self.m.sync_alert_after({}), 3)
        self.assertEqual(self.m.sync_alert_after({"sync_alert_after": "2"}), 2)
        self.assertEqual(self.m.sync_alert_after({"sync_alert_after": 0}), 3)
        self.assertEqual(self.m.sync_alert_after({"sync_alert_after": "abc"}), 3)
        s = self.m.SyncFailStreak()
        self.assertIsNone(s.record("net", NET_STDERR, threshold=2))
        self.assertIsNotNone(s.record("net", NET_STDERR, threshold=2))

    # ---- S6: 파일 저장·복원
    def test_state_survives_file_roundtrip(self):
        p = os.path.join(self.root, "state", "alert-rt.json")
        s = self.m.SyncFailStreak.load(p)
        self.assertEqual(s.count, 0)
        s.record("hook", HOOK_STDERR, threshold=3)
        s.save(p)
        s2 = self.m.SyncFailStreak.load(p)
        self.assertEqual((s2.kind, s2.count), ("hook", 1))
        self.assertIsNone(s2.record("hook", HOOK_STDERR, threshold=3))
        self.assertIsNotNone(s2.record("hook", HOOK_STDERR, threshold=3))
        s2.save(p)
        with open(p, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertEqual(self.m.SyncFailStreak.load(p).count, 0)

    # ---- S3 · S8: 문구와 칩 사실
    def test_text_and_chip_fact(self):
        s = self.m.SyncFailStreak()
        a = None
        for _ in range(3):
            a = s.record("hook", HOOK_STDERR, threshold=3) or a
        text = self.m.sync_alert_text(a, pending=5)
        self.assertIn("3회 연속 실패", text)
        self.assertIn("훅 오류", text)
        self.assertIn("SyntaxWarning", text)
        self.assertIn("commit 5개가 push 되지 않았습니다", text)
        # 다음 행동은 `s9 sync`(한 번 더 오간다)가 아니라 `s9 sync --status`
        # (무엇이 걸렸는지 본다)다 (REQ-20260915-009-2n7g): 실패를 보고 있는
        # 사람에게 필요한 것은 한 번 더 시도하는 것이 아니라 사유다.
        self.assertIn("`s9 sync --status`", text)
        for bad in ("막혔", "섰다", "죽었", "멈췄"):
            self.assertNotIn(bad, text)
        fact = self.m.sync_alert_fact(s, pending=5)
        self.assertEqual((fact["kind"], fact["count"]), ("hook", 3))
        self.assertIn("3회", fact["label"])
        self.assertEqual(fact["text"], text)
        s.success()
        self.assertIsNone(self.m.sync_alert_fact(s, pending=0))
        # 임계 전에는 칩에 서지 않는다
        s.record("hook", HOOK_STDERR, threshold=3)
        self.assertIsNone(self.m.sync_alert_fact(s, pending=1))

    # ---- 알림은 살아 있는 세션 수신함마다 event 한 줄
    def test_notify_writes_event_to_live_inboxes(self):
        m = self.m
        sent = []

        def fake_send(text, sid8=None, sender="", kind="chat", **kw):
            sent.append((sid8, sender, kind, text))
            return sid8
        from unittest import mock
        bindings = [{"session": "aaaaaaaa"}, {"session": "bbbbbbbb", "ended": True}]
        with mock.patch.object(m, "_sync_live_sessions", lambda: ["aaaaaaaa"]), \
                mock.patch.object(m, "chat_send", fake_send):
            n = m._sync_alert_notify({"kind": "hook", "count": 3,
                                      "line": "x: SyntaxWarning", "since": "t"},
                                     pending=2)
        self.assertEqual(n, 1)
        self.assertEqual(sent[0][0], "aaaaaaaa")
        self.assertEqual((sent[0][1], sent[0][2]), ("sync", "event"))
        self.assertIn("2개가 push 되지 않았습니다", sent[0][3])
        del bindings


if __name__ == "__main__":
    unittest.main()
