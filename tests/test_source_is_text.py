"""화면 소스는 텍스트다 — 제어 바이트가 섞이면 file(1) 이 data 로 판정하고
grep 이 -a 없이 파일을 통째로 건너뛴다 (REQ-20260907-020, 실제로 graph.js 의
캐시 키 구분자로 쓰인 NUL 두 바이트가 그랬다). 탭·줄바꿈만 허용한다."""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")


def control_bytes(path):
    data = open(path, "rb").read()
    return [i for i, b in enumerate(data) if b < 32 and b not in (9, 10, 13)]


class SourceIsText(unittest.TestCase):
    def test_web_sources_have_no_control_bytes(self):
        bad = []
        for base, _d, files in os.walk(WEB):
            for fn in files:
                if not fn.endswith((".js", ".css", ".html")):
                    continue
                p = os.path.join(base, fn)
                hits = control_bytes(p)
                if hits:
                    bad.append(f"{os.path.relpath(p, ROOT)}: byte {hits[0]} (+{len(hits) - 1})")
        self.assertEqual(bad, [], "제어 바이트가 든 화면 소스 — 이스케이프(\\u0000)로 바꿔라")


if __name__ == "__main__":
    unittest.main()
