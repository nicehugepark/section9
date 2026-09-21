"""문서를 세우는 명령이 stdin 을 기다려 멎지 않는다 (REQ-20260921-013-62x6).

실제 사고 2026-09-21: 리드가 백그라운드로 띄운 루프 안의 `s9 new request` 가 **한
시간** 동안 끝나지 않았고, 그 프로세스가 잠금을 잡아 뒤이은 요청 생성이 세 번 시한에
걸렸다. `read_body_arg` 가 `isatty()` 만 보고 `sys.stdin.read()` 로 끝까지 읽은
탓이다 — 백그라운드 실행의 stdin 은 터미널이 아니면서 EOF 도 오지 않는다.

같은 모양이 REQ-20260918-020-62x6 에서 `--from-pending` 한 갈래로 이미 났고, 그때는
그 갈래만 고쳤다(test_continuation C6). 이 시험은 **평범한 호출**을 지킨다.

계약 넷.
  S1 stdin 이 열린 채여도 멎지 않는다 — 본문은 비어 있다
  S2 이미 와 있는 데이터는 읽는다 — `echo … | s9 new` 가 그대로 선다
  S3 `--body -` 는 끝까지 기다려 읽는다 — 늦게 오는 자리를 위한 명시적인 길
  S4 `--body` · `--body-file` 이 있으면 stdin 을 아예 건드리지 않는다

실행: python3 tests/ body_stdin
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

# stdin 을 열어 둔 채 부른 명령이 이 안에 끝나야 한다. 실제 사고는 한 시간이었다.
NO_HANG_SEC = 45


class BodyStdin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9body-")
        cls.env = dict(os.environ, S9_ROOT=cls.root, S9_SESSION="bbbb2222")
        for argv in (["init"], ["user", "add", "tester"]):
            subprocess.run([sys.executable, S9, *argv], env=cls.env,
                           capture_output=True, timeout=120)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def _new(self, *extra, stdin_open=False, feed=None, timeout=NO_HANG_SEC):
        """요청 하나를 세운다. stdin_open 이면 **EOF 를 주지 않고** 기다려 본다."""
        argv = [sys.executable, S9, "new", "request",
                "--title", "stdin 계약", "--summary", "요약",
                "--goal", "판별 가능한 한 문장", "--size", "S",
                "--user", "tester", *extra]
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=self.env, text=True)
        if stdin_open:
            # 아무것도 보내지 않고 닫지도 않는다 — 사람이 터미널 앞에 앉아 있는 모양이자
            # 백그라운드 실행이 물려받은 stdin 의 모양이다.
            try:
                out, err = p.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                p.kill()
                p.communicate()
                self.fail("stdin 을 기다려 멎었습니다 — 백그라운드 실행이 여기서 죽습니다")
            return out, err
        out, err = p.communicate(input=feed, timeout=timeout)
        return out, err

    def _body_of(self, out):
        rid = (out or "").split()[0] if (out or "").strip() else ""
        self.assertTrue(rid.startswith("REQ-"), out)
        r = subprocess.run([sys.executable, S9, "show", rid], env=self.env,
                           capture_output=True, text=True, timeout=60)
        return rid, r.stdout

    # S1. 열린 stdin 에서 멎지 않는다 — 이 시험이 실제 사고를 그대로 재현한다
    def test_s1_open_stdin_does_not_hang(self):
        t0 = time.time()
        out, err = self._new(stdin_open=True)
        self.assertLess(time.time() - t0, NO_HANG_SEC,
                        "stdin 을 기다렸습니다")
        rid, _doc = self._body_of(out or err)
        self.assertTrue(rid)

    # S2. 이미 와 있는 데이터는 읽는다 — 파이프로 본문을 넘기는 길은 살아 있다
    def test_s2_piped_body_still_arrives(self):
        out, err = self._new(feed="파이프로 넘긴 원문입니다")
        _rid, doc = self._body_of(out or err)
        self.assertIn("파이프로 넘긴 원문입니다", doc)

    # S3. `--body -` 는 끝까지 기다린다 — 늦게 오는 자리를 위한 명시적인 길
    def test_s3_dash_reads_to_the_end(self):
        argv = [sys.executable, S9, "new", "request", "--title", "늦게 오는 본문",
                "--summary", "요약", "--goal", "한 문장", "--size", "S",
                "--user", "tester", "--body", "-"]
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=self.env, text=True)
        time.sleep(1.0)                      # 엿보기 시한보다 한참 늦게 보낸다
        out, err = p.communicate(input="늦게 도착한 원문입니다", timeout=NO_HANG_SEC)
        _rid, doc = self._body_of(out or err)
        self.assertIn("늦게 도착한 원문입니다", doc)

    # S3b. 「-」 는 본문 한 글자가 아니다
    def test_s3b_dash_is_not_a_body(self):
        argv = [sys.executable, S9, "new", "request", "--title", "빗금 하나",
                "--summary", "요약", "--goal", "한 문장", "--size", "S",
                "--user", "tester", "--body", "-"]
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=self.env, text=True)
        out, err = p.communicate(input="", timeout=NO_HANG_SEC)
        _rid, doc = self._body_of(out or err)
        self.assertNotIn("\n-\n", doc)

    # S4. 명시된 본문이 있으면 stdin 은 건드리지 않는다
    def test_s4_explicit_body_ignores_stdin(self):
        t0 = time.time()
        out, err = self._new("--body", "명시한 원문입니다", stdin_open=True)
        self.assertLess(time.time() - t0, NO_HANG_SEC)
        _rid, doc = self._body_of(out or err)
        self.assertIn("명시한 원문입니다", doc)

    def test_s4b_body_file_ignores_stdin(self):
        path = os.path.join(self.root, "body.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("파일에서 온 원문입니다")
        out, err = self._new("--body-file", path, stdin_open=True)
        _rid, doc = self._body_of(out or err)
        self.assertIn("파일에서 온 원문입니다", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
