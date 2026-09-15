"""휴지통의 수명과 거르개 (REQ-20260915-062-62x6).

여태 휴지통은 **버린 때조차 추측**이었다 — 파일 mtime 을 버린 때로 읽었는데
그 값은 동기화·복사가 건드리면 틀어진다. 버린 사람도 어디서 버렸는지도 아무
데도 없었고, 그래서 백 건이 넘게 쌓인 목록에서 되돌릴 하나를 찾는 비용이
목록 길이에 비례했다(REQ-20260910-006 designer 검토 3순위).

여기서 잠그는 계약은 셋이다.
  ① 버린 사실은 **문서에 적힌다** — 언제·누가·어디서(화면/명령).
  ② 되돌아온 문서에는 그 세 줄이 남지 않는다 — 살아 있는 문서가 제가
     버려졌다고 말하면 안 된다.
  ③ 모르는 것은 지어내지 않는다 — 안 적힌 옛 문서는 mtime 을 쓰되 어디서
     버렸는지는 빈 값이고, 수명을 넘긴 쪽으로 세지 않는다.

화면 쪽(거르개·검색·바닥 문장)은 여기서 소스 글자로 재지 않는다 — 그런 시험은
동작을 재지 않으면서 리팩터에 깨지고 값싸서 끝없이 는다(tests/BUDGET.json 라쳇).
그 자리는 `web/verify-trash-sieve.html` 이 맡는다: 실제 MouseEvent·input 으로
눌러·쳐서 목록이 좁아지는지 본다.

실행: python3 tests/ trash_sieve
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


class TrashSieveTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9trsv-")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_MACHINE": "testbox", "S9_AUDIT": "off",
                    "S9_REWORK_WATCH": "off"}
        for k in ("S9_SESSION", "S9_PORT", "S9_USER"):
            self.env.pop(k, None)
        self.ok("init")
        self.ok("user", "add", "boss", "--role", "admin")

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
                       "--goal", "g", "--body", "b").split()[0].strip()

    def mod(self):
        os.environ["S9_ROOT"] = self.root
        name = "s9trsv_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def entry(self, doc_id):
        return next(e for e in self.mod().trash_entries() if e["id"] == doc_id)

    # ------------------------------------------------------- n1 · 버린 사실
    def test_n1_cli_rm_records_who_when_where(self):
        rid = self.new_req("명령으로 버린 것")
        self.ok("rm", rid)
        e = self.entry(rid)
        self.assertTrue(e["deleted"], "버린 때가 비었다")
        self.assertEqual(e["trashed_how"], "cli",
                         "명령으로 버린 것이 명령으로 안 적혔다")
        self.assertEqual(e["trashed_by"], "boss", "버린 사람이 안 적혔다")
        # 파일에도 그대로 있어야 한다 — 화면이 읽는 원천은 파일이다.
        txt = open(os.path.join(self.root, e["path"]), encoding="utf-8").read()
        for k in ("trashed:", "trashed_by:", "trashed_how:"):
            self.assertIn(k, txt, f"{k} 가 문서에 없다")

    # ------------------------------------------------- n2 · 화면에서 버린 것
    def test_n2_screen_rm_is_marked_screen(self):
        rid = self.new_req("화면에서 버린 것")
        m = self.mod()
        r = m.docs_bulk("rm", [rid], actor="boss")
        self.assertEqual(r["done"], [rid], f"버리지 못했다: {r}")
        self.assertEqual(self.entry(rid)["trashed_how"], "screen",
                         "판에서 버린 것이 화면으로 안 적혔다")

    # ------------------------------------------- r1 · 되돌리면 자취가 없다
    def test_r1_restore_clears_the_marks(self):
        rid = self.new_req("되돌아올 것")
        self.ok("rm", rid)
        self.ok("restore", rid)
        p = self.mod().find_path(rid)
        txt = open(p, encoding="utf-8").read()
        for k in ("trashed:", "trashed_by:", "trashed_how:"):
            self.assertNotIn(k, txt,
                             f"되돌아온 문서에 {k} 가 남았다 — 제가 버려졌다고 말한다")

    # --------------------------------------------------------- 수명 세기
    def test_b1_unmarked_old_doc_keeps_its_mtime_and_says_nothing(self):
        """옛 문서에는 적힌 적이 없다 — 때는 mtime 으로 메우되 어디서
        버렸는지는 **빈 값**이다. 지어내면 거르개가 거짓을 말한다."""
        rid = self.new_req("옛 문서")
        self.ok("rm", rid)
        m = self.mod()
        e = self.entry(rid)
        p = os.path.join(self.root, e["path"])
        meta, body = m.read_doc(p)
        for k in ("trashed", "trashed_by", "trashed_how"):
            meta.pop(k, None)
        m.write_doc(p, meta, body)
        e2 = self.entry(rid)
        self.assertEqual(e2["trashed_how"], "", "모르는 것을 지어냈다")
        self.assertTrue(e2["deleted"], "mtime 으로도 때를 못 메웠다")

    def test_b2_overdue_counts_only_what_it_can_read(self):
        m = self.mod()
        rows = [{"deleted": "2000-01-01T00:00:00"}, {"deleted": ""},
                {"deleted": m.now_iso()}]
        self.assertEqual(len(m.trash_overdue(rows, 30)), 1,
                         "읽을 수 있는 것만 넘긴 것으로 세야 한다")
        self.assertEqual(m.trash_overdue(rows, 0), [],
                         "수명이 꺼졌는데 넘겼다고 말한다")

    def test_b4_keep_days_setting_is_read(self):
        m = self.mod()
        self.assertEqual(m.trash_keep_days("boss"), m.TRASH_KEEP_DAYS)
        self.ok("user", "config", "boss", "trash_keep_days", "0")
        self.assertEqual(self.mod().trash_keep_days("boss"), 0,
                         "끈 설정이 안 읽힌다")


if __name__ == "__main__":
    unittest.main()
