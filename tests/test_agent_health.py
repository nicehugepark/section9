"""에이전트 헬스체크 테스트 (REQ-20260825-089-62x6).

설계 근거: DOC-20260825-003-62x6 3단계.
사고: fable 한도로 스폰 직후 죽은 워커가 앰버 점멸로 10분간 "기동 중"이었다.
**신호가 생존을 보증하지 않았다.** 이 테스트가 고정하는 것은 그 반대다 —
판정은 pid 생존·진전·기록된 상태라는 근거에서만 나온다.

격리: S9_ROOT=mktemp. 서버는 띄우지 않는다 (포트 규율).
실행: python3 tests/ agent_health
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

_spec = importlib.util.spec_from_loader(
    "s9health", importlib.machinery.SourceFileLoader("s9health", S9))
s9 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s9)


class JudgeTest(unittest.TestCase):
    """H1~H5, H9: 순수 판정 함수 — 파일시스템 없이 규칙만 고정한다."""

    def test_judge_test(self):
        """H1~H5, H9: 순수 판정 함수 — 파일시스템 없이 규칙만 고정한다."""
        with self.subTest("h1_lead"):
            st, _ = s9.judge_health("lead:claude-opus-5", age=10, pid_alive=True)
            self.assertEqual(st, "alive")
            st, why = s9.judge_health("lead:claude-opus-5", age=10, pid_alive=False)
            self.assertEqual(st, "failed")
            self.assertTrue(why)
            st, _ = s9.judge_health("lead:claude-opus-5", age=9999, pid_alive=None)
            self.assertEqual(st, "stalled")
        with self.subTest("h2_sub"):
            self.assertEqual(
                s9.judge_health("sub:designer:a1fefd40", age=30)[0], "alive")
            self.assertEqual(
                s9.judge_health("sub:designer:a1fefd40", age=600)[0], "stalled")
        with self.subTest("h3_worker_failed_on_limit_log"):
            st, why = s9.judge_health(
                "worker:auto-resume", age=5, pid_alive=False,
                log_line="Claude usage limit reached for model fable")
            self.assertEqual(st, "failed")
            self.assertIn("limit", why)
        with self.subTest("h3_worker_dead_without_log_is_failed"):
            st, why = s9.judge_health("worker:auto-resume", age=5, pid_alive=False)
            self.assertEqual(st, "failed")
            self.assertTrue(why, "사유 없는 failed 는 화면에서 쓸모가 없다")
        with self.subTest("h4_worker_alive"):
            self.assertEqual(
                s9.judge_health("worker:auto-resume", age=5, pid_alive=True)[0],
                "alive")
            # 살아 있어도 진전이 없으면 stalled — pid 생존은 진행의 증거가 아니다
            self.assertEqual(
                s9.judge_health("worker:auto-resume", age=9999, pid_alive=True)[0],
                "stalled")
        with self.subTest("h5_recorded_state_wins"):
            self.assertEqual(
                s9.judge_health("sub:x:1", age=9999, recorded="done")[0], "done")
            self.assertEqual(
                s9.judge_health("sub:x:1", age=1, recorded="failed")[0], "failed")
        with self.subTest("h9_unknown_when_no_signal"):
            st, _ = s9.judge_health("sub:x:1")
            self.assertEqual(st, "unknown")
            st, _ = s9.judge_health("garbage-actor", age=1)
            self.assertEqual(st, "unknown")
        with self.subTest("h9_never_raises"):
            for kw in ({"age": "bad"}, {"pid_alive": "x"}, {"log_line": None}):
                s9.judge_health("sub:x:1", **kw)

class HealthReportTest(unittest.TestCase):
    """H6~H8: `s9 agents health --json` 계약과 스캔 범위."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9health")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_SESSION": "deadbeef", "S9_AUDIT": "off"}
        self.env.pop("S9_PORT", None)
        self.s9run("init")
        self.doc = self.s9run("new", "request", "--title", "헬스 대상",
                              "--summary", "s", "--body",
                              "b").stdout.split()[0].strip()
        self.s9run("status", self.doc, "in-progress", "--note", "착수")
        self.done = self.s9run("new", "request", "--title", "끝난 문서",
                               "--summary", "s", "--body",
                               "b").stdout.split()[0].strip()
        self.s9run("status", self.done, "in-progress", "--note", "착수")
        self.s9run("contrib", self.done, "--actor", "sub:qa:dddd4444",
                   "--item", "종결분", "--result", "running")
        self.s9run("status", self.done, "done", "--note", "완료", "--force")

    def s9run(self, *argv):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_h6_json_contract(self):
        self.s9run("contrib", self.doc, "--actor", "sub:designer:eeee5555",
                   "--item", "N1", "--result", "running",
                   "--transcript", "/nonexistent/a.output")
        out = json.loads(self.s9run("agents", "health", "--json").stdout)
        self.assertIn("generated", out)
        self.assertIsInstance(out["agents"], list)
        row = next(a for a in out["agents"] if a["req"] == self.doc)
        for k in ("req", "actor", "item", "state", "reason", "age",
                  "transcript"):
            self.assertIn(k, row)
        self.assertEqual(row["actor"], "sub:designer:eeee5555")

    def test_h7_stalled_when_transcript_missing(self):
        """적어 둔 기록 자리가 없으면 그 기여는 **끝난 것**이다.

        전제가 갈린 자리다 (REQ-20260828-041 라운드1). 종전엔 '경로 미등록'과
        '등록됐는데 파일이 없다'가 똑같이 unknown 이었고, health_apply 는
        unknown 을 되쓰지 않으므로 문서의 running 이 영원히 남았다. 워크트리가
        거둬지면 그 안에서 돌던 서브에이전트가 정확히 이 모양이 된다 — 실사고
        2026-08-29: REQ-041 자신이 그 상태로 하루 종일 '누가 붙어 있음'이라
        판정돼 화면에서 깨우기가 사라지고 wake 는 busy 로 거부됐다.
        지금은 failed(기록 자리가 사라졌다)로 종결돼 클레임이 풀린다."""
        self.s9run("contrib", self.doc, "--actor", "sub:designer:eeee5555",
                   "--item", "N1", "--result", "running",
                   "--transcript", "/nonexistent/a.output")
        out = json.loads(self.s9run("agents", "health", "--json").stdout)
        row = next(a for a in out["agents"] if a["req"] == self.doc)
        self.assertIn(row["state"], ("stalled", "failed"))
        self.assertNotEqual(row["state"], "unknown",
                            "되쓸 수 없는 판정이라 running 이 영원히 남는다")
        self.assertTrue(row["reason"], "사유 없는 종결은 화면에서 쓸모가 없다")

    def test_h8_scans_only_open_docs(self):
        out = json.loads(self.s9run("agents", "health", "--json").stdout)
        self.assertFalse([a for a in out["agents"] if a["req"] == self.done],
                         "종결 문서까지 스캔하면 워처 부하가 문서 수만큼 는다")

    def test_h6_text_mode_runs(self):
        r = self.s9run("agents", "health")
        self.assertIsInstance(r.stdout, str)


class DashboardStopLightTest(unittest.TestCase):
    """H10: 상태 표시 영역이 정지 상태를 그리는 분기를 갖는가 (정적 검사)."""

    def test_h10_markup_has_failed_and_stalled_branch(self):
        html = open(index_path(),
                    encoding="utf-8").read()
        self.assertIn("spawn_failed", html)
        self.assertIn("stalled", html,
                      "정지(stalled) 상태를 그리는 분기가 없다")
        self.assertIn("dot-stopped", html,
                      "정지등 클래스(dot-stopped)가 없다")


if __name__ == "__main__":
    unittest.main()
