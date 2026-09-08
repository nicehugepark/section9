"""요청별 토큰 기록 (REQ-20260907-009-62x6 · 설계 REQ-20260907-008).

transcript 의 `message.usage` 를 contributions 의 시간 창으로 합쳐
contributions[].tokens 와 문서 머리 tokens 에 적고, catalog_row 가 싣고,
`s9 metrics report --by req|agent|day` 가 집계한다.

원칙: 모르는 것을 0 으로 적지 않는다 — 파일·창·이벤트가 없으면 키가 생기지 않는다.
격리: S9_ROOT=mktemp. 실행: python3 tests/ req_tokens
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")

_spec = importlib.util.spec_from_loader(
    "s9tok", importlib.machinery.SourceFileLoader("s9tok", S9))
s9 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s9)


def _ev(ts, mid, i, o, cr, cc, typ="assistant"):
    return {"type": typ, "timestamp": ts, "uuid": mid + "-u",
            "message": {"id": mid, "role": typ, "usage": {
                "input_tokens": i, "output_tokens": o,
                "cache_read_input_tokens": cr,
                "cache_creation_input_tokens": cc}}}


def _write_jsonl(path, events):
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


# 창: 09:00:00 ~ 09:10:00 (KST). transcript 시각은 UTC 'Z' 표기 — 실제 Claude 형식.
WIN_LO = "2026-09-07T09:00:00+09:00"
WIN_HI = "2026-09-07T09:10:00+09:00"
EVENTS = [
    _ev("2026-09-06T23:59:00.000Z", "m0", 100, 1, 1000, 10),   # 창 앞
    {"type": "user", "timestamp": "2026-09-07T00:01:00.000Z",
     "message": {"role": "user", "content": "질문"}},           # usage 없음
    _ev("2026-09-07T00:02:00.000Z", "m1", 3, 40, 500, 60),     # 창 안
    _ev("2026-09-07T00:02:00.300Z", "m1", 3, 40, 500, 60),     # 같은 id 반복 줄
    _ev("2026-09-07T00:03:00.000Z", "m2", 5, 70, 800, 90),     # 창 안
    _ev("2026-09-07T00:20:00.000Z", "m3", 1000, 1, 1, 1),      # 창 뒤
]
IN_WINDOW = {"in": 8, "out": 110, "cache_read": 1300, "cache_create": 150}


class UsageSumTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="s9tok")
        self.tp = os.path.join(self.dir, "t.jsonl")
        _write_jsonl(self.tp, EVENTS)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_s1_s2_window_and_dedupe(self):
        """S1·S2: 창 안 이벤트만, 같은 message.id 는 한 번만."""
        self.assertEqual(s9.transcript_usage(self.tp, WIN_LO, WIN_HI), IN_WINDOW)

    def test_s3_unknown_is_absent_not_zero(self):
        """S3: 파일 없음·창 없음·창 안 이벤트 없음 → None (0 아님)."""
        self.assertIsNone(s9.transcript_usage(self.tp + ".none", WIN_LO, WIN_HI))
        self.assertIsNone(s9.transcript_usage("", WIN_LO, WIN_HI))
        self.assertIsNone(s9.transcript_usage(self.tp, "", WIN_HI))
        self.assertIsNone(s9.transcript_usage(self.tp, WIN_LO, ""))
        self.assertIsNone(s9.transcript_usage(
            self.tp, "2026-09-07T10:00:00+09:00", "2026-09-07T10:01:00+09:00"))
        self.assertIsNone(s9.transcript_usage(self.tp, WIN_HI, WIN_LO))

    def test_s7_event_usage_extraction(self):
        """S7: 이벤트 하나의 usage 추출 규칙은 함수 하나 — usage 없으면 None."""
        self.assertEqual(s9.event_usage(EVENTS[2]),
                         {"in": 3, "out": 40, "cache_read": 500, "cache_create": 60})
        self.assertIsNone(s9.event_usage(EVENTS[1]))
        self.assertIsNone(s9.event_usage({}))
        # 스트림 화면의 증분 스캐너가 같은 함수를 쓴다 (코드 경로 공유 확인)
        src = open(S9 + ".py", encoding="utf-8").read()
        i = src.index("def agent_file_stats(")
        self.assertIn("event_usage(ev)", src[i:i + 3000])
        self.assertNotIn('u.get("output_tokens")', src[i:i + 3000])

    def test_s4_record_contribution_writes_tokens(self):
        """S4: 기여를 닫을 때 창 안 usage 를 항목과 문서 머리에 적는다; 다시 닫으면
        늘어난 만큼만 더한다."""
        meta = {}
        e = s9.record_contribution(meta, "lead:x", item="i1", result="done",
                                   transcript=self.tp, ts=WIN_HI, started=WIN_LO)
        self.assertEqual(e["tokens"], IN_WINDOW)
        self.assertEqual(meta["tokens"], IN_WINDOW)
        # 같은 actor·item 을 더 넓은 창으로 다시 닫는다 → m3 만큼만 더해진다
        e2 = s9.record_contribution(meta, "lead:x", item="i1", result="done",
                                    transcript=self.tp, ts="2026-09-07T09:30:00+09:00")
        self.assertIs(e2, meta["contributions"][0])
        self.assertEqual(e2["tokens"]["in"], 1008)
        self.assertEqual(meta["tokens"], {"in": 1008, "out": 111,
                                          "cache_read": 1301, "cache_create": 151})
        # 창이 없는 새 항목(started == ended)에는 tokens 키가 생기지 않는다
        e3 = s9.record_contribution(meta, "lead:x", item="i2", result="done",
                                    transcript=self.tp, ts="2026-09-07T09:31:00+09:00")
        self.assertNotIn("tokens", e3)
        self.assertEqual(meta["tokens"]["in"], 1008)
        # transcript 가 없으면 아무것도 적지 않는다
        m2 = {}
        e4 = s9.record_contribution(m2, "lead:x", item="i", ts=WIN_HI, started=WIN_LO)
        self.assertNotIn("tokens", e4)
        self.assertNotIn("tokens", m2)

    def test_s5_catalog_row_carries_tokens(self):
        """S5: catalog_row 가 meta.tokens 를 싣는다 — 없으면 빈 값."""
        p = os.path.join(s9.ROOT, "vault", "x.md")
        row = s9.catalog_row({"id": "REQ-1", "type": "request", "tokens": IN_WINDOW}, p)
        self.assertEqual(row["tokens"], IN_WINDOW)
        self.assertEqual(s9.catalog_row({"id": "REQ-2", "type": "request"}, p)["tokens"], "")


class ReportCliTest(unittest.TestCase):
    """S6: s9 metrics report --by req|agent|day 가 표를 낸다 (격리 루트, CLI 1회 왕복)."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9tokcli")
        cls.env = {**os.environ, "S9_ROOT": cls.root,
                   "S9_SESSION": "deadbeef", "S9_AUDIT": "off"}
        cls.env.pop("S9_PORT", None)
        cls.tp = os.path.join(cls.root, "t.jsonl")
        _write_jsonl(cls.tp, EVENTS)
        cls.s9run("init")
        out = cls.s9run("new", "request", "--title", "토큰 표 시험", "--summary", "s",
                      "--goal", "g", "--body", "b")
        cls.doc = out.stdout.split()[0].strip()
        cls.s9run("contrib", cls.doc, "--actor", "lead:fable", "--item", "i1",
                "--result", "done", "--transcript", cls.tp, "--started", WIN_LO,
                "--ended", WIN_HI)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def s9run(cls, *argv):
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env=cls.env, timeout=60)

    def test_s6_report_tables(self):
        for by in ("req", "agent", "day"):
            with self.subTest(by=by):
                r = self.s9run("metrics", "report", "--by", by)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("cache_read", r.stdout)
                self.assertIn("cache_create", r.stdout)
                self.assertIn("110", r.stdout)     # out
                self.assertIn("1300", r.stdout)    # cache_read 는 따로
                self.assertIn("150", r.stdout)     # cache_create 는 따로
                self.assertNotIn("1450", r.stdout)  # 캐시 둘을 합치지 않는다
        r = self.s9run("metrics", "report", "--by", "req")
        self.assertIn(self.doc, r.stdout)
        self.assertIn("토큰 표 시험", r.stdout)
        r = self.s9run("metrics", "report", "--by", "agent")
        self.assertIn("lead:fable", r.stdout)
        r = self.s9run("metrics", "report", "--by", "day")
        self.assertIn("2026-09-07", r.stdout)
        r = self.s9run("metrics", "report", "--by", "req", "--json")
        rows = json.loads(r.stdout)
        self.assertEqual(rows[0]["tokens"], IN_WINDOW)


class CardTest(unittest.TestCase):
    def test_s8_card_token_line(self):
        """S8: 토큰 줄은 **카드에 서지 않는다** (REQ-20260908-004).

        한때 카드에도 그렸다(REQ-20260907-009). 주인이 2026-09-08 에 「카드에까지
        보여줄 필요는 없다」고 했고, 값이 하한값이라(서브에이전트 몫만 세므로
        리드가 직접 한 요청은 늘 비어 있다) 값 있는 카드만 줄이 하나 더 생겨
        키가 들쭉날쭉해지던 자리다. 짓는 함수는 문서 화면이 쓰므로 그대로 산다.
        """
        src = open(os.path.join(ROOT, "web", "app", "card.js"), encoding="utf-8").read()
        self.assertIn("function tokensLineHTML(r)", src)
        self.assertNotIn("tokensLineHTML(r)", src.split("function cardHTML(r)")[1],
                         "카드가 토큰 줄을 다시 그린다")
        body = src.split("function tokensLineHTML(r)")[1].split("\nfunction cardHTML")[0]
        self.assertIn("if (!t", body)      # 없으면 아무것도 그리지 않는다
        for word in ("출력", "입력", "캐시"):
            self.assertIn(word, body)
        # 백틱·괄호 짝이 맞는다 (node 가 없는 환경의 최소 문법 검사)
        self.assertEqual(body.count("`") % 2, 0)
        self.assertEqual(body.count("{"), body.count("}"))
        self.assertEqual(body.count("("), body.count(")"))
        node = shutil.which("node")
        if node:
            r = subprocess.run([node, "--check", os.path.join(ROOT, "web", "app", "card.js")],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
