"""불변식: 추적됨 ∩ 무시됨 = ∅ — state/ 는 index 에 없다 (REQ-20260909-024, architect).

`.gitignore` 에 줄이 늘 때마다 index 정리를 잊은 것을 전부 잡는다. 맥미니 실측:
옛 커밋에 남은 state/sessions/approvals_seen.json 이 pull 을 12시간 막았다.

실행: python3 tests/ state_untracked
"""
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class StateUntracked(unittest.TestCase):

    def test_u6_nothing_tracked_is_ignored_and_state_is_not_in_the_index(self):
        both = subprocess.run(["git", "-C", ROOT, "ls-files", "-ci", "--exclude-standard"],
                              capture_output=True, text=True).stdout.split()
        self.assertEqual(both, [], "추적됨∩무시됨 파일이 있다 — bin/s9 doctor --untrack-state")
        st = subprocess.run(["git", "-C", ROOT, "ls-files", "state"],
                            capture_output=True, text=True).stdout.split()
        self.assertEqual(st, [], "state/ 가 index 에 있다 — 기계 살림은 추적하지 않는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
