"""설치가 남의 기본 포트를 집지 않는다 (REQ-20260915-014-2n7g).

실제 사고 2026-09-15 23:27·23:37. 사람의 대시보드(http://127.0.0.1:9909/)가 404 를
냈고 본문은 우리 서버가 내는 「web/index.html not found」였다. 파일은 멀쩡했다 —
그 포트를 쥔 프로세스의 뿌리가 저장소가 아니라 **시험 임시 디렉터리**였다
(S9_ROOT=/T/s9run-…/s9hook-…).

경위 한 줄: `bin/s9-install` 의 `start_dashboard()` 는 포트를 S9_PORT →
`<ROOT>/state/port` → **9909** 순으로 정한다. 시험이 임시 뿌리로 이 스크립트를
돌리면 그 뿌리에는 state/port 가 없어 기본 포트로 떨어지고, 거기에 세운
`serve --supervise --port-auto` 가 시험이 끝난 뒤에도 살아남아 9909 가 비는 순간
집는다. 같은 회차에서 두 번 났다.

여기서 고정하는 것: **기본 포트는 이 설치본의 저장소 것이다.** 남의 뿌리에 포트를
일러 주지 않았으면 띄우지 않는다 — 어느 포트여야 하는지 모르는 것이고, 모를 때
고를 기본값이 하필 남의 자리다.

실행: python3 tests/ install_port_grab
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import re
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")


def start_dashboard_src():
    """start_dashboard 함수 본문 — 들여쓰기 없는 다음 정의 전까지."""
    src = open(INSTALL, encoding="utf-8").read()
    i = src.index("def start_dashboard():")
    m = re.compile(r"^\S", re.M).search(src, i + 10)
    return src[i:m.start() if m else len(src)]


class DefaultPortBelongsToThisCheckout(unittest.TestCase):
    """설치가 기본 포트로 떨어지는 조건 — 소스가 그 순서를 지키는가."""

    @classmethod
    def setUpClass(cls):
        cls.src = start_dashboard_src()

    def test_1_nested_check_sits_inside_the_untold_branch(self):
        """5. 안쪽 시험 검사는 「포트를 일러 주지 않았을 때」 안에 선다 (REQ-20260916-007-2n7g).

        맨 앞에 두었더니 포트를 일러 준 시험까지 돌려보내 전체 회차가 깨졌다.
        막을 것은 기본값으로 떨어지는 것이지 시험 안에서 띄우는 것이 아니다."""
        head = self.src[:self.src.index("port = int(os.environ")]
        self.assertNotIn("S9_TESTS_NESTED", head,
                         "안쪽 검사가 포트를 정하기 전에 서면 일러 준 포트까지 막는다")
        gate = self.src[self.src.index("if not told:"):]
        self.assertIn("S9_TESTS_NESTED", gate[:gate.index("subprocess.Popen")],
                      "안쪽 검사가 not told 갈래 안에 있어야 한다")

    def test_2_foreign_root_without_a_told_port_starts_nothing(self):
        """4. 남의 뿌리인데 포트를 일러 주지 않았으면 안 띄운다 — 이번 사고."""
        gate = self.src[self.src.index("port = int(os.environ"):]
        spawn = gate.index("subprocess.Popen")
        before = gate[:spawn]
        self.assertIn("realpath(ROOT)", before,
                      "뿌리가 이 설치본의 저장소인지 보는 검사가 Popen 앞에 서야 한다")
        self.assertIn("main_worktree_root", before)
        self.assertIn("return", before, "어긋나면 띄우지 말고 돌려보내야 한다")

    def test_3_told_port_still_starts(self):
        """2·6. S9_PORT 나 그 뿌리의 state/port 로 일러 준 포트는 종전대로 띄운다."""
        gate = self.src
        self.assertIn("told", gate, "일러 준 포트인지를 가르는 표가 있어야 한다")
        # S9_PORT 갈래와 state/port 갈래 둘 다 그 표를 세운다
        self.assertRegex(gate, r"told = bool\(port\)")
        self.assertRegex(gate, r"state\", \"port\"[\s\S]{0,200}told = True")

    def test_4_it_says_why(self):
        """7. 안 띄울 때는 조용히 넘어가지 않고 사유를 말한다."""
        for chunk in ("시험 안쪽 실행", "state/port"):
            self.assertIn(chunk, self.src, f"사유 문장에 「{chunk}」이 없다")
        self.assertGreaterEqual(self.src.count("say("), 3,
                                "두 갈래의 사유와 기동 알림이 모두 말해야 한다")

    def test_5_default_is_still_9909(self):
        """1. 진짜 저장소에서는 종전대로 9909(또는 state/port)로 띄운다."""
        self.assertIn("port = 9909", self.src)
        self.assertIn("subprocess.Popen", self.src)


def load_install(root):
    """S9_ROOT 를 못 박고 s9-install 을 모듈로 읽는다 — ROOT 가 모듈 최상단에서
    정해지므로 환경을 먼저 세우고 불러야 한다. main() 은 __main__ 가드 뒤라 안 돈다."""
    prev = os.environ.get("S9_ROOT")
    nested = os.environ.pop("S9_TESTS_NESTED", None)
    os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            "s9inst", importlib.machinery.SourceFileLoader("s9inst", INSTALL))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev
        if nested is not None:
            os.environ["S9_TESTS_NESTED"] = nested


class ItActuallyDoesNotSpawn(unittest.TestCase):
    """소스의 모양이 아니라 **부른 결과**로 잰다 — Popen 이 불렸는가."""

    def run_start(self, root, env=None):
        m = load_install(root)
        calls, said = [], io.StringIO()
        import subprocess as sp
        real = sp.Popen
        keep = {k: os.environ.get(k) for k in ("S9_PORT", "S9_TESTS_NESTED")}
        try:
            for k, v in (env or {}).items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            def spy(*a, **k):
                # 이 함수가 부르는 Popen 은 둘이다 — 뿌리를 재는 git 과 서버.
                # 세는 것은 **서버**뿐이다.
                argv = list(a[0]) if a and isinstance(a[0], (list, tuple)) else []
                if "serve" in [str(x) for x in argv]:
                    calls.append(argv)
                return real(["true"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            sp.Popen = spy
            with contextlib.redirect_stdout(said):
                m.start_dashboard()
        finally:
            sp.Popen = real
            for k, v in keep.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        return calls, said.getvalue()

    def test_6_foreign_temp_root_spawns_nothing(self):
        """4. 임시 뿌리 + 일러 준 포트 없음 → Popen 이 한 번도 안 불린다 (이번 사고)."""
        root = tempfile.mkdtemp(prefix="s9portgrab-")
        calls, out = self.run_start(root, {"S9_PORT": None, "S9_TESTS_NESTED": None})
        self.assertEqual(calls, [], f"남의 뿌리에서 서버를 띄웠다: {out}")
        self.assertIn("state/port", out, f"사유를 말하지 않았다: {out}")

    def test_7_nested_run_without_a_told_port_spawns_nothing(self):
        """5. 안쪽 시험 실행 + 일러 준 포트 없음 → 안 띄운다."""
        root = tempfile.mkdtemp(prefix="s9portgrab-")
        calls, out = self.run_start(root, {"S9_TESTS_NESTED": "1", "S9_PORT": None})
        self.assertEqual(calls, [], f"시험 안쪽인데 서버를 띄웠다: {out}")
        # 사유가 둘 중 어느 것인지는 묻지 않는다 — 임시 뿌리는 남의 뿌리이기도 해서
        # 먼저 걸리는 쪽이 말한다. 순서는 위 test_1 이 구조로 잡는다.
        self.assertIn("띄우지 않습니다", out, f"사유를 말하지 않았다: {out}")

    def test_7b_nested_run_with_a_told_port_does_spawn(self):
        """5b. 안쪽 시험이어도 포트를 일러 줬으면 띄운다 (REQ-20260916-007-2n7g).

        test_port_pin_ghost 의 a2 가 정확히 이 모양이다 — 임시 뿌리에 state/port 를
        적어 두고 start_dashboard 를 불러 세워지는 argv 를 본다."""
        root = tempfile.mkdtemp(prefix="s9portgrab-")
        calls, out = self.run_start(root, {"S9_TESTS_NESTED": "1",
                                           "S9_PORT": "29098"})
        self.assertEqual(len(calls), 1, f"일러 준 포트인데 안 띄웠다: {out}")
        self.assertIn("29098", [str(x) for x in calls[0]], calls[0])

    def test_8_told_port_does_spawn(self):
        """2. 포트를 일러 주면 남의 뿌리여도 종전대로 띄운다 — 막는 것은 기본값뿐이다."""
        root = tempfile.mkdtemp(prefix="s9portgrab-")
        calls, out = self.run_start(root, {"S9_PORT": "29099", "S9_TESTS_NESTED": None})
        self.assertEqual(len(calls), 1, f"일러 준 포트인데 안 띄웠다: {out}")
        self.assertIn("29099", [str(x) for x in calls[0]], calls[0])


if __name__ == "__main__":
    unittest.main()
