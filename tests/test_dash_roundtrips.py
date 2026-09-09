"""탭을 옮겼다고 같은 것을 다시 받지 않는다 (REQ-20260909-086-62x6).

이 환경의 WSL 루프백 중계는 요청의 30~50% 를 끊고, 재시도가 그것을 메우느라 왕복
하나에 0.2~0.6초가 붙는다(REQ-20260909-067·076). 그러니 체감을 정하는 것은 서버의
계산이 아니라 **왕복의 수**다. 실측(2026-09-09, Chrome/Playwright): 탭을 여섯 번
옮기는 동안 /api/catalog 가 다섯 번·/api/projects 가 여섯 번 갔고, 다른 탭으로
옮겨 둔 대시보드가 20초 동안 문서 목록·색인·본문 넷을 더 받아 갔다.

처방 둘을 여기서 잰다:
  ① 신선도 장부(web/app/net.js `s9Keep`/`s9Fresh`) — 방금 받은 자료는 다시 받지
     않는다. 다만 **창이 다르면**(보드 창 ↔ 전량) 신선해도 다시 받는다.
  ② 안 보이는 화면은 묻지 않는다(`s9Every`) — 그리고 돌아왔을 때 **한 번만** 돈다.

판정은 동작을 잰다: 함수를 그대로 떼어 node 로 실행하고 호출 횟수를 센다 —
소스 글자를 대조하지 않는다.

실행: python3 tests/ dash_roundtrips
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


def _fn(fname, name):
    """이름으로 함수 하나를 떼어 온다 — 중괄호를 세어 끝을 찾는다."""
    src = _file(fname)
    m = re.search(r"^function %s\s*\(" % re.escape(name), src, re.M)
    assert m, "%s 에서 %s 를 찾지 못했다" % (fname, name)
    i = src.index("{", m.end() - 1)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
    raise AssertionError("%s 의 %s 가 안 닫힌다" % (fname, name))


def _const(fname, name):
    """`const 이름 = 값;` 한 줄 — 값을 시험에 베끼지 않고 원본을 쓴다."""
    m = re.search(r"^const %s\s*=\s*[^;]+;" % re.escape(name), _file(fname), re.M)
    assert m, "%s 에서 %s 를 찾지 못했다" % (fname, name)
    return m.group(0)


def run(js):
    node = find_node()
    out = subprocess.run([node, "-e", js], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@unittest.skipUnless(find_node(), "node 가 없다")
class TheScreenDoesNotAskTwiceForTheSameThing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = _file("net.js")
        cls.wants = _fn("app.js", "catalogWantsAll")
        cls.fresh = _const("app.js", "CATALOG_TTL") + "\n" + _fn("app.js", "catalogFresh")

    def ledger(self, body, hidden="false"):
        """신선도 장부 + catalogFresh 를 실제로 실행한다."""
        js = """
globalThis.document = {hidden: %s, addEventListener(){}, getElementById: () => null};
globalThis.location = {hash: "#board", search: ""};
let tab = "board", selectedDoc = null, catalog = [], catalogAll = false;
%s
%s
%s
const out = {};
%s
console.log(JSON.stringify(out));
""" % (hidden, self.net, self.wants, self.fresh, body)
        return run(js)

    def test_fresh_ledger(self):
        """받은 시각을 적어 두면 그 안의 물음은 왕복을 내지 않는다."""
        with self.subTest("s1_fresh_is_reused"):
            r = self.ledger("""
catalog = [{id: "a"}]; catalogAll = true;
s9Keep("catalog:got", true);
out.fresh = catalogFresh();
""")
            self.assertTrue(r["fresh"], "방금 받은 목록을 낡았다고 판정했다")

        with self.subTest("s2_stale_after_ttl"):
            # CATALOG_TTL 을 넘긴 자리 — 장부의 시각을 과거로 밀어 잰다
            r = self.ledger("""
catalog = [{id: "a"}]; catalogAll = true;
s9Keep("catalog:got", true);
S9_FRESH.get("catalog:got").at -= 60000;
out.fresh = catalogFresh();
""")
            self.assertFalse(r["fresh"], "한참 지난 목록을 신선하다고 판정했다")

        with self.subTest("s2b_never_fetched_is_not_fresh"):
            r = self.ledger("""
catalog = [{id: "a"}]; catalogAll = true;
out.fresh = catalogFresh();
""")
            self.assertFalse(r["fresh"], "받은 적 없는 목록을 신선하다고 판정했다")

        with self.subTest("s3_narrow_window_is_not_fresh_for_a_wide_screen"):
            r = self.ledger("""
catalog = [{id: "a"}]; catalogAll = false;   // 보드 창만 받아 봤다
s9Keep("catalog:got", false);
out.board = catalogFresh();
location.hash = "#docs";                     // 전량이 필요한 화면
out.docs = catalogFresh();
""")
            self.assertTrue(r["board"], "보드 창은 보드 화면에 신선하다")
            self.assertFalse(r["docs"],
                             "좁은 판을 신선하다는 이유로 넓은 화면에 썼다")

        with self.subTest("s3b_stale_clears_the_line"):
            r = self.ledger("""
catalog = [{id: "a"}]; catalogAll = true;
s9Keep("catalog:got", true);
s9Stale("catalog:got");
out.fresh = catalogFresh();
""")
            self.assertFalse(r["fresh"], "지운 줄이 남아 있다")

    def test_hidden_screen_asks_nothing(self):
        """안 보이는 화면은 폴을 돌리지 않고, 돌아오면 한 번만 돈다."""
        js = """
const H = {};
globalThis.document = {
  hidden: true,
  addEventListener(name, fn){ H[name] = fn; },
};
%s
let n = 0;
s9Every("probe", 10, () => { n++; });
const out = {};
setTimeout(() => {
  out.hidden = n;                    // 안 보이는 동안의 왕복
  document.hidden = false;
  H["visibilitychange"]();           // 돌아왔다
  out.resumed = n;                   // 몰아 돌지 않고 한 번
  setTimeout(() => {
    out.after = n;                   // 그 뒤로는 제 주기대로
    console.log(JSON.stringify(out));
    process.exit(0);
  }, 45);
}, 80);
""" % self.net
        r = run(js)
        with self.subTest("s4_hidden_polls_nothing"):
            self.assertEqual(r["hidden"], 0,
                             "안 보이는 화면이 %d번 물었다" % r["hidden"])
        with self.subTest("s5_resume_runs_once"):
            self.assertEqual(r["resumed"], 1,
                             "돌아온 순간 %d번 몰아 돌았다" % r["resumed"])
        with self.subTest("s5b_belt_keeps_running"):
            self.assertGreater(r["after"], r["resumed"],
                               "다시 보이는데도 벨트가 멈춰 있다")


if __name__ == "__main__":
    unittest.main()
