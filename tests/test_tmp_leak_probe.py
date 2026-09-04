"""러너의 임시자리 회수를 시험하기 위한 미끼 (REQ-20260829-003).

test_tmp_hygiene.py 의 Runner 시험이 이 파일만 골라 러너를 실제로 돌린다.
`S9_TMP_LEAK_PROBE=1` 일 때만 일부러 흘린다 — 평소 스위트에서는 아무것도
남기지 않는다.
"""
import os
import subprocess
import sys
import tempfile
import unittest

LEAK = os.environ.get("S9_TMP_LEAK_PROBE") == "1"

# 모듈 수준에서 만드는 자리 — discovery 가 import 하는 그 순간에 생긴다.
# 러너가 임시 루트를 discovery **뒤에** 세우면 이것이 문 밖에 남는다.
# 여러 실제 테스트(test_tags·test_session_wake·test_link_integrity 등)가
# 정확히 이 모양이라, 미끼도 같은 모양이어야 한다.
MODULE_TMP = tempfile.mkdtemp(prefix="s9probe-")


class Probe(unittest.TestCase):
    def test_probe(self):
        """일부러 안 지운다 — 러너가 거두는지가 시험 대상이다."""
        with self.subTest("leak_is_contained_by_the_run_root"):
            d = tempfile.mkdtemp(prefix="s9gate-")
            self.assertTrue(os.path.isdir(d))
            if not LEAK:
                os.rmdir(d)
        with self.subTest("module_level_dir_is_inside_the_run_root"):
            self.assertTrue(os.path.isdir(MODULE_TMP))
            self.assertEqual(os.path.realpath(os.path.dirname(MODULE_TMP)),
                             os.path.realpath(tempfile.gettempdir()),
                             "모듈 수준 임시 자리가 실행 루트 밖에 생겼다")
        with self.subTest("child_process_sees_the_same_temp_root"):
            root = os.path.realpath(tempfile.gettempdir())
            out = subprocess.run(
                [sys.executable, "-c",
                 "import tempfile;print(tempfile.gettempdir())"],
                capture_output=True, text=True, timeout=60).stdout.strip()
            self.assertEqual(os.path.realpath(out), root)
            sys.stderr.write("PROBE-CHILD-INSIDE\n")

if __name__ == "__main__":
    unittest.main(verbosity=2)
