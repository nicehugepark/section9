"""러너가 넘겨받은 패턴을 전부 도는가 (REQ-20260829-006).

커밋 게이트(bin/s9-guard)는 스테이지된 테스트 파일 이름을 전부 모아
`python3 tests/ a b c` 로 넘긴다. 그런데 러너는 sys.argv[1] 하나만 패턴으로
썼다 — 두 번째부터는 아무 말 없이 선택되지 않고, 게이트는 "담긴 테스트가
통과했다"고 판정했다. 실제로 `python3 tests/ commit_gate streams_untracked` 가
commit_gate 만 돌고 있었다.

이 파일이 못박는 것은 둘이다: 전부 돈다는 것, 그리고 **못 고른 패턴이 있으면
실패로 끝난다**는 것. 후자가 핵심이다 — '안 돌았다'가 '통과했다'로 보이면
게이트는 장식이다.

실행: python3 tests/ runner_patterns
"""
import importlib.util
import os
import subprocess
import sys
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_spec = importlib.util.spec_from_loader(
    "s9runner", SourceFileLoader("s9runner", os.path.join(HERE, "__main__.py")))
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


def files_of(suite):
    """선택된 테스트들이 어느 파일에서 왔는가 — id 의 모듈 이름으로 센다."""
    return sorted({t.id().split(".")[0] for t in runner.flatten(suite)})


class Patterns(unittest.TestCase):
    """R4·R5. 인자 형태를 그대로 받는다."""

    def test_patterns(self):
        """R4·R5. 인자 형태를 그대로 받는다."""
        with self.subTest("no_args_means_everything"):
            self.assertEqual(runner.patterns([]), ["test_*.py"])
            self.assertEqual(runner.patterns([""]), ["test_*.py"])
        with self.subTest("three_shapes_of_one_name"):
            # 조각 형태는 넓힌다 — 사람이 치는 것.
            for arg in ("uid", "test_uid"):
                self.assertEqual(runner.patterns([arg]), ["test_*uid*.py"], arg)
            # 정확한 파일명은 넓히지 않는다 (REQ-20260830-029): 커밋 게이트·--smoke·
            # --changed 가 고른 파일이 이웃(test_uid_extra 등)까지 끌고 오면 계층과
            # 선택의 뜻이 사라진다. 정확 일치도 그 파일 하나는 그대로 돈다.
            self.assertEqual(runner.patterns(["tests/test_uid.py"]),
                             ["test_uid.py"])
        with self.subTest("many_names_become_many_patterns"):
            self.assertEqual(runner.patterns(["uid", "tags"]),
                             ["test_*uid*.py", "test_*tags*.py"])

class Discovery(unittest.TestCase):
    """R1·R2·R3. 전부 고르고, 겹치면 한 번만, 못 고르면 이름을 댄다."""

    def test_discovery(self):
        """R1·R2·R3. 전부 고르고, 겹치면 한 번만, 못 고르면 이름을 댄다."""
        with self.subTest("every_pattern_is_collected"):
            suite, empty = runner.discover(["test_*uid*.py", "test_*tags*.py"])
            got = files_of(suite)
            self.assertIn("test_uid", got)
            self.assertIn("test_tags", got)
            self.assertEqual(empty, [])
        with self.subTest("overlapping_patterns_run_once"):
            one, _ = runner.discover(["test_*uid*.py"])
            twice, _ = runner.discover(["test_*uid*.py", "test_*uid*.py"])
            self.assertEqual(twice.countTestCases(), one.countTestCases())
        with self.subTest("unmatched_pattern_is_named"):
            suite, empty = runner.discover(
                ["test_*uid*.py", "test_*없는것abcxyz*.py"])
            self.assertEqual(empty, ["test_*없는것abcxyz*.py"])
            self.assertGreater(suite.countTestCases(), 0,
                               "고른 것은 그대로 돌아야 한다")

class EndToEnd(unittest.TestCase):
    """R1·R3·R6. 진짜로 돌려서 본다 — 계약은 프로세스 경계에서 지켜져야 한다."""

    def _run(self, *args):
        env = {**os.environ}
        env.pop("TMPDIR", None)
        env["S9_TESTS_NESTED"] = "1"   # 바깥 실행의 세계를 청소하지 않는다
        return subprocess.run([sys.executable, HERE, *args], env=env,
                              capture_output=True, text=True, timeout=600,
                              cwd=os.path.dirname(HERE))

    def test_end_to_end(self):
        """R1·R3·R6. 진짜로 돌려서 본다 — 계약은 프로세스 경계에서 지켜져야 한다."""
        with self.subTest("two_names_both_actually_run"):
            r = self._run("uid", "tags")
            out = r.stdout + r.stderr
            self.assertIn("test_uid", out)
            self.assertIn("test_tags", out)
            self.assertEqual(r.returncode, 0, out[-1500:])
        with self.subTest("unmatched_name_fails_the_run"):
            r = self._run("uid", "없는것abcxyz")
            out = r.stdout + r.stderr
            self.assertIn("없는것abcxyz", out)
            self.assertEqual(r.returncode, 1,
                             "못 고른 패턴이 있는데 성공으로 끝났다")
        with self.subTest("single_name_still_works"):
            r = self._run("uid")
            self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-1500:])

class GateHandsOffEveryName(unittest.TestCase):
    """R6. 게이트가 만드는 이름 목록이 러너에서 전부 선택된다."""

    def setUp(self):
        sp = importlib.util.spec_from_loader(
            "s9guard_pat", SourceFileLoader(
                "s9guard_pat", os.path.join(HERE, "..", "bin", "s9-guard")))
        self.guard = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(self.guard)

    def test_names_derived_by_the_guard_all_resolve(self):
        staged = ["tests/test_uid.py", "tests/test_tags.py",
                  "web/index.html", "tests/test_commit_gate.py"]
        names = [os.path.basename(f)[len("test_"):-len(".py")]
                 for f in staged
                 if f.startswith("tests/test_") and f.endswith(".py")]
        self.assertEqual(names, ["uid", "tags", "commit_gate"])
        suite, empty = runner.discover(runner.patterns(names))
        self.assertEqual(empty, [], "게이트가 넘긴 이름 중 안 도는 것이 있다")
        got = files_of(suite)
        for f in ("test_uid", "test_tags", "test_commit_gate"):
            self.assertIn(f, got)


if __name__ == "__main__":
    unittest.main(verbosity=2)
