"""좁은 카탈로그가 넓은 목록을 덮지 않는다 (REQ-20260907-066-62x6).

사용자가 본 것: Board 에 갔다 Docs 로 돌아온 **첫 그림**에서 목록이 405장으로
서고, 15초 뒤 다음 폴에 1306장으로 늘었다 — 문서가 줄었다가 되돌아오는 것처럼
보인다.

까닭은 창(window)이다. 보드는 카탈로그를 좁혀 받는다(열린 일 전부 + 최근 닫힌
것). 그 좁은 응답이 손에 든 넓은 판을 **덮어써서** 화면이 짧아졌다. 좁은 응답은
전량의 부분집합이므로, 덮지 말고 합치면 목록은 짧아지지 않는다.

판정은 정규식으로 짐작하지 않고 `app.js` 의 `mergeNarrow` 를 떼어 node 로 실행한다.

실행: python3 tests/ docs_catalog_merge
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
    """node 를 찾는다 — 없으면 이 시험은 건너뛴다.

    다른 시험 모듈에서 가져오지 않는다: 시험 파일은 표준 라이브러리 밖을
    import 하지 않는다(tests/test_stdlib_only.py). 시험끼리 엮이면 한 파일의
    이름을 바꾸는 것이 남의 파일을 깨뜨린다."""
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


def merge_src():
    src = open(os.path.join(WEB, "app.js"), encoding="utf-8").read()
    m = re.search(r"^function mergeNarrow\(rows\)\{.*?^\}", src, re.S | re.M)
    assert m, "app.js 에서 mergeNarrow 를 찾지 못했다"
    return m.group(0)


def run(catalog, catalog_all, rows):
    """mergeNarrow(rows) 를 실행해 합쳐진 목록의 id 순서를 돌려준다."""
    js = ("let catalog = %s, catalogAll = %s;\n%s\n"
          "console.log(JSON.stringify(mergeNarrow(%s).map(r => r.id)));"
          % (json.dumps(catalog), "true" if catalog_all else "false",
             merge_src(), json.dumps(rows)))
    out = subprocess.run([find_node(), "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def rowset(*ids):
    return [{"id": i, "updated": "u"} for i in ids]


@unittest.skipUnless(find_node(), "node 없음")
class CatalogMerge(unittest.TestCase):
    def test_s1_narrow_does_not_shrink(self):
        """S1 — 좁은 응답이 넓은 판을 덮지 않는다: 수가 줄지 않고 내용은 갱신된다"""
        wide = rowset(*["D%d" % i for i in range(6)])
        narrow = [{"id": "D0", "updated": "새것"}, {"id": "D1", "updated": "u"}]
        got = run(wide, True, narrow)
        self.assertEqual(got, ["D%d" % i for i in range(6)])   # 자리도 그대로
        js = ("let catalog = %s, catalogAll = true;\n%s\n"
              "console.log(mergeNarrow(%s)[0].updated);"
              % (json.dumps(wide), merge_src(), json.dumps(narrow)))
        out = subprocess.run([find_node(), "-e", js], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "새것")   # 내용은 새 응답의 것

    def test_s2_first_full_answer_stands_alone(self):
        """S2 — 전량을 받아 본 적이 없으면 합치지 않는다(수가 부풀지 않는다)"""
        self.assertEqual(run(rowset("A", "B"), False, rowset("C")), ["C"])

    def test_s3_truly_new_doc_goes_on_top(self):
        """S3 — 이번 응답에만 있는 문서(정말 새것)는 맨 위에 선다"""
        self.assertEqual(run(rowset("A", "B"), True, rowset("N", "A")),
                         ["N", "A", "B"])


if __name__ == "__main__":
    unittest.main()
