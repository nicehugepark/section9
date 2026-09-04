"""같은 것을 두 번 돌지 않는다 (REQ-20260903-010).

사용자: "테스트가 너무 오래걸리고 시스템에 부하를 준다 … 동시 요청 작업 처리 시
같은 테스트를 스위트라는 명목으로 중복, 중첩 실행되는것을 방지하려고 하는거다."

리드와 무인 작업자는 실제로 동시에 스위트를 돌린다. 그러면 같은 시험이 두 벌
돌며 서로의 포트·임시자리·CPU 를 뺏는다 — 실측으로 `test_port_pool` 이 그렇게
깨졌다. 두 겹으로 막는다.

  ① **기록** — 선택(패턴 묶음)마다 마지막 green 의 나무 지문을 적어 둔다.
     지문이 같으면 돌 이유가 없다.
  ② **단일비행** — 같은 선택이 이미 돌고 있으면 두 번째는 새로 돌리지 않고
     **기다렸다가 그 결과를 받는다.**

**이 파일은 동작을 잰다** (REQ-20260903-009 의 규칙): 소스에 그 글자가 있는지
보지 않고, 실제로 기록을 남기고 잠가 보고 러너를 두 번 돌려 잰다.

실행: python3 tests/ runner_reuse
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import shutil
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_runner = os.path.join(_here, "__main__.py")


def _load():
    """러너를 모듈로 읽어 들인다 — 부작용 없이 도우미만 부르려는 것이다."""
    sys.path.insert(0, _here)
    try:
        spec = importlib.util.spec_from_loader(
            "s9_runner", importlib.machinery.SourceFileLoader(
                "s9_runner", _runner))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if sys.path and sys.path[0] == _here:
            sys.path.pop(0)


class Reuse(unittest.TestCase):
    """① 기록 — 같은 지문이면 다시 돌지 않는다."""

    def setUp(self):
        self.m = _load()
        self.tmp = tempfile.mkdtemp(prefix="s9reuse-")
        # 실제 저장소의 state/ 를 더럽히지 않는다 — 시험이 남긴 green 기록이
        # 사람의 다음 실행을 건너뛰게 만들면 그게 더 나쁜 결함이다.
        self.m.REUSE_DIR = os.path.join(self.tmp, "green")
        self.m.RUN_LOCKS = os.path.join(self.tmp, "jobs")

    def test_a_selection_is_remembered_only_with_its_fingerprint(self):
        pats = ["test_alpha.py"]
        self.assertFalse(self.m.green_seen(pats, "fp1"), "빈 기록이 참이라 했다")
        self.m.mark_green(pats, "fp1")
        self.assertTrue(self.m.green_seen(pats, "fp1"))
        self.assertFalse(self.m.green_seen(pats, "fp2"),
                         "나무가 바뀌었는데 통과로 봤다 — 이러면 안 도는 게 아니라"
                         " 안 재는 것이다")

    def test_selections_do_not_borrow_each_others_pass(self):
        """다른 선택은 남의 통과를 빌려 쓰지 못한다.

        예외는 **전체**뿐이다 — 아래 FullCovers 를 보라. 여기서 빌려 주는 쪽은
        부분 선택이라 덮지 않는다.
        """
        self.m.mark_green(["test_alpha.py"], "fp1")
        self.assertFalse(self.m.green_seen(["test_beta.py"], "fp1"))
        self.assertFalse(self.m.green_seen(["test_alpha.py", "test_beta.py"],
                                           "fp1"))

    def test_order_does_not_change_the_selection(self):
        """같은 묶음은 순서가 달라도 같은 선택이다."""
        self.m.mark_green(["b.py", "a.py"], "fp1")
        self.assertTrue(self.m.green_seen(["a.py", "b.py"], "fp1"))

    def test_an_unknown_tree_is_never_remembered(self):
        """지문을 못 재면(git 이 안 되면) 기록하지 않는다 — 모르면 다시 돈다."""
        self.m.mark_green(["test_alpha.py"], None)
        self.assertFalse(self.m.green_seen(["test_alpha.py"], None))

    def test_the_fingerprint_is_stable_while_nothing_changes(self):
        fp = self.m.tree_fingerprint()
        if fp is None:
            self.skipTest("git 을 못 읽는 자리 — 지문 없이 늘 다시 돈다")
        self.assertEqual(fp, self.m.tree_fingerprint())
        self.assertRegex(fp, r"^[0-9a-f]{40}$")

    def test_touching_a_file_without_changing_it_keeps_the_fingerprint(self):
        """**내용이 그대로면 지문도 그대로다** (REQ-20260903-012).

        예전 지문은 mtime 이었다. 그런데 스위트를 돌리는 것만으로 mtime 이
        움직이는 파일이 있어서(내용 동일·mtime 이동), 전체가 초록이어도 끝난
        순간 지문이 달라졌다 — 그 초록 기록은 아무도 못 쓰고, 넓은 변경의
        커밋 문은 방금 초록을 본 사람에게도 「돌려라」만 되풀이한다.

        실행 중인 저장소를 건드리지 않으려고, 이 시험은 **자기 저장소**를
        하나 세워 그 안에서 잰다.
        """
        import subprocess as _sp
        repo = tempfile.mkdtemp(prefix="s9fp-")
        try:
            _sp.run(["git", "init", "-q", repo], check=True)
            f = os.path.join(repo, "a.txt")
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("hello")
            before = self.m.tree_fingerprint(repo)
            if before is None:
                self.skipTest("git 을 못 읽는 자리")
            os.utime(f, (0, 0))                    # 시각만 움직인다
            self.assertEqual(self.m.tree_fingerprint(repo), before,
                             "내용이 그대로인데 지문이 움직였다")
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("hello!")                 # 이번엔 내용이 바뀐다
            self.assertNotEqual(self.m.tree_fingerprint(repo), before,
                                "내용이 바뀌었는데 지문이 그대로다")
        finally:
            shutil.rmtree(repo, ignore_errors=True)


class SingleFlight(unittest.TestCase):
    """② 단일비행 — 같은 선택이 돌고 있으면 두 번째는 기다린다."""

    def setUp(self):
        self.m = _load()
        self.tmp = tempfile.mkdtemp(prefix="s9flight-")
        self.m.RUN_LOCKS = os.path.join(self.tmp, "jobs")
        self.m.REUSE_DIR = os.path.join(self.tmp, "green")

    def test_the_first_run_takes_it_without_waiting(self):
        fh, waited = self.m.hold_run_lock(["test_alpha.py"])
        try:
            self.assertFalse(waited, "아무도 안 쥐었는데 기다렸다")
        finally:
            self.m.drop_run_lock(fh)

    def test_a_second_run_of_the_same_selection_waits(self):
        """다른 프로세스가 쥐고 있으면 기다린다 — 나란히 돌지 않는다."""
        holder = subprocess.Popen(
            [sys.executable, "-c",
             "import fcntl,os,sys,time\n"
             "os.makedirs(sys.argv[1], exist_ok=True)\n"
             "f=open(os.path.join(sys.argv[1], sys.argv[2]), 'a+')\n"
             "fcntl.flock(f, fcntl.LOCK_EX)\n"
             "print('held', flush=True)\n"
             "time.sleep(6)\n",
             self.m.RUN_LOCKS,
             f"tests-{self.m._selection_key(['test_alpha.py'])}.lock"],
            stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            self.m.REUSE_WAIT_SEC = 2          # 오래 기다리는 시험은 나쁜 시험이다
            t0 = time.time()
            fh, waited = self.m.hold_run_lock(["test_alpha.py"])
            took = time.time() - t0
            self.m.drop_run_lock(fh)
            self.assertTrue(waited, "남이 쥐고 있는데 그냥 들어갔다")
            self.assertGreaterEqual(took, 1.5, "기다린 시늉만 했다")
        finally:
            holder.kill()
            holder.wait()

    def test_a_different_selection_does_not_wait(self):
        """다른 선택은 서로를 막지 않는다 — 막으면 그냥 직렬화다."""
        fh1, _ = self.m.hold_run_lock(["test_alpha.py"])
        try:
            self.m.REUSE_WAIT_SEC = 2
            t0 = time.time()
            fh2, waited = self.m.hold_run_lock(["test_beta.py"])
            self.m.drop_run_lock(fh2)
            self.assertFalse(waited)
            self.assertLess(time.time() - t0, 1.0)
        finally:
            self.m.drop_run_lock(fh1)


class EndToEnd(unittest.TestCase):
    """러너를 실제로 두 번 돌려 본다 — 도우미가 아니라 사람이 겪는 길이다."""

    def test_the_second_run_of_an_unchanged_tree_is_instant(self):
        env = {**os.environ}
        env.pop("S9_TESTS_NESTED", None)
        first = subprocess.run([sys.executable, _here, "uid", "--no-reuse"],
                               capture_output=True, text=True, timeout=300,
                               env=env)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        t0 = time.time()
        second = subprocess.run([sys.executable, _here, "uid"],
                                capture_output=True, text=True, timeout=300,
                                env=env)
        took = time.time() - t0
        said = second.stdout + second.stderr
        self.assertEqual(second.returncode, 0, said)
        self.assertIn("바뀐 것이 없다", said, said[-400:])
        self.assertLess(took, 2.0, f"재사용인데 {took:.1f}초 걸렸다")

    def test_no_reuse_really_runs_it_again(self):
        """`--no-reuse` 는 기록을 믿지 말라는 뜻이다 — 안 도는 길이 아니다."""
        env = {**os.environ}
        env.pop("S9_TESTS_NESTED", None)
        r = subprocess.run([sys.executable, _here, "uid", "--no-reuse"],
                           capture_output=True, text=True, timeout=300,
                           env=env)
        said = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, said)
        self.assertNotIn("바뀐 것이 없다", said)
        self.assertIn("Ran ", said, said[-300:])


if __name__ == "__main__":
    unittest.main()


class FullCovers(unittest.TestCase):
    """전체가 초록이면 그 안의 어떤 선택도 초록이다 (REQ-20260904-005).

    왜 필요한가(실측 2026-09-04): 전체 297파일을 초록으로 돌린 **직후** 커밋
    문이 그 안의 234파일을 고르면 `_selection_key` 가 달라 「처음 보는 조합」이
    되고, 방금 통과한 시험을 5분에 걸쳐 다시 돌렸다. 재사용 계층이 있는데도
    커밋마다 분 단위를 무는 자리가 여기였다.

    선택은 언제나 `discover(HERE)` 안에서 고른 것이라 전체의 부분집합임이
    구조로 보장된다 — 그래서 부분집합인지 따로 세지 않는다.
    """

    def setUp(self):
        self.m = _load()
        self.tmp = tempfile.mkdtemp(prefix="s9cover-")
        self.m.REUSE_DIR = os.path.join(self.tmp, "green")
        self.m.RUN_LOCKS = os.path.join(self.tmp, "jobs")
        self.full = self.m.patterns([])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_one_file_is_covered_by_a_green_whole(self):
        """C1. 전체가 F 로 초록이면 한 파일짜리 선택도 이미 통과다."""
        self.m.mark_green(self.full, "fp1")
        self.assertTrue(self.m.green_seen(["test_port_pool.py"], "fp1"))

    def test_a_smoke_sized_selection_is_covered(self):
        """C2. 여러 파일을 고른 선택(스모크 꼴)도 덮인다."""
        self.m.mark_green(self.full, "fp1")
        many = [f"test_x{i}.py" for i in range(12)]
        self.assertTrue(self.m.green_seen(many, "fp1"))

    def test_its_own_record_still_wins(self):
        """C3. 자기 기록이 있으면 그대로 쓴다 — 종전 동작 불변."""
        self.m.mark_green(["test_alpha.py"], "fp1")
        self.assertTrue(self.m.green_seen(["test_alpha.py"], "fp1"))

    def test_a_different_tree_is_not_covered(self):
        """C4. 나무가 바뀌면 전체 기록이 있어도 덮지 않는다."""
        self.m.mark_green(self.full, "fp1")
        self.assertFalse(self.m.green_seen(["test_alpha.py"], "fp2"))

    def test_without_a_whole_record_nothing_is_covered(self):
        """C5. 전체 기록이 아예 없으면 덮을 것이 없다."""
        self.assertFalse(self.m.green_seen(["test_alpha.py"], "fp1"))

    def test_is_green_asks_only_the_whole(self):
        """C6. 「전체가 초록이었나」는 전체 기록으로만 답한다.

        부분집합 기록으로 그렇다고 답하면 넓은 변경의 커밋 문(WIDE gate)이
        거짓 초록을 보고 붉은 나무를 통과시킨다.
        """
        self.m.mark_green(["test_alpha.py"], "fp1")
        self.assertFalse(self.m.green_seen(self.full, "fp1", cover=False))
        self.m.mark_green(self.full, "fp1")
        self.assertTrue(self.m.green_seen(self.full, "fp1", cover=False))

    def test_the_message_says_what_covered_it(self):
        """C1b. 화면이 무엇 덕에 안 돌았는지 말한다.

        「안 돌았다」만 보이면 사람이 문을 의심한다 — 오늘 그 의심에 값을 치렀다.
        """
        src = open(_runner, encoding="utf-8").read()
        self.assertIn("전체 스위트가 이미 초록이다", src)
