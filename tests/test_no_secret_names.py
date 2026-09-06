"""개인 장치의 이름은 코드 밖에 둔다 (REQ-20260906-011, projects/section9/CONTEXT.md).

이 기계의 비밀 이름(`s9 secret ls`)이 bin/·tests/·harness/·web/ 의 추적 파일에 나오면
실패한다 — 그 이름은 한 사람의 비밀로 만든 장치라, 저장소를 이어받는 사람은 몰라야 한다.
비밀의 **값**은 읽지 않는다(이름만).

실행: python3 tests/ no_secret_names
"""
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")
SCAN = ("bin", "tests", "harness", "web")


def secret_names():
    r = subprocess.run([S9, "secret", "ls"], capture_output=True, text=True, timeout=30,
                       env={**os.environ, "S9_SESSION": ""})
    names = []
    for ln in r.stdout.splitlines():
        m = re.match(r"^\s{2}(\S+)\s+(internal|external)\b", ln)
        if m:
            names.append(m.group(1))
    return names


class NoSecretNames(unittest.TestCase):
    def test_secret_names_do_not_appear_in_code(self):
        names = [n for n in secret_names() if len(n) >= 4 and n != "test"]
        if not names:
            self.skipTest("이 기계에 비밀 이름이 없다 — 지킬 재료가 없다")
        hits = []
        for n in names:
            r = subprocess.run(["git", "-C", REPO, "grep", "-n", "-i", "-w", n, "--", *SCAN],
                               capture_output=True, text=True, timeout=60)
            for ln in r.stdout.splitlines():
                if len(ln) > 400:            # base64 같은 데이터 줄은 우연이다
                    continue
                if ln.split(":", 1)[0].endswith("test_no_secret_names.py"):
                    continue
                hits.append(ln[:160])
        self.assertEqual(hits, [], "개인 장치의 이름이 코드에 있다 — 인자·환경·state/ 로 옮겨라: "
                         + "; ".join(hits[:6]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
