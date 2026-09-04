"""터미널 수신 연결 상태 가시화 계약 (REQ-20260825-032).

실사고: 서버 재기동으로 SSE 수신이 끊겨도 화면에 아무 표시가 없어
사용자가 무응답으로 오인, 같은 질문을 30초에 3회 재전송했다.
이 테스트는 "수신 스트림 단절/폴백/재접속 상태가 상태줄에 보이고,
복구되면 사라진다"를 index.html 구조 계약으로 고정한다.

실행: python3 tests/ term_conn
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


def _fn_body(html, name):
    """function <name>(...){...} 본문 — 중괄호 균형으로 잘라낸다."""
    m = re.search(r"function %s\([^)]*\)\{" % re.escape(name), html)
    if not m:
        return None
    i, depth = m.end() - 1, 0
    for j in range(i, len(html)):
        if html[j] == "{":
            depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                return html[m.end():j]
    return None


class TestTermConn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.html = f.read()

    # S1~S4 공통: 상태 전이 단일 경로 termConnSet가 존재하고
    # retry/down은 경고(ccwarn), 정상 상태는 표시를 숨긴다.
    def test_test_term_conn(self):
        """TestTermConn 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("conn_setter_exists_with_states"):
            body = _fn_body(self.html, "termConnSet")
            self.assertIsNotNone(body, "termConnSet 함수가 index.html에 없다")
            self.assertIn("hidden", body, "정상 복구 시 표시를 숨기는 경로가 없다")
            # 상태 → 라벨/색 테이블 (const TERM_CONN)
            tbl = re.search(r"const TERM_CONN\s*=\s*\{(.*?)\n\};", self.html, re.S)
            self.assertIsNotNone(tbl, "수신 상태 라벨 테이블(TERM_CONN)이 없다")
            for state in ("retry", "down", "poll"):
                self.assertIn(state + ":", tbl.group(1),
                              f"TERM_CONN에 {state} 상태가 없다")
            self.assertIn("ccwarn", tbl.group(1), "단절 상태에 경고색(ccwarn)이 없다")
        with self.subTest("conn_element_in_status_strip"):
                self.assertRegex(
                    self.html, r'id="cc-conn"[^>]*hidden',
                    "상태줄에 cc-conn 표시 요소(기본 hidden)가 없다")

            # S1. SSE 단절 → '재접속 중' 경고
        with self.subTest("sse_error_marks_retry"):
                body = _fn_body(self.html, "termConnectSSE")
                self.assertIsNotNone(body)
                onerr = body[body.index("es.onerror"):]
                self.assertRegex(
                    onerr, r"""termConnSet\(T,\s*["']retry["']\)""",
                    "es.onerror에서 재접속 중 상태를 표시하지 않는다")

            # S4. SSE 복구 → 표시 소거
        with self.subTest("sse_recovery_clears"):
                body = _fn_body(self.html, "termConnectSSE")
                self.assertIsNotNone(body)
                self.assertRegex(
                    body, r"""termConnSet\(T,\s*["']sse["']\)""",
                    "SSE 수신 재개 시 표시를 정상으로 되돌리지 않는다")

            # S2. 폴백 진입 표시 + S3. 폴백 연속 실패 → 불통 경고 + S4. 폴 성공 리셋
        with self.subTest("poll_fallback_states"):
                body = _fn_body(self.html, "termPollFallback")
                self.assertIsNotNone(body)
                self.assertRegex(
                    body, r"""termConnSet\(T,\s*["']poll["']\)""",
                    "폴백 진입을 표시하지 않는다")
                self.assertIn("pollFails", body,
                              "폴 실패 누적 카운터(pollFails)가 없다")
                self.assertRegex(
                    body, r"""termConnSet\(T,\s*["']down["']\)""",
                    "폴백 연속 실패를 불통 경고로 승격하지 않는다")
                self.assertRegex(
                    body, r"pollFails\s*=\s*0",
                    "폴 성공 시 실패 카운터를 리셋하지 않는다")

            # S5. 하단 meta도 conn 상태를 반영
        with self.subTest("meta_reflects_conn"):
                body = _fn_body(self.html, "termMeta")
                self.assertIsNotNone(body)
                self.assertIn("T.conn", body, "cc-meta가 수신 연결 상태를 반영하지 않는다")

            # 부착/재부착 시 이전 세션의 단절 표시가 새 세션으로 새지 않는다
        with self.subTest("attach_resets_conn"):
            body = _fn_body(self.html, "termAttach")
            self.assertIsNotNone(body)
            self.assertRegex(
                body, r"pollFails\s*=\s*0",
                "세션 재부착 시 폴 실패 카운터를 리셋하지 않는다")

