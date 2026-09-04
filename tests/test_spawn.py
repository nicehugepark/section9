"""세션에서 떼어 띄우는 길은 한 문이다 (REQ-20260903-005).

이 저장소가 무언가를 사람 세션과 무관하게 살려 두는 자리는 둘이다 — 상시
계기와 서버 감시자. 둘 다 `double fork + setsid` 로만 서 있었고, **윈도우
파이썬에는 `fork` 가 없다.** 그래서 네이티브 윈도우에서는 그 둘이 통째로 안
떴다: 계기가 없으면 사고 뒤에 아무것도 안 남고, 감시자가 없으면 서버가 죽어도
아무도 안 살린다.

그래서 갈래를 **이름으로 먼저 가른다**(`spawn_backend`) — `pid_alive` 가
`proc_backend` 로 그렇게 하는 것과 같은 규율이다. 리눅스에서 윈도우 갈래를
흉내 내 시험할 수 있어야 하고, 흉내가 진짜와 다른 길로 가면 시험이 헛돈다.

실행: python3 tests/ spawn
"""
import importlib.machinery
import importlib.util
import os
import re
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

os.environ.setdefault("S9_ROOT", tempfile.mkdtemp(prefix="s9spawn-"))
spec = importlib.util.spec_from_loader(
    "s9_spawn", importlib.machinery.SourceFileLoader("s9_spawn", S9))
s9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s9)


class Spawn(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="s9spawnout-")
        self.out = os.path.join(self.d, "out.txt")
        self._env = os.environ.get("S9_SPAWN_BACKEND")

    def tearDown(self):
        if self._env is None:
            os.environ.pop("S9_SPAWN_BACKEND", None)
        else:
            os.environ["S9_SPAWN_BACKEND"] = self._env

    def wait_for(self, path, want, secs=8.0):
        end = time.time() + secs
        while time.time() < end:
            try:
                with open(path, encoding="utf-8") as f:
                    if want in f.read():
                        return True
            except OSError:
                pass
            time.sleep(0.1)
        return False

    # ---- ① 갈래를 이름으로 가른다 -----------------------------------------
    def test_n1_backend_follows_the_platform(self):
        os.environ.pop("S9_SPAWN_BACKEND", None)
        self.assertEqual(s9.spawn_backend(),
                         "fork" if hasattr(os, "fork") else "spawn")

    def test_n2_backend_can_be_forced(self):
        """리눅스에서 윈도우 갈래를 흉내 낼 수 있어야 시험이 선다."""
        for want in ("fork", "spawn"):
            os.environ["S9_SPAWN_BACKEND"] = want
            self.assertEqual(s9.spawn_backend(), want)

    def test_b1_garbage_falls_back_to_the_platform(self):
        os.environ["S9_SPAWN_BACKEND"] = "무엇"
        self.assertEqual(s9.spawn_backend(),
                         "fork" if hasattr(os, "fork") else "spawn")

    # ---- ② 두 갈래가 같은 계약을 지킨다 ------------------------------------
    def test_n3_both_backends_actually_start_it(self):
        """부모는 곧 돌아오고, 자식은 제 일을 한다 — 갈래가 달라도 같다."""
        for how in ("fork", "spawn"):
            with self.subTest(how=how):
                os.environ["S9_SPAWN_BACKEND"] = how
                out = os.path.join(self.d, f"{how}.txt")
                t0 = time.time()
                ok = s9.spawn_detached(
                    ["/bin/sh", "-c", f"echo 떴다-{how}; sleep 2"],
                    out_path=out)
                took = time.time() - t0
                self.assertTrue(ok, f"{how}: 띄우지 못했다")
                self.assertLess(took, 3.0,
                                f"{how}: 부모가 자식을 기다리고 있다")
                self.assertTrue(self.wait_for(out, f"떴다-{how}"),
                                f"{how}: 자식이 제 일을 안 했다")

    def test_f1_a_missing_program_is_reported_not_raised(self):
        """없는 프로그램은 False 다 — 예외로 부르는 쪽을 죽이지 않는다."""
        for how in ("fork", "spawn"):
            with self.subTest(how=how):
                os.environ["S9_SPAWN_BACKEND"] = how
                self.assertIsNotNone(
                    s9.spawn_detached([os.path.join(self.d, "없는것")],
                                      out_path=self.out))

    def test_b2_output_goes_to_the_given_file(self):
        os.environ["S9_SPAWN_BACKEND"] = "spawn"
        s9.spawn_detached(["/bin/sh", "-c", "echo 표준출력; echo 표준오류 >&2"],
                          out_path=self.out)
        self.assertTrue(self.wait_for(self.out, "표준출력"))
        self.assertTrue(self.wait_for(self.out, "표준오류"))

    # ---- ③ 떼는 자리들이 그 문을 지난다 (인라인 fork 금지) ------------------
    def test_c1_metrics_detach_uses_the_door(self):
        with open(S9, encoding="utf-8") as f:
            src = f.read()
        body = src[src.index("def metrics_detach("):
                   src.index("def metrics_read(")]
        self.assertIn("spawn_detached(", body)
        self.assertNotIn("os.fork()", body,
                         "떼는 방법이 여기 인라인으로 다시 생겼다 — "
                         "fork 가 없는 판에서 통째로 안 뜬다")
        # 떨어져 나온 자식이 들어오는 문이 CLI 에 실제로 있어야 한다
        self.assertTrue(re.search(r'"prune",\s*"run"', src)
                        or re.search(r'"run",\s*"prune"', src),
                        "metrics run 진입점이 CLI 에 없다")

    def test_c1b_guard_detach_uses_the_door_too(self):
        """감시자도 같은 문을 지난다 — 둘 중 하나만 옮기면 반쪽이다."""
        with open(S9, encoding="utf-8") as f:
            src = f.read()
        body = src[src.index("def _guard_detach("):
                   src.index("def catalog_with_live(")]
        self.assertIn("spawn_detached(", body)
        self.assertNotIn("os.fork()", body)
        # 떨어져 나온 자식은 **다시 떼지 않는다** — 떼면 자기를 무한히 띄운다.
        self.assertIn("--guard-run", body)
        self.assertIn('"--supervise"', body,
                      "ps 에서 감시자로 읽히는 이름이 사라졌다 — "
                      "진단·시험이 그 낱말로 센다")
        self.assertIn('if getattr(args, "guard_run", False):', src)

    def test_c2_the_fork_free_path_exists_at_all(self):
        """윈도우에는 fork 가 없다 — 그 판에서 도는 갈래가 코드에 있어야 한다."""
        with open(S9, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("def _spawn_detached_subprocess(", src)
        self.assertIn("CREATE_NEW_PROCESS_GROUP", src)


if __name__ == "__main__":
    unittest.main()
