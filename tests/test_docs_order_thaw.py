"""오래 연 목록의 순서가 낡으면 화면이 그 사실을 말한다 (REQ-20260907-058-62x6).

사용자: "문서 목록 순서가 또 뭔가 이상해진듯한데.."

정렬은 맞았다. 어긋난 것은 **얼린 순서**다 — 목록은 읽는 동안 자리를 잡아 두는데
(REQ-20260828-009), 한 화면을 열어 둔 채 문서 스무 건이 넘게 바뀌자 새로 생긴
문서만 맨 위에 서고 글이 붙은 문서는 옛 자리에 머물러 둘이 섞였다.

얼림은 없애지 않는다 — 읽던 줄이 발밑에서 튀는 것을 막는 장치이고 그 목적은
그대로 옳다. 여기서 잠그는 것은 **나가는 문**이다: 얼마나 낡았는지를 세고, 문턱
(세 건 = 얼림이 전제한 "두어 건"을 넘는 순간)을 넘을 때만 말하고, 사람이 녹이면
지금 순서로 다시 선다.

판정은 정규식으로 짐작하지 않고 `state.js` 의 정렬 조각을 떼어 node 로 **실행**한다.

실행: python3 tests/ docs_order_thaw
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


NODE = find_node()

DRIVER = r"""
const out = [];
const rows = ids => ids.map(([id, updated]) => ({id, type: "request", updated}));
// 얼린다 → 그 뒤의 배경 갱신은 조건도 화면도 그대로다(refreeze=false)
const freeze = rs => stableOrder(rs, "k", true);
const poll = rs => stableOrder(rs, "k", false);
// `updated` 는 ISO 문자열이라 글자 순으로 비교된다 — 자릿수를 맞춰 둔다
const base = rows([["A", "90"], ["B", "80"], ["C", "70"], ["D", "60"], ["E", "50"]]);
const hit  = rows([["A", "90"], ["B", "99"], ["C", "98"], ["D", "97"], ["E", "50"]]);

// S1 · S6: 세 건에 글이 붙어도 순서는 그대로이고, 셈만 3 이 된다
freeze(base);
let o = poll(hit);
out.push(["S1_count", docStale], ["S1_shown", docStaleCount()]);
out.push(["S6_order", o.map(r => r.id).join("")]);

// S2: 두 건이면 셈은 있어도 화면에 내지 않는다 — 얼림이 전제한 자리다
freeze(base);
poll(rows([["A", "90"], ["B", "80"], ["C", "98"], ["D", "97"], ["E", "50"]]));
out.push(["S2_count", docStale], ["S2_shown", docStaleCount()]);

// S8: 목록이 **넓어져** 돌아온 옛 문서는 제 자리에 끼인다 (REQ-20260907-058 재작업).
//     Board 로 갔다 오면 카탈로그를 좁혀 받은 405장으로 순서가 얼고, 곧이어 온
//     폴이 전량을 준다. 그때 돌아온 옛 문서를 "새 문서"로 보고 맨 위에 세우면
//     오늘 것 위에 옛것이 앉는다 — 사용자가 본 그 화면이다.
freeze(rows([["A", "90"], ["B", "80"]]));            // 좁게 받은 목록으로 얼었다
o = poll(rows([["A", "90"], ["B", "80"], ["P", "85"], ["Q", "70"], ["R", "99"]]));
out.push(["S8_order", o.map(r => r.id).join("")]);   // R 만 맨 위, P·Q 는 제 자리
out.push(["S8_count", docStale]);                    // 끼워 넣기는 낡음이 아니다

// S3: 얼린 뒤 새로 온 문서는 이미 맨 위에 선다 — 낡음으로 세지 않는다
freeze(base);
o = poll(base.concat(rows([["X", "91"], ["Y", "92"], ["Z", "93"]])));
out.push(["S3_count", docStale]);
out.push(["S3_order", o.map(r => r.id).join("")]);

// S4: 맨 위 문서에 글이 붙어도 자리가 그대로면 세지 않는다
freeze(base);
poll(rows([["A", "99"], ["B", "80"], ["C", "70"], ["D", "60"], ["E", "50"]]));
out.push(["S4_count", docStale]);

// S5: 사람이 녹이면 지금 순서로 다시 서고 셈이 0 으로 돌아간다
freeze(base);
poll(hit);
thawDocOrder();
o = poll(hit);
out.push(["S5_order", o.map(r => r.id).join("")], ["S5_count", docStale]);
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, "node 가 없다 — 실행 판정을 못 한다")
class DocsOrderThaw(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(WEB, "state.js"), encoding="utf-8") as f:
            src = f.read()
        m = re.search(r"const upd = r =>.*?function thawDocOrder\(\)\{[^}]*\}",
                      src, re.S)
        assert m, "정렬 조각(upd~thawDocOrder)을 못 찾았다 — 이름이 바뀌었으면 이 시험도 따라가야 한다"
        r = subprocess.run([NODE, "-e", m.group(0) + DRIVER],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        cls.got = dict(json.loads(r.stdout))

    def test_s1_three_changed_is_told(self):
        """S1 — 얼린 뒤 세 건에 글이 붙으면 그 셋을 세어 말한다"""
        self.assertEqual(self.got["S1_count"], 3)
        self.assertEqual(self.got["S1_shown"], 3)

    def test_s2_two_changed_stays_quiet(self):
        """S2 — 두 건은 얼림이 전제한 자리라 말하지 않는다"""
        self.assertEqual(self.got["S2_count"], 2)
        self.assertEqual(self.got["S2_shown"], 0)

    # S8. 넓어져 돌아온 옛 문서는 제 자리에 끼인다 (REQ-20260907-058 재작업)
    def test_s8_widened_list_keeps_places(self):
        # R(99)만 맨 위 · P(85)는 A(90)와 B(80) 사이 · Q(70)는 맨 뒤
        self.assertEqual(self.got["S8_order"], "RAPBQ",
                         "목록이 넓어지자 옛 문서가 오늘 것 위로 올라갔다 — "
                         "사용자가 본 '순서가 제멋대로 바뀐다'가 이것이다")
        self.assertEqual(self.got["S8_count"], 0)

    def test_s3_new_docs_are_not_stale(self):
        """S3 — 새로 온 문서는 맨 위에 서므로 낡음이 아니다"""
        self.assertEqual(self.got["S3_count"], 0)
        self.assertEqual(self.got["S3_order"], "ZYXABCDE")

    def test_s4_changed_but_not_moved(self):
        """S4 — 글이 붙어도 자리가 그대로면 세지 않는다"""
        self.assertEqual(self.got["S4_count"], 0)

    def test_s5_thaw_restores_now_order(self):
        """S5 — 녹이면 지금 순서로 다시 서고 셈이 0 이 된다"""
        self.assertEqual(self.got["S5_order"], "BCDAE")
        self.assertEqual(self.got["S5_count"], 0)

    def test_s6_freeze_still_holds(self):
        """S6 — 누르기 전에는 배경 갱신이 순서를 바꾸지 않는다 (REQ-20260828-009)"""
        self.assertEqual(self.got["S6_order"], "ABCDE")
