"""테스트가 /tmp 를 흘리지 않는가 (REQ-20260829-003).

2026-08-29 실측: 부팅 48분 만에 /tmp 최상위 128개 중 127개가 우리 테스트
것이었다. tests/*.py 84개가 mkdtemp 로 만들고 지우지 않는다. 그 대가는 부트에서
돌아온다 — systemd-tmpfiles 가 부트마다 /tmp 를 통째로 지우느라 73초를 쓰고,
그동안 sysinit 이 막혀 WSL 의 10초 사용자 세션 창을 놓친다.

파일마다 tearDown 을 84번 심는 대신 러너에서 문을 닫는다: 실행마다 전용 루트를
세우고 tempfile·TMPDIR 을 그리로 돌린 뒤, 끝나면 통째로 지운다. 여기서는 그
계약을 못박는다 — 특히 **남의 것은 절대 건드리지 않는다**.

실행: python3 tests/ tmp_hygiene
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tmproot  # noqa: E402


class Naming(unittest.TestCase):
    """T5. 우리 것과 남의 것을 이름으로 가른다."""

    def test_naming(self):
        """T5. 우리 것과 남의 것을 이름으로 가른다."""
        with self.subTest("ours"):
            for n in ("s9gate-abc", "s9run-1234-xy", "s9hookstamp-q", "s9-portpool"):
                self.assertTrue(tmproot.is_ours(n), n)
        with self.subTest("not_ours"):
            for n in ("claude-1000", "snap-private-tmp", ".X11-unix",
                      "systemd-private-abc-systemd-logind.service-ZG4TI0",
                      "tmp1234", "pip-build-x"):
                self.assertFalse(tmproot.is_ours(n), n)
        with self.subTest("run_root_pid_parsed"):
            self.assertEqual(tmproot.run_root_pid("s9run-4242-abcd"), 4242)
            self.assertIsNone(tmproot.run_root_pid("s9gate-abcd"))
            self.assertIsNone(tmproot.run_root_pid("s9run-notapid-x"))

class Stale(unittest.TestCase):
    """T4. 무엇을 거두고 무엇을 남기는가 — 판정만 따로 시험한다."""

    def setUp(self):
        self.base = "/base"
        self.now = 10_000.0
        self.ages = {}

    def stale(self, names, alive=lambda pid: False):
        return [os.path.basename(p) for p in tmproot.stale_dirs(
            self.base, now=self.now, alive=alive, names=names,
            mtime=lambda p: self.ages[os.path.basename(p)])]

    def test_old_ours_is_swept(self):
        self.ages = {"s9gate-a": 0.0}
        self.assertEqual(self.stale(["s9gate-a"]), ["s9gate-a"])

    def test_fresh_ours_is_left(self):
        """방금 만들어진 것은 지금 도는 누군가의 것일 수 있다."""
        self.ages = {"s9gate-a": self.now - 60}
        self.assertEqual(self.stale(["s9gate-a"]), [])

    def test_live_run_root_is_left_however_old(self):
        self.ages = {"s9run-777-a": 0.0}
        self.assertEqual(self.stale(["s9run-777-a"], alive=lambda p: p == 777),
                         [])

    def test_dead_run_root_is_swept(self):
        self.ages = {"s9run-777-a": 0.0}
        self.assertEqual(self.stale(["s9run-777-a"], alive=lambda p: False),
                         ["s9run-777-a"])

    def test_shared_port_lock_is_never_swept(self):
        """s9-portpool 은 실행끼리 나눠 쓰는 락이다 — 나이로 지우면 두 실행이
        같은 포트를 제 것이라 믿는다."""
        self.ages = {"s9-portpool": 0.0}
        self.assertEqual(self.stale(["s9-portpool"]), [])

    def test_others_are_never_swept_however_old(self):
        names = ["claude-1000", "snap-private-tmp", ".X11-unix",
                 "systemd-private-x-systemd-logind.service-ZG4TI0"]
        self.ages = {n: 0.0 for n in names}
        self.assertEqual(self.stale(names), [])


class RunRoot(unittest.TestCase):
    """T1·T2·T3. 세우고, 그 안에 담기고, 통째로 사라진다."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="s9tmphyg-")
        self._tmpdir = tempfile.tempdir
        self._env = os.environ.get("TMPDIR")

    def tearDown(self):
        tempfile.tempdir = self._tmpdir
        if self._env is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = self._env
        import shutil
        shutil.rmtree(self.base, ignore_errors=True)

    def test_mkdtemp_lands_inside_the_run_root(self):
        root, prev = tmproot.make_run_root(base=self.base)
        try:
            self.assertTrue(os.path.basename(root).startswith(
                tmproot.RUN_PREFIX + str(os.getpid()) + "-"), root)
            d = tempfile.mkdtemp(prefix="s9gate-")
            self.assertEqual(os.path.dirname(d), root,
                             "테스트가 만든 자리가 루트 밖이다")
            self.assertEqual(os.environ["TMPDIR"], root)
        finally:
            tmproot.drop_run_root(root, prev)

    def test_drop_removes_everything_and_names_what_was_left(self):
        root, prev = tmproot.make_run_root(base=self.base)
        os.mkdir(os.path.join(root, "s9gate-aaa"))
        os.mkdir(os.path.join(root, "s9doc-bbb"))
        left = tmproot.drop_run_root(root, prev)
        self.assertEqual(left, ["s9doc-bbb", "s9gate-aaa"])
        self.assertFalse(os.path.exists(root))

    def test_drop_restores_the_previous_tmpdir(self):
        os.environ["TMPDIR"] = "/previous"
        root, prev = tmproot.make_run_root(base=self.base)
        tmproot.drop_run_root(root, prev)
        self.assertEqual(os.environ.get("TMPDIR"), "/previous")
        self.assertIsNone(tempfile.tempdir)

    def test_sweep_stale_actually_removes(self):
        old = os.path.join(self.base, "s9gate-old")
        keep = os.path.join(self.base, "claude-1000")
        os.mkdir(old)
        os.mkdir(keep)
        os.utime(old, (0, 0))
        os.utime(keep, (0, 0))
        gone = tmproot.sweep_stale(base=self.base)
        self.assertEqual([os.path.basename(p) for p in gone], ["s9gate-old"])
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(keep), "남의 것을 지웠다")


class DoctorSweep(unittest.TestCase):
    """러너 밖에서도 닫는다 — 옛 체크아웃·워크트리의 러너 사본은 그대로 흘린다.

    그 자리는 매분 도는 회수 틱(s9-doctor --sweep)이 맡는다. 러너와 규칙이
    같아야 한다: 우리 표식만, 살아 있는 실행 루트는 남긴다.
    """

    def setUp(self):
        import importlib.util
        from importlib.machinery import SourceFileLoader
        path = os.path.join(HERE, "..", "bin", "s9-doctor")
        sp = importlib.util.spec_from_loader(
            "s9doctor_tmp", SourceFileLoader("s9doctor_tmp", path))
        self.d = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(self.d)
        self.base = tempfile.mkdtemp(prefix="s9tmpsw-")
        self.addCleanup(__import__("shutil").rmtree, self.base,
                        ignore_errors=True)

    def _old(self, name):
        p = os.path.join(self.base, name)
        os.mkdir(p)
        os.utime(p, (0, 0))
        return p

    def test_sweeps_our_stale_dirs(self):
        self._old("s9gate-x")
        self._old("s9hookstamp-y")
        r = self.d.sweep_stale_tmp(base=self.base)
        self.assertEqual(r["dirs"], 2)
        self.assertEqual(os.listdir(self.base), [])

    def test_never_touches_others(self):
        for n in ("claude-1000", "snap-private-tmp", ".X11-unix",
                  "systemd-private-a-systemd-logind.service-Z"):
            self._old(n)
        r = self.d.sweep_stale_tmp(base=self.base)
        self.assertEqual(r["dirs"], 0)
        self.assertEqual(len(os.listdir(self.base)), 4)

    def test_live_run_root_survives(self):
        self._old(f"s9run-{os.getpid()}-abcd")
        self._old("s9run-999999-dead")
        r = self.d.sweep_stale_tmp(base=self.base)
        self.assertEqual(r["dirs"], 1)
        self.assertEqual(os.listdir(self.base),
                         [f"s9run-{os.getpid()}-abcd"])

    def test_shared_port_lock_survives(self):
        self._old("s9-portpool")
        self.assertEqual(self.d.sweep_stale_tmp(base=self.base)["dirs"], 0)

    def test_keep_list_matches_the_runner(self):
        self.assertEqual(set(self.d.TMP_KEEP), set(tmproot.KEEP))

    def test_fresh_dirs_survive(self):
        os.mkdir(os.path.join(self.base, "s9gate-fresh"))
        self.assertEqual(self.d.sweep_stale_tmp(base=self.base)["dirs"], 0)

    def test_same_stale_age_as_the_runner(self):
        self.assertEqual(self.d.TMP_STALE_AGE, tmproot.STALE_AGE)


class Runner(unittest.TestCase):
    """T2·T3·T6. 러너가 실제로 문을 닫는가 — 진짜로 돌려서 본다."""

    def _run(self, pattern, leak=True):
        env = {**os.environ}
        env.pop("TMPDIR", None)
        env["S9_TESTS_NESTED"] = "1"   # 바깥 실행의 세계를 청소하지 않는다
        if leak:
            env["S9_TMP_LEAK_PROBE"] = "1"
        return subprocess.run([sys.executable, HERE, pattern], env=env,
                              capture_output=True, text=True, timeout=600,
                              cwd=os.path.dirname(HERE))

    def test_runner(self):
        """T2·T3·T6. 러너가 실제로 문을 닫는가 — 진짜로 돌려서 본다."""
        with self.subTest("a_real_run_leaves_nothing_behind_in_tmp"):
            before = set(os.listdir(tmproot.SYS_TMP))
            r = self._run("tmp_leak_probe")
            self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
            after = set(os.listdir(tmproot.SYS_TMP))
            new = {n for n in after - before if tmproot.is_ours(n)}
            self.assertEqual(new, set(),
                             f"실행이 /tmp 에 남긴 것: {sorted(new)}")
        with self.subTest("runner_reports_what_it_reaped"):
            r = self._run("tmp_leak_probe")
            self.assertIn("임시자리", r.stderr,
                          "조용히 치웠다 — 무엇이 남았는지 알리지 않는다")
        with self.subTest("subprocess_inherits_the_run_root"):
            r = self._run("tmp_leak_probe")
            self.assertIn("PROBE-CHILD-INSIDE", r.stderr + r.stdout)

if __name__ == "__main__":
    unittest.main(verbosity=2)
