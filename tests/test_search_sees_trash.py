"""찾기가 휴지통에 든 것도 본다 (REQ-20260915-093-62x6).

product-owner: 「한참 뒤 어디 갔지」 여정의 첫 행동은 Docs 검색인데 검색은
`.trash` 를 보지 않았다. 빈손이 되면 사람은 그 문서가 **없다**고 읽고 Settings
의 휴지통까지 가 볼 생각을 못 한다 — 버렸다는 것 자체를 잊었기 때문에 찾는다.

버린 것은 **뒤에** 세운다: 살아 있는 문서가 먼저이고, 휴지통 것은 「그래도
이런 게 있다」로 이어진다. 행에는 `trashed_doc` 표를 실어 화면이 그 사실과
되돌리는 손을 세울 수 있게 한다.

실행: python3 tests/ search_sees_trash
"""
import contextlib
import importlib.machinery
import importlib.util
import io as _io
import os
import shutil
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


class TheSearchLooksInTheTrashToo(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9search-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.environ["S9_ROOT"] = self.root
        self.addCleanup(os.environ.pop, "S9_ROOT", None)
        spec = importlib.util.spec_from_loader(
            "s9_search", importlib.machinery.SourceFileLoader("s9_search", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        with contextlib.redirect_stdout(_io.StringIO()):
            self.m.cmd_init(types.SimpleNamespace())

    def mk(self, title, body):
        args = types.SimpleNamespace(
            doc_type="request", title=title, summary="s", goal="g",
            status="open", size="S", priority=None, user=None, assignee=None,
            tag_list=[], parent=None, derived_from=None, relates=None, why="",
            ref_doc=None, ref_link=None, ref_file=None, needs_os=None,
            needs_machine="", any_machine=True, from_chat="", project=None,
            project_tag=None, body=body, body_file=None, origin="human",
            agent="", root=True)
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        return out.getvalue().split()[0].rstrip(":")

    def ids(self, d):
        return [r["id"] for r in d["results"]]

    # 사고의 본체 — 버린 문서가 검색에 안 나오던 자리
    def test_a_trashed_document_is_found(self):
        rid = self.mk("잃어버린 것", "깃발무늬 라는 낱말이 여기 있다")
        with contextlib.redirect_stdout(_io.StringIO()):
            self.m.do_rm(rid, "치운다")
        d = self.m.search_data("깃발무늬")
        self.assertIn(rid, self.ids(d), "버린 문서가 검색에서 안 나온다")
        self.assertEqual(1, d["trashed"])

    # 그 줄은 버린 것임을 말한다 — 화면이 표시와 손잡이를 세울 근거
    def test_the_row_says_it_is_in_the_trash(self):
        rid = self.mk("잃어버린 것", "깃발무늬")
        with contextlib.redirect_stdout(_io.StringIO()):
            self.m.do_rm(rid, "치운다")
        row = next(r for r in self.m.search_data("깃발무늬")["results"]
                   if r["id"] == rid)
        self.assertTrue(row.get("trashed_doc"), "버린 것이라는 표가 없다")
        self.assertTrue(row.get("matches"), "걸린 줄이 없다")

    # 차례 — 살아 있는 것이 먼저다
    def test_live_documents_come_first(self):
        gone = self.mk("버릴 것", "깃발무늬")
        with contextlib.redirect_stdout(_io.StringIO()):
            self.m.do_rm(gone, "치운다")
        live = self.mk("살아 있는 것", "깃발무늬")
        ids = self.ids(self.m.search_data("깃발무늬"))
        self.assertLess(ids.index(live), ids.index(gone),
                        "버린 것이 살아 있는 것보다 앞에 선다")

    # 경계 — 안 걸리는 낱말에는 아무것도 안 붙는다
    def test_nothing_is_added_when_it_does_not_match(self):
        rid = self.mk("버릴 것", "깃발무늬")
        with contextlib.redirect_stdout(_io.StringIO()):
            self.m.do_rm(rid, "치운다")
        d = self.m.search_data("없는낱말")
        self.assertEqual([], self.ids(d))
        self.assertEqual(0, d["trashed"])

    # 회귀 — 살아 있는 문서의 검색은 그대로다
    def test_a_live_document_is_still_found(self):
        rid = self.mk("살아 있는 것", "깃발무늬 가 여기")
        d = self.m.search_data("깃발무늬")
        self.assertEqual([rid], self.ids(d))
        self.assertEqual(0, d["trashed"])
        self.assertFalse(d["results"][0].get("trashed_doc"))

    def test_an_empty_query_finds_nothing(self):
        self.assertEqual([], self.m.search_data("  ")["results"])


if __name__ == "__main__":
    unittest.main()
