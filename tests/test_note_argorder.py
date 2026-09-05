"""기록 명령이 조용히 실패하는가 (REQ-20260826-041-62x6).

하루치 작업 노트가 문서에 안 남고 사라졌다. 원인은 인자 순서였다.

    s9 note <id> <본문> --label response     ← 남는다
    s9 note <id> --label response <본문>     ← 죽는다

argparse 는 위치 인자를 **첫 연속 구간**에만 붙인다. 그래서 뒤쪽 형태는
`unrecognized arguments: <본문>` 으로 죽는데 — **그 메시지가 입력 원문을 그대로
되비춘다.** 긴 노트를 파이프로 넘기며 마지막 줄만 확인하면, 실패 메시지의 꼬리와
성공한 노트의 꼬리가 글자 그대로 같다. 성공처럼 보이는 실패였다.

이 시스템의 전제가 "컨텍스트는 사라지고 문서만 남는다"이므로, **기록 명령이
조용히 실패하는 것은 기능 결함이 아니라 전제의 붕괴**다.

고침은 습관을 고치라 하지 않고 명령이 받아들이게 하는 것이다 — 사람도
에이전트도 옵션을 먼저 쓴다.

실행: python3 tests/ note_argorder
"""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


class NoteArgOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9argord-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_SESSION": "argordse", "S9_REWORK_WATCH": "off"}
        cls.cli("init")
        cls.cli("user", "add", "tester")
        cls.doc = cls.cli("new", "request", "--title", "대상", "--summary", "t",
                          "--goal", "t", "--size", "S", "--user", "tester",
                          "--body", "x").stdout.split()[0]

    @classmethod
    def cli(cls, *args):
        return subprocess.run([S9, *args], capture_output=True, text=True,
                              timeout=20, env=cls.env,
                              stdin=subprocess.DEVNULL)

    def body(self):
        return self.cli("show", self.doc).stdout

    def test_note_arg_order(self):
        """NoteArgOrder 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("a1_option_before_text"):
            r = self.cli("note", self.doc, "--label", "response", "옵션이먼저온본문")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("옵션이먼저온본문", self.body())
        with self.subTest("a2_text_before_option"):
            r = self.cli("note", self.doc, "본문이먼저온것", "--label", "decision")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("본문이먼저온것", self.body())
        with self.subTest("a3_label_is_not_eaten_as_text"):
            self.cli("note", self.doc, "--label", "response", "라벨검사본문")
            body = self.body()
            self.assertIn("response (by", body)
            self.assertNotIn("### ", body.split("라벨검사본문")[0][-40:]
                             .replace("response", ""))
        with self.subTest("a4_failure_is_never_silent"):
            r = self.cli("note", self.doc, "--label", "response")
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        with self.subTest("a6_the_same_trap_elsewhere_is_closed"):
            r = self.cli("resume", "--cwd", "/tmp", "abcd1234", "이어서 해")
            self.assertNotIn("unrecognized arguments", r.stdout + r.stderr)
            r = self.cli("user", "--role", "admin", "add", "bob")
            self.assertNotIn("unrecognized arguments", r.stdout + r.stderr)
        with self.subTest("a7_the_rule_is_asked_of_the_parser"):
            with open(S9_SRC, encoding="utf-8") as f:
                src = f.read()
            self.assertIn("sub.choices.get(sys.argv[1])", src,
                          "정규화가 파서에게 묻지 않는다")
            self.assertNotIn('"note": {"--file"', src,
                             "손으로 관리하는 명령 목록이 남아 있다")
        with self.subTest("a5_log_has_the_same_trap_closed"):
            r = self.cli("log", "--session", "argordse", "옵션먼저로그")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

if __name__ == "__main__":
    unittest.main()
