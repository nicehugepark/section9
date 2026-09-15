"""문서를 치우는 길 — 보관 · 삭제 · 소거 (REQ-20260829-025-62x6).

치우는 길은 **세 층**이고, 층마다 되돌릴 수 있는 정도가 다르다:

  보관(archive)  파일은 제자리. 목록에서만 내린다. 언제든 되돌린다.
  삭제(rm)       같은 폴더의 .trash/ 로 옮긴다. 목록에서 사라지되 번호는
                 계속 물고 있다 — 지운 번호가 다른 문서로 재발급되던 사고를
                 막던 그 tombstone 이다 (REQ-20260825-031/-006).
  소거(purge)    .trash 안의 것만 지운다. 되돌릴 수 없다.

여기서 잠그는 계약 중 가장 비싼 것은 **S8** 이다: 소거가 재발번 방어를 뚫으면
삭제를 tombstone 으로 만든 이유가 통째로 없어진다. 그래서 소거는 파일을
지우되 그 자리에 번호만 남긴 묘비(.trash/purged/<id>.md)를 세운다.

실행: python3 tests/ doc_tidy
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import sys
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


class DocTidyTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9tidy-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                    "S9_AUDIT": "off"}
        for k in ("S9_SESSION", "S9_PORT"):
            self.env.pop(k, None)
        self.cli("init")
        self.a = self.new("첫 문서")
        self.b = self.new("둘째 문서")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # ------------------------------------------------------------ 도우미
    def cli(self, *argv):
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env=self.env, timeout=90,
                              stdin=subprocess.DEVNULL)

    def ok(self, *argv):
        r = self.cli(*argv)
        self.assertEqual(r.returncode, 0, f"{argv} 실패: {r.stderr}")
        return r.stdout

    def new(self, title):
        return self.ok("new", "request", "--title", title, "--summary", "s",
                       "--body", "b").split()[0].strip()

    def mod(self):
        """s9 를 모듈로 들여온다 — docs_bulk 같은 내부 계약을 직접 부른다."""
        os.environ["S9_ROOT"] = self.root
        name = "s9tidy_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def doc_path(self, doc_id):
        """살아 있는 자리의 경로 — .trash 는 자리가 아니다."""
        for dirpath, dirs, files in os.walk(os.path.join(self.root, "vault")):
            dirs[:] = [d for d in dirs if d != ".trash"]
            for fn in files:
                if fn == doc_id + ".md":
                    return os.path.join(dirpath, fn)
        return None

    def rows(self, *extra):
        return self.ok("ls", *extra)

    def catalog(self):
        # 병합된 목록은 `index cat` 만이 준다 (REQ-20260902-035).
        return [json.loads(l) for l in self.ok("index", "cat").splitlines()
                if l.strip()]

    # ---------------------------------------------------------------- S1
    def test_s1_archive_marks_and_records(self):
        """보관은 frontmatter 한 칸과 History 한 줄로 남는다 — 파일은 제자리."""
        p = self.doc_path(self.a)
        self.ok("archive", self.a, "--reason", "다 끝난 실험")
        self.assertTrue(os.path.exists(p), "보관은 파일을 옮기지 않는다")
        text = open(p, encoding="utf-8").read()
        self.assertRegex(text, r"(?m)^archived: \d{4}-")
        self.assertRegex(text, r"(?m)^archived_by: ")
        self.assertRegex(text, r"(?m)^- \S+ archived \(by .+\) — 다 끝난 실험$")

    # ---------------------------------------------------------------- S2
    def test_s2_archived_leaves_default_list_only(self):
        """기본 목록에서는 빠지고 --archived 에서만 온다. 행 자체는 남는다."""
        self.ok("archive", self.a)
        self.assertNotIn(self.a, self.rows())
        self.assertIn(self.b, self.rows())
        arch = self.rows("--archived")
        self.assertIn(self.a, arch)
        self.assertNotIn(self.b, arch)
        row = next(r for r in self.catalog() if r["id"] == self.a)
        self.assertTrue(row.get("archived"), "카탈로그 행에는 남아야 찾을 수 있다")

    # ---------------------------------------------------------------- S3
    def test_s3_unarchive_returns(self):
        self.ok("archive", self.a)
        self.ok("unarchive", self.a)
        self.assertIn(self.a, self.rows())
        self.assertNotIn(self.a, self.rows("--archived"))
        self.assertNotIn("archived:", open(self.doc_path(self.a),
                                           encoding="utf-8").read())

    # ---------------------------------------------------------------- S4
    def test_s4_rm_takes_many_at_once(self):
        """여러 건을 한 번에 — 그리고 파일은 소거되지 않고 .trash 로 간다."""
        out = self.ok("rm", self.a, self.b, "--reason", "duplicate")
        self.assertIn(self.a, out)
        self.assertIn(self.b, out)
        listed = self.rows()
        self.assertNotIn(self.a, listed)
        self.assertNotIn(self.b, listed)
        for i in (self.a, self.b):
            self.assertIsNone(self.doc_path(i), "원래 자리에 남아 있으면 안 된다")
        trash = json.loads(self.ok("trash", "--json"))
        self.assertEqual({e["id"] for e in trash}, {self.a, self.b})

    # ---------------------------------------------------------------- S5
    def test_s5_trash_shows_what_and_when(self):
        self.ok("rm", self.a)
        ents = json.loads(self.ok("trash", "--json"))
        self.assertEqual(len(ents), 1)
        e = ents[0]
        self.assertEqual(e["id"], self.a)
        self.assertEqual(e["title"], "첫 문서")
        self.assertRegex(e["deleted"], r"^\d{4}-\d\d-\d\dT")
        self.assertIn(".trash", e["path"].replace("\\", "/"))
        self.assertIn(self.a, self.ok("trash"))

    # ---------------------------------------------------------------- S6
    def test_s6_restore_puts_it_back(self):
        self.ok("rm", self.a)
        self.ok("restore", self.a)
        p = self.doc_path(self.a)
        self.assertIsNotNone(p, "원래 자리로 돌아와야 한다")
        self.assertNotIn(".trash", p.replace("\\", "/"))
        self.assertIn(self.a, self.rows())
        self.assertRegex(open(p, encoding="utf-8").read(),
                         r"(?m)^- \S+ restored \(by .+\)$")
        self.assertEqual(json.loads(self.ok("trash", "--json")), [])

    # ---------------------------------------------------------------- S7
    def test_s7_purge_needs_yes_and_a_tombstone(self):
        """--yes 없이는 아무 일도 없고, 휴지통 밖의 살아 있는 문서는 거부한다."""
        self.ok("rm", self.a)
        r = self.cli("purge", self.a)
        self.assertNotEqual(r.returncode, 0, "--yes 없이 소거되면 안 된다")
        self.assertEqual(len(json.loads(self.ok("trash", "--json"))), 1)

        # 살아 있는 문서(b)는 먼저 휴지통을 지나야 한다
        r = self.cli("purge", self.b, "--yes")
        self.assertIn("휴지통에 없다", r.stdout + r.stderr)
        self.assertIsNotNone(self.doc_path(self.b))

        self.ok("purge", self.a, "--yes")
        self.assertEqual(json.loads(self.ok("trash", "--json")), [])
        for dirpath, _d, files in os.walk(os.path.join(self.root, "vault")):
            if os.path.basename(dirpath) == "purged":
                continue
            self.assertNotIn(self.a + ".md", files, "소거된 문서가 남아 있다")

    # ---------------------------------------------------------------- S8
    def test_s8_purged_number_is_never_reissued(self):
        """소거가 재발번 방어를 뚫으면 tombstone 을 만든 이유가 사라진다."""
        self.ok("rm", self.b)
        self.ok("purge", self.b, "--yes")
        fresh = self.new("셋째 문서")
        self.assertNotEqual(fresh, self.b)
        self.assertNotEqual(fresh, self.a)
        tomb = os.path.join(os.path.dirname(self.doc_path(self.a)),
                            ".trash", "purged", self.b + ".md")
        self.assertTrue(os.path.exists(tomb), "번호를 태워 둔 묘비가 있어야 한다")

    # ---------------------------------------------------------------- S9
    def test_s9_dashboard_and_cli_share_one_path(self):
        """화면의 묶음 처리는 CLI 와 **같은 함수**를 지난다 (두 벌이면 한 벌만 고쳐진다)."""
        m = self.mod()
        r = m.docs_bulk("archive", [self.a, self.b], "")
        self.assertEqual(set(r["done"]), {self.a, self.b})
        self.assertEqual(r["failed"], [])
        # 같은 처리를 두 번 — 이미 그 상태인 것은 실패로 정직하게 돌려준다
        again = m.docs_bulk("archive", [self.a], "")
        self.assertEqual(again["done"], [])
        self.assertEqual(again["failed"][0]["id"], self.a)

        self.assertEqual(m.docs_bulk("unarchive", [self.a, self.b], "")["done"],
                         [self.a, self.b])
        self.assertEqual(m.docs_bulk("rm", [self.a], "")["done"], [self.a])
        self.assertEqual(m.docs_bulk("restore", [self.a], "")["done"], [self.a])
        m.docs_bulk("rm", [self.a], "")
        self.assertEqual(m.docs_bulk("purge", [self.a], "")["done"], [self.a])

        # 없는 것은 넘어지되 **나머지는 간다**
        mixed = m.docs_bulk("archive", ["REQ-99999999-999-zzzz", self.b], "")
        self.assertEqual(mixed["done"], [self.b])
        self.assertEqual(len(mixed["failed"]), 1)

        with self.assertRaises(ValueError):
            m.docs_bulk("nuke", [self.b], "")

        src = open(S9_SRC, encoding="utf-8").read()
        self.assertIn('"/api/docs/tidy"', src)
        self.assertIn('"/api/trash"', src)

    # --------------------------------------------------------------- S10
    def test_s10_screen_handles_and_load_order(self):
        """화면 — 손잡이가 다 있고, **스킨·밀도 뒤에** 실린다.

        고르기 눈금은 줄 안쪽에 절대 배치로 서고 그 자리는 `.doclist.picking
        .row{padding-left}` 가 낸다. 그런데 스킨(calm)과 밀도(compact)가 같은
        무게로 `.doclist .row{padding}` 을 다시 쓴다 — 순서가 앞서면 눈금이
        문서 번호 위에 겹쳐 앉는다(실측: `REQ-…` 의 첫 글자가 먹혔다).
        무게로는 못 이기고 순서로 이기는 자리라, 순서를 시험이 잡아 둔다.
        """
        import webasset
        css, app = webasset.parts()
        self.assertIn("tidy.css", css)
        self.assertIn("tidy.js", app)
        for earlier in ("docs.css", "skins.css", "density.css", "calm.css"):
            self.assertLess(css.index(earlier), css.index("tidy.css"),
                            f"{earlier} 뒤에 실려야 눈금 자리가 살아남는다")

        src = webasset.source()
        self.assertIn(".doclist.picking .row{padding-left:", src)
        # 목록(고르기·묶음 처리) · 문서 한 장 · 보관함·휴지통 판 — 세 자리의 손잡이
        for handle in ("pick", "open", "tick", "all", "none",
                       "archive", "rm", "arch1", "unarch1", "rm1",
                       "back", "purge", "purgeall", "tab", "close"):
            self.assertIn(f'"{handle}"', src, f"손잡이 {handle} 이 없다")

    # --------------------------------------------------------------- S11
    def test_s11_the_handler_never_trusts_the_target(self):
        """손잡이가 화면을 죽이지 않는다 (REQ-20260830-006 실사고).

        `TypeError: e.target.closest is not a function` — 이 조각의 클릭
        리스너는 **문서 전체**를 캡처 단계에서 듣는다. 그러니 Element 가 아닌
        대상도 온다. 종전에는 첫 줄만 `e.target.closest &&` 로 지키고, 판을
        닫는 둘째 줄은 안 지켰다. 하필 그 줄은 판이 떠 있을 때만 도는 줄이라
        평소에는 한 번도 안 밟혔고, 사용자가 휴지통을 열어 둔 채 클릭한 순간
        조각 하나가 통째로 죽었다.

        그래서 계약은 "지켰나"가 아니라 **"두 번 묻지 않는다"** 로 잡는다 —
        지키는 자리가 둘이면 언젠가 한쪽만 지켜진다.
        """
        import webasset
        js = open(os.path.join(os.path.dirname(webasset.WEB), "web", "app",
                               "tidy.js"), encoding="utf-8").read()
        self.assertEqual(js.count(".closest("), 1,
                         "조상을 거슬러 찾는 자리가 둘 이상이다 — "
                         "둘이면 언젠가 한쪽만 지켜진다")
        # 듣는 자리가 둘이 됐다(누르는 손 + 글을 받는 칸, REQ-20260915-062-62x6).
        # 계약은 그대로다 — 둘 다 `tidyNear` 한 곳을 지나므로 위의 `.closest(`
        # 한 번이 그 사실을 이미 잰다.
        self.assertIn("evEl(e.target)", js,
                      "눌린 자리를 공용 경로(evEl)으로 거르지 않는다 — "
                      "조각마다 자기 방어를 두면 조각 수만큼 구멍이 남는다 "
                      "(REQ-20260830-010 에서 events.js 가 같은 오류로 죽었다)")
        self.assertIn('near("[data-tidy]")', js, "손잡이를 near 로 찾지 않는다")
        self.assertIn('near(".tidypanel,.dlgbox")', js,
                      "판 밖 판정을 near 로 하지 않는다")


class TidyBarStable(unittest.TestCase):
    """묶음 처리 띠는 서명이 바뀔 때만 다시 그린다 (REQ-20260907-028).

    innerHTML 비교는 `disabled` → `disabled=""` 직렬화 차이로 n=0 에서 매번
    어긋나, 목록 갱신마다 버튼이 새 노드로 바뀌어 사람의 누름이 떨어졌다."""

    def test_bar_rerenders_by_signature_not_innerhtml(self):
        import os
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "web", "app", "tidy.js"), encoding="utf-8").read()
        i = src.index('data-tidy="all"')
        tail = src[i:i + 1200]
        self.assertIn("bar2.dataset.sig", tail)
        self.assertNotIn("bar2.innerHTML !== html", tail)


if __name__ == "__main__":
    unittest.main()


class TidyHandleNamesBothPlaces(unittest.TestCase):
    """손잡이·판이 「치운 것」 대신 **보관함·휴지통** 두 이름을 그대로 세운다
    (REQ-20260907-085-62x6).

    넷이 다시 판정한 자리다. 「치우다」는 우리말에서 버림 쪽으로 기울어 보관의
    뜻을 잃고(translator), 판 안의 탭·행 버튼이 이미 「보관함」·「휴지통」인데
    손잡이만 셋째 사전을 열었다(tech-writer, 규약 2조 ⑤). 합계 한 수
    (1+76=77)로는 어느 쪽이 77건인지 알 수 없어 두 수를 따로 센다(designer).

    실행: python3 tests/ doc_tidy
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(HERE, "..", "web"))
        import webasset
        cls.src = webasset.source()
        cls.js = open(os.path.join(HERE, "..", "web", "app", "tidy.js"),
                      encoding="utf-8").read()

    def _strings(self, src):
        """주석은 빼고 **사람이 보는 문자열만** 남긴다 — 옛 이름이 근거로 남는
        주석과 화면에 서는 글자를 같은 자로 재면 판정이 흐려진다."""
        out = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        return re.sub(r"^\s*//.*$", "", out, flags=re.M)

    def test_s1_the_handle_counts_two_piles_apart(self):
        vis = self._strings(self.js)
        self.assertIn('`보관함${cnt(na)} · 휴지통${cnt(nt)}`', vis,
                      "손잡이가 두 이름·두 수로 서지 않는다")
        self.assertNotIn("tidyArch.length + tidyTrash.length", vis,
                         "합계 한 수는 무엇을 세는지 말하지 못한다")
        # 자리 기억 열쇠(dlgDragBind·dlgPosPlaceFor 의 인자)만 옛 이름을 지킨다 —
        # 화면에 안 나오는 저장 열쇠라, 바꾸면 판을 옮겨 둔 사람의 자리가 한 번
        # 초기화된다. 그 두 줄을 뺀 나머지에는 한 자리도 없어야 한다.
        screen = "\n".join(l for l in vis.splitlines()
                           if "dlgDragBind" not in l and "dlgPosPlaceFor" not in l)
        self.assertNotIn("치운 것", screen,
                         "화면 문자열에 「치운 것」이 남아 있다")
        self.assertIn('dlgPosPlaceFor(tidyBox, "치운 것")', self.js,
                      "자리 기억 열쇠는 그대로 둔다")
        # 화면 전체(HTML 안내문 포함)에서도 걷혔다
        guide = open(os.path.join(HERE, "..", "web", "guide.html"),
                     encoding="utf-8").read()
        self.assertNotIn("치운 것", guide)

    def test_s2_no_number_before_the_lists_arrive(self):
        """아직 못 받아 왔으면 수 없이 이름만 — 0 을 미리 적으면 비었다고
        거짓말을 한다."""
        self.assertIn("const cnt = n => n === null ? \"\" : `<b>${n}</b>`",
                      self.js)
        self.assertIn("const na = tidyArch === null ? null : tidyArch.length",
                      self.js)

    def test_s3_the_pick_tip_says_both_destinations_politely(self):
        vis = self._strings(self.js)
        self.assertIn("여러 문서를 골라 한 번에 보관하거나 지웁니다", vis)
        self.assertNotIn("한 번에 치운다", vis)
        self.assertNotIn("고르기를 끝낸다", vis, "화면은 존댓말이다")

    def test_s4_the_confirm_names_where_the_handle_is(self):
        """되돌릴 자리를 **화면에 실제로 있는 이름**으로 말한다.

        종전 문장은 「휴지통에서 되돌릴 수 있습니다」였다 — 그 휴지통이 어디에
        있는지는 말하지 않았고, 손잡이는 Docs 타입바 끝 한 곳뿐이라 주인은 버린
        뒤 한참을 뒤졌다 (REQ-20260910-005/006)."""
        vis = self._strings(self.js)
        self.assertIn("Docs 탭 위 <b>「보관함 · 휴지통」</b>에서 ", vis)
        self.assertNotIn("치운 것 → 휴지통", vis)

    def test_s5_the_words_are_the_settled_six(self):
        """확정 사전 여섯만 선다 (REQ-20260910-006).

        보관 / 보관 해제 · 휴지통으로 · 되돌리기 · 완전히 지우기 · 휴지통 비우기.
        폐기한 낱말이 한 곳이라도 남으면 같은 것에 이름이 둘이 된다."""
        vis = self._strings(self.js)
        for gone in ("영구 삭제", "전부 영구 삭제", "영구 삭제하기", "소거"):
            self.assertNotIn(gone, vis, "폐기한 낱말: " + gone)
        self.assertIn("완전히 지우기", vis)
        self.assertIn("휴지통 비우기", vis)
        # 한 낱말이 두 뜻을 지지 않는다 — 휴지통 탭은 되돌리기, 보관함 탭은 보관 해제
        self.assertIn('${tidyTab === "trash" ? "되돌리기" : "보관 해제"}', self.js)

    def test_s6_one_signal_invalidates_both_lists(self):
        """치우는 손은 **한 신호**만 지난다 (REQ-20260910-005 실제 사고).

        종전에는 여기서 카탈로그만 다시 받아, 같은 삭제가 Docs 에서는 반영되고
        Projects 레일에서는 안 됐다 — 버리면 남고 되돌리면 사라졌다. 목록이
        둘인데 무효화가 하나였던 것이 뿌리다. 다음에 붙는 변이가 또 한쪽을
        빠뜨리지 않게, 부르는 자리는 `docsChanged` 하나로 고정한다."""
        send = self.js.split("async function tidySend(")[1].split("\n}\n")[0]
        self.assertIn("await docsChanged();", send)
        self.assertNotIn("refreshCatalog(", send,
                         "목록을 낱개로 다시 받으면 다음 변이가 또 한쪽을 빠뜨린다")
        app = open(os.path.join(HERE, "..", "web", "app", "app.js"),
                   encoding="utf-8").read()
        self.assertIn("async function docsChanged()", app)
        body = app.split("async function docsChanged()")[1].split("\n}\n")[0]
        self.assertIn("await refreshProjects();", body)
        self.assertIn("await refreshCatalog(true);", body)
        # 프로젝트를 먼저 받는다 — 그래야 같은 변화를 두 번 세지 않는다
        self.assertLess(body.index("refreshProjects"), body.index("refreshCatalog"))

    def test_s7_the_undo_line_stands_where_the_doc_was_thrown(self):
        """버린 그 자리에 되돌리는 손이 선다 (REQ-20260910-006 ②).

        되돌릴 수 있는 일에만 되돌리는 손을 세우고, 완전히 지운 뒤에는 없는
        행동을 지어내지 않는다. 스스로 사라지지 않는다 — 몇 초 뒤에 접히는
        줄은 그때 화면을 안 보던 사람에게는 없는 줄이다."""
        vis = self._strings(self.js)
        self.assertIn("휴지통으로 보냈습니다", vis)
        self.assertIn("보관함으로 내렸습니다", vis)
        self.assertIn("문서 목록으로 되돌렸습니다.", vis)
        self.assertIn('data-tidy="undo"', self.js)
        self.assertIn('data-tidy="seetrash"', self.js)
        self.assertIn('data-tidy="undox"', self.js)
        body = self.js.split("function tidyUndoHTML()")[1].split("\n}\n")[0]
        self.assertIn('op === "rm" || op === "archive"', body,
                      "되돌릴 수 있는 일에만 되돌리는 손이 선다")
        self.assertNotIn("setTimeout", body, "스스로 사라지는 줄은 없는 줄이다")

    def test_s5_the_panel_opens_the_pile_that_is_not_empty(self):
        """한쪽이 0 이면 반대쪽부터 연다 — 둘 다 있으면 보관함 그대로."""
        self.assertIn('if (!na && nt) tidyTab = "trash";', self.js)
        self.assertIn('else if (na && !nt) tidyTab = "archived";', self.js)
        open_body = self.js.split("async function tidyOpen()")[1]
        self.assertLess(open_body.index("await tidyFetch()"),
                        open_body.index('tidyTab = "trash"'),
                        "탭은 **받아 온 뒤에** 고른다")

    def test_s6_the_empty_tab_points_at_the_other_pile(self):
        self.assertIn("${n}건이 있습니다.", self.js)
        self.assertIn('tidyTab === "trash" ? "보관함에" : "휴지통에"', self.js)
        self.assertIn("if (!n) return \"\";", self.js,
                      "반대쪽도 비었으면 둘째 줄은 서지 않는다")
        css = open(os.path.join(HERE, "..", "web", "css", "tidy.css"),
                   encoding="utf-8").read()
        self.assertIn(".tidypanel .tempty .tsub{", css)
        self.assertNotIn(".tidypanel .tempty{padding:22px 16px;color:var(--faint)",
                         css, "빈 상태는 읽어야 하는 글자다 — --faint 금지")
