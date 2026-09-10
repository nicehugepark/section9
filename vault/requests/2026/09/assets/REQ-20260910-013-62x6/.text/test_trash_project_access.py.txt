"""버린 프로젝트의 열람·되돌리기 (REQ-20260910-013-62x6).

프로젝트 문서를 버리면 등록부(project_path)는 그 slug 를 잊는다 — 문서가
`vault/projects/.trash/` 로 갔고 등록부는 그 아래를 보지 않기 때문이다.
그런데 `doc_access` 는 프로젝트를 **등록부로만** 찾았다. 그래서 버리는 순간
그 프로젝트에 속한 모든 문서가 판정에서 「아무 소속도 없는 문서」가 되고,
담당·만든 사람이 아닌 멤버에게는 통째로 사라졌다. 버린 프로젝트 문서 자신은
더 나빴다 — PRJ 문서에는 `user` 도 `creator` 도 없어 admin 말고는 **아무도**
보지 못했고, `restore` 가 같은 판정을 쓰는 탓에 되돌릴 수도 없었다.

여기서 잠그는 계약은 **버리는 일이 보이는 범위를 바꾸지 않는다**는 것이다.
넓히면 삭제가 격리를 우회하는 열람 경로가 되고(남이 남의 것을 보게 된다),
좁히면 멤버가 자기 프로젝트를 되돌릴 수 없다(admin 을 불러야 한다).

실행: python3 tests/ trash_project_access
"""
import importlib.machinery
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class TrashProjectAccessTest(unittest.TestCase):
    """boss(admin) 가 만든 프로젝트 shop 에 mem 이 contributor 로 있다.
    outsider 는 남이고, gone 은 만료된 옛 멤버다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9trprj-")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_MACHINE": "testbox", "S9_AUDIT": "off",
                    "S9_REWORK_WATCH": "off"}
        for k in ("S9_SESSION", "S9_PORT", "S9_USER"):
            self.env.pop(k, None)
        self.ok("init")
        for u, role in (("boss", "admin"), ("mem", "member"),
                        ("outsider", "member"), ("gone", "member")):
            self.ok("user", "add", u, "--role", role)
        self.ok("project", "add", "shop", "--name", "가게", "--summary", "s")
        self.ok("project", "member", "shop", "add", "mem",
                "--role", "contributor")
        self.ok("project", "member", "shop", "add", "gone",
                "--role", "contributor", "--until", "2020-01-01")
        self.req = self.new_req("버린 요청")
        self.live = self.new_req("살아 있는 요청")
        ptxt = open(os.path.join(self.root, "vault", "projects", "shop.md"),
                    encoding="utf-8").read()
        self.prj = re.search(r"(?m)^id: (\S+)", ptxt).group(1)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # ------------------------------------------------------------ 도우미
    def cli(self, *argv, who="boss"):
        env = {**self.env, "S9_USER": who} if who else self.env
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env=env, timeout=90, stdin=subprocess.DEVNULL)

    def ok(self, *argv, who="boss"):
        r = self.cli(*argv, who=who)
        self.assertEqual(r.returncode, 0, f"{argv} 실패: {r.stdout}{r.stderr}")
        return r.stdout

    def new_req(self, title):
        return self.ok("new", "request", "--title", title, "--summary", "s",
                       "--goal", "g", "--body", "b",
                       "--project", "shop").split()[0].strip()

    def mod(self):
        """s9 를 모듈로 들여온다 — doc_visible·docs_bulk 를 직접 부른다.
        판정은 매번 새로 읽어야 한다(휴지통은 도중에 바뀐다)."""
        os.environ["S9_ROOT"] = self.root
        name = "s9trprj_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def trash(self):
        m = self.mod()
        return m, {e["id"]: e for e in m.trash_entries()}

    # ---------------------------------------------------------------- S1
    def test_s1_live_project_trashed_doc_stays_visible(self):
        """기준선 — 프로젝트가 살아 있으면 버린 요청은 멤버에게 보이고
        남에게는 안 보인다. 아래 장면들이 이 선을 넘지 않아야 한다."""
        self.ok("rm", self.req, "--reason", "테스트")
        m, ents = self.trash()
        self.assertTrue(m.doc_visible(ents[self.req], "mem"))
        self.assertFalse(m.doc_visible(ents[self.req], "outsider"))

    # ---------------------------------------------------------------- S2
    def test_s2_trashed_project_visible_to_its_members(self):
        """버린 프로젝트 문서는 그 명부의 활성 멤버에게 보인다.

        PRJ 문서에는 `user`·`creator` 가 없다 — 등록부가 slug 를 잊으면
        기댈 곳이 명부뿐인데, 그 명부는 .trash 안의 문서 자신이 들고 있다."""
        self.ok("rm", self.prj, "--reason", "테스트")
        m, ents = self.trash()
        self.assertIn(self.prj, ents, "버린 프로젝트가 휴지통 목록에 있어야 한다")
        self.assertTrue(m.doc_visible(ents[self.prj], "mem"),
                        "멤버에게 안 보이면 되돌릴 사람이 admin 뿐이다")
        self.assertTrue(m.doc_visible(ents[self.prj], "boss"))

    # ---------------------------------------------------------------- S3
    def test_s3_trashed_project_hidden_from_outsiders(self):
        """넓히지 않는다 — 남과 만료된 옛 멤버는 못 본다.
        여기가 무너지면 **삭제가 격리를 우회하는 열람 경로**가 된다."""
        self.ok("rm", self.prj, "--reason", "테스트")
        m, ents = self.trash()
        self.assertFalse(m.doc_visible(ents[self.prj], "outsider"))
        self.assertFalse(m.doc_visible(ents[self.prj], "gone"))

    # ---------------------------------------------------------------- S4
    def test_s4_trashing_project_does_not_hide_its_documents(self):
        """프로젝트를 버려도 그 프로젝트의 문서는 멤버에게 그대로 보인다 —
        버린 것도, **살아 있는 것도**. 이것이 이 결함의 진짜 반경이었다:
        프로젝트 하나를 버리면 멤버의 화면에서 그 프로젝트가 통째로 사라졌다."""
        self.ok("rm", self.req, "--reason", "테스트")
        self.ok("rm", self.prj, "--reason", "테스트")
        m, ents = self.trash()
        self.assertTrue(m.doc_visible(ents[self.req], "mem"),
                        "버린 프로젝트의 버린 요청")
        live_meta, _ = m.read_doc(m.locate(self.live))
        self.assertTrue(m.doc_visible(live_meta, "mem"),
                        "버린 프로젝트의 살아 있는 요청")
        self.assertFalse(m.doc_visible(live_meta, "outsider"))

    # ---------------------------------------------------------------- S5
    def test_s5_member_restores_trashed_project(self):
        """멤버가 되돌리면 원래 자리로 가고, 등록부가 그 slug 를 다시 안다."""
        self.ok("rm", self.prj, "--reason", "테스트")
        m, _ = self.trash()
        r = m.docs_bulk("restore", [self.prj], actor="mem")
        self.assertEqual((r["done"], r["failed"]), ([self.prj], []))
        self.assertTrue(os.path.exists(
            os.path.join(self.root, "vault", "projects", "shop.md")))
        self.assertTrue(self.mod().project_path("shop"),
                        "되돌린 프로젝트를 등록부가 다시 알아야 한다")

    # ---------------------------------------------------------------- S6
    def test_s6_outsider_cannot_restore_or_purge(self):
        """남은 되돌리지도 소거하지도 못한다 — 되돌릴 수 없는 쪽이 더 비싸다."""
        self.ok("rm", self.prj, "--reason", "테스트")
        m, _ = self.trash()
        for op in ("restore", "purge"):
            r = m.docs_bulk(op, [self.prj], actor="outsider")
            self.assertEqual(r["done"], [], f"{op} 가 통과하면 안 된다")
            self.assertEqual([f["error"] for f in r["failed"]], ["권한 없음"])

    # ---------------------------------------------------------------- S7
    def test_s7_trash_row_carries_the_fields_judgment_reads(self):
        """휴지통 행은 판정이 보는 원 필드를 싣는다.

        행이 슬림하면 `doc_access` 는 살아 있는 문서와 **다른 갈래**를 탄다:
        slug 가 없으면 PRJ 행이 자기 프로젝트를 대지 못하고, `creator_raw` 가
        없으면 `creator_field` 가 `path` 를 보고 옛 catalog 행으로 여겨 닫는다
        (fail-closed) — 만든 사람이 자기 문서를 휴지통에서 못 보게 된다."""
        self.ok("rm", self.prj, "--reason", "테스트")
        _, ents = self.trash()
        row = ents[self.prj]
        self.assertEqual(row.get("slug"), "shop")
        for k in ("creator_raw", "assignee"):
            self.assertIn(k, row, f"{k} 가 빠지면 살아 있을 때와 판정이 갈린다")

    # ---------------------------------------------------------------- S8
    def test_s8_registry_does_not_resurrect_a_trashed_project(self):
        """판정이 .trash 를 보게 됐다고 **등록부까지** 보면 안 된다 —
        버린 프로젝트는 목록에 서지 않는다. 이것이 무너지면 버린 일이
        무효가 된다: 화면에 다시 서고, 기본 프로젝트 후보로도 돌아온다.

        (`--project <버린 slug>` 로 새 요청을 세우는 것은 여기서 막지
        않는다 — 등록부에 없는 slug 는 원래 다 통과한다(「정책 부재」).
        버린 프로젝트만의 일이 아니라서 이 시험의 계약이 아니다.)"""
        self.ok("rm", self.prj, "--reason", "테스트")
        m = self.mod()
        self.assertIsNone(m.project_path("shop"))
        self.assertNotIn("shop", [p.get("slug") for p in m.all_projects()])


if __name__ == "__main__":
    unittest.main(verbosity=2)
