"""로스터를 다시 놓는 동안 그 이름이 비는 순간이 없다 (REQ-20260915-083-62x6).

실제 사고 2026-09-15 22:17 · 2026-09-16 10:19. 세션 도중 설치가 다시 돌면서
`~/.claude/agents` 의 서른 개를 한 바퀴 다시 썼다. 종전 코드는 우리 것이면 먼저
`os.remove(dst)` 하고 그다음 `os.symlink` 을 걸었는데 — 그 둘 사이에 그 이름은
**없다**. 그 창에 Claude 가 디렉터리를 읽어 「s9-agnt-* 를 더는 못 쓴다」가 떴고,
리드는 그 틈에 역할 에이전트를 세우지 못해 정의를 손으로 넣었다. 주인 눈에는
에이전트와 스킬이 사라진 것으로 보였다.

이 시험은 **다시 놓는 동안 밖에서 계속 세어 본다** — 한 번이라도 수가 줄면 진다.

실행: python3 tests/ roster_never_blinks
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_install_blink",
        importlib.machinery.SourceFileLoader("s9_install_blink", INSTALL))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


N = 30          # 그날의 그 수 — 역할 에이전트 서른


class ThePlacedNamesNeverGoMissing(unittest.TestCase):

    def setUp(self):
        self.m = _load()
        self.tmp = tempfile.mkdtemp(prefix="s9roster-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = os.path.join(self.tmp, "src")
        self.dst = os.path.join(self.tmp, "agents")
        os.makedirs(self.src)
        os.makedirs(self.dst)
        self.names = ["s9-agnt-role%02d.md" % i for i in range(N)]
        for n in self.names:
            with open(os.path.join(self.src, n), "w", encoding="utf-8") as f:
                f.write("---\nname: %s\n---\n역할\n" % n[:-3])

    def place_all(self):
        for n in self.names:
            self.m._place_atomic(os.path.join(self.src, n),
                                 os.path.join(self.dst, n))

    def ours(self):
        return [n for n in os.listdir(self.dst) if n.startswith("s9-agnt-")]

    # 정상 — 처음 놓으면 서른이 선다
    def test_a_first_placement_puts_them_all(self):
        self.place_all()
        self.assertEqual(N, len(self.ours()))
        for n in self.names:
            self.assertTrue(os.path.lexists(os.path.join(self.dst, n)), n)

    # 사고의 본체 — 다시 놓는 동안 밖에서 세면 한 번도 안 줄어든다
    def test_a_replacement_never_shows_fewer_names(self):
        self.place_all()
        seen = []
        stop = threading.Event()

        def watch():
            while not stop.is_set():
                try:
                    seen.append(len(self.ours()))
                except OSError:
                    seen.append(-1)
                time.sleep(0.0005)

        t = threading.Thread(target=watch, daemon=True)
        t.start()
        try:
            for _ in range(5):          # 다섯 바퀴 — 그날처럼 되풀이 설치
                self.place_all()
        finally:
            stop.set()
            t.join(timeout=5)
        self.assertTrue(seen, "밖에서 한 번도 못 셌다 — 시험이 뜻이 없다")
        self.assertEqual(N, min(seen),
                         "다시 놓는 동안 목록이 %d 까지 줄었다 — 그 창에 Claude 가 "
                         "읽으면 에이전트가 사라진 것으로 보인다" % min(seen))

    # 정상 — 원천이 바뀌면 바뀐 것을 가리킨다 (제자리 교체가 갱신을 막지 않는다)
    def test_a_replacement_points_at_the_new_source(self):
        self.place_all()
        n = self.names[0]
        with open(os.path.join(self.src, n), "w", encoding="utf-8") as f:
            f.write("바뀐 원천\n")
        self.m._place_atomic(os.path.join(self.src, n), os.path.join(self.dst, n))
        with open(os.path.join(self.dst, n), encoding="utf-8") as f:
            self.assertEqual("바뀐 원천\n", f.read())

    # 경계 — 디렉터리(스킬)도 비는 순간 없이 바뀐다
    def test_a_directory_is_replaced_without_vanishing(self):
        d = os.path.join(self.src, "s9-skl-thing")
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("첫 판\n")
        target = os.path.join(self.dst, "s9-skl-thing")
        self.m._place_atomic(d, target)
        self.assertTrue(os.path.lexists(target))
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("둘째 판\n")
        self.m._place_atomic(d, target)
        with open(os.path.join(target, "SKILL.md"), encoding="utf-8") as f:
            self.assertEqual("둘째 판\n", f.read())

    # 회귀 — 임시 자리를 남기지 않는다
    def test_no_temporary_leftovers(self):
        self.place_all()
        self.place_all()
        left = [n for n in os.listdir(self.dst) if n.startswith(".s9-place-")]
        self.assertEqual([], left, "임시 자리가 남았다: %s" % left)


if __name__ == "__main__":
    unittest.main()
