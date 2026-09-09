"""화면의 왕복 하나가 끊겨도 사람이 그것을 보지 않는다 (REQ-20260909-076-62x6).

이 머신의 WSL 루프백 중계는 윈도우 쪽 클라이언트가 응답을 기다리지 않고 끊으면
같은 포트의 **다른** 연결을 RST 한다 — 실서버에 붙은 연결의 30~55% 가 요청을 읽기
전에 끊겼다(REQ-20260909-067 실측). 화면 쪽 처방이 둘이고, 여기서 그 둘을 잰다:

  ① `s9Fetch`(web/app/net.js) — 멱등한 GET 은 다시 걸고, POST 는 응답이 온 실패에
     다시 걸지 않는다(상태 옮기기가 두 번 일어나면 안 된다).
  ② 세대 번호 · SSE 유예 — 진행 중인 요청을 끊는 대신 늦게 온 응답을 버린다.
     끊는 것 자체가 이 환경에서 다른 연결을 RST 하게 만들기 때문이다.

판정은 **동작을 잰다**: net.js 와 terminal.js 의 함수를 그대로 떼어 node 로 실행하고
가짜 fetch 의 호출 횟수를 센다 — 소스 글자를 대조하지 않는다.

실행: python3 tests/ net_retry
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web", "app")


def find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node",
                "/mnt/c/Temp/s9-webkit/node-*/node.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def _file(name):
    return open(os.path.join(WEB, name), encoding="utf-8").read()


def _src(fname, pat):
    m = re.search(pat, _file(fname), re.S | re.M)
    assert m, "%s 에서 %s 를 찾지 못했다" % (fname, pat)
    return m.group(0)


def run(js):
    node = find_node()
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


NET = None          # net.js 원본 (클래스 setUp 에서 한 번 읽는다)


def call(plan, url="/api/x", opts="undefined"):
    """가짜 서버 계획대로 응답하며 s9Fetch 를 부른다 → {calls, ok, status, body, threw}

    plan 은 시도마다의 답이다: {"throw": 1} 은 네트워크 오류(응답 없음),
    {"status": n, "body": "…"} 는 온 응답, {"cut": 1} 은 머리는 왔는데 본문에서 끊긴 것.
    """
    js = """
const PLAN = %s;
let calls = 0;
globalThis.fetch = async (u, o) => {
  const p = PLAN[Math.min(calls, PLAN.length - 1)];
  calls++;
  if (p.throw) throw new TypeError("Failed to fetch");
  const st = p.status === undefined ? 200 : p.status;
  return {
    ok: st >= 200 && st < 300, status: st, statusText: "", headers: null,
    url: u, redirected: false,
    text: async () => { if (p.cut) throw new TypeError("network error"); return p.body === undefined ? "{}" : p.body; },
  };
};
%s
(async () => {
  let out = {threw: false};
  try{
    const r = await s9Fetch(%s, %s);
    out.ok = r.ok; out.status = r.status; out.body = await r.text();
  }catch(e){ out.threw = true; out.err = String(e && e.message || e); }
  out.calls = calls;
  console.log(JSON.stringify(out));
})();
""" % (json.dumps(plan), NET, json.dumps(url), opts)
    return run(js)


@unittest.skipUnless(find_node(), "node 가 없다")
class TheScreenAbsorbsOneLostRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global NET
        NET = _file("net.js")

    def test_net_retry(self):
        """s9Fetch 의 계약을 한 항목으로 — 검사는 아래 갈래마다다."""
        with self.subTest("s1_ok_goes_straight_through"):
            r = call([{"status": 200, "body": '{"a":1}'}])
            self.assertEqual(r["calls"], 1, "성공한 것을 다시 걸었다")
            self.assertTrue(r["ok"])
            self.assertEqual(r["body"], '{"a":1}')

        with self.subTest("s2_get_retries_a_network_error"):
            r = call([{"throw": 1}, {"throw": 1}, {"status": 200, "body": '{"a":2}'}])
            self.assertEqual(r["calls"], 3, "GET 이 두 번까지 다시 걸지 않는다")
            self.assertFalse(r["threw"])
            self.assertEqual(r["body"], '{"a":2}')

        with self.subTest("s2b_get_gives_up_after_two_retries"):
            r = call([{"throw": 1}])
            self.assertEqual(r["calls"], 3, "끝없이 다시 건다")
            self.assertTrue(r["threw"], "끝내 못 받은 것을 성공으로 돌려준다")

        with self.subTest("s3_empty_body_and_502_are_not_an_answer"):
            r = call([{"status": 200, "body": ""}, {"status": 200, "body": '{"a":3}'}])
            self.assertEqual(r["calls"], 2, "빈 응답을 받은 것으로 친다")
            self.assertEqual(r["body"], '{"a":3}')
            r = call([{"status": 502, "body": "bad gateway"},
                      {"status": 200, "body": '{"a":4}'}])
            self.assertEqual(r["calls"], 2, "502 를 받은 것으로 친다")
            self.assertEqual(r["body"], '{"a":4}')

        with self.subTest("s3b_a_cut_body_is_refetched"):
            r = call([{"cut": 1}, {"status": 200, "body": '{"a":5}'}])
            self.assertEqual(r["calls"], 2, "본문에서 끊긴 GET 을 다시 걸지 않는다")
            self.assertEqual(r["body"], '{"a":5}')

        with self.subTest("s4_post_does_not_repeat_a_real_failure"):
            r = call([{"status": 500, "body": "no"}], opts='{method:"POST"}')
            self.assertEqual(r["calls"], 1, "POST 를 다시 걸었다 — 두 번 실행될 수 있다")
            self.assertEqual(r["status"], 500)
            r = call([{"status": 200, "body": ""}], opts='{method:"POST"}')
            self.assertEqual(r["calls"], 1, "POST 를 빈 응답으로 다시 걸었다")

        with self.subTest("s5_post_retries_once_when_nothing_answered"):
            r = call([{"throw": 1}, {"status": 200, "body": '{"ok":1}'}],
                     opts='{method:"POST"}')
            self.assertEqual(r["calls"], 2, "닿지도 못한 POST 를 한 번은 다시 걸어야 한다")
            self.assertFalse(r["threw"])
            r = call([{"throw": 1}], opts='{method:"POST"}')
            self.assertEqual(r["calls"], 2, "POST 를 두 번 넘게 다시 걸었다")
            self.assertTrue(r["threw"])

        with self.subTest("s5b_a_cut_post_is_not_repeated"):
            # 응답이 오다 끊긴 POST 는 서버가 이미 받아 실행한 것이다.
            r = call([{"cut": 1}, {"status": 200, "body": "{}"}], opts='{method:"POST"}')
            self.assertEqual(r["calls"], 1, "이미 실행된 POST 를 다시 걸었다")
            self.assertTrue(r["threw"])

    def test_generation_drops_the_late_answer(self):
        """S6 세대: 떠난 뒤 늦게 온 응답은 버리고, 최신 세대는 그린다."""
        js = (NET + "\nconst a = s9Gen('t'); const b = s9Gen('t');\n"
              "console.log(JSON.stringify({old: s9GenStale('t', a),"
              " now: s9GenStale('t', b), other: s9GenStale('u', 1)}));")
        r = run(js)
        self.assertTrue(r["old"], "지난 세대의 응답을 그대로 그린다")
        self.assertFalse(r["now"], "최신 세대의 응답까지 버린다")
        self.assertTrue(r["other"], "부르지도 않은 이름이 최신으로 잡힌다")

    def test_a_short_tab_switch_keeps_the_connection(self):
        """S7 취소 줄이기: 잠깐 떠난 것으로 EventSource 를 끊지 않는다."""
        fn = _src("terminal.js", r"^function termVisibility\(T, hidden\)\{.*?^\}$")
        idle = _src("terminal.js", r"^const TERM_SSE_IDLE_MS = \d+;$")
        js = """
let closed = 0, opened = 0;
let document = {hidden: false};
function termCloseSSE(T){ closed++; T.es = null; }
function termConnectSSE(T){ opened++; T.es = {}; }
%s
%s
const T = {es: {}, poll: false};
document.hidden = true;  termVisibility(T, true);    // 다른 창을 본다
document.hidden = false; termVisibility(T, false);   // 곧 돌아온다
setTimeout(() => console.log(JSON.stringify(
  {closed, opened, idle: TERM_SSE_IDLE_MS, timer: !!T.esIdleT})), 20);
""" % (idle, fn)
        r = run(js)
        self.assertEqual(r["closed"], 0, "탭을 잠깐 옮긴 것으로 연결을 끊는다")
        self.assertEqual(r["opened"], 0, "끊지도 않았는데 다시 연다")
        self.assertFalse(r["timer"], "돌아왔는데 반납 시한이 남아 있다")
        self.assertGreaterEqual(r["idle"], 10000, "유예가 짧아 탭 전환마다 끊는다")

    def test_a_long_absence_gives_the_connection_back(self):
        """S7b 경계: 오래 떠나 있으면 반납한다 — 서버 슬롯을 물고 있지 않는다."""
        fn = _src("terminal.js", r"^function termVisibility\(T, hidden\)\{.*?^\}$")
        js = """
let closed = 0, opened = 0;
let document = {hidden: true};
function termCloseSSE(T){ closed++; T.es = null; }
function termConnectSSE(T){ opened++; T.es = {}; }
const TERM_SSE_IDLE_MS = 30;   // 시험에서만 짧게 — 유예의 길이가 아니라 반납을 잰다
%s
const T = {es: {}, poll: false};
termVisibility(T, true);
setTimeout(() => console.log(JSON.stringify({closed, opened})), 80);
""" % fn
        r = run(js)
        self.assertEqual(r["closed"], 1, "오래 떠나 있어도 연결을 안 놓는다")


if __name__ == "__main__":
    unittest.main()
