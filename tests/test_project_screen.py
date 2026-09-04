"""프로젝트 화면의 계약 — 골격(mock) 몫 (REQ-20260831-028-62x6).

설계(REQ-20260831-026 designer 판정)가 정한 것은 **새 탭 0 · 새 화면 0** 이다.
프로젝트는 문서에 살고, 화면은 세 자리에 얹힌다 — Docs 좌측 목록 · PRJ 문서 뷰
패널 · Board 위 한 줄 띠. 이 파일이 지키는 것은 그 셋의 계약이다.

B2(실연동)에서 계약이 하나 늘었다 — **관문이 하나인가**. 골격은 기존 css 를 안
만지는 조건이라 멤버 표 규칙이 두 벌(`.proj-info`·`.pmem`)로 서 있었고, 저장도
두 벌(app.js `wireMemberControls`·project.js `prjPost`)이었다. 그 둘을 없앤 것이
이 물결의 첫 손이고, 되살아나는 것을 여기서 막는다.

계약은 셋으로 나뉜다.

  ① **읽어서 아는 것** (`web/app/project.js` · `web/css/project.css`) — 문구가
     한 곳에 모였는가, 저장 관문이 하나인가, 색을 리터럴로 적지 않았는가,
     `.proj-info` 를 복제하지 않았는가, 배율이 갈릴 기하를 새로 만들지 않았는가.
     스킨 열 벌이 저마다 색을 말해 둔 자리를 새로 그리면 그 순간 관문이 열
     곳이 된다(벨트 글리프 때의 그 함정).
  ② **띄워 봐야 아는 것** (`web/verify-project.html` + 실브라우저) — 상태마다
     무엇이 그려지는가. 권한이 없을 때 컨트롤이 **회색으로 있는 게 아니라
     없는가**, 멤버 0 인데 넣을 사람도 0 일 때 다른 문구가 서는가, 만료가
     붉은색이 아니라 물러난 색인가, 띠가 정말 한 줄(32px)인가.
     Chrome 이 없으면 그 갈래만 건너뛴다 — 읽어서 아는 것은 그래도 돈다.
  ③ **밟아 봐야 아는 것** (실서버 + 실브라우저) — 생성·멤버·설정·보관·거부를
     끝까지 밟는 시나리오. 이 파일에는 없다(라이브 vault 를 건드리지 않으려면
     격리 루트에 서버를 세워야 해서 느리다): 실측 결과와 캡처는 REQ 문서의
     response 노트에 있다.

실행: python3 tests/ project_screen
"""
import json
import os
import re
import subprocess
import time
import unittest
import urllib.error
import urllib.request

from cdpreal import WS, chrome_path, reclaim
from portpool import free_port, wait_server   # 포트 규율은 풀 한 곳에서

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")
JS = os.path.join(WEB, "app", "project.js")
CSS = os.path.join(WEB, "css", "project.css")
FIX = "verify-project.html"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def strip_comments(src):
    """/* … */ 와 // … 를 걷어낸다 — 계약은 코드가 하는 말만 본다."""
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    return re.sub(r"(?m)^\s*//.*$", "", src)


class TheWordsLiveInOnePlace(unittest.TestCase):
    """문구는 `PRJ_TEXT` 한 곳이다 — W2 의 판정이 표 하나만 갈아 끼우면 되게."""

    def test_the_words_live_in_one_place(self):
        """문구는 `PRJ_TEXT` 한 곳이다 — W2 의 판정이 표 하나만 갈아 끼우면 되게."""
        with self.subTest("no_korean_string_outside_the_table"):
            src = strip_comments(read(JS))
            m = re.search(r"const PRJ_TEXT = \{[\s\S]*?\n\};", src)
            self.assertTrue(m, "PRJ_TEXT 표가 없다")
            rest = src[:m.start()] + src[m.end():]
            stray = re.findall(r"""["'`][^"'`\n]*[가-힣][^"'`\n]*["'`]""", rest)
            self.assertEqual(
                stray, [],
                "화면 글자가 PRJ_TEXT 밖에 있다 — 문구 판정이 한 곳을 못 고친다: %r"
                % stray[:4])
        with self.subTest("no_key_is_written_twice"):
            src = read(JS)
            m = re.search(r"const PRJ_TEXT = \{([\s\S]*?)\n\};", src)
            keys = re.findall(r"(?m)^\s{2}(\w+):", m.group(1))
            dup = sorted({k for k in keys if keys.count(k) > 1})
            self.assertEqual(dup, [], "PRJ_TEXT 에 같은 이름이 둘 있다: %r" % dup)
        with self.subTest("the_fixture_calls_the_real_builders"):
            fix = read(os.path.join(WEB, FIX))
            for fn in ("prjListHTML", "prjPanelHTML", "prjStripHTML",
                       "prjCreateDlg", "prjWire"):
                self.assertIn(fn + "(", fix, "검증 자가 %s 를 부르지 않는다" % fn)
            for copied in ("dlghead", "dlgfoot", "dlgcap"):
                self.assertNotIn(copied, fix,
                                 "창 껍데기를 베꼈다(%s) — 진짜 창을 띄워라" % copied)

class TheSaveHasOneGate(unittest.TestCase):
    """설정 인라인이든 멤버 표든 한 문을 지난다 — 두 벌이면 한 벌만 고쳐진다."""

    def test_the_save_has_one_gate(self):
        """설정 인라인이든 멤버 표든 한 문을 지난다 — 두 벌이면 한 벌만 고쳐진다."""
        with self.subTest("only_one_fetch"):
            src = strip_comments(read(JS))
            self.assertEqual(
                len(re.findall(r"\bfetch\(", src)), 1,
                "요청을 보내는 자리가 둘 이상이다 — 저장 규칙이 갈라진다")
        with self.subTest("every_write_goes_through_prjpost"):
            src = strip_comments(read(JS))
            for path in ("/api/project/set", "/api/project/member",
                         "/api/project/member/rm", "/api/project/add"):
                for line in [ln for ln in src.splitlines() if path in ln]:
                    self.assertTrue(
                        re.search(r"\b(post|prjPost)\(", line),
                        "%s 가 관문(prjPost) 밖에서 불린다: %s" % (path, line.strip()))
        with self.subTest("nothing_asks_before_saving_a_value"):
            src = strip_comments(read(JS))

            def between(a, b):
                i = src.index(a)
                j = src.index(b, i)
                return src[i:j]

            st = between("stSel.addEventListener", 'querySelectorAll("[data-pjmem]")')
            self.assertNotIn("s9dlg(", st, "보관에 확인 창이 섰다")
            self.assertIn('post("/api/project/set"', st, "보관이 저장을 안 한다")
            edit = between('querySelectorAll("[data-pjset]")', "const stSel")
            self.assertNotIn("s9dlg(", edit, "값 하나 고치는데 창을 띄운다")
            self.assertIn('post("/api/project/set"', edit, "값 편집이 저장을 안 한다")
            # 창은 셋뿐 — 만들기 하나, 멤버 둘(제거·나가기)
            self.assertEqual(len(re.findall(r"s9dlg\(\{", src)), 3)
        with self.subTest("only_the_changed_field_goes_out"):
            src = strip_comments(read(JS))
            for line in [ln for ln in src.splitlines()
                         if '"/api/project/set"' in ln]:
                body = re.search(r'"/api/project/set",\s*\{([^}]*)\}', line)
                self.assertTrue(body, "set 요청 몸통을 못 읽었다: %s" % line.strip())
                self.assertEqual(body.group(1).count(":"), 1,
                                 "한 번에 여러 필드를 보낸다: %s" % line.strip())
        with self.subTest("the_screen_does_not_invent_refusals"):
            src = strip_comments(read(JS))
            self.assertIn("d.error", src, "서버 사유를 그리지 않는다")
            for word in ("권한이 없습니다", "실패했습니다", "오류"):
                self.assertNotIn(word, src, "화면이 거부 사유를 지어낸다: %s" % word)

class TheDialogIsBorrowed(unittest.TestCase):
    """창은 `s9dlg` 것이다 — 새 창 부품을 만들지 않는다."""

    def test_the_dialog_is_borrowed(self):
        """창은 `s9dlg` 것이다 — 새 창 부품을 만들지 않는다."""
        with self.subTest("it_calls_s9dlg"):
            self.assertIn("s9dlg({", strip_comments(read(JS)))
        with self.subTest("it_does_not_build_its_own_shell"):
            src = strip_comments(read(JS))
            for cls in ("dlghead", "dlgfoot", "dlgbox", "dlgcap"):
                self.assertNotIn(
                    '"' + cls, src,
                    "창 껍데기(%s)를 스스로 짓는다 — 창이 두 벌이 된다" % cls)
        with self.subTest("the_form_has_four_fields_only"):
            src = read(JS)
            body = re.search(r"function prjFormHTML\(v\)\{[\s\S]*?\n\}", src)
            self.assertTrue(body)
            got = re.findall(r'f\("(\w+)"', body.group(0))
            self.assertEqual(got, ["name", "slug", "summary", "customer"])
            self.assertNotIn("contact_", body.group(0),
                             "만들 때 담당자를 묻는다 — 그 창의 결정은 하나여야 한다")

class TheRulesSayNoColour(unittest.TestCase):
    """규칙 파일은 배치와 밀도만 말한다 — 색은 토큰에서만 온다."""

    def test_the_rules_say_no_colour(self):
        """규칙 파일은 배치와 밀도만 말한다 — 색은 토큰에서만 온다."""
        with self.subTest("no_colour_literal"):
            body = re.sub(r"/\*[\s\S]*?\*/", "", read(CSS))
            bad = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", body)
            self.assertEqual(bad, [], "색을 직접 적었다: %r" % bad)
        with self.subTest("no_round_no_shadow_no_side_bar"):
            body = re.sub(r"/\*[\s\S]*?\*/", "", read(CSS))
            self.assertNotIn("box-shadow", body, "그림자 금지")
            for m in re.findall(r"border-radius:([^;}]+)", body):
                self.assertEqual(m.strip(), "0", "라운드 금지")
            self.assertFalse(re.search(r"border-left:\s*[1-9]", body),
                             "카드 좌측 세로 띠 금지")
        with self.subTest("the_member_table_has_one_gate"):
            body = re.sub(r"/\*[\s\S]*?\*/", "", read(CSS))
            self.assertNotIn(".proj-info", body,
                             "기존 패널 셀렉터를 복제했다 — 관문이 둘이 된다")
            for name in os.listdir(os.path.join(WEB, "css")):
                if name == "project.css":
                    continue
                other = re.sub(r"/\*[\s\S]*?\*/", "",
                               read(os.path.join(WEB, "css", name)))
                self.assertNotIn(".pmem", other,
                                 "%s 가 멤버 표 규칙을 나눠 갖는다" % name)
        with self.subTest("expiry_is_not_a_fault"):
            body = re.sub(r"/\*[\s\S]*?\*/", "", read(CSS))
            self.assertIn(".pmem .m-off{color:var(--muted)}", body)
            for rule in re.findall(r"([^{}]+)\{[^{}]*--c-blocked[^{}]*\}", body):
                self.assertIn("pjerr", rule,
                              "붉은 잉크가 실패 줄 밖에서 쓰인다: %s" % rule.strip())
        with self.subTest("no_geometry_that_splits_at_1_25"):
            body = re.sub(r"/\*[\s\S]*?\*/", "", read(CSS))
            for prop, val in re.findall(
                    r"\b(width|height|min-height|min-width)\s*:\s*([0-9.]+)px", body):
                n = float(val)
                if (prop, val) in (("width", "7"), ("height", "7")):
                    continue                      # .cdot 무대 — 확정값
                self.assertEqual(n, int(n), "%s:%spx — 소수 치수" % (prop, val))
                self.assertEqual(int(n) % 2, 0,
                                 "%s:%spx — 홀수 치수는 1.25배에서 갈린다"
                                 % (prop, val))
            for w in re.findall(r"border[a-z-]*\s*:\s*([0-9.]+)px", body):
                self.assertEqual(float(w), 1.0, "소수/굵은 테두리: %spx" % w)

class TheTwoRulebooksBecameOne(unittest.TestCase):
    """B2 의 첫 손 — 규칙이 두 벌이던 자리를 없앤다.

    골격(B1)은 기존 css 를 만지지 않는 조건이라 멤버 표 규칙이 `.proj-info`(옛
    패널)와 `.pmem`(새 패널) 두 벌로 서 있었다. 두 벌인 채로 끝나면 관문이 둘이
    되고, 스킨 열 벌이 저마다 한 벌만 고친다 — 벨트 글리프 때 이 저장소가 이미
    치른 값이다. 되살아나는 것도 여기서 막는다."""

    def test_the_two_rulebooks_became_one(self):
        """B2 의 첫 손 — 규칙이 두 벌이던 자리를 없앤다."""
        with self.subTest("the_old_panel_rules_are_gone"):
            css = os.path.join(WEB, "css")
            for name in sorted(os.listdir(css)):
                body = re.sub(r"/\*[\s\S]*?\*/", "", read(os.path.join(css, name)))
                for dead in (".proj-info", ".pi-x", ".pi-err", ".pi-grid"):
                    self.assertNotIn(dead, body,
                                     "%s 에 옛 패널 규칙이 남아 있다: %s" % (name, dead))
        with self.subTest("the_old_panel_markup_is_gone"):
            app = strip_comments(read(os.path.join(WEB, "app", "app.js")))
            for dead in ("wireMemberControls", "pi-role", "pi-newuser", "pi-addrow"):
                self.assertNotIn(dead, app,
                                 "app.js 가 아직 멤버 표를 짓는다: %s" % dead)
        with self.subTest("the_row_grammar_is_one"):
            docs = strip_comments(read(os.path.join(WEB, "app", "docs.js")))
            self.assertIn("prjPanelHTML(", docs, "PRJ 문서 뷰에 패널이 없다")
            for gone in ("prjRowHTML(", "prjListHTML("):
                self.assertNotIn(gone, docs,
                                 "Docs 가 아직 프로젝트 목록을 그린다 — 문이 둘이다: %s"
                                 % gone)
            prj = strip_comments(read(JS))
            for fn in ("function prjRowHTML", "function prjListHTML",
                       "function renderProjects"):
                self.assertIn(fn, prj, "프로젝트 화면 조각이 흩어졌다: %s" % fn)
        with self.subTest("the_projects_list_is_off_the_polling_belt"):
            app = strip_comments(read(os.path.join(WEB, "app", "app.js")))
            body = app[app.index("async function refreshCatalog"):]
            body = body[:body.index("\nfunction ")]
            self.assertNotIn("refreshProjects", body,
                             "프로젝트 목록이 아직 폴링 벨트에 실려 있다")
            ev = strip_comments(read(os.path.join(WEB, "app", "events.js")))
            self.assertIn("refreshProjects", ev, "탭에 들어와도 목록을 안 받는다")
        with self.subTest("the_poll_does_not_wipe_a_hand_on_the_form"):
            js = strip_comments(read(JS))
            self.assertIn("function prjEditing", js, "편집 중인지 묻는 자가 없다")
            docs = strip_comments(read(os.path.join(WEB, "app", "docs.js")))
            m = re.search(r"if \(selectedDoc && [^\n]*prjEditing[^\n]*\)\s*\n?"
                          r"\s*loadDoc\(selectedDoc, !fresh\);", docs)
            self.assertTrue(m, "배경 재로드에 편집 가드가 없다")
            # 가드가 서는 자리는 **배경 갱신**뿐이다 — 배선(prjWire) 안에 들이면
            # 변이 뒤의 되읽기까지 물린다. 창은 그 함수 하나로 자른다: 파일 끝까지
            # 자르면 뒤에 선 판(renderProjects)의 정당한 가드를 되읽기로 오해한다.
            i = js.index("function prjWire")
            wire = js[i:js.index("\n}", i)]
            self.assertIn("o.reload", js, "되읽기 손을 부르는 쪽에서 받지 않는다")
            self.assertNotIn("prjEditing", wire, "되읽기까지 가드에 물렸다")
        with self.subTest("the_reread_after_a_change_always_redraws"):
            docs = strip_comments(read(os.path.join(WEB, "app", "docs.js")))
            self.assertRegex(docs, r"function loadDoc\(id, bg, force\)",
                             "되읽기와 배경 갱신을 가를 자가 없다")
            self.assertRegex(docs, r"if \(bg && !force &&",
                             "건너뛰기 문이 force 를 안 본다")
            self.assertRegex(docs, r"reload: async \(\) => \{[\s\S]{0,400}?"
                                   r"loadDoc\(id, true, true\)",
                             "되읽기가 다시 그리기를 강제하지 않는다")
        with self.subTest("the_project_doc_has_one_archive"):
            tidy = strip_comments(read(os.path.join(WEB, "app", "tidy.js")))
            i = tidy.index('data-tidy="${arch ? "unarch1" : "arch1"}"')
            head = tidy[max(0, i - 400):i]
            self.assertIn('type === "project"', head,
                          "프로젝트 문서에서도 문서 치우기 「보관」이 선다")

# ─── 띄워 봐야 아는 것 ────────────────────────────────────────────────────

PROBE = r"""
(() => {
  const q = (s, r) => (r || document).querySelector(s);
  const qa = (s, r) => [...(r || document).querySelectorAll(s)];
  const cases = qa(".case");
  const byTitle = t => cases.find(c => q("h2", c).textContent.includes(t));
  const cs = (el, p) => getComputedStyle(el).getPropertyValue(p);
  const resolve = v => { const e = document.createElement("span");
    e.style.color = v; document.body.appendChild(e);
    const c = getComputedStyle(e).color; e.remove(); return c; };
  const listN = byTitle("N개"), list0 = byTitle("0개"),
        list1 = byTitle("1개"), listNo = byTitle("만들 권한 없음"),
        pOwner = byTitle("owner (전부"), pMaint = byTitle("maintainer"),
        pView = byTitle("뷰어"), pNoMem = byTitle("넣을 사람 있음"),
        pNoUser = byTitle("등록 사용자도 0"), strip = byTitle("32px 한 줄"),
        listArc = byTitle("보관 펼침"), stripArc = byTitle("보관됨");
  const rows = qa(".pjrow", listN);
  const ownerTr = q('[data-pjmem="nicehugepark"]', pOwner);
  const maintOwnerTr = q('[data-pjmem="nicehugepark"]', pMaint);
  const stripEl = q(".pjstrip", strip);
  const expTr = qa(".pmem tr.exp", pOwner)[0];
  const soonInp = q('[data-pjmem="e7test"] [data-pjuntil]', pOwner);
  return {
    rowIds: rows.map(r => r.dataset.doc),
    rowMeta: rows.map(r => q(".pjmeta", r).textContent),
    rowStatus: rows.map(r => q(".st", r).textContent),
    listNCreate: !!q("[data-prjnew]", listN),
    list0Create: !!q("[data-prjnew]", list0),
    list0None: (q(".pjnone", list0) || {}).textContent || "",
    list1Head: !!q(".pjhead", list1),
    list1Create: !!q("[data-prjnew]", list1),
    listNoCreate: !!q("[data-prjnew]", listNo),
    fold: (q("[data-prjarc]", listN) || {}).textContent || "",
    ownerControls: qa(".pmem select, .pmem input", pOwner).length,
    viewControls: qa(".pmem select, .pmem input, .pmem button", pView).length,
    viewNote: (q(".pjnote", pView) || {}).textContent || "",
    viewSetEdit: qa("[data-pjset]", pView).length,
    viewSetRows: qa(".pjset tr", pView).length,
    ownerSetRows: qa(".pjset tr", pOwner).length,
    maintOwnerRoleDisabled: q("[data-pjrole]", maintOwnerTr).disabled,
    maintOwnerRoleTitle: q("[data-pjrole]", maintOwnerTr).title,
    ownerRmDisabled: q("[data-pjrm]", ownerTr).disabled,
    rmOffColour: cs(q("[data-pjrm]", ownerTr), "color"),
    rmOnColour: cs(q('[data-pjmem="e7test"] [data-pjrm]', pOwner), "color"),
    ownerRmTitle: q("[data-pjrm]", ownerTr).title,
    ownerRmAria: q("[data-pjrm]", ownerTr).getAttribute("aria-label"),
    caption: q(".pmem caption", pOwner).textContent,
    scopes: qa(".pmem th", pOwner).map(th => th.getAttribute("scope")),
    addRow: !!q(".pjadd", pNoMem),
    noUserTable: !!q(".pmem", pNoUser),
    noUserLink: (q(".pjnote a", pNoUser) || {}).getAttribute
      ? q(".pjnote a", pNoUser).getAttribute("href") : "",
    expColour: expTr ? cs(q(".m-state", expTr), "color") : "",
    // 토큰을 **화면이 푸는 그대로** 재 온다 — `--muted` 는 #hex 로 돌아오고
    // color 는 rgb() 로 돌아와 글자끼리는 견줄 수 없다
    mutedColour: resolve("var(--muted)"),
    blockedColour: resolve("var(--c-blocked)"),
    soonClass: soonInp ? soonInp.className : "",
    stripH: Math.round(stripEl.getBoundingClientRect().height),
    stripLines: qa(".pjstrip > *", stripEl).length,
    stripBorderLeft: cs(stripEl, "border-left-width"),
    stripBg: cs(stripEl, "background-color"),
    stripTable: !!q("table", stripEl),
    stripOpen: (q(".pjs-open", stripEl) || {}).className || "",
    dlgFields: qa("[data-pjf]").map(e => e.dataset.pjf),
    dlgYesDisabled: q(".dlgyes").disabled,
    stripNone: prjStripHTML(null, {}),
    // ── B2: 029 확정 문구 · 리드 판정 ──────────────────────────────────
    createText: q("[data-prjnew]", listN).textContent,
    createAria: q("[data-prjnew]", listN).getAttribute("aria-label"),
    createInk: cs(q("[data-prjnew]", listN), "color"),
    faintColour: resolve("var(--faint)"),
    arcText: q("[data-prjarc]", listN).textContent,
    arcExpanded: q("[data-prjarc]", listN).getAttribute("aria-expanded"),
    arcOpenText: q("[data-prjarc]", listArc).textContent,
    arcOpenExpanded: q("[data-prjarc]", listArc).getAttribute("aria-expanded"),
    arcRowsHidden: qa(".pjrow.off", listN).length,
    arcRowsShown: qa(".pjrow.off", listArc).length,
    stripArcSt: (q(".pjs-st", stripArc) || {}).textContent || "",
    stripActSt: (q(".pjs-st", strip) || {}).textContent || "",
    stripMeta: qa(".pjs-m", strip).map(e => e.textContent),
    legendOwner: !!q(".pjlegend", pOwner),
    legendView: !!q(".pjlegend", pView),
    selfRmText: q("[data-pjrm]", ownerTr).textContent,
    otherRmText: q('[data-pjmem="e7test"] [data-pjrm]', pOwner).textContent,
    otherRmAria: q('[data-pjmem="e7test"] [data-pjrm]', pOwner)
      .getAttribute("aria-label"),
    capPlain: q("#failhost .pjpanel caption").textContent,
    colHeads: qa(".pmem th", pOwner).map(t => t.textContent.trim()),
    slugNote: !!q(".pjset .pjhint", pOwner),
    slugEditable: !!q('.pjset [data-pjset="slug"]', pOwner),
    statusSelect: !!q("[data-pjstatus]", pOwner),
    setKeys: qa("[data-pjset]", pOwner).map(e => e.dataset.pjset),
    soonTip: soonInp ? soonInp.title : "",
  };
})()
"""

TYPE = r"""
(() => {
  const q = s => document.querySelector(s);
  const set = (sel, v) => { const e = q(sel); e.value = v;
    e.dispatchEvent(new Event("input", {bubbles: true})); };
  set('[data-pjf="name"]', %s);
  return {slug: q('[data-pjf="slug"]').value,
          yes: q(".dlgyes").disabled,
          err: q(".pjform .pjerr").textContent,
          errShown: !q(".pjform .pjerr").hidden};
})()
"""

FAIL = r"""
(() => {
  const p = document.querySelector('#failhost .pjpanel');
  const sel = p.querySelector('[data-pjmem="nicehugepark"] [data-pjrole]');
  const was = sel.value;
  sel.value = "maintainer";
  sel.dispatchEvent(new Event("change", {bubbles: true}));
  return new Promise(r => setTimeout(() => {
    const now = document.querySelector('#failhost .pjpanel');
    const line = now.querySelector(".pjerr");
    r({was, back: now.querySelector('[data-pjmem="nicehugepark"] [data-pjrole]').value,
       shown: !line.hidden, text: line.textContent});
  }, 160));
})()
"""

SAVE = r"""
(() => {
  const p = [...document.querySelectorAll(".pjpanel")]
    .find(x => x.dataset.pjslug === "section9");
  const line = p.querySelector(".pjerr");
  const sel = p.querySelector('[data-pjmem="e7test"] [data-pjrole]');
  // ① 값이 그대로면 아무것도 나가지 않는다 (같은 값 재선택 = 요청 0회)
  sel.dispatchEvent(new Event("change", {bubbles: true}));
  return new Promise(r => setTimeout(() => {
    const idle = line.textContent;
    // ② 값이 바뀌면 한 번 나간다
    sel.value = "viewer";
    sel.dispatchEvent(new Event("change", {bubbles: true}));
    setTimeout(() => r({idle, sent: line.textContent}), 120);
  }, 120));
})()
"""


def probe(scale=1.0):
    """검증 자를 실브라우저에 띄워 DOM 을 재 온다 (없으면 SkipTest)."""
    chrome = chrome_path()
    if chrome is None:
        raise unittest.SkipTest("실브라우저 미검증 — Chrome/Edge 를 찾지 못했다")
    win = chrome.startswith("/mnt/")
    marker = "s9prj-%d" % os.getpid()
    prof_wsl = ("/mnt/c/Temp/" + marker) if win else "/tmp/" + marker
    prof_arg = ("C:\\Temp\\" + marker) if win else prof_wsl
    if win:
        os.makedirs("/mnt/c/Temp", exist_ok=True)
    # 검증 자는 조각(css/·app/)을 상대 주소로 부른다 — 파일 하나가 아니라
    # 자리(web/)를 통째로 내주는 정적 서버가 필요하다. 포트는 풀에서 빌리고
    # 기다림은 백오프로 (tests/portpool.py 의 규율).
    port = free_port()
    srv = subprocess.Popen(
        ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=WEB, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_server(port)
        url = "http://127.0.0.1:%d/%s" % (port, FIX)
        proc = subprocess.Popen(
            [chrome, "--headless=new", "--disable-gpu",
             "--user-data-dir=" + prof_arg, "--no-first-run",
             "--no-default-browser-check", "--disable-extensions",
             "--disable-background-networking", "--remote-debugging-port=0",
             "--force-device-scale-factor=%g" % scale,
             "--window-size=1280,900", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws = None
        try:
            dev = os.path.join(prof_wsl, "DevToolsActivePort")
            cdp = None
            for _ in range(120):
                if os.path.exists(dev):
                    try:
                        cdp = int(open(dev, encoding="utf-8")
                                  .read().splitlines()[0])
                        break
                    except (ValueError, IndexError, OSError):
                        pass
                time.sleep(0.25)
            if cdp is None:
                raise ConnectionError("DevToolsActivePort 미출현")
            pages = json.loads(urllib.request.urlopen(
                "http://127.0.0.1:%d/json/list" % cdp, timeout=10).read())
            page = next(p for p in pages if p.get("type") == "page")
            ws = WS(page["webSocketDebuggerUrl"])
            # 판이 **실제로 섰는지**를 묻는다 — readyState=="complete" 는
            # about:blank 에서도 참이다. 스위트를 병렬로 돌리면 붙는 순간의
            # 탭이 아직 이동 전이라 빈 판을 재고, 그 위의 모든 물음이
            # null.disabled 로 죽어 열넷이 한꺼번에 ERROR 로 나온다
            # (전체 실행에서 실제로 그랬다 — 단독 실행에서는 안 났다).
            for _ in range(160):
                if ws.eval("document.querySelectorAll('.case').length"):
                    break
                time.sleep(0.25)
            else:
                raise ConnectionError("검증 자가 판을 세우지 못했다")
            out = {"dom": ws.eval(PROBE)}
            out["typed"] = ws.eval(TYPE % json.dumps("고객사 포털 개편"))
            out["typedAscii"] = ws.eval(TYPE % json.dumps("Portal Rework"))
            out["taken"] = ws.eval(TYPE % json.dumps("section9"))
            r = ws.call("Runtime.evaluate", expression=SAVE,
                        returnByValue=True, awaitPromise=True)
            out["saved"] = r.get("result", {}).get("value")
            r = ws.call("Runtime.evaluate", expression=FAIL,
                        returnByValue=True, awaitPromise=True)
            out["failed"] = r.get("result", {}).get("value")
            # 못 잰 것을 **잰 척하지 않는다** — 하나라도 비면 그 자리에서 말한다
            # (안 그러면 시험마다 'NoneType' 이 열넷 쏟아져 원인이 묻힌다).
            for k, v in out.items():
                if v is None:
                    raise ConnectionError("검증 자에서 %s 를 재지 못했다" % k)
            return out
        finally:
            if ws is not None:
                ws.close()
            try:
                proc.terminate()
            except OSError:
                pass
            reclaim(marker, win)
    finally:
        srv.terminate()
        import shutil
        shutil.rmtree(prof_wsl, ignore_errors=True)


class TheStatesAreAllDrawn(unittest.TestCase):
    """상태 전부 — 0·1·N · 보관 · 권한 셋 · 멤버 0 두 갈래 · 만료 · 띠."""

    out = None

    @classmethod
    def setUpClass(cls):
        try:
            cls.out = probe()
        except (ConnectionError, StopIteration, OSError,
                RuntimeError, urllib.error.URLError) as e:
            raise unittest.SkipTest("실브라우저 미검증 — CDP 실패: %r" % e)

    @property
    def d(self):
        return self.out["dom"]

    def test_the_states_are_all_drawn(self):
        """상태 전부 — 0·1·N · 보관 · 권한 셋 · 멤버 0 두 갈래 · 만료 · 띠."""
        with self.subTest("the_list_sorts_by_recent_work"):
            self.assertEqual(self.d["rowIds"],
                             ["PRJ-20260823-001", "PRJ-20260901-002"])
            self.assertIn("멤버 2", self.d["rowMeta"][0])
            self.assertIn("열린 요청 12", self.d["rowMeta"][0])
            self.assertIn("마지막 활동 4분 전", self.d["rowMeta"][0])
            # 정상은 말하지 않는다 — active 는 글자를 안 받는다 (REQ-20260830-040)
            self.assertEqual(self.d["rowStatus"], ["", ""])
        with self.subTest("archived_folds_and_says_what_is_folded"):
            self.assertEqual(self.d["fold"], "보관된 프로젝트 1개")
            self.assertEqual(self.d["arcExpanded"], "false")
            self.assertEqual(self.d["arcOpenText"], "접기")
            self.assertEqual(self.d["arcOpenExpanded"], "true")
            self.assertEqual(self.d["arcRowsHidden"], 0, "접었는데 보관된 줄이 섰다")
            self.assertEqual(self.d["arcRowsShown"], 1, "펼쳤는데 보관된 줄이 안 섰다")
        with self.subTest("zero_and_one_keep_the_same_shape"):
            # 빈 자리의 말은 **문장**이다 — 한 낱말(「없음」)은 안내도 행동도 아니다
            self.assertIn("프로젝트가 없습니다", self.d["list0None"])
            self.assertTrue(self.d["list0Create"])
            self.assertTrue(self.d["list1Head"])
            self.assertTrue(self.d["list1Create"])
        with self.subTest("without_the_right_the_button_is_gone_not_grey"):
            self.assertTrue(self.d["listNCreate"])
            self.assertFalse(self.d["listNoCreate"],
                             "만들 권한이 없는데 단추가 그려졌다 — 회색 단추는 "
                             "눌릴 것 같은 거짓 약속이다")
        with self.subTest("the_viewer_sees_values_not_dead_controls"):
            self.assertGreater(self.d["ownerControls"], 0)
            self.assertEqual(self.d["viewControls"], 0,
                             "뷰어에게 컨트롤을 그렸다")
            self.assertEqual(self.d["viewSetEdit"], 0,
                             "뷰어에게 설정 편집 자리를 그렸다")
            # 축을 밝힌다 — Settings 의 시스템 role 에도 viewer 가 있다(tech-writer)
            self.assertIn("maintainer 이상", self.d["viewNote"])
            self.assertFalse(self.d["legendView"],
                             "못 바꾸는 사람에게 권한 범례를 세웠다")
        with self.subTest("an_empty_slot_is_a_place_only_for_who_can_fill_it"):
            self.assertGreater(self.d["ownerSetRows"], self.d["viewSetRows"],
                               "빈 칸이 고칠 수 없는 사람에게도 자리를 차지한다")
        with self.subTest("only_the_owner_row_is_grey"):
            self.assertTrue(self.d["maintOwnerRoleDisabled"])
            self.assertIn("owner", self.d["maintOwnerRoleTitle"])
        with self.subTest("the_last_owner_cannot_be_removed"):
            self.assertTrue(self.d["ownerRmDisabled"])
            self.assertIn("마지막 owner", self.d["ownerRmTitle"])
        with self.subTest("leaving_is_not_removing"):
            self.assertIn("나가기", self.d["selfRmText"])
            self.assertIn("제거", self.d["otherRmText"])
            self.assertIn("e7test", self.d["otherRmAria"])
            self.assertIn("section9", self.d["ownerRmAria"])
        with self.subTest("a_dead_button_looks_dead"):
            self.assertNotEqual(self.d["rmOffColour"], self.d["rmOnColour"],
                                "잠긴 「제거」가 살아 있는 것과 같은 잉크다")
        with self.subTest("the_table_names_itself_and_its_columns"):
            # 만료가 없으면 「만료 0」을 세우지 않는다 — 없는 문제를 보고하는 꼴이다
            self.assertEqual(self.d["caption"], "멤버 3명 — 활성 2 · 만료 1")
            self.assertEqual(self.d["capPlain"], "멤버 1명")
            # 한 화면에 상태 축이 둘이다(프로젝트 status · 멤버십) — 열 이름이 가른다
            self.assertIn("참여 상태", self.d["colHeads"])
            self.assertTrue(self.d["legendOwner"],
                            "권한을 바꿀 수 있는데 role 넷의 뜻이 어디에도 없다")
            self.assertTrue(all(s == "col" for s in self.d["scopes"]),
                            "열 머리에 scope 가 없다 — 읽어 주는 화면이 표를 못 읽는다")
        with self.subTest("no_members_gives_an_action_or_a_way_out"):
            self.assertTrue(self.d["addRow"], "넣을 사람이 있는데 추가 행이 없다")
            self.assertFalse(self.d["noUserTable"],
                             "후보가 0명인데 추가 폼을 보여 준다 — 막다른 길이다")
            self.assertEqual(self.d["noUserLink"], "#settings/users")
        with self.subTest("expiry_is_muted_not_red"):
            self.assertEqual(self.d["expColour"], self.d["mutedColour"],
                             "만료 잉크가 --muted 가 아니다")
            self.assertNotEqual(self.d["expColour"], self.d["blockedColour"],
                                "만료를 고장(붉은 잉크)으로 그렸다")
            self.assertIn("m-soon", self.d["soonClass"],
                          "만료 14일 이내인데 임박 잉크가 없다")
            # 「만료 14일 이내」는 기준선이지 사실이 아니다 — 시간은 사람 단위로
            self.assertRegex(self.d["soonTip"], r"^\d+일 뒤 만료$")
        with self.subTest("the_door_is_visible_and_says_what_it_makes"):
            self.assertEqual(self.d["createText"], "프로젝트 만들기")
            self.assertIn("만듭니다", self.d["createAria"])
            self.assertNotEqual(self.d["createInk"], self.d["faintColour"],
                                "문을 화면에서 가장 옅은 잉크로 그렸다")
            self.assertEqual(self.d["createInk"], self.d["mutedColour"])
        with self.subTest("the_settings_grid_is_one_dictionary"):
            self.assertEqual(self.d["setKeys"],
                             ["name", "summary", "customer", "contact_name",
                              "contact_org", "contact_email", "contact_phone"])
            self.assertFalse(self.d["slugEditable"], "slug 를 고칠 수 있게 그렸다")
            self.assertTrue(self.d["slugNote"], "고칠 수 없는 칸에 까닭이 없다")
            self.assertTrue(self.d["statusSelect"])
        with self.subTest("the_strip_is_one_line"):
            self.assertEqual(self.d["stripH"], 32,
                             "문맥 띠가 한 줄(32px)이 아니다 — 244px 표를 대신하는 자리다")
            self.assertFalse(self.d["stripTable"], "띠에 표가 남아 있다")
            self.assertEqual(self.d["stripBorderLeft"], "0px", "좌측 세로 띠 금지")
            self.assertIn(self.d["stripBg"],
                          ("rgba(0, 0, 0, 0)", "transparent"), "색면 금지")
            self.assertIn("doclink", self.d["stripOpen"])
            # 정상은 말하지 않는다 — 보관만 글자를 받고, 값은 영문 원문이다
            self.assertEqual(self.d["stripActSt"], "")
            self.assertEqual(self.d["stripArcSt"], "archived")
            # 세 자리가 같은 낱말로 같은 것을 센다 (ux-writer 판정 7)
            self.assertTrue(any("열린 요청" in t for t in self.d["stripMeta"]),
                            "띠가 목록·요약과 다른 낱말로 센다")
        with self.subTest("the_form_asks_four_things"):
            self.assertEqual(self.d["dlgFields"],
                             ["name", "slug", "summary", "customer"])
            self.assertTrue(self.d["dlgYesDisabled"],
                            "빈 창인데 확인이 눌린다 — 눌러 보고 다그치는 창이 된다")
        with self.subTest("the_slug_candidate_never_guesses_korean"):
            self.assertEqual(self.out["typed"]["slug"], "")
            self.assertTrue(self.out["typed"]["yes"])
            self.assertTrue(self.out["typed"]["errShown"])
            self.assertIn("slug", self.out["typed"]["err"])
            self.assertEqual(self.out["typedAscii"]["slug"], "portal-rework")
            self.assertFalse(self.out["typedAscii"]["yes"])
        with self.subTest("a_taken_name_is_told_on_the_spot"):
            self.assertTrue(self.out["taken"]["yes"], "중복인데 만들 수 있다")
            # 「이미 있는 이름입니다」는 **무엇과** 부딪혔는지를 말하지 않는다
            self.assertIn("이미 section9", self.out["taken"]["err"])
        with self.subTest("a_member_change_goes_out_once_through_the_gate"):
            self.assertEqual(self.out["saved"]["idle"], "",
                             "값이 그대로인데 요청이 나갔다")
            self.assertIn("/api/project/member", self.out["saved"]["sent"])
            self.assertIn('"role":"viewer"',
                          self.out["saved"]["sent"].replace(" ", ""))
        with self.subTest("the_strip_has_no_place_without_a_project"):
            self.assertEqual(self.d["stripNone"], "",
                             "고른 프로젝트가 없는데 띠가 자리를 먹는다")
        with self.subTest("a_refusal_puts_the_control_back_and_says_why"):
            f = self.out["failed"]
            self.assertEqual(f["back"], f["was"], "거부당했는데 화면에 바뀐 값이 남았다")
            self.assertTrue(f["shown"], "거부 사유가 안 보인다")
            self.assertIn("maintainer 이상이 필요합니다", f["text"],
                          "서버가 준 문장이 아니라 화면이 지어낸 말이 섰다")

