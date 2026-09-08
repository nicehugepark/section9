"""한 번 요청으로 세운 채팅 줄은 다시 끌려오지 않는다 (REQ-20260908-008-62x6).

주인이 본 것: REQ-20260908-004 의 본문 머리에 「선행 대화 — 직전 미문서화
메시지」로 08:18 의 말(「문서를 왜 못 불러오지?」)이 실려 있는데, 그 말은 이미
REQ-20260908-003 으로 세워 둔 뒤였다.

까닭은 표가 두 갈래이기 때문이다. 훅이 세운 요청은 수신함 줄에 `req` 가 실려
오지만, **리드가 손으로 세운 요청**은 그 줄에 아무 표도 남기지 않는다. 그래서
`_chat_context` 는 그 줄을 여전히 「미문서화」로 보고 다음 요청의 본문에 옮긴다.

표는 수신함 줄 자체가 아니라 옆 파일에 쌓는다 — 그 파일은 서버가 계속 덧붙이는
중이라 다시 쓰면 그 사이의 줄을 잃는다.

실행: python3 tests/ chat_documented
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9.py")

TMP = tempfile.mkdtemp(prefix="s9-chatdoc-")
_prev = os.environ.get("S9_ROOT")
os.environ["S9_ROOT"] = TMP
try:
    spec = importlib.util.spec_from_loader(
        "s9_chatdoc", importlib.machinery.SourceFileLoader("s9_chatdoc", S9))
    s9 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(s9)
finally:
    if _prev is None:
        os.environ.pop("S9_ROOT", None)
    else:
        os.environ["S9_ROOT"] = _prev

SID = "abcd1234"


def write_inbox(lines):
    p = s9.chat_inbox_path(SID, make=True)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for l in lines:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")


def chat(ts, text, req=None):
    d = {"ts": ts, "from": "someone", "kind": "chat", "text": text}
    if req:
        d["req"] = req
    return d


class TheMarkStopsTheEcho(unittest.TestCase):

    def setUp(self):
        for p in (s9.chat_inbox_path(SID), s9.chat_documented_path(SID)):
            try:
                os.remove(p)
            except OSError:
                pass

    def _ctx(self):
        return [l["text"] for l in s9._chat_context(SID, "someone")
                if not l.get("req")]

    def test_an_undocumented_line_is_carried_as_context(self):
        """정상 — 표가 없으면 종전대로 문맥으로 싣는다(REQ-20260825-007)."""
        write_inbox([chat(s9.now_iso(), "앞말")])
        self.assertEqual(self._ctx(), ["앞말"])

    def test_a_marked_line_is_not_carried(self):
        """실패 자리 — 손으로 요청을 세운 줄은 다시 실리지 않는다."""
        ts = s9.now_iso()
        write_inbox([chat(ts, "앞말")])
        s9.mark_chat_documented(SID, ts, "REQ-1")
        self.assertEqual(self._ctx(), [])

    def test_the_mark_carries_the_request_id(self):
        """정상 — 표에는 어느 요청으로 세웠는지가 남는다(관계로 쓸 수 있게)."""
        ts = s9.now_iso()
        write_inbox([chat(ts, "앞말")])
        s9.mark_chat_documented(SID, ts, "REQ-1")
        got = s9._chat_context(SID, "someone")
        self.assertTrue(got and got[-1].get("req") == "REQ-1", got)

    def test_a_line_after_the_marked_one_still_comes(self):
        """경계 — 표는 그 줄에서 멈추는 표시다. 그 뒤의 새 말은 그대로 실린다.

        표의 열쇠는 ts 이고 ts 는 초 단위다 — 같은 초에 두 줄이 오면 둘 다
        표를 받는다. 사람이 채팅으로 말하는 자리라 그 일이 실제로 나기 어렵고,
        나더라도 잃는 것은 문맥 한 줄이라 열쇠를 더 무겁게 만들지 않았다.
        """
        t1, t2 = "2026-09-08T10:00:00+09:00", "2026-09-08T10:00:05+09:00"
        write_inbox([chat(t1, "옛말"), chat(t2, "새말")])
        s9.mark_chat_documented(SID, t1, "REQ-1")
        self.assertEqual(self._ctx(), ["새말"])

    def test_no_mark_file_is_not_an_error(self):
        """경계 — 표 파일이 아예 없는 판에서도 종전대로 돈다."""
        write_inbox([chat(s9.now_iso(), "앞말")])
        self.assertEqual(s9.chat_documented_set(SID), {})
        self.assertEqual(self._ctx(), ["앞말"])

    def test_the_mark_is_not_written_into_the_inbox(self):
        """회귀 — 수신함 파일은 건드리지 않는다(서버가 덧붙이는 중이다)."""
        ts = s9.now_iso()
        write_inbox([chat(ts, "앞말")])
        before = open(s9.chat_inbox_path(SID), encoding="utf-8").read()
        s9.mark_chat_documented(SID, ts, "REQ-1")
        self.assertEqual(open(s9.chat_inbox_path(SID), encoding="utf-8").read(),
                         before, "수신함 줄을 다시 썼다")


if __name__ == "__main__":
    unittest.main()
