"""늦은 응답 판정이 판을 영영 비워 두지 않는다 (REQ-20260908-003-62x6).

실측 재현(Playwright, 2026-09-08): 문서 요청이 15초 폴보다 느리면 매 폴이 앞
세대를 물리고 제 응답도 다음 폴에 물려, 85초 동안 세대 1~6 이 **전부 버려졌다**.
목록은 66줄로 살아 있고 고른 표시도 섰는데 오른쪽 판만 「문서를 불러오는 중…」에
갇힌다 — 주인이 본 화면이 그것이다.

판정은 `state.js` 의 `docLoadStale` 과 `docs.js` 의 `docFailHTML` 을 떼어 node 로
실행한다 — 소스 글자를 대조하지 않는다.

실행: python3 tests/ doc_load_gen
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


def _src(fname, pat):
    src = open(os.path.join(WEB, fname), encoding="utf-8").read()
    m = re.search(pat, src, re.S | re.M)
    assert m, "%s 에서 %s 를 찾지 못했다" % (fname, pat)
    return m.group(0)


def run(js):
    node = find_node()
    out = subprocess.run([node, "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def stale(gen, cur_gen, id_, selected, showing):
    """docLoadStale 을 그 자리의 사실로 부른다 — 버리면 True."""
    js = ("let docLoadGen = %d;\nlet selectedDoc = %s;\n%s\n"
          "console.log(JSON.stringify(docLoadStale(%d, %s, %s)));"
          % (cur_gen, json.dumps(selected),
             _src("state.js", r"^function docLoadStale\(gen, id, viewer\)\{.*?^\}$"),
             gen, json.dumps(id_),
             "{dataset:{showing:%s}}" % json.dumps(showing) if showing is not None else "null"))
    return json.loads(run(js))


@unittest.skipUnless(find_node(), "node 가 없다")
class TheLateAnswerStillFillsTheEmptyPane(unittest.TestCase):
    ID = "REQ-20260907-088-62x6"

    def test_s1_my_turn_draws(self):
        """S1 정상: 아직 내 세대면 그린다."""
        self.assertFalse(stale(3, 3, self.ID, self.ID, ""))

    def test_s2_late_answer_fills_empty_pane(self):
        """S2 회귀(이 사고): 세대가 지났어도 같은 문서이고 판이 비었으면 그린다."""
        self.assertFalse(stale(1, 6, self.ID, self.ID, ""))

    def test_s3_other_doc_is_dropped(self):
        """S3 실패 경로(REQ-20260907-067): 다른 문서를 열었으면 버린다."""
        self.assertTrue(stale(1, 2, self.ID, "QST-20260907-016-62x6", ""))

    def test_s4_same_doc_already_standing_is_dropped(self):
        """S4 경계: 그 문서가 이미 판에 서 있으면 옛 응답으로 덮지 않는다."""
        self.assertTrue(stale(1, 2, self.ID, self.ID, self.ID))

    def test_s5_no_pane_is_dropped(self):
        """S5 경계: 그릴 판이 없으면 버린다(고른 것도 없는 자리)."""
        self.assertTrue(stale(1, 2, self.ID, None, None))

    def test_s6_the_wait_ends_with_a_handle(self):
        """S6 실패 자리: 못 받았다는 말에 다시 받는 손잡이가 함께 선다."""
        js = ("const esc = s => String(s);\n%s\nconsole.log(docFailHTML('%s'));"
              % (_src("docs.js", r"^const docFailHTML = id =>.*?;$"), self.ID))
        html = run(js)
        self.assertIn("다시 받기", html)
        self.assertIn('data-retrydoc="%s"' % self.ID, html)
        self.assertIn("문서를 열지 못했습니다", html)


if __name__ == "__main__":
    unittest.main()
