"""돌고 있는 서버가 낡았음을 스스로 알린다 (REQ-20260826-011).

2026-08-26 사고: 지목 전송(REQ-095)이 구현·테스트 통과된 뒤에도 12시간 동안
동작하지 않았다. 원인은 코드가 아니라 **구동 중이던 serve 가 그 기능 이전
코드였다**는 것이다. 파이썬 서버는 기동 시점 코드를 메모리에 들고 돈다.

이 어긋남이 특히 조용한 이유:
  - web/index.html 같은 정적 파일은 디스크에서 바로 읽히니 화면은 즉시 바뀐다
    → "UI 는 바뀌었는데 동작만 안 된다"로 보인다.
  - 테스트는 디스크의 코드를 직접 실행하니 전부 통과한다
    → "고쳤고 검증도 됐다"는 확신만 남는다.
아무도 알려주지 않으면 그 상태가 며칠도 간다.

그래서 서버가 **기동 시점의 자기 코드 지문**을 들고 있다가 디스크와 달라지면
그 사실을 내보낸다. 판단(재기동할지)은 사람 몫이다 — 진행 중 요청·SSE 를
끊는 일이라 서버가 스스로 결정할 것이 아니다.

실행: python3 tests/ stale_serve
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

os.environ.setdefault("S9_ROOT", tempfile.mkdtemp(prefix="s9-stale-"))
spec = importlib.util.spec_from_loader(
    "s9_mod_stale", importlib.machinery.SourceFileLoader("s9_mod_stale", S9))
s9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s9)


class CodeStamp(unittest.TestCase):
    def test_code_stamp(self):
        """CodeStamp 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("stamp_reads_the_running_file"):
            st = s9.code_stamp()
            self.assertTrue(st.get("size"), st)
            self.assertTrue(st.get("mtime"), st)
        with self.subTest("same_file_same_stamp"):
            self.assertEqual(s9.code_stamp(), s9.code_stamp())
        with self.subTest("changed_file_changes_the_stamp"):
            a = {"mtime": 100.0, "size": 10}
            self.assertTrue(s9.code_is_stale(a, {"mtime": 101.0, "size": 10}))
            self.assertTrue(s9.code_is_stale(a, {"mtime": 100.0, "size": 11}))
            self.assertFalse(s9.code_is_stale(a, {"mtime": 100.0, "size": 10}))
        with self.subTest("unknown_stamp_is_not_stale"):
            self.assertFalse(s9.code_is_stale({}, {"mtime": 1.0, "size": 2}))
            self.assertFalse(s9.code_is_stale({"mtime": 1.0, "size": 2}, {}))
            self.assertFalse(s9.code_is_stale(None, None))

class ServeInfoContract(unittest.TestCase):
    """엔드포인트가 판단에 필요한 것을 모두 담는다 — 사람이 '언제 뜬 서버가
    무엇과 다른가'를 알아야 재기동을 결정할 수 있다."""

    def test_handler_exists_and_reports_staleness(self):
        with open(S9, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('parsed.path == "/api/serveinfo"', src,
                      "서버 상태를 물어볼 창구가 없다")
        i = src.index('parsed.path == "/api/serveinfo"')
        seg = src[i:i + 900]
        for key in ("stale", "started", "code_stamp"):
            self.assertIn(key, seg, key)


if __name__ == "__main__":
    unittest.main()
