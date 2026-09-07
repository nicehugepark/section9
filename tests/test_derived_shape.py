"""derived_from 은 하나든 여럿이든 같은 뜻으로 읽힌다 (REQ-20260907-075-62x6).

사용자가 본 것: 「Graph 탭이 열리지 않는다.」 서버는 `/api/graph` 에서
`TypeError: unhashable type: 'list'` 로 끊겼다 — 흡수(open→done)가 여럿을 적어
`derived_from` 이 목록인 문서가 하나 생겼는데, 읽는 자리들은 문자열 하나를
가정하고 그 값을 그대로 집합에 물었다.

쓰는 자리가 둘이면 모양도 둘이다. 읽는 자리마다 모양을 가르면 언젠가 한 곳을
빠뜨리고, 그날 화면 하나가 통째로 죽는다. 그래서 가르는 자리를 하나로 모았다
(`derived_ids`). 이 파일은 그 한 자리와, 그것을 쓰는 그래프를 잰다.

실행: python3 tests/ derived_shape
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")

spec = importlib.util.spec_from_loader(
    "s9_derived", importlib.machinery.SourceFileLoader("s9_derived", S9))
s9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s9)


class TheShapeIsReadInOnePlace(unittest.TestCase):

    def test_one_id_as_text(self):
        """정상 — new·set 이 쓰는 문자열 하나."""
        self.assertEqual(s9.derived_ids({"derived_from": "REQ-1"}), ["REQ-1"])

    def test_several_ids_as_a_list(self):
        """정상 — 흡수가 쓰는 목록."""
        self.assertEqual(s9.derived_ids({"derived_from": ["REQ-1", "REQ-2"]}),
                         ["REQ-1", "REQ-2"])

    def test_nothing_is_an_empty_list(self):
        """경계 — 없음·빈 문자열·빈 목록·필드 자체가 없음은 모두 빈 목록이다."""
        for v in ({"derived_from": ""}, {"derived_from": "   "},
                  {"derived_from": []}, {}, None):
            with self.subTest(v=v):
                self.assertEqual(s9.derived_ids(v), [])

    def test_empty_entries_inside_a_list_are_dropped(self):
        """경계 — 목록 안의 빈 값은 간선이 될 수 없다."""
        self.assertEqual(s9.derived_ids({"derived_from": ["REQ-1", "", None]}),
                         ["REQ-1"])


class TheGraphSurvivesBothShapes(unittest.TestCase):
    """실패 자리 — 목록인 문서 하나가 그래프 전체를 죽이지 않는다."""

    def _edges(self, metas):
        """graph_data 가 하는 일을 같은 재료로 잰다: 간선을 짓고 존재하는 것만 남긴다."""
        edges, ids = [], {m["id"] for m in metas}
        for m in metas:
            for t in s9.derived_ids(m):
                edges.append({"from": m["id"], "to": t, "rel": "derived_from"})
        return [e for e in edges if e["to"] in ids]      # 여기서 죽었다

    def test_a_list_valued_document_does_not_break_the_graph(self):
        metas = [{"id": "REQ-A", "derived_from": ["REQ-B", "REQ-C"]},
                 {"id": "REQ-B"}, {"id": "REQ-C", "derived_from": "REQ-B"}]
        got = [(e["from"], e["to"]) for e in self._edges(metas)]
        self.assertEqual(sorted(got),
                         [("REQ-A", "REQ-B"), ("REQ-A", "REQ-C"), ("REQ-C", "REQ-B")])

    def test_an_edge_to_a_missing_document_is_dropped(self):
        """경계 — 없는 문서로 가는 간선은 유령 화살표라 남기지 않는다."""
        metas = [{"id": "REQ-A", "derived_from": ["REQ-없음"]}]
        self.assertEqual(self._edges(metas), [])


if __name__ == "__main__":
    unittest.main()
