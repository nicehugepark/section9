"""터미널의 폴은 한 줄로 선다 (REQ-20260918-014-62x6).

실측 2026-09-18: 이 기계의 127.0.0.1 은 WSL 미러 네트워킹의 중계를 지나고, 그
중계에는 **같은 순간에 받아 주는 연결 수의 천장**이 있다. 동시 16연결을 걸면 우리
서버(받아들이기 큐 128)든 방금 띄운 임시 서버(큐 5)든 똑같이 60/160 이 거부됐다 —
큐가 25배 다른데 같은 비율이니 끊는 것은 서버가 아니다. 기계가 바쁘면 천장은 한둘까지
내려와, CLI 를 분당 2196회 돌린 직후에는 동시 2연결에서 회차마다 하나가 사라졌다.

천장은 우리 것이 아니다. **한꺼번에 거는 것**이 우리 것이다. 그래서 셋을 지킨다.

  S1 세션에 붙을 때 가장 무거운 두 응답(/api/chat/log · /api/stream)을 차례로 부른다.
     예전엔 `Promise.all` 이었고, 그 자리가 「로컬 터미널에서 친 프롬프트가 대시보드에
     안 뜬다」로 보이던 자리다.
  S2 되풀이되는 폴(대상 5초 · 수신함 3초)은 termSerial 의 줄에 매달려 차례로 간다.
     둘은 서로 다른 시계라 15초마다 같은 초에 겹쳤다(초 10/25/40/55).
  S3 간헐 실패 재시도가 1회가 아니다 — 물러나며 여러 번 건다.

실행: python3 tests/ terminal_polls_serial
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "web", "app", "terminal.js"))


def read():
    with open(SRC, encoding="utf-8") as f:
        return f.read()


class PollsGoInOneLine(unittest.TestCase):
    def setUp(self):
        self.src = read()

    def test_s1_the_two_heavy_fetches_are_sequential(self):
        """S1. chat/log 와 stream 을 한꺼번에 걸지 않는다."""
        # Promise.all 자체를 금하지는 않는다 — 이 파일의 다른 자리에는 한꺼번에
        # 걸어도 되는 가벼운 것들이 있다. 막는 것은 **이 둘이 같이 걸리는 것**이다.
        for m in re.finditer(r"Promise\.all\(\[(.*?)\]\)", self.src, re.S):
            body = m.group(1)
            self.assertFalse("/api/chat/log" in body and "/api/stream" in body,
                             "가장 무거운 응답 둘을 다시 한꺼번에 건다 — "
                             "중계의 천장에 함께 걸린다")
        order = [m.start() for m in re.finditer(
            r'await retry\("/api/(chat/log|stream)', self.src)]
        self.assertEqual(len(order), 2,
                         "두 응답을 각각 await 로 부르는 자리가 둘이 아니다")

    def test_s2_the_repeating_polls_share_one_chain(self):
        """S2. 되풀이 폴 둘이 termSerial 의 줄을 탄다."""
        self.assertIn("function termSerial(", self.src, "폴을 줄 세우는 붓이 없다")
        for body in ('termSerial(T, tick)', 'termSerial(T, () => refreshTermChat(T))'):
            self.assertIn(body, self.src, "%s 가 줄에 안 매달렸다" % body)

    def test_s2b_a_failed_poll_does_not_break_the_line(self):
        """S2b. 폴 하나가 예외로 끝나도 다음 폴이 계속 돈다 — then(fn, fn)."""
        m = re.search(r'function termSerial\(T, fn\)\{(.*?)\n\}', self.src, re.S)
        self.assertIsNotNone(m)
        self.assertIn(".then(fn, fn)", m.group(1),
                      "성공에만 이으면 한 번 실패한 뒤로 줄이 멎는다")

    def test_s3_retry_tries_more_than_once(self):
        """S3. 재시도가 1회가 아니다."""
        m = re.search(r'const retry = async url => \{(.*?)\n  \};', self.src, re.S)
        self.assertIsNotNone(m, "retry 를 못 찾았다")
        self.assertRegex(m.group(1), r'for \(let i = 0; i < [2-9]',
                         "재시도가 한 번뿐이다 — 천장에 걸리는 구간에서는 대부분 빈손이다")


if __name__ == "__main__":
    unittest.main()
