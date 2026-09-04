"""동시에 열어 두는 것들의 상한은 한 표에서 온다 (REQ-20260903-004).

사용자가 짚었다 — "요청이 소강이 되는 상황에는 문제가 없다. 동시에 여러개
요청 작업을 할 때 테스트가 몰리면 발생하는것같다." 재 보니 그대로였다:
윈도우 동적 포트는 **동시에 열려 있는 연결 하나당 하나씩** 잡히고(120 동시 →
+121) 닫으면 돌아온다(+1). 순차는 200회를 걸어도 0이다.

그러므로 지표는 총량이 아니라 **최고치**이고, 상한이 여러 곳에 흩어져 있으면
겹칠 때의 합을 아무도 모른다.

**이 파일은 동작을 잰다** (REQ-20260903-009). 처음 판은 소스에 그 글자가
있는지 보는 시험 11건이었는데, 그런 시험은 「그 줄이 있다」만 말하고 「그 일이
된다」는 말하지 않는다 — 게다가 값싸서 끝없이 늘어난다. 표를 실제로 바꿔
보고 쓰는 쪽이 따라오는지 본다. 6건으로 줄었고 잡는 것은 더 많다.

실행: python3 tests/ concurrency
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
DOCTOR = os.path.join(HERE, "..", "bin", "s9-doctor")

os.environ.setdefault("S9_ROOT", tempfile.mkdtemp(prefix="s9conc-"))


def _load(env=None):
    """주어진 환경으로 bin/s9 를 새로 읽어 들인다 — 표는 import 시점에 선다."""
    old = {k: os.environ.get(k) for k in (env or {})}
    os.environ.update(env or {})
    try:
        spec = importlib.util.spec_from_loader(
            "s9_conc", importlib.machinery.SourceFileLoader("s9_conc", S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _doctor_concurrency(env_extra):
    r = subprocess.run([sys.executable, DOCTOR, "--json"],
                       capture_output=True, text=True, timeout=240,
                       env={**os.environ, **env_extra})
    return json.loads(r.stdout).get("concurrency")


class Concurrency(unittest.TestCase):
    # ---- ① 표가 실제로 값을 정한다 ----------------------------------------
    def test_concurrency(self):
        """Concurrency 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("a1_the_table_has_the_three_caps"):
            m = _load()
            for key in ("headless", "test_jobs", "conns"):
                self.assertIn(key, m.CONCURRENCY)
                self.assertGreater(m.CONCURRENCY[key], 0)
        with self.subTest("a2_env_actually_moves_the_table"):
            m = _load({"S9_MAX_HEADLESS": "3", "S9_MAX_JOBS": "9",
                       "S9_MAX_CONNS": "77"})
            self.assertEqual(m.CONCURRENCY["headless"], 3)
            self.assertEqual(m.CONCURRENCY["test_jobs"], 9)
            self.assertEqual(m.CONCURRENCY["conns"], 77)
        with self.subTest("a3_the_capture_cap_follows_the_table"):
            # 표를 바꾸면 캡처 상한이 **따라 움직인다** — 상수 두 벌이면 안 움직인다
            self.assertEqual(_load({"S9_MAX_HEADLESS": "3"}).SHOT_MAX_HEADLESS,
                             3)
            self.assertEqual(_load({"S9_MAX_HEADLESS": "11"}).SHOT_MAX_HEADLESS,
                             11)
        # ---- ② 시험 러너가 같은 손잡이로 묶인다 -------------------------------
        with self.subTest("b1_the_runner_caps_jobs_and_says_so"):
            r = subprocess.run(
                [sys.executable, HERE, "--jobs", "8", "no_such_pattern_xyz"],
                capture_output=True, text=True, timeout=180,
                env={**os.environ, "S9_MAX_JOBS": "2"})
            said = r.stdout + r.stderr
            self.assertIn("→ 2 로 묶는다", said, said[-400:])
        # ---- ③ 사람이 겹칠 때의 합을 물을 수 있다 -----------------------------
        with self.subTest("c1_doctor_reports_the_table"):
            self.assertEqual(_doctor_concurrency({"S9_MAX_HEADLESS": "3",
                                                  "S9_MAX_JOBS": "4",
                                                  "S9_MAX_CONNS": "5"}),
                             {"headless": 3, "test_jobs": 4, "conns": 5})
        with self.subTest("c2_the_two_tables_do_not_drift"):
            env = {"S9_MAX_HEADLESS": "6", "S9_MAX_JOBS": "7", "S9_MAX_CONNS": "8"}
            self.assertEqual(_doctor_concurrency(env), _load(env).CONCURRENCY,
                             "두 파일의 상한 표가 갈렸다")

if __name__ == "__main__":
    unittest.main()
