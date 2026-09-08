"""대시보드 데이터 4종을 직접 불러 값을 잰다 (REQ-20260908-007-62x6).

`graph_data`·`search_data`·`audit_data`·`projects_data` 는 `cmd_serve()` 안에
중첩 정의돼 있었다. 전송이 아니라 카탈로그에서 화면용 파생물을 만드는 일인데
전송 계층 함수 몸통 안에 갇혀 있어, 서버를 띄우지 않고는 어느 시험도 닿지
못했다 — 대시보드 데이터 전부가 회귀 시험을 붙일 자리 자체가 없었다.

값은 이미 치렀다: 2026-09-07 에 `graph_data` 가 `derived_from` 의 모양 하나로
죽어 Graph 탭이 열리지 않았고(REQ-20260907-075), 그 자리를 잴 시험이 없어
사용자가 화면으로 발견했다.

넷을 모듈 최상위로 끌어올린 뒤, 여기서 직접 부른다.

실행: python3 tests/ serve_data
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)

FM = """---
id: {id}
type: {type}
title: {title}
status: open
user: alice
project: section9
tags: []
{extra}---

{body}
"""


class ServeData(unittest.TestCase):
    """넷 모두 한 fixture 로 잰다 — s9 왕복은 setUpClass 에서 한 번뿐이다."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9serve-data-")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "boxA",
                   "S9_USER": "alice"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "alice")
        # 본문 검색용 — 한쪽에만 '알파', 양쪽에 '산딸기'.
        cls.A = cls.mk("검색 대상 알파", "산딸기 알파\n" * 20)
        cls.B = cls.mk("검색 대상 베타", "산딸기 베타")

        # 모듈 내부를 손대지 않고 환경으로 격리한다 — ROOT 는 import 시점에
        # 갈라져 나가는 값이라 나중에 덮으면 일부만 바뀐다.
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "boxA"
        os.environ["S9_USER"] = "alice"
        cls.m = _load("s9_serve_data", S9_SRC)

        # 관계 모양이 갈리는 문서는 직접 쓴다 — CLI 로는 `derived_from` 의
        # 두 모양(문자열/목록)을 한 vault 안에 나란히 세울 수 없다.
        d = os.path.join(cls.root, "vault", "requests", "2026", "09")
        os.makedirs(d, exist_ok=True)
        cls.wr(os.path.join(d, "t1.md"), id="REQ-T001", type="request",
               title="모양 하나", extra='parent: REQ-T002\n'
               'derived_from: "REQ-T002"\n')
        cls.wr(os.path.join(d, "t2.md"), id="REQ-T002", type="request",
               title="모양 둘",
               extra='derived_from: ["REQ-T001", "REQ-T404"]\n')
        cls.wr(os.path.join(d, "t3.md"), id="SES-T003", type="session",
               title="세션 하나", extra="session: aaaa1111\nmachine: boxA\n",
               body="## Notes\n- 이 줄은 이벤트가 아니다\n\n"
                    "## History\n"
                    "- 2026-09-08T01:00:00+09:00 첫 일 (by alice)\n"
                    "- 2026-09-08T03:00:00+09:00 나중 일 (by alice)\n")
        pd = os.path.join(cls.root, "vault", "projects")
        os.makedirs(pd, exist_ok=True)
        cls.wr(os.path.join(pd, "tproj.md"), id="PRJ-T009", type="project",
               title="시험 프로젝트",
               extra='slug: tproj\nmembers: [{"user": "alice", "until": ""}, '
                     '{"user": "bob", "until": "2000-01-01"}]\n',
               body="## History\n- 만들었다\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def cli(cls, *argv):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=60)
        if r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    @classmethod
    def mk(cls, title, body):
        return cls.cli("new", "request", "--title", title, "--summary", "s",
                       "--goal", "g", "--size", "S", "--user", "alice",
                       "--body", body).split()[0]

    @classmethod
    def wr(cls, path, body="본문", **kw):
        kw.setdefault("extra", "")
        with open(path, "w", encoding="utf-8") as f:
            f.write(FM.format(body=body, **kw))

    # ---- graph_data ------------------------------------------------------

    def test_s1_graph_empty_vault(self):
        """S1. 문서가 하나도 없어도 죽지 않고 빈 그래프를 준다."""
        empty = tempfile.mkdtemp(prefix="s9serve-empty-")
        old = self.m.VAULT
        try:
            self.m.VAULT = empty
            self.assertEqual(self.m.graph_data(), {"nodes": [], "edges": []})
        finally:
            self.m.VAULT = old
            shutil.rmtree(empty, ignore_errors=True)

    def test_s2_graph_parent_edge_and_dangling_dropped(self):
        """S2. parent 엣지가 나고, 없는 문서를 가리키는 엣지는 버려진다."""
        g = self.m.graph_data()
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("REQ-T001", ids)
        self.assertIn("REQ-T002", ids)
        self.assertIn({"from": "REQ-T001", "to": "REQ-T002", "rel": "parent"},
                      g["edges"])
        self.assertNotIn("REQ-T404", {e["to"] for e in g["edges"]})

    def test_s3_graph_derived_from_both_shapes(self):
        """S3. derived_from 이 문자열이든 목록이든 엣지가 난다 (REQ-20260907-075)."""
        edges = self.m.graph_data()["edges"]
        self.assertIn({"from": "REQ-T001", "to": "REQ-T002",
                       "rel": "derived_from"}, edges)     # 문자열 하나
        self.assertIn({"from": "REQ-T002", "to": "REQ-T001",
                       "rel": "derived_from"}, edges)     # 목록의 첫 항목

    # ---- search_data -----------------------------------------------------

    def test_s4_search_empty_query(self):
        """S4. 빈 질의는 전수 반환이 아니라 빈 결과다."""
        self.assertEqual(self.m.search_data(""), {"results": []})
        self.assertEqual(self.m.search_data("   "), {"results": []})

    def test_s5_search_all_terms_and_match_cap(self):
        """S5. 모든 낱말이 든 문서만 나오고, 문서당 matches 는 8줄까지다."""
        got = {r["id"] for r in self.m.search_data("산딸기")["results"]}
        self.assertEqual({self.A, self.B} & got, {self.A, self.B})
        only = self.m.search_data("산딸기 알파")["results"]
        self.assertEqual([r["id"] for r in only], [self.A])
        self.assertLessEqual(len(only[0]["matches"]), 8)
        self.assertTrue(only[0]["matches"])

    # ---- audit_data ------------------------------------------------------

    def test_s6_audit_history_only_and_sorted(self):
        """S6. session 문서의 ## History 줄만 이벤트가 되고 ts 내림차순이다."""
        events = self.m.audit_data()["events"]
        mine = [e for e in events if e["doc"] == "SES-T003"]
        self.assertEqual([e["text"] for e in mine], ["나중 일", "첫 일"])
        self.assertEqual(mine[0]["by"], "alice")
        self.assertEqual(mine[0]["session"], "aaaa1111")
        self.assertNotIn("이 줄은 이벤트가 아니다", [e["text"] for e in events])
        ts = [e["ts"] for e in events]
        self.assertEqual(ts, sorted(ts, reverse=True))

    # ---- projects_data ---------------------------------------------------

    def test_s7_projects_members_counted(self):
        """S7. 멤버의 활성/만료가 문서에서 계산된다."""
        rows = {p["id"]: p for p in self.m.projects_data()["projects"]}
        p = rows["PRJ-T009"]
        self.assertEqual(p["slug"], "tproj")
        self.assertEqual((p["member_total"], p["member_active"]), (2, 1))
        self.assertEqual([m["user"] for m in p["members"] if m["active"]],
                         ["alice"])
        self.assertEqual(p["history_tail"], ["만들었다"])

    # ---- 끌어올림 자체 ---------------------------------------------------

    def test_s8_functions_live_at_module_top_level(self):
        """S8. 넷은 모듈 최상위에 있다 — cmd_serve 를 부르지 않고 부를 수 있다."""
        import inspect
        for name in ("graph_data", "search_data", "audit_data",
                     "projects_data"):
            fn = getattr(self.m, name, None)
            self.assertTrue(callable(fn), f"{name} 이 모듈 최상위에 없다")
            self.assertEqual(fn.__qualname__, name,
                             f"{name} 이 아직 다른 함수 안에 있다")
        src = inspect.getsource(self.m.cmd_serve)
        for name in ("graph_data", "search_data", "audit_data",
                     "projects_data"):
            self.assertNotIn(f"def {name}(", src,
                             f"cmd_serve 안에 {name} 정의가 남아 있다")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    unittest.main()
