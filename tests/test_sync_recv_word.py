"""시간 안에 못 끝낸 것과 못 닿은 것은 다른 사실이다 (REQ-20260917-001-2n7g).

실측 2026-09-17 (맥미니): 상태 줄이 「받기 실패 — origin 에 닿지 못합니다」를
한 시간에 세 번 띄웠는데 망은 멀쩡했다 — 그때마다 손으로 `git fetch origin` 을
걸면 종료 0 이었고, state/sync.jsonl 의 폴 이벤트는 net·ok·net·ok 로 엇갈렸다.
정말 못 닿는 것이면 그렇게 번갈아 들지 않는다.

까닭은 `_sync_poll_once` 의 `except Exception: return "net"` 이
`subprocess.TimeoutExpired` 까지 삼킨 것이다. 같은 파일의 `sync_poll_classify`
주석이 같은 계보의 사고를 적고 있다 — 2026-09-08~09 에 142회 연속 실패가 전부
「net」으로 적혔는데 fetch 는 됐다. 그때 dirty·diverged 를 갈랐고 **시간 초과만
net 에 남아 있었다.**

낱말이 값을 갖는 까닭은 하나다: 사람이 **무엇을 할지**가 갈린다. 못 닿으면
네트워크·인증을 보고, 시간이 모자라면 기다린다. 앞의 말을 띄우고 스스로 회복하면
사람은 없는 고장을 찾으러 간다.

이 시험이 지키는 계약:
  ① 시간 초과는 「timeout」이다 — 「net」이 아니다.
  ② 상태 줄의 낱말이 갈린다. 시간 초과 쪽은 「실패」라 부르지 않는다.
  ③ 다음 행동도 갈린다 — 시간 초과에는 네트워크를 보라고 하지 않는다.
  ④ 정말 못 닿는 실패는 종전대로 「net」이고, dirty·diverged·busy 도 그대로다.
  ⑤ 시간 초과는 「받았다」로 세지 않는다.
  ⑥ 폴의 자가 이 저장소의 실측 fetch 시간을 덮는다.

실행: python3 tests/ sync_recv_word
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


def _load():
    name = "s9_recvword"
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TimeoutIsNotUnreachable(unittest.TestCase):
    """① 시간 초과는 제 이름을 갖는다."""

    def setUp(self):
        self.m = _load()

    def _poll_with(self, exc):
        with mock.patch.object(self.m, "sync_mode", lambda: "remote"), \
             mock.patch.object(self.m, "_sync_commit_busy", lambda: False), \
             mock.patch.object(self.m, "_sync_clear_stale_index_lock", lambda: None), \
             mock.patch.object(self.m, "_sync_lock_take", lambda *a, **k: ""):
            # 잠금을 못 잡으면 busy — 그 갈래가 살아 있는지부터 본다
            self.assertEqual(self.m._sync_poll_once(), "busy")
        with mock.patch.object(self.m, "sync_mode", lambda: "remote"), \
             mock.patch.object(self.m, "_sync_commit_busy", lambda: False), \
             mock.patch.object(self.m, "_sync_clear_stale_index_lock", lambda: None), \
             mock.patch.object(self.m, "_sync_lock_take",
                               lambda *a, **k: os.path.join(HERE, "..", "state", ".x")), \
             mock.patch.object(self.m, "_sync_git", lambda *a, **k: mock.Mock(stdout="")), \
             mock.patch.object(self.m, "git_run", side_effect=exc), \
             mock.patch.object(self.m.os, "remove", lambda p: None):
            return self.m._sync_poll_once()

    def test_a_timeout_says_timeout(self):
        got = self._poll_with(subprocess.TimeoutExpired(cmd="git pull", timeout=20))
        self.assertEqual(got, "timeout",
                         "시간 안에 못 끝낸 것을 못 닿았다고 적는다")

    def test_a_real_failure_is_still_net(self):
        """④ 정말 못 닿는 것은 종전대로 net 이다 — 갈래를 늘리되 옮기지 않는다."""
        got = self._poll_with(OSError("could not resolve host"))
        self.assertEqual(got, "net")


class TheWordsSplit(unittest.TestCase):
    """②③ 화면의 말과 다음 행동이 갈린다."""

    def setUp(self):
        self.m = _load()

    def test_the_status_line_does_not_say_unreachable(self):
        word = self.m.SYNC_RECV_WORD["timeout"]
        self.assertNotIn("닿지", word, "시간 초과에 못 닿았다고 적는다")
        self.assertNotIn("실패", word,
                         "다음 회차가 대개 그냥 받는데 실패라 부른다")
        self.assertIn("시간", word)

    def test_unreachable_keeps_its_own_word(self):
        self.assertIn("닿지", self.m.SYNC_RECV_WORD["net"])

    def test_the_line_carries_it(self):
        line = self.m.sync_status_line(
            {"last_sent": 0, "last_received": 0, "pending": 0,
             "recv_kind": "timeout"}, now=0)
        self.assertIn(self.m.SYNC_RECV_WORD["timeout"], line)

    def test_the_next_step_is_not_check_the_network(self):
        """③ 시간 초과에 네트워크를 보라고 하면 사람을 없는 고장으로 보낸다."""
        hint = self.m.sync_status_hint({"recv_level": "late", "recv_kind": "timeout"})
        self.assertNotIn("네트워크", hint)
        self.assertNotIn("인증", hint)
        self.assertIn("기다", hint)

    def test_the_network_step_is_unchanged(self):
        hint = self.m.sync_status_hint({"recv_level": "late", "recv_kind": "net"})
        self.assertIn("네트워크", hint)


class WhatStillCounts(unittest.TestCase):
    """⑤⑥ 센 것과 재는 자."""

    def setUp(self):
        self.m = _load()

    def test_a_timeout_is_not_a_receipt(self):
        """받지 못한 회차를 「받았다」로 올리면 다른 컴퓨터가 이 컴퓨터를 오해한다."""
        called = []
        with mock.patch.object(self.m, "sync_mode", lambda: "remote"), \
             mock.patch.object(self.m, "_sync_commit_busy", lambda: False), \
             mock.patch.object(self.m, "_sync_poll_once", lambda t: "timeout"), \
             mock.patch.object(self.m, "_sync_poll_record", lambda *a, **k: None), \
             mock.patch.object(self.m, "machine_recv_beat",
                               lambda **k: called.append(k)):
            self.assertEqual(self.m.sync_poll(), "timeout")
        self.assertEqual(called, [], "못 받은 회차를 받았다고 올렸다")

    def test_every_network_git_gets_the_same_limit(self):
        """망을 타는 git 셋이 한 자를 쓴다 (REQ-20260918-002 · -003).

        세 번 반쪽으로 고친 자리다: 폴만 → 당기기 셋만 → push. 그래서 **부르는
        자리마다** 재지 않고, 실제로 git 에 넘어가는 자를 받아 본다.
        """
        import inspect
        sig = inspect.signature(self.m._sync_pull_cmd)
        self.assertEqual(sig.parameters["timeout"].default,
                         self.m.SYNC_NET_TIMEOUT_SEC,
                         "당기기의 기본 자가 망의 자와 다르다")

        seen = []

        def rec(*argv, timeout=6):
            seen.append((argv[0] if argv else "", timeout))
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(self.m, "_sync_git", rec):
            self.m._sync_pull_cmd()
        got = {name: t for name, t in seen}
        self.assertEqual(got.get("fetch"), self.m.SYNC_NET_TIMEOUT_SEC,
                         f"fetch 가 다른 자를 받는다: {seen}")
        self.assertEqual(got.get("rebase"), self.m.SYNC_NET_TIMEOUT_SEC,
                         f"위쪽으로 rebase 가 다른 자를 받는다: {seen}")

    def test_a_whole_transport_round_hands_both_the_same_limit(self):
        """당기기만 늘리면 회차는 여전히 통째로 물러난다 (REQ-20260918-003-2n7g).

        실측 2026-09-18: pull 이 12.3~17.0초로 성공하게 된 그 회차가, 8초로
        남아 있던 push(잰 값 5.0~5.8초) 때문에 시간 초과로 물러났다. 그래서
        한 자리씩 보지 않고 **회차를 실제로 돌려** 넘어가는 자를 받아 본다.
        """
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp(prefix="s9netlimit-")
        try:
            os.makedirs(os.path.join(tmp, "state"), exist_ok=True)
            old = os.environ.get("S9_ROOT")
            os.environ["S9_ROOT"] = tmp
            try:
                m = _load()          # 임시 뿌리로 다시 읽는다 (잠금·큐가 거기 선다)
            finally:
                if old is None:
                    os.environ.pop("S9_ROOT", None)
                else:
                    os.environ["S9_ROOT"] = old

            seen = []

            def rec(*argv, timeout=6):
                seen.append((argv[0] if argv else "", timeout))
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(m, "sync_mode", lambda: "remote"), \
                 mock.patch.object(m, "_sync_git", rec), \
                 mock.patch.object(m, "_sync_pull_cmd",
                                   lambda timeout=m.SYNC_NET_TIMEOUT_SEC:
                                   rec("pull", timeout=timeout)), \
                 mock.patch.object(m, "_sync_event", lambda *a, **k: None), \
                 mock.patch.object(m, "_sync_log", lambda *a, **k: None), \
                 mock.patch.object(m, "_sync_pull_stamp", lambda: None):
                self.assertEqual(m.sync_run(reason="probe", transport=True), "ok")
            got = [x for x in seen if x[0] in ("pull", "push")]
            self.assertEqual(got, [("pull", m.SYNC_NET_TIMEOUT_SEC),
                                   ("push", m.SYNC_NET_TIMEOUT_SEC)],
                             f"회차가 당기기와 밀기에 같은 자를 주지 않는다: {seen}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_local_git_keeps_its_own_limit(self):
        """지역 명령까지 늘리지 않는다 — 늘리는 것과 남을 세워 두는 것은 맞바꿈이다."""
        import inspect
        sig = inspect.signature(self.m._sync_git)
        self.assertEqual(sig.parameters["timeout"].default, 6)
        self.assertLess(6, self.m.SYNC_NET_TIMEOUT_SEC)

    def test_the_limit_covers_what_we_measured(self):
        """⑥ 잰 값(최대 7.34초)을 덮는 자라야 이 사고가 안 난다.

        자를 8초로 되돌리면 실측의 최댓값이 상한에서 0.7초 안에 들어와,
        다섯 중 하나가 다시 시간 초과가 된다.
        """
        self.assertGreaterEqual(self.m.SYNC_NET_TIMEOUT_SEC, 15)
        # 끝없이 늘리는 것도 답이 아니다 — 폴은 동기화 잠금을 쥐고 돌고,
        # 그동안 `s9 commit` 이 기다린다.
        self.assertLessEqual(self.m.SYNC_NET_TIMEOUT_SEC, 60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
