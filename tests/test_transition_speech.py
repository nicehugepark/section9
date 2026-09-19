"""전이 메모가 반말이면 전이를 막는다 (REQ-20260919-008-62x6).

주인 물음 2026-09-19 10:20: 「그렇다면 부분 백필을 해서는 말투가 회귀될 수 밖에
없다는 뜻인가?」 — 그렇지 않습니다. 매 턴 읽는 것은 옛 문서가 아니라 CLAUDE.md
(규약이라 명령형으로 둔 것)와 그 세션이라, 백필의 넓이는 회귀를 막지 못합니다.
남는 자리는 **검사가 사후에만 온다**는 것 하나였습니다.

실측 9/18~9/19: 전이 메모 75건 중 48건(64%)이 반말이었고 그대로 History 에
남았습니다. 같은 전이 경로가 확인 포인트 길이·담기지 않은 코드·가지가 main 에
닿았나는 이미 거부하는데 존댓말만 경고였습니다.

계약 일곱.
  T1 반말 메모는 전이가 거부된다
  T2 존댓말 메모는 지나간다
  T3 --force 는 지나간다 (사람이 친 말을 옮기는 자리)
  T4 사람의 판정(judge)은 걸리지 않는다 — 대시보드 반려는 사람이 친 글자를 그대로 싣는다
  T5 워처가 지은 메모(auto)는 걸리지 않는다
  T6 개인 설정이 이긴다 — pref_* 가 반말을 말하면 검사가 서지 않는다
  T7 그 설정을 지우면 규약의 기본값으로 돌아간다

실행: python3 tests/ transition_speech
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.normpath(os.path.join(HERE, "..", "bin", "s9"))
RID = "REQ-20260919-001-62x6"


class TransitionSpeechGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9speech-")
        cls.env = dict(os.environ)
        cls.env["S9_ROOT"] = cls.root
        cls.env["S9_SESSION"] = "bbbb2222"
        cls.env.pop("S9_AUTO_RESUME", None)
        cls.s9("init")
        cls.s9("user", "add", "tester")
        cls.s9("new", "request", "--title", "말투 가드 시험", "--summary", "요약",
                "--goal", "판별 가능한 한 문장", "--size", "S", "--user", "tester",
                "--body", "본문")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def s9(cls, *argv):
        return subprocess.run([sys.executable, S9, *argv], env=cls.env,
                              stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=120)

    def status(self, new, note, *extra):
        return self.s9("status", RID, new, "--note", note, "--user", "tester", *extra)

    def test_t1_plain_note_is_refused(self):
        r = self.status("in-progress", "이 메모는 반말이다 — 막혀야 한다")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("전이 메모가 반말이다", r.stderr)

    def test_t2_polite_note_passes(self):
        r = self.status("in-progress", "이 메모는 존댓말입니다 — 지나가야 합니다.")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_t3_force_passes(self):
        r = self.status("review", "사람이 친 말을 옮깁니다 — 반려: 그대로다", "--force")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_t4_t5_judge_and_auto_are_not_gated(self):
        """T4·T5 — 사람이 친 말과 워처가 지은 메모는 거부 대상이 아니다."""
        import importlib.machinery
        import importlib.util
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_speech_gate",
            importlib.machinery.SourceFileLoader(
                "s9_speech_gate", os.path.normpath(os.path.join(HERE, "..", "bin", "s9.py"))))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.do_transition(RID, "in-progress",
                        note="반려: 파비콘은 그대로다. [via dashboard]",
                        user="tester", judge=True)
        m.do_transition(RID, "review", note="[auto] 이 머신의 워처가 집었다",
                        user="tester", auto=True)

    def test_t6_t7_personal_setting_wins_and_delete_restores(self):
        """T6·T7 — 개인 설정이 이기고, 지우면 규약의 기본값으로 돌아간다."""
        self.s9("user", "config", "tester", "pref_말투", "나에게는 반말로 해라")
        r = self.status("in-progress", "개인 설정이 있으니 이 반말은 지나가야 한다")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.s9("user", "config", "tester", "pref_말투", "")
        r = self.status("review", "설정을 지웠으니 이 반말은 막혀야 한다")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("전이 메모가 반말이다", r.stderr)


if __name__ == "__main__":
    unittest.main()
