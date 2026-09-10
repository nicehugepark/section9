"""죽은 실행 자리가 아이노드를 바닥내지 않는가 (REQ-20260910-012).

실측 2026-09-10 17:00. `df -i /tmp` 가 1,048,576 중 남은 것 0 을 냈다. 그
상태에서는 bash 도구가 제 출력 파일조차 만들지 못해 s9 명령도 테스트도 아무것도
돌지 않았다 — 작업자가 32분 멈춰 보인 자리가 이것이다. 남아 있던 것은 전부
`s9run-<pid>-` 실행 루트였고 pid 는 전부 이미 없었으며(그중 하나가 32,746개),
거두니 35,921 개가 돌아왔다.

왜 안 거둬졌나. 회수(러너 시작 · s9-doctor 틱)는 주인 없는 실행 루트에도 「한
시간」 나이 문턱을 걸고 있었다. 그날 여덟 자리는 전부 한 시간이 안 된 것이었다 —
바닥나는 데 걸린 시간이 그보다 짧았다.

여기서 못박는 것 둘.
  ① 주인 pid 가 없는 실행 루트는 **나이를 묻지 않고** 거둔다. pid 가 없다는 것은
     짐작이 아니라 확정이다. 나이 문턱은 pid 로 주인을 물을 수 없는 자리에만 남는다.
  ② 남은 아이노드가 바닥이면 **시작하지 않는다.** 바닥난 채로 시작하면 실패가
     원인과 상관없는 모습으로 파일마다 흩어져, 무엇이 문제인지 아무 데도 안 적힌다.

실행: python3 tests/ tmp_inodes
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tmproot  # noqa: E402


def _statvfs(free, total):
    class R:
        f_favail = free
        f_ffree = free
        f_files = total
    return lambda path: R()


class DeadRunRoot(unittest.TestCase):
    """시나리오 1·2·3. 주인이 없으면 나이를 묻지 않는다."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="s9inode-")
        self.addCleanup(__import__("shutil").rmtree, self.base,
                        ignore_errors=True)

    def _mk(self, name, mtime=None):
        p = os.path.join(self.base, name)
        os.mkdir(p)
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def test_dead_run_root_is_swept_however_fresh(self):
        """1. 방금 만들어졌어도 pid 가 없으면 거둔다 — 그날 사고의 자리다."""
        p = self._mk("s9run-999999-justnow")          # 방금
        gone = tmproot.sweep_stale(base=self.base, alive=lambda pid: False)
        self.assertEqual(gone, [p])
        self.assertFalse(os.path.exists(p))

    def test_live_run_root_survives_however_old(self):
        """2. 살아 있는 실행의 자리는 아무리 오래돼도 남긴다."""
        p = self._mk("s9run-777-old", mtime=0)
        gone = tmproot.sweep_stale(base=self.base, alive=lambda pid: pid == 777)
        self.assertEqual(gone, [])
        self.assertTrue(os.path.exists(p))

    def test_fresh_non_run_dir_still_waits_for_the_age(self):
        """3. pid 로 주인을 물을 수 없는 자리에는 나이 문턱이 그대로 남는다 —
        지금 도는 누군가의 것일 수 있다."""
        p = self._mk("s9gate-fresh")
        self.assertEqual(tmproot.sweep_stale(base=self.base,
                                             alive=lambda pid: False), [])
        self.assertTrue(os.path.exists(p))

    def test_others_are_untouched(self):
        """남의 것은 이름이 무엇이든 건드리지 않는다 (기존 계약)."""
        p = self._mk("claude-1000", mtime=0)
        self.assertEqual(tmproot.sweep_stale(base=self.base,
                                             alive=lambda pid: False), [])
        self.assertTrue(os.path.exists(p))


class Verdict(unittest.TestCase):
    """시나리오 4~7. 아이노드를 어떻게 읽고 무엇이라 말하는가."""

    def test_plenty_is_silent(self):
        """4. 넉넉하면 아무 말도 하지 않는다."""
        level, line = tmproot.inode_verdict(500_000, 1_048_576)
        self.assertEqual(level, "ok")
        self.assertIsNone(line)

    def test_below_one_run_warns_but_keeps_going(self):
        """5. 전체 실행 한 번 몫이 안 남았으면 알리되 막지는 않는다."""
        level, line = tmproot.inode_verdict(30_000, 1_048_576)
        self.assertEqual(level, "warn")
        self.assertIn("30,000", line)

    def test_floor_stops_and_says_the_way_out(self):
        """6. 바닥이면 멈추고, 남은 수와 여는 길을 한 줄에 적는다."""
        level, line = tmproot.inode_verdict(120, 1_048_576)
        self.assertEqual(level, "stop")
        self.assertIn("120", line)
        self.assertIn("TMPDIR", line)
        self.assertIn("S9_TMP_ANYWAY", line)

    def test_filesystem_that_does_not_count_is_not_judged(self):
        """7. 아이노드를 미리 정해 두지 않는 파일시스템은 판정하지 않는다 —
        모르는 것을 아는 척해 실행을 막지 않는다."""
        self.assertEqual(tmproot.inode_free(statvfs=_statvfs(0, 0)),
                         (None, None))
        level, line = tmproot.inode_verdict(None, None)
        self.assertEqual(level, "unknown")
        self.assertIsNone(line)
        ok, line = tmproot.inode_gate(env={}, statvfs=_statvfs(0, 0))
        self.assertTrue(ok)
        self.assertIsNone(line)

    def test_reads_the_real_filesystem(self):
        """실제 파일시스템에서도 숫자가 나온다 — 못 읽으면 (None, None)."""
        free, total = tmproot.inode_free()
        if total is not None:
            self.assertGreaterEqual(free, 0)
            self.assertGreater(total, 0)


class Gate(unittest.TestCase):
    """시나리오 8·9. 문턱을 넘겼을 때 러너가 실제로 어떻게 하는가."""

    def test_gate_blocks_at_the_floor(self):
        ok, line = tmproot.inode_gate(env={}, statvfs=_statvfs(5, 1_000_000))
        self.assertFalse(ok)
        self.assertIn("아이노드", line)

    def test_env_moves_the_floor(self):
        env = {"S9_TMP_INODE_FLOOR": "900000"}
        ok, _ = tmproot.inode_gate(env=env, statvfs=_statvfs(500_000, 1_000_000))
        self.assertFalse(ok)

    def test_anyway_passes_through_but_still_says_it(self):
        """9. 사람이 알고 지나가는 것이지 판정이 사라지는 것이 아니다."""
        env = {"S9_TMP_ANYWAY": "1"}
        ok, line = tmproot.inode_gate(env=env, statvfs=_statvfs(5, 1_000_000))
        self.assertTrue(ok)
        self.assertIn("S9_TMP_ANYWAY=1", line)

    def _run(self, extra):
        # 안쪽 실행은 바깥 스위트의 세계를 청소하지 않는다(S9_TESTS_NESTED=1).
        # 아이노드 판정은 읽기만 하므로 안쪽에서도 그대로 선다.
        env = {**os.environ, "S9_TESTS_NESTED": "1", "S9_TMP_LEAK_PROBE": "1"}
        env.pop("TMPDIR", None)
        env.update(extra)
        return subprocess.run([sys.executable, HERE, "--local", "tmp_leak_probe"],
                              env=env, capture_output=True, text=True,
                              timeout=300, cwd=os.path.dirname(HERE))

    def test_runner_refuses_to_start_when_the_floor_is_hit(self):
        """8. 진짜로 돌려서 본다 — 시험을 하나도 시작하지 않고 2 로 끝난다."""
        r = self._run({"S9_TMP_INODE_FLOOR": "999999999"})
        self.assertEqual(r.returncode, 2, r.stdout[-800:] + r.stderr[-800:])
        self.assertIn("아이노드", r.stderr)
        self.assertNotIn("PROBE-CHILD-INSIDE", r.stdout + r.stderr)

    def test_runner_goes_on_when_told_anyway(self):
        r = self._run({"S9_TMP_INODE_FLOOR": "999999999",
                       "S9_TMP_ANYWAY": "1"})
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        self.assertIn("PROBE-CHILD-INSIDE", r.stdout + r.stderr)


class Doctor(unittest.TestCase):
    """시나리오 10·11. 러너 밖의 회수·진단도 같은 규칙으로 선다."""

    def setUp(self):
        path = os.path.join(HERE, "..", "bin", "s9-doctor")
        sp = importlib.util.spec_from_loader(
            "s9doctor_ino", SourceFileLoader("s9doctor_ino", path))
        self.d = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(self.d)
        self.base = tempfile.mkdtemp(prefix="s9inodoc-")
        self.addCleanup(__import__("shutil").rmtree, self.base,
                        ignore_errors=True)

    def test_dead_run_root_is_swept_however_fresh(self):
        """10. 매분 도는 회수도 나이를 묻지 않는다 — 러너와 같은 규칙."""
        p = os.path.join(self.base, "s9run-999999-justnow")
        os.mkdir(p)
        self.assertEqual(self.d.sweep_stale_tmp(base=self.base)["dirs"], 1)
        self.assertFalse(os.path.exists(p))

    def test_live_run_root_still_survives(self):
        os.mkdir(os.path.join(self.base, f"s9run-{os.getpid()}-mine"))
        self.assertEqual(self.d.sweep_stale_tmp(base=self.base)["dirs"], 0)

    def test_thresholds_match_the_runner(self):
        """판정이 두 벌이면 한쪽이 괜찮다는 자리에서 다른 쪽이 멈춘다."""
        self.assertEqual(self.d.TMP_INODE_WARN, tmproot.INODE_RUN_NEED)
        self.assertEqual(self.d.TMP_INODE_CRIT, tmproot.INODE_FLOOR)

    def test_verdict_rises_on_inode_pressure(self):
        """11. 최상위가 몇 개뿐이어도 아이노드가 바닥이면 등급이 오른다."""
        base = {"entries": 8, "ours": 8, "dir_bytes": 4096}
        ok = self.d.tmp_verdict({**base, "inode_free": 900_000,
                                 "inode_total": 1_048_576})
        self.assertEqual(ok["level"], "ok")
        warn = self.d.tmp_verdict({**base, "inode_free": 30_000,
                                   "inode_total": 1_048_576})
        self.assertEqual(warn["level"], "warn")
        crit = self.d.tmp_verdict({**base, "inode_free": 0,
                                   "inode_total": 1_048_576})
        self.assertEqual(crit["level"], "critical")
        self.assertIn("아이노드", crit["line"])

    def test_verdict_is_unchanged_when_inodes_are_unknown(self):
        v = self.d.tmp_verdict({"entries": 8, "ours": 8, "dir_bytes": 4096,
                                "inode_free": None, "inode_total": None})
        self.assertEqual(v["level"], "ok")
        self.assertNotIn("아이노드", v["line"])

    def test_info_reports_inodes(self):
        info = self.d.tmp_info(self.base)
        self.assertIn("inode_free", info)
        self.assertIn("inode_total", info)


if __name__ == "__main__":
    unittest.main(verbosity=2)
