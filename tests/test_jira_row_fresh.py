"""문서 판의 Jira 행은 방금 받은 문서 메타를 따른다 (REQ-20260909-047).

맥 Safari 실측(2026-09-09 11:55): 「이슈 잇기」·「끊기」 뒤 서버는 바뀌었는데 열려 있는
판의 Jira 행은 다시 열어야 바뀌었다. 행이 카탈로그 줄(rec.jira)을 문서 메타(m.jira)보다
앞세웠고, 판을 다시 그리는 reloadShowing 이 카탈로그 갱신보다 먼저 돌아 옛 값이 남았다.
여기서는 그 함수를 node 로 **실행해** 무엇을 그리는지 잰다 — 글자를 세지 않는다.

실행: python3 tests/ jira_row_fresh
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def _node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    import glob
    for pat in ("/home/*/.vscode-server/bin/*/node", "/root/.vscode-server/bin/*/node"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def _fn(src, name):
    m = re.search(r"\nfunction %s\([^)]*\)\{[\s\S]*?\n\}" % name, src)
    assert m, name
    return m.group(0)


PRELUDE = r"""
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const prjAgo = () => "방금";
const TERMINAL = new Set(["done", "cancelled"]);
globalThis.window = {__whoami: {role: "admin"}, __projects: [{slug: "p", jira: {project_key: "MP1"}}]};
"""


@unittest.skipUnless(_node(), "node 없음 — 실행 검증 생략")
class TheRowFollowsTheDocument(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 시험 자신이 실행할 함수를 떠 오는 자리 — 글자를 단정하지 않고 node 로 돌린다.
        path = os.path.join(HERE, "..", "web", "app", "docs.js")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        cls.code = PRELUDE + _fn(src, "docJiraLive") + "\n" + _fn(src, "docJiraRowHTML") + "\n"

    def render(self, m, rec):
        js = self.code + "process.stdout.write(JSON.stringify(docJiraRowHTML(%s, %s)));" % (
            json.dumps(m, ensure_ascii=False), json.dumps(rec, ensure_ascii=False))
        d = tempfile.mkdtemp(prefix="s9-jrow-")
        try:
            p = os.path.join(d, "t.js")
            with open(p, "w", encoding="utf-8") as f:
                f.write(js)
            r = subprocess.run([_node(), p], capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr[-1500:])
            return json.loads(r.stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    M = {"id": "REQ-1", "type": "request", "status": "open", "project": "p"}

    def test_f1_linked_meta_beats_a_stale_catalog_row(self):
        """잇기 직후 — 카탈로그는 아직 빈 값, 메타에는 키. 행은 키와 「끊기」다."""
        html = self.render(dict(self.M, jira={"key": "MP1-9", "url": "u", "status": "완료"}),
                           {"id": "REQ-1", "jira": {}})
        self.assertIn("MP1-9", html)
        self.assertIn("끊기", html)
        self.assertNotIn("이슈 잇기", html)

    def test_f2_an_empty_meta_block_is_a_value(self):
        """끊은 직후 — 메타 jira={} · 카탈로그에는 옛 키. 행은 「이슈 잇기」다."""
        html = self.render(dict(self.M, jira={}),
                           {"id": "REQ-1", "jira": {"key": "MP1-9", "status": "완료"}})
        self.assertIn("이슈 잇기", html)
        self.assertNotIn("MP1-9", html)

    def test_f3_without_meta_the_catalog_row_still_serves(self):
        """회귀 — 메타에 jira 가 없으면 카탈로그 줄을 쓴다."""
        html = self.render(dict(self.M), {"id": "REQ-1", "jira": {"key": "MP1-3", "status": "해야 할 일"}})
        self.assertIn("MP1-3", html)


if __name__ == "__main__":
    unittest.main()
