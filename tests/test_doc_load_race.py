"""늦은 응답은 방금 연 문서를 덮지 않는다 (REQ-20260907-067).

loadDoc 은 서버 왕복을 두 번까지 기다린다(실패 시 800ms 뒤 재시도). 그 사이
사람이 다른 문서를 열면 먼저 시작한 요청의 늦은 응답이 나중에 도착해 방금 연
문서를 덮어썼다 — 목록은 새 문서를 골라 표시했는데 판은 이전 문서였다.

계약은 세대 표식 둘(`docLoadStart`·`docLoadStale`)에 있다 — state.js 의 그
조각을 node 로 **실행**해 잰다(소스 글자 대조 아님). loadDoc 이 그것을 세 자리
(재시도 대기 뒤·응답 뒤·본문 파싱 뒤)에서 묻는지는 한 번 부르는지로만 본다.

실행: python3 tests/ doc_load_race
"""
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 소스는 준비 삼아 **한 번만** 읽는다 — 그 뒤로는 이 문자열을 돌린다
# (DOC-20260907-002: 글자를 몇 번이고 대조하는 파일이 아니다).
STATE_SRC = open(os.path.join(HERE, "..", "web", "app", "state.js"), encoding="utf-8").read()
DOCS_SRC = open(os.path.join(HERE, "..", "web", "app", "docs.js"), encoding="utf-8").read()

import glob
import shutil


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


def _slice(src, start_pat):
    i = src.index(start_pat)
    return src[i:]


class Generation(unittest.TestCase):
    @unittest.skipUnless(NODE, "node 가 없다 — 이 판에서는 실행 시험을 못 돈다")
    def test_a_newer_open_makes_the_older_one_stale(self):
        piece = _slice(STATE_SRC, "let docLoadGen = 0;")
        driver = piece + r"""
const out = [];
const g1 = docLoadStart();              // 사람이 066 을 연다 (응답 대기 중)
out.push(["g1_fresh_alone", !docLoadStale(g1)]);
const g2 = docLoadStart();              // 그 사이 016 을 연다
out.push(["g1_now_stale", docLoadStale(g1)]);   // 066 의 늦은 응답은 버려야 한다
out.push(["g2_fresh", !docLoadStale(g2)]);       // 016 은 아직 내 차례다
const g3 = docLoadStart();
out.push(["g2_then_stale", docLoadStale(g2)]);
out.push(["only_latest", !docLoadStale(g3)]);
console.log(JSON.stringify(out));
"""
        r = subprocess.run([NODE, "-e", driver], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        import json as _j
        got = dict(_j.loads(r.stdout.strip()))
        self.assertTrue(got["g1_fresh_alone"])
        self.assertTrue(got["g1_now_stale"], "먼저 시작한 열기가 뒤의 열기에 밀리지 않았다")
        self.assertTrue(got["g2_fresh"])
        self.assertTrue(got["g2_then_stale"])
        self.assertTrue(got["only_latest"])


class LoadDocAsksAtEveryWait(unittest.TestCase):
    def test_the_guard_is_asked_after_each_await(self):
        """기다림이 끝날 때마다 묻는다 — 한 자리만 물으면 그 사이 창이 남는다."""
        body = DOCS_SRC[DOCS_SRC.index("async function loadDoc("):]
        body = body[:body.index("\n}\n")]
        self.assertIn("docLoadStart()", body, "세대 표를 받지 않는다")
        self.assertGreaterEqual(body.count("docLoadStale(gen)"), 3,
                                "재시도 대기 뒤·응답 뒤·본문 파싱 뒤 세 자리에서 물어야 한다")


if __name__ == "__main__":
    unittest.main()
