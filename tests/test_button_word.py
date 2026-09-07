"""화면·코드·시험에 UI 뜻의 「단추」가 남지 않는다 (REQ-20260907-007).

주인 지시 2026-09-07: 이제 사람들은 「단추」를 의복에서만 쓴다 — 화면의 그것은 버튼이다.
용어 검사기의 표 한 줄(bin/s9.py 의 ("단추", "버튼"))만 예외다."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = ("web", "harness", "tests", "bin")
SKIP_EXT = (".png", ".jpg", ".ico", ".cmd", ".pyc")


def offenders():
    hits = []
    for d in DIRS:
        for base, _dirs, files in os.walk(os.path.join(ROOT, d)):
            if "__pycache__" in base or "node_modules" in base:
                continue
            for fn in files:
                if fn.endswith(SKIP_EXT):
                    continue
                p = os.path.join(base, fn)
                try:
                    text = open(p, encoding="utf-8").read()
                except (UnicodeDecodeError, OSError):
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if "단추" not in line:
                        continue
                    if fn == "s9.py" and ("(\"단추\", \"버튼\")" in line or "「단추」는 의복" in line):
                        continue                      # 용어 검사기의 표와 그 주석
                    if fn == "test_button_word.py":
                        continue
                    hits.append(f"{os.path.relpath(p, ROOT)}:{i}: {line.strip()[:80]}")
    return hits


class NoButtonWord(unittest.TestCase):
    def test_no_danchu_left(self):
        self.assertEqual(offenders(), [], "「단추」가 남았다 — 버튼으로 바꿔라 (REQ-20260907-007)")


if __name__ == "__main__":
    unittest.main()
