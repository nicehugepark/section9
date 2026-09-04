"""s9 doctor 의 시야를 시스템 전반으로 넓힌 판정 테스트 (REQ-20260829-004).

배경: 2026-08-29 재부팅 직후 대시보드가 안 열리고 새 서버가 안 떴다. 이미
떠 있던 것은 멀쩡했다 — DOC-20260826-008 이 '고갈의 지문'이라 못박은 그
비대칭이다. 그런데 실제 원인은 포트가 아니라 부트였다(systemd-tmpfiles 가
sysinit 을 73초 붙잡아 그동안 아무것도 리슨하지 못했다, REQ-20260829-003).
사용자가 그때 `s9 doctor` 를 돌렸지만 '정상' 한 줄만 나왔다 — 원인이 doctor
의 시야 밖이었기 때문이다.

그래서 판정 축을 포트 밖으로 넓힌다. 판정은 순수 함수(입력 dict → 등급)로
두고 수집기와 분리해, 실제 시스템 상태에 기대지 않고 등급을 고정한다.

실행: python3 tests/ doctor_system
"""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
DOCTOR = os.path.join(HERE, "..", "bin", "s9-doctor")

spec = importlib.util.spec_from_loader(
    "s9doctor", SourceFileLoader("s9doctor", DOCTOR))
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


class BootVerdict(unittest.TestCase):
    """D1. 부트가 사용자 세션 창을 놓치는지를 본다."""

    def test_boot_verdict(self):
        """D1. 부트가 사용자 세션 창을 놓치는지를 본다."""
        with self.subTest("no_systemd_is_ok"):
            v = doctor.boot_verdict({"init": "init", "userspace_sec": None,
                                     "user_session_failed": False})
            self.assertEqual(v["level"], "ok")
            self.assertIn("systemd", v["line"])
        with self.subTest("slow_boot_grades"):
            def lvl(sec):
                return doctor.boot_verdict(
                    {"init": "systemd", "userspace_sec": sec,
                     "user_session_failed": False})["level"]
            self.assertEqual(lvl(3.0), "ok")
            self.assertEqual(lvl(10.0), "warn")
            self.assertEqual(lvl(29.9), "warn")
            self.assertEqual(lvl(30.0), "critical")
            self.assertEqual(lvl(76.9), "critical")
        with self.subTest("user_session_failure_is_critical_regardless"):
            v = doctor.boot_verdict({"init": "systemd", "userspace_sec": 2.0,
                                     "user_session_failed": True})
            self.assertEqual(v["level"], "critical")
            self.assertIn("사용자 세션", v["line"])
        with self.subTest("unknown_when_timing_unavailable"):
            v = doctor.boot_verdict({"init": "systemd", "userspace_sec": None,
                                     "user_session_failed": False})
            self.assertEqual(v["level"], "unknown")
        with self.subTest("slow_boot_advice_names_the_symptom"):
            v = doctor.boot_verdict({"init": "systemd", "userspace_sec": 76.9,
                                     "user_session_failed": False})
            # 고갈과 지문이 겹친다는 사실 자체가 조치의 핵심이다
            self.assertTrue(v["advice"])
            self.assertIn("부트", v["advice"])

class TmpVerdict(unittest.TestCase):
    """D2. /tmp 누적 — 부트마다 통째로 지워지는 자리라 비용이 여기서 난다."""

    def test_tmp_verdict(self):
        """D2. /tmp 누적 — 부트마다 통째로 지워지는 자리라 비용이 여기서 난다."""
        with self.subTest("entry_grades"):
            def lvl(n):
                return doctor.tmp_verdict(
                    {"entries": n, "dir_bytes": 4096, "ours": 0})["level"]
            self.assertEqual(lvl(20), "ok")
            self.assertEqual(lvl(2001), "warn")
            self.assertEqual(lvl(20001), "critical")
        with self.subTest("grown_directory_is_reported_even_when_empty_now"):
            v = doctor.tmp_verdict({"entries": 19, "dir_bytes": 7860224,
                                    "ours": 13})
            self.assertIn("누적", v["line"])
        with self.subTest("small_directory_says_nothing_about_history"):
            v = doctor.tmp_verdict({"entries": 19, "dir_bytes": 4096, "ours": 0})
            self.assertNotIn("누적", v["line"])

class DiskVerdict(unittest.TestCase):
    """D3. 디스크 — 조용히 차면 s9 는 쓰기부터 죽는다."""

    def test_grades_by_worst_path(self):
        rows = [{"path": "/", "used_pct": 40.0},
                {"path": "/home/x/section9", "used_pct": 91.0}]
        v = doctor.disk_verdict(rows)
        self.assertEqual(v["level"], "warn")
        self.assertIn("section9", v["line"])
        rows[1]["used_pct"] = 96.0
        self.assertEqual(doctor.disk_verdict(rows)["level"], "critical")
        rows[1]["used_pct"] = 50.0
        self.assertEqual(doctor.disk_verdict(rows)["level"], "ok")


class ServeVerdict(unittest.TestCase):
    """D4. '포트가 열려 있다' 와 '실제로 답한다' 는 다른 사실이다."""

    def test_serve_verdict(self):
        """D4. '포트가 열려 있다' 와 '실제로 답한다' 는 다른 사실이다."""
        with self.subTest("listening_but_mute_is_critical"):
            v = doctor.serve_verdict({"listening": True, "responds": False,
                                      "latency": None, "port": 9909})
            self.assertEqual(v["level"], "critical")
        with self.subTest("not_running_is_warn_not_critical"):
            # s9 serve stop 으로 일부러 내린 상태가 있다 — 고장이 아니다
            v = doctor.serve_verdict({"listening": False, "responds": False,
                                      "latency": None, "port": 9909})
            self.assertEqual(v["level"], "warn")
        with self.subTest("slow_response_is_warn"):
            self.assertEqual(doctor.serve_verdict(
                {"listening": True, "responds": True, "latency": 2.5,
                 "port": 9909})["level"], "warn")
            self.assertEqual(doctor.serve_verdict(
                {"listening": True, "responds": True, "latency": 0.1,
                 "port": 9909})["level"], "ok")

class HooksVerdict(unittest.TestCase):
    """D5. 감사 훅과 커밋 게이트가 빠지면 기록이 조용히 끊긴다."""

    def test_hooks_verdict(self):
        """D5. 감사 훅과 커밋 게이트가 빠지면 기록이 조용히 끊긴다."""
        with self.subTest("missing_hooks_are_named"):
            v = doctor.hooks_verdict({"claude_missing": ["Stop", "SessionStart"],
                                      "git_hook": True})
            self.assertEqual(v["level"], "warn")
            self.assertIn("Stop", v["line"])
        with self.subTest("missing_git_hook_is_named"):
            v = doctor.hooks_verdict({"claude_missing": [], "git_hook": False})
            self.assertEqual(v["level"], "warn")
            self.assertIn("pre-commit", v["line"])
        with self.subTest("all_present_is_ok"):
            v = doctor.hooks_verdict({"claude_missing": [], "git_hook": True})
            self.assertEqual(v["level"], "ok")
        with self.subTest("hooks_dir_asked_of_git"):
            d = doctor.git_hooks_dir(os.path.join(HERE, ".."))
            self.assertTrue(d)
            self.assertTrue(os.path.isabs(d), d)

    def test_deps_verdict(self):
        """D6. 없으면 죽는 것과 그 기능만 죽는 것을 가른다."""
        with self.subTest("all_present_is_ok"):
            v = doctor.hooks_verdict({"claude_missing": [], "git_hook": True})
            self.assertEqual(v["level"], "ok")

class RepoVerdict(unittest.TestCase):
    """D5b. 커밋을 못 받는 저장소는 커밋 시점에야 드러난다 — 미리 본다."""

    def test_repo_verdict(self):
        """D5b. 커밋을 못 받는 저장소는 커밋 시점에야 드러난다 — 미리 본다."""
        with self.subTest("bare_flag_on_a_real_worktree_is_critical"):
            v = doctor.repo_verdict({"is_bare": True, "worktree_ok": False,
                                     "branch": "", "worktrees": 3})
            self.assertEqual(v["level"], "critical")
            self.assertIn("core.bare", v["line"])
            self.assertIn("core.bare false", v["advice"])
        with self.subTest("no_worktree_is_critical"):
            self.assertEqual(doctor.repo_verdict(
                {"is_bare": False, "worktree_ok": False, "branch": "",
                 "worktrees": 0})["level"], "critical")
        with self.subTest("healthy_repo_names_branch"):
            v = doctor.repo_verdict({"is_bare": False, "worktree_ok": True,
                                     "branch": "main", "worktrees": 3})
            self.assertEqual(v["level"], "ok")
            self.assertIn("main", v["line"])

class DepsVerdict(unittest.TestCase):
    """D6. 없으면 죽는 것과 그 기능만 죽는 것을 가른다."""

    def test_hooks_verdict(self):
        """D5. 감사 훅과 커밋 게이트가 빠지면 기록이 조용히 끊긴다."""
        with self.subTest("all_present_is_ok"):
            self.assertEqual(doctor.deps_verdict(
                {"missing_required": [], "missing_optional": []})["level"], "ok")

    def test_deps_verdict(self):
        """D6. 없으면 죽는 것과 그 기능만 죽는 것을 가른다."""
        with self.subTest("required_missing_is_critical"):
            v = doctor.deps_verdict({"missing_required": ["git"],
                                     "missing_optional": []})
            self.assertEqual(v["level"], "critical")
            self.assertIn("git", v["line"])
        with self.subTest("optional_missing_is_warn"):
            v = doctor.deps_verdict({"missing_required": [],
                                     "missing_optional": ["chrome"]})
            self.assertEqual(v["level"], "warn")
        with self.subTest("all_present_is_ok"):
            self.assertEqual(doctor.deps_verdict(
                {"missing_required": [], "missing_optional": []})["level"], "ok")

class Overall(unittest.TestCase):
    """D7. 네트워크가 정상이어도 다른 곳이 아프면 '정상' 이라 말하지 않는다."""

    def _clean_net(self, system):
        return {"probe": {"ok": True, "latency": 0.2}, "degraded": False,
                "orphan_test_servers": [], "windows_ports": {},
                "system": system}

    def test_overall(self):
        """D7. 네트워크가 정상이어도 다른 곳이 아프면 '정상' 이라 말하지 않는다."""
        with self.subTest("healthy_everything_says_normal"):
            d = self._clean_net([{"key": "boot", "label": "부트", "level": "ok",
                                  "line": "부트: 빠름", "advice": None}])
            out = "\n".join(doctor.advise(d))
            self.assertIn("정상", out)
        with self.subTest("system_fault_overrides_normal_verdict"):
            d = self._clean_net([
                {"key": "boot", "label": "부트", "level": "critical",
                 "line": "부트: userspace 76.9초", "advice": "부트가 느리다"},
                {"key": "tmp", "label": "/tmp", "level": "ok",
                 "line": "/tmp: 19개", "advice": None}])
            out = "\n".join(doctor.advise(d))
            self.assertNotIn("정상 —", out)
            self.assertIn("부트", out)
            self.assertIn("부트가 느리다", out)
        with self.subTest("worst_level_is_named_first"):
            d = self._clean_net([
                {"key": "tmp", "label": "/tmp", "level": "warn",
                 "line": "/tmp: 많다", "advice": "치워라"},
                {"key": "disk", "label": "디스크", "level": "critical",
                 "line": "디스크: 96%", "advice": "비워라"}])
            lines = doctor.advise(d)
            joined = "\n".join(lines)
            self.assertLess(joined.index("디스크"), joined.index("/tmp"))
        with self.subTest("worst_level_helper"):
            self.assertEqual(doctor.worst_level(["ok", "warn", "critical"]),
                             "critical")
            self.assertEqual(doctor.worst_level(["ok", "unknown"]), "unknown")
            self.assertEqual(doctor.worst_level(["ok", "ok"]), "ok")
            self.assertEqual(doctor.worst_level([]), "ok")

class Shape(unittest.TestCase):
    """D8. 수집 결과의 모양 — 기계 판독이 항목을 셀 수 있어야 한다."""

    def test_system_checks_shape(self):
        rows = doctor.system_checks()
        self.assertTrue(rows)
        keys = {r["key"] for r in rows}
        for want in ("boot", "tmp", "disk", "serve", "repo", "hooks", "deps"):
            self.assertIn(want, keys)
        for r in rows:
            self.assertIn(r["level"],
                          ("ok", "warn", "critical", "unknown"), r)
            self.assertTrue(r["line"].strip(), r)
            self.assertTrue(r["label"].strip(), r)

    def test_json_carries_system(self):
        r = subprocess.run(["python3", DOCTOR, "--json"],
                           capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode in (0, 1), True, r.stderr[-500:])
        d = json.loads(r.stdout)
        self.assertIn("system", d)
        self.assertTrue(any(x["key"] == "boot" for x in d["system"]))


class DeadStampDistrust(unittest.TestCase):
    """D9. 죽은 pid 의 지문은 믿지 않는다 (REQ-20260830-005 (다)).

    실사고 2026-08-30 아침: 시험이 남긴 임시 포트 지문(pid 죽음, port 18898)을
    doctor 가 그대로 믿고 죽은 포트를 두드리며 "서버가 안 떠 있다"고 했다 —
    실제 대시보드는 9909 에서 멀쩡히 돌고 있었다 (REQ-20260830-004)."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9doc-")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        self._old_root = doctor.ROOT
        doctor.ROOT = self.root
        self._old_env = os.environ.pop("S9_PORT", None)
        # 규범 포트를 아무도 안 듣는 포트로 — 실제 리스너에 붙지 않게.
        # 임시 포트를 직접 bind 하면 안 된다(port_pool 계약): 병렬의 다른
        # 시험이 그 순간 같은 포트를 받을 수 있다 — 실제로 두 번 충돌했다.
        import portpool
        self.canon = portpool.free_port()
        with open(os.path.join(self.root, "state", "port"), "w") as f:
            f.write(str(self.canon))

    def tearDown(self):
        doctor.ROOT = self._old_root
        if self._old_env is not None:
            os.environ["S9_PORT"] = self._old_env

    def stamp(self, d):
        with open(os.path.join(self.root, "state", "serve-code.json"),
                  "w", encoding="utf-8") as f:
            json.dump(d, f)

    # D9a. 죽은 pid 지문 → 지문 포트가 아니라 규범 포트(state/port·9909)로
    def test_dead_pid_falls_back_to_canonical_port(self):
        self.stamp({"pid": 999999999, "port": 18898})
        self.assertEqual(doctor.serve_info()["port"], self.canon)

    # D9b. 살아 있는 pid 지문 → 지문 포트를 그대로 쓴다
    def test_live_pid_stamp_is_trusted(self):
        self.stamp({"pid": os.getpid(), "port": 18899})
        self.assertEqual(doctor.serve_info()["port"], 18899)

    # D9c. pid 가 없는(0 포함) 지문도 불신 — 지문 없음과 같이 규범 포트로
    def test_no_pid_stamp_is_distrusted(self):
        self.stamp({"port": 18898})
        self.assertEqual(doctor.serve_info()["port"], self.canon)
        os.unlink(os.path.join(self.root, "state", "serve-code.json"))
        self.assertEqual(doctor.serve_info()["port"], self.canon)


if __name__ == "__main__":
    unittest.main(verbosity=2)
