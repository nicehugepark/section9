"""코드는 갈리고 데이터는 하나다 (REQ-20260828-011-62x6).

같은 파일을 두 주체가 동시에 고쳐 **남의 미커밋 작업이 조용히 사라진** 일이 이
저장소에서 네 번 났다(2026-08-26 테스트 파일 소실, 08-27 반쪽 커밋, 08-27 디자이너
"내가 쓰지 않은 코드가 있다", 08-28 셋이 한 파일에 동시에 붙음). 네 번 다 같은
파일 하나였다 — `web/index.html`.

워크트리는 그 충돌을 **없애지 않는다. 보이는 충돌로 바꾼다.** 지금은 그 자리에서
소실되고 나중에야 알아챈다.

**다만 그냥 만들면 더 나빠진다.** 이 저장소에는 코드만 있는 게 아니라 데이터가
같이 산다(vault·index·state·users). 워크트리를 그냥 쓰면 데이터도 갈려 **진실이
두 벌**이 된다 — 이 저장소의 제1 원칙("판정이 두 벌이면 한 벌만 고쳐진다")을
정면으로 어긴다.

그래서 `S9_ROOT` 를 본 저장소로 못박는다. 실측으로 갈라지는 것을 보였다:

    S9_ROOT 고정   워크트리의 s9 가 **살아 있는 문서**를 본다
    S9_ROOT 없음   워크트리에 커밋돼 있던 **옛 사본**을 본다

실행: python3 tests/ worktree
"""
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class Worktree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = open(S9, encoding="utf-8").read()
        i = cls.src.index("def cmd_worktree(")
        cls.seg = cls.src[i:cls.src.index("\ndef ", i + 10)]

    # N1. 만들면 S9_ROOT 를 못박으라고 **말해 준다** — 이걸 빼먹으면 진실이 갈린다
    def test_worktree(self):
        """Worktree 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_pins_root"):
                self.assertIn("S9_ROOT", self.seg)
                self.assertIn("진실이 두 벌", self.seg)

            # N2. 거두는 자리를 함께 만든다 — 안 거두면 쌓인다
        with self.subTest("n2_has_remove"):
                self.assertIn('act == "rm"', self.seg)
                self.assertIn('"worktree", "remove"', self.seg,
                              "거두는 명령을 실제로 부르지 않는다")

            # B1. 미커밋 변경이 있으면 거두지 않는다 — 말없이 지우지 않는 것이 존재 이유다
        with self.subTest("b1_refuses_dirty_remove"):
                self.assertIn("확인 없이 지우지 않는다", self.seg)

            # B2. 이름을 가린다 — 경로를 벗어나는 이름을 받지 않는다
        with self.subTest("b2_name_validated"):
                self.assertIn("re.fullmatch", self.seg)
                m = re.search(r're\.fullmatch\(r"([^"]+)"', self.seg)
                self.assertIsNotNone(m)
                for bad in ("../x", "a/b", ""):
                    self.assertIsNone(re.fullmatch(m.group(1), bad), bad)
                self.assertIsNotNone(re.fullmatch(m.group(1), "designer-1"))

            # R1. 워크트리 자리는 저장소에 담기지 않는다
        with self.subTest("r1_not_committed"):
            r = subprocess.run(["git", "check-ignore", "-q",
                                "state/worktrees/anything"],
                               cwd=os.path.join(HERE, ".."), timeout=15)
            self.assertEqual(r.returncode, 0,
                             "워크트리 자리가 저장소에 담긴다")

if __name__ == "__main__":
    unittest.main()
