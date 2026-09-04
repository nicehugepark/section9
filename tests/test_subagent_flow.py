"""서브에이전트의 말이 제자리에서 흐른다 (REQ-20260829-014-62x6).

서브에이전트의 말은 리드 세션 transcript 에 **한 줄도 없다** — 별도 파일
(`<sessionUUID>/subagents/agent-<id>.jsonl`)에 isSidechain 으로 쌓인다. 그래서
대시보드 터미널은 스폰 두 줄을 그린 뒤 완료 통지가 올 때까지 통째로 침묵했다.

1차 수정은 그 말을 **main 판에 섞었다.** 사용자가 반려했다: "이것 때문에 메인
리드 에이전트 터미널 창이 지저분해지고 있구나. 서브 에이전트가 스폰되면 터미널
하단에서 에이전트를 선택할 수 있게 되어있는데 그 터미널에서 로그를 출력해야지."
맞다 — 에이전트 하나가 도구를 백 번 부르면 리드의 문장 사이가 남의 로그 수백
줄로 밀린다. 침묵을 없애려다 **읽을 수 없는 판**을 만든 것이다.

그래서 자리가 셋으로 갈린다.

  ① **main 판은 리드의 판이다.** 서브에이전트의 줄은 여기 오지 않는다.
     `termAttach` 는 에이전트 파일을 되돌려 읽지 않고, 폴러는 그 줄을 main
     버퍼(`T.buf`)에 넣지 않는다.
  ② **말은 그 에이전트의 판에서 흐른다.** 하단 스트립의 행을 누르면(또는 ←)
     `#cc-agview` 가 그 에이전트의 transcript 를 열고 2초마다 이어 받는다.
     처음 열 때는 최근 상한만큼만 그리고, 자른 사실을 한 줄로 적는다.
  ③ **main 에 남는 것은 셈 하나다.** "저 판에 새 N줄" — 이게 "지금 말하고
     있다"의 신호이자 누를 자리를 가리키는 손이다. 셈의 규칙은 둘이다:
     처음 본 에이전트는 세지 않고(기준선), 읽은 뒤에는 0에서 다시 센다.
     붙자마자 "새 300줄"이 떠 있으면 그건 새것이 아니라 과거다.

  ④ **offset 은 원천마다 따로다.** 서버 `/api/stream` 의 offset 은 파일 하나의
     바이트값이라 두 파일을 서버에서 머지하면 그 계약이 바뀐다. 그래서 화면이
     에이전트마다 자기 offset 을 들고 증분만 받는다 — 같은 줄을 두 번 세지
     않고, 한 번 실패해도 그 자리를 잃지 않는다.
  ⑤ **지나간 에이전트를 새로 따라잡지 않는다.** 내려간 뒤 한 번(tail)만 더
     받고 닫는다 — 끝난 에이전트를 영원히 두드리면 세션이 길어질수록 틱마다
     요청이 쌓인다.

순수 로직은 `subagent … core (pure)` 마커로 묶여 있고 이 시험은 그것을 **그대로
떼어 node 로 실행한다**. node 가 없으면 실행 검증만 건너뛰고 소스·서버 계약은
언제나 검사한다.

실행: python3 tests/ subagent_flow
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()
S9 = os.path.join(HERE, "..", "bin", "s9")

# 순수 블록은 여럿일 수 있다(merge core · unread core) — 전부 이어 붙여 돌린다.
CORE_RE = re.compile(
    r"/\* ==== subagent [a-z ]*core \(pure\).*?\*/\n(.*?)\n/\* ==== /subagent",
    re.S)


def find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


NODE = find_node()


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class FollowCore(unittest.TestCase):
    """순수 로직을 실제로 돌려 본다 — 무엇을 물어볼지, 몇 줄이 새것인지."""

    @classmethod
    def setUpClass(cls):
        blocks = CORE_RE.findall(read(INDEX))
        assert blocks, ("subagent core (pure) 블록을 못 찾았다 — 순수 로직이 "
                        "DOM/fetch 와 얽히면 시험이 그것을 못 본다")
        cls.core = "\n".join(blocks)

    def run_js(self, body):
        if not NODE:
            self.skipTest("node 없음 — 실행 검증 생략 (소스 계약은 별도 검사)")
        p = subprocess.run([NODE, "-e", self.core + "\n" + body],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])

    # ------------------------------------------------------------------ ④

    def test_follow_core(self):
        """순수 로직을 실제로 돌려 본다 — 무엇을 물어볼지, 몇 줄이 새것인지."""
        with self.subTest("each_agent_carries_its_own_offset"):
            got = self.run_js("""
            const subs = {a1:{off:512, type:"designer"}, a2:{off:0, type:"deep-diver"}};
            const rows = [{id:"a1", show:true, type:"designer"},
                          {id:"a2", show:true, type:"deep-diver"}];
            console.log(JSON.stringify(subFollowPlan(subs, rows)
              .map(p => [p.id, p.after, p.type])));
            """)
            self.assertEqual(got, [["a1", 512, "designer"], ["a2", 0, "deep-diver"]])
        with self.subTest("a_new_agent_starts_from_the_beginning"):
                got = self.run_js("""
                console.log(JSON.stringify(
                  subFollowPlan({}, [{id:"z", show:true, type:"ux-writer"}])));
                """)
                self.assertEqual(got[0]["after"], 0)
                self.assertFalse(got[0]["tail"])

            # ------------------------------------------------------------------ ⑤
        with self.subTest("a_gone_agent_is_not_newly_followed"):
            got = self.run_js("""
            console.log(JSON.stringify(
              subFollowPlan({}, [{id:"old", show:false, active:false, type:"designer"}])));
            """)
            self.assertEqual(got, [])
        with self.subTest("a_followed_agent_gets_one_last_catch_up"):
            got = self.run_js("""
            const rows = [{id:"a1", show:false, active:false, type:"designer"}];
            const first = subFollowPlan({a1:{off:9, type:"designer"}}, rows);
            const after = subFollowPlan({a1:{off:12, type:"designer", tail:true}}, rows);
            console.log(JSON.stringify([first.map(p => [p.id, p.after, p.tail]), after]));
            """)
            self.assertEqual(got[0], [["a1", 9, True]])
            self.assertEqual(got[1], [], "닫은 에이전트를 계속 두드리면 틱마다 요청이 쌓인다")
        with self.subTest("show_falls_back_to_active"):
                got = self.run_js("""
                console.log(JSON.stringify([
                  subFollowPlan({}, [{id:"a", active:true}]).length,
                  subFollowPlan({}, [{id:"b", active:false}]).length]));
                """)
                self.assertEqual(got, [1, 0])

            # ------------------------------------------------------------------ ③
        with self.subTest("the_first_sight_of_an_agent_counts_as_nothing"):
            got = self.run_js("""
            console.log(JSON.stringify([subUnread(null, 300), subUnread(undefined, 7)]));
            """)
            self.assertEqual(got, [0, 0])
        with self.subTest("the_count_accumulates_between_readings"):
            got = self.run_js("""
            let s = {off:1};                 // 이미 한 번 본 에이전트
            s = {off:2, new: subUnread(s, 3)};
            s = {off:3, new: subUnread(s, 4)};
            s = {off:4, new: subUnread(s, 0)};
            console.log(JSON.stringify(s.new));
            """)
            self.assertEqual(got, 7)
        with self.subTest("reading_resets_the_count"):
            got = self.run_js("""
            const read = {off:9, new:0};     // 판을 열었다 닫은 직후
            console.log(JSON.stringify(subUnread(read, 2)));
            """)
            self.assertEqual(got, 2)
        with self.subTest("zero_says_nothing"):
                got = self.run_js("""
                console.log(JSON.stringify([subNewMark(0), subNewMark(1), subNewMark(120)]));
                """)
                self.assertEqual(got[0], "")
                self.assertEqual(got[1], "새 1줄")
                self.assertEqual(got[2], "새 99+줄", "세 자리 수가 스트립 행을 밀어낸다")

            # ------------------------------------------------------------------ ②
        with self.subTest("the_agent_view_backfill_is_bounded"):
            got = self.run_js("""
            const many = Array.from({length: 900}, (_, i) => ({ts:"t", text:String(i)}));
            const cut = subCap(many);
            console.log(JSON.stringify(
              [cut.length, cut[cut.length - 1].text, SUB_BACKFILL_MAX]));
            """)
            self.assertEqual(got[0], got[2])
            self.assertLessEqual(got[0], 400)
            self.assertEqual(got[1], "899", "상한은 **최근** 줄을 남긴다")
        with self.subTest("missing_pieces_do_not_throw"):
            got = self.run_js("""
            console.log(JSON.stringify([
              subCap(null).length, subFollowPlan(null, null).length,
              subFollowPlan({}, [null, {show:true}]).length,
              subUnread(null, null), subUnread({new:1}, null), subNewMark(null) === ""]));
            """)
            self.assertEqual(got, [0, 0, 0, 0, 1, True])

class TheMainPaneStaysTheLeads(unittest.TestCase):
    """① main 판에 서브에이전트의 줄이 오지 않는다 (반려 사유)."""

    @classmethod
    def setUpClass(cls):
        cls.src = read(INDEX)

    def test_the_main_pane_stays_the_leads(self):
        """① main 판에 서브에이전트의 줄이 오지 않는다 (반려 사유)."""
        with self.subTest("attach_does_not_backfill_agent_files"):
            m = re.search(r"async function termAttach\(T, nt\)\{[\s\S]*?\n\}", self.src)
            self.assertTrue(m, "termAttach 를 못 찾았다")
            body = m.group(0)
            self.assertNotIn("/api/agentstream", body)
            self.assertNotIn("subBackfillPlan", body)
        with self.subTest("the_follow_tick_never_feeds_the_main_buffer"):
            m = re.search(r"const agNewTick = async \(\) => \{[\s\S]*?\n  \};", self.src)
            self.assertTrue(m, "agNewTick 이 없다 — 신호가 없으면 누를 자리도 안 보인다")
            body = m.group(0)
            self.assertIn("subFollowPlan(T.subs", body)
            self.assertIn("after=${p.after}", body)
            self.assertIn("subUnread(", body)
            self.assertNotIn("T.buf", body, "main 판은 리드의 판이다 (2차 반려 사유)")
            self.assertNotIn("termScheduleFlush", body)
            self.assertRegex(self.src, r"setInterval\(agNewTick, \d+\)")
        with self.subTest("the_main_batch_is_not_reordered_by_the_agent_merge"):
            m = re.search(r"function termScheduleFlush\(T\)\{[\s\S]*?\n\}", self.src)
            self.assertTrue(m)
            self.assertNotIn("subOrder", m.group(0))
        with self.subTest("the_open_view_is_not_double_counted"):
            m = re.search(r"const agNewTick = async \(\) => \{[\s\S]*?\n  \};", self.src)
            self.assertIn("T.agv && T.agv.id === p.id", m.group(0))

class TheAgentPaneCarriesTheLog(unittest.TestCase):
    """②③ 말은 그 에이전트의 판에서 흐르고, main 에는 셈만 남는다."""

    @classmethod
    def setUpClass(cls):
        cls.src = read(INDEX)
        cls.open = re.search(r"function termAgentOpen\(T, id\)\{[\s\S]*?\n\}",
                             cls.src).group(0)

    def test_the_agent_pane_carries_the_log(self):
        """②③ 말은 그 에이전트의 판에서 흐르고, main 에는 셈만 남는다."""
        with self.subTest("the_view_streams_that_agent"):
            self.assertIn("/api/agentstream?session=", self.open)
            self.assertIn("after=${T.agv.off}", self.open)
            self.assertRegex(self.open, r"setInterval\(\(\) => \{ if \(!document\.hidden\) load\(\); \}, \d+\)")
        with self.subTest("opening_bounds_the_first_draw_and_says_so"):
            self.assertIn("subCap(all)", self.open)
            self.assertIn("생략", self.open)
        with self.subTest("opening_clears_the_count"):
            self.assertIn("T.subs[id].new = 0", self.open)
        with self.subTest("closing_keeps_the_place"):
            m = re.search(r"function termAgentClose\(T\)\{[\s\S]*?\n\}", self.src)
            self.assertIn("s.off = T.agv.off", m.group(0))
            self.assertIn("s.new = 0", m.group(0))
        with self.subTest("the_strip_row_shows_the_count"):
            m = re.search(r"function termAgentsRender\(T\)\{[\s\S]*?\n\}", self.src)
            body = m.group(0)
            self.assertIn("subNewMark(", body)
            self.assertNotIn("background:var(--cc-green)", body)
        with self.subTest("a_spawn_fills_the_strip_at_once"):
            m = re.search(r"function termAgentSpawn\(T, type, desc\)\{[\s\S]*?\n\}",
                          self.src)
            self.assertIn("T.agTick", m.group(0))
            self.assertIn("setTimeout", m.group(0), "과거 줄을 되그릴 때 몰려 오므로 묶는다")

class ScriptParses(unittest.TestCase):
    """화면 스크립트가 통째로 문법이 맞는가 — 이 판의 가장 나쁜 실패는 빈 화면이다."""

    def test_the_dashboard_script_parses(self):
        if not NODE:
            self.skipTest("node 없음")
        blocks = re.findall(r"<script[^>]*>(.*?)</script>", read(INDEX), re.S)
        self.assertTrue(blocks, "스크립트 블록을 못 찾았다")
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8",
                                         delete=False) as f:
            f.write(max(blocks, key=len))
            path = f.name
        try:
            p = subprocess.run([NODE, "--check", path], capture_output=True,
                               text=True, timeout=60)
            self.assertEqual(p.returncode, 0, p.stderr)
        finally:
            os.unlink(path)


class ServerContract(unittest.TestCase):
    """화면이 기대는 두 길이 서버에 있는가."""

    @classmethod
    def setUpClass(cls):
        cls.src = read(S9)

    def test_the_agent_stream_route_exists(self):
        self.assertIn('parsed.path == "/api/agentstream"', self.src)
        self.assertIn('parsed.path == "/api/agents"', self.src)

    def test_the_agent_stream_returns_an_offset_of_its_own(self):
        """에이전트 파일의 offset 은 그 파일의 것이다 — /api/stream 계약은 그대로."""
        m = re.search(r'parsed\.path == "/api/agentstream"[\s\S]{0,1400}', self.src)
        self.assertIn("parse_stream_file(apath, after)", m.group(0))
        m2 = re.search(r"def parse_stream_file\(path, after=0\):[\s\S]*?return \{[\s\S]*?\}",
                       self.src)
        self.assertIn('"offset": new_offset', m2.group(0))


class TheSilenceIsFilled(unittest.TestCase):
    """실서버 두 길로 침묵의 구간이 실제로 메워지는가 (통합).

    리드 파일에는 스폰 두 줄과 십 분 뒤 완료 한 줄뿐이고 그 사이는 0이다 —
    사용자가 본 그 화면. 같은 구간의 말이 에이전트 파일에 있고, 화면이 읽는
    두 길(/api/agents · /api/agentstream)로 그것이 온다.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.mkdtemp(prefix="s9subflow-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)

        def cli(*argv, env_extra=None):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env={**cls.env, **(env_extra or {})}, timeout=20,
                               stdin=subprocess.DEVNULL)
            if r.returncode:
                raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        cli("init")
        cli("user", "add", "tester")

        cls.sid = "livesess"
        # 세션 바인딩 — 이게 있어야 화면이 그 세션의 기록을 열 수 있다
        cli("log", "session start", env_extra={"S9_SESSION": cls.sid})
        cli("bind", "attach_pid", "1", env_extra={"S9_SESSION": cls.sid})
        apath = os.path.join(cls.tmp, "agent-adeadbeef.jsonl")
        os.makedirs(os.path.join(cls.tmp, "streams"), exist_ok=True)
        lead = [
            {"type": "assistant", "timestamp": "2026-08-29T10:00:00.000Z",
             "message": {"content": [
                 {"type": "text", "text": "designer 에게 맡긴다"},
                 {"type": "tool_use", "id": "tu1", "name": "Agent",
                  "input": {"subagent_type": "designer",
                            "description": "카드 손질"}}]}},
            {"type": "user", "timestamp": "2026-08-29T10:00:01.000Z",
             "message": {"content": [
                 {"type": "tool_result", "tool_use_id": "tu1",
                  "content": f"agentId: adeadbeef\noutput_file: {apath}"}]}},
            {"type": "assistant", "timestamp": "2026-08-29T10:10:00.000Z",
             "message": {"content": [{"type": "text", "text": "끝났다"}]}},
        ]
        with open(os.path.join(cls.tmp, "streams", f"{cls.sid}-full.jsonl"),
                  "w", encoding="utf-8") as f:
            for o in lead:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
        with open(apath, "w", encoding="utf-8") as f:
            for i, t in enumerate(("10:02:00", "10:05:00", "10:08:00")):
                f.write(json.dumps({
                    "type": "assistant", "isSidechain": True,
                    "timestamp": f"2026-08-29T{t}.000Z",
                    "message": {"content": [
                        {"type": "text", "text": f"에이전트 진행 {i}"}]}},
                    ensure_ascii=False) + "\n")

        from portpool import free_port, wait_server
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**cls.env, "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def api(cls, path):
        import urllib.request
        with urllib.request.urlopen(
                f"http://127.0.0.1:{cls.port}{path}", timeout=5) as r:
            return json.loads(r.read().decode())

    def test_the_gap_is_empty_in_the_lead_file_and_full_in_the_agent_file(self):
        lead = self.api(f"/api/stream?session={self.sid}")
        row = self.api(f"/api/agents?session={self.sid}")["agents"]
        self.assertEqual([a["id"] for a in row], ["adeadbeef"])
        self.assertEqual(row[0]["type"], "designer")
        sub = self.api(f"/api/agentstream?session={self.sid}&agent=adeadbeef")
        texts = [e["text"] for e in sub["events"]]
        self.assertEqual(texts, ["에이전트 진행 0", "에이전트 진행 1",
                                 "에이전트 진행 2"])
        lo, hi = sub["events"][0]["ts"], sub["events"][-1]["ts"]
        between = [e for e in lead["events"] if lo <= e["ts"] <= hi]
        self.assertEqual(between, [], "리드 파일에 그 구간의 말이 있었다면 "
                                      "이 문서의 전제가 틀린 것이다")
        self.assertTrue(lead["events"][0]["ts"] < lo,
                        "에이전트의 말은 스폰 뒤에 온다")
        self.assertTrue(lead["events"][-1]["ts"] > hi,
                        "완료 통지는 에이전트의 마지막 말 뒤에 온다")

    def test_the_agent_offset_is_its_own_and_increments(self):
        """두 번째 물음엔 새 줄이 없다 — 같은 줄을 두 번 세지 않는다."""
        first = self.api(f"/api/agentstream?session={self.sid}&agent=adeadbeef")
        self.assertGreater(first["offset"], 0)
        again = self.api(f"/api/agentstream?session={self.sid}"
                         f"&agent=adeadbeef&after={first['offset']}")
        self.assertEqual(again["events"], [])
        self.assertEqual(again["offset"], first["offset"])
        lead = self.api(f"/api/stream?session={self.sid}")
        self.assertNotEqual(lead["offset"], first["offset"],
                            "두 원천의 offset 이 우연히 같으면 이 시험이 "
                            "섞인 것을 못 본다 — 픽스처를 바꿔라")


if __name__ == "__main__":
    unittest.main(verbosity=2)
