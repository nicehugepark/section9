"""담당자 화면 — 누가 만들고 누가 맡았나, 그리고 그 자리를 옮기는 손잡이
(REQ-20260902-021-62x6, DOC-20260902-001 §2 축1+2).

`user` 가 **담당자**로 재정의되면서(D2) 화면이 답해야 할 물음이 늘었다: 배지의
이름이 만든 사람인가 맡은 사람인가, 이 요청은 어느 컴퓨터에서 도는가, 여기서
이어받을 수 있는가. 이 파일이 그 계약이다.

계약은 여섯이다.

  ① **화면은 내부어를 모른다.** `lease`·`claim`·`takeover`·`assignee` 는 사람이
     치는 낱말이 아니라 코드가 자기끼리 쓰는 말이다 — 사용자에게 보이는 글자
     (본문·title)에 한 번도 서지 않는다. 화면에 서는 것은 「담당」·「만든이」·
     「이 컴퓨터에서 이어서 하기」다.
  ② **모르는 것을 지어내지 않는다.** origin 이 빈 값인 옛 문서는 「기록 없음」이
     아니라 **아무것도 안 그린다** (D6 — 파일을 고치지 않고 읽을 때 맞춘다).
  ③ **시계는 하나다.** 화면의 리스 만료 초는 bin/s9 의 `DOC_LEASE_TTL` 과 같은
     수여야 한다. 갈라지면 화면이 「진행 중」이라 쓴 카드를 서버는 free 로 보고
     작업자를 띄운다 (`SLOW_WIN`↔`STALLED_WIN` 이 세운 그 규율).
  ④ **진행 축은 한 줄이다.** 다른 컴퓨터가 쥐고 있으면 그 줄이 사다리 맨 위에
     서고 아래(중단·멈춤·오래 걸림)는 서지 않는다 — 저쪽에서 도는 것을 여기서
     「멈춤」이라 적으면 점과 줄이 서로 다른 말을 한다.
  ⑤ **판정도 문구도 서버 한 곳이다.** 권한 없는 사람에게 손잡이를 숨기지 않고,
     서버의 거부 문장을 그대로 옮긴다. 화면이 권한 표를 한 벌 더 들지 않는다.
  ⑥ **새 층을 만들지 않는다.** 색면 하이라이트·카드 좌측 세로 띠 없이, 카드가
     이미 쓰는 메타 줄(.m)과 한 줄 문법(.rvpt)과 행위 버튼(.deed)을 입는다.

실행: python3 tests/ assign_screen
"""
import os
import re
import unittest

from webasset import index_path   # 브라우저가 받는 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
CSS = os.path.join(os.path.dirname(HERE), "web", "css", "actions.css")

# 화면에 서면 안 되는 낱말. 사람이 터미널에 치는 것은 `s9 assign` 하나뿐이고,
# 아래 넷은 그마저도 아니다 — 코드가 자기끼리 쓰는 말이다.
INNER = ("lease", "claim", "takeover", "assignee", "리스", "클레임")

# 화면에 **서야 하는** 낱말 (ux-writer·tech-writer·translator 판정본).
WORDS = ("만든 사람", "맡은 사람", "사람이 직접", "에이전트",
         "다른 컴퓨터", "에서 진행 중", "이 컴퓨터에서 이어서 하기", "담당 바꾸기",
         "백그라운드 작업", "리드")


def _grab(src, name):
    m = re.search(r"function %s\([^)]*\)\{[\s\S]*?\n\}" % name, src)
    assert m, name
    return m.group(0)


def _decomment(s):
    s = re.sub(r"/\*[\s\S]*?\*/", " ", s)
    return re.sub(r"^\s*//.*$", " ", s, flags=re.M)


def _visible(src):
    """사람 눈에 닿는 글자만 — 본문 텍스트와 title/aria 값.

    식별자(`data-takeover`)·경로(`/api/claim_takeover`)·필드(`r.lease`)는 화면이
    아니라 배선이므로 여기서 걸러진다. 걸러진 뒤에도 내부어가 남으면 그것은
    정말로 사람이 읽는 자리에 있는 것이다.
    """
    s = _decomment(src)
    out = []
    out += re.findall(r'title="([^"]*)"', s)
    out += re.findall(r'aria-label="([^"]*)"', s)
    out += re.findall(r'placeholder="([^"]*)"', s)
    # 인라인 HTML 의 텍스트 노드 — 태그와 태그 사이
    out += re.findall(r">([^<>`{}]*)<", s)
    # 창을 짓는 자리의 낱말 인자 (cap·ok·sub·label·desc·title·empty·idle)
    out += re.findall(
        r'\b(?:cap|ok|cancel|sub|label|desc|title|empty|idle|pickNote|'
        r'placeholder)\s*:\s*"([^"]*)"', s)
    # 문자열 조각 중 한글을 문 것 (템플릿 리터럴 안의 문장)
    out += [t for t in re.findall(r"[\"'`]([^\"'`]*)[\"'`]", s)
            if re.search(r"[가-힣]", t)]
    return [t for t in out if t.strip()]


class Screen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(index_path(), encoding="utf-8") as f:
            cls.src = f.read()
        with open(S9_SRC, encoding="utf-8") as f:
            cls.s9 = f.read()
        with open(CSS, encoding="utf-8") as f:
            cls.css = f.read()
        cls.parts = {n: _grab(cls.src, n) for n in (
            # `originFace` 는 사람이 아닌 것이 만들었을 때의 **이름**을 짓는 한
            # 자리다 (REQ-20260911-016) — 「에이전트 …」가 이제 여기 산다.
            "originWho", "originFace", "originBits", "lineageChip", "lineageTell",
            "lineageRowHTML", "leaseElsewhere", "canTakeover",
            "elsewhereRowHTML", "assignBtnHTML", "ownerBadgeHTML",
            "badgeFace",
            "assignDoc", "assignPick", "takeoverDoc", "stallHTML",
            "cardHTML",
            # 담당 컴퓨터 (REQ-20260910-017-62x6)
            "waitingMachine", "waitingWords", "waitingRowHTML",
            "machineBtnHTML", "machineDoc")}
        cls.mine = "\n".join(cls.parts[n] for n in (
            "originWho", "originFace", "originBits", "lineageChip", "lineageTell",
            "lineageRowHTML", "leaseElsewhere", "canTakeover",
            "elsewhereRowHTML", "assignBtnHTML", "ownerBadgeHTML",
            "assignDoc", "takeoverDoc",
            "waitingWords", "waitingRowHTML", "machineBtnHTML", "machineDoc"))

    # ---- ① 화면은 내부어를 모른다 ------------------------------------------
    def test_screen(self):
        """Screen 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("a1_no_inner_words_where_people_read"):
            for text in _visible(self.mine):
                for w in INNER:
                    self.assertNotIn(w.lower(), text.lower(),
                                     f"내부어 '{w}' 가 화면 글자에 섰다: {text!r}")
        with self.subTest("a2_the_words_that_should_stand"):
            seen = " ".join(_visible(self.mine))
            for w in WORDS:
                self.assertIn(w, seen, f"화면 낱말 '{w}' 가 사라졌다")
        with self.subTest("a4_the_machine_in_charge_stands"):
            # 담당 컴퓨터 (REQ-20260910-017-62x6): 기다리는 줄과 지름길의 낱말.
            # 「가져오기」는 이 화면에서 이미 다른 뜻이라 여기서는 쓰지 않는다.
            mach = "\n".join(self.parts[n] for n in
                              ("waitingRowHTML", "machineBtnHTML", "machineDoc"))
            self.assertIn("을 기다리는 중", mach)
            self.assertIn("이 컴퓨터로 바꾸기", mach)
            self.assertIn("담당 컴퓨터 바꾸기", mach)
            self.assertNotIn("가져오기", mach)
            self.assertIn("어느 컴퓨터에서나", mach)
            # 맡기기 (REQ-20260910-003-t8rc): 일을 받을 수 있는 컴퓨터인지가
            # **고르는 자리에** 선다. 맡기기 스위치는 컴퓨터마다 따로이고
            # 저장소에 실리지 않아(무인 실행 스위치다), 배정하는 쪽에서는
            # 저쪽이 꺼져 있는 것을 볼 길이 없었다 — 배정된 요청이 나흘 동안
            # 조용히 걸러졌다. 줄에도 적고, 골랐을 때 확인 줄도 말한다.
            self.assertIn("맡기기 꺼짐", self.src)
            self.assertIn("맡기기 켜짐", self.src)
            self.assertIn("takesWord(v)", mach, "목록 줄에 맡기기가 서지 않는다")
            i = mach.index("confirm:")
            self.assertIn("맡기기가 꺼져 있어", mach[i:i + 700],
                          "꺼진 컴퓨터를 골라도 확인 줄이 아무 말도 하지 않는다")
            # 손잡이가 길에 이어져 있다 (events.js)
            self.assertIn('closest("[data-machset]")', self.src)
            # 바꾸는 길은 서버 한 곳 — 화면이 프론트매터를 직접 쓰지 않는다
            self.assertIn('"/api/machines"', self.s9)
            self.assertIn('"needs_machine": req.get("needs_machine")', self.s9)

        with self.subTest("a3_role_names_are_not_translated"):
                who = self.parts["originWho"] + self.parts["originFace"]
                self.assertIn('a.slice(4)', who, "sub:<역할> 은 역할 이름 그대로여야 한다")
                self.assertIn("리드", who)
                self.assertIn("백그라운드 작업", who)

            # ---- ② 모르는 것을 지어내지 않는다 -------------------------------------
        with self.subTest("b1_old_docs_draw_nothing"):
            self.assertNotIn("기록 없음", " ".join(_visible(self.src)))
            bits = _decomment(self.parts["originBits"])
            self.assertRegex(bits, r"if\s*\(!o\)\s*return\s*\[\]",
                             "origin 이 없으면 빈 목록으로 물러나야 한다")
        with self.subTest("b2_creator_falls_back_like_the_server"):
                self.assertRegex(self.src, r"docCreator\s*=\s*r\s*=>[\s\S]{0,80}"
                                           r"r\.creator \|\| r\.user")
                self.assertRegex(self.s9, r"def doc_creator\(meta\):[\s\S]{0,400}?"
                                          r'get\("creator"\)[\s\S]{0,60}?get\("user"\)')

            # ---- ③ 시계는 하나다 ----------------------------------------------------
        with self.subTest("c1_one_clock_for_the_lease"):
            m = re.search(r"const LEASE_TTL = (\d+);", self.src)
            self.assertTrue(m, "화면에 LEASE_TTL 이 없다")
            g = re.search(r"^CLAIM_GRACE = (\d+)", self.s9, re.M)
            self.assertTrue(g, "bin/s9 에 CLAIM_GRACE 가 없다")
            self.assertIn("DOC_LEASE_TTL = CLAIM_GRACE", self.s9)
            self.assertEqual(int(m.group(1)), int(g.group(1)),
                             "화면과 서버의 리스 시계가 갈렸다")
        with self.subTest("c2_stale_or_absent_or_mine_draws_nothing"):
                f = _decomment(self.parts["leaseElsewhere"])
                self.assertRegex(f, r"if\s*\(!l \|\| !l\.machine\)\s*return null",
                                 "리스가 없으면 그릴 것도 없다")
                self.assertRegex(f, r"l\.machine === mine\)\s*return null",
                                 "제 컴퓨터의 리스는 남의 자리가 아니다")
                self.assertRegex(f, r"age >= LEASE_TTL\)\s*return null",
                                 "만료된 리스는 아무도 안 쥔 것이다")

            # ---- ④ 진행 축은 한 줄이다 ---------------------------------------------
        with self.subTest("d1_elsewhere_wins_the_progress_axis"):
            f = _decomment(self.parts["stallHTML"])
            i_el = f.index("elsewhereRowHTML")
            i_stop = f.index("stoppedRowHTML")
            i_slow = f.index("slowRowHTML")
            self.assertLess(i_el, i_stop)
            self.assertLess(i_el, i_slow)
            self.assertRegex(f, r"if \(elsew\) return elsew;")
        with self.subTest("d2_the_dot_keeps_its_seven_faces"):
                card = self.parts["cardHTML"]
                seg = card[card.index("elsewDot"):][:900]
                self.assertIn("livedot off", seg, "있는 마크(○ 모름)를 써야 한다")
                for face in ("livedot elsew", "livedot away", "livedot remote"):
                    self.assertNotIn(face, self.src, f"새 얼굴({face})을 만들면 안 된다")

            # ---- ⑤ 판정도 문구도 서버 한 곳이다 -------------------------------------
        with self.subTest("e1_the_handle_is_not_hidden_from_the_powerless"):
            f = _decomment(self.parts["assignBtnHTML"]) \
                + _decomment(self.parts["ownerBadgeHTML"])
            for w in ("isAdmin", "role", "viewMe"):
                self.assertNotIn(w, f, f"손잡이가 권한({w})을 스스로 재고 있다")
        with self.subTest("e2_the_refusal_sentence_comes_from_the_server"):
            for name in ("assignDoc", "takeoverDoc"):
                f = _decomment(self.parts[name])
                self.assertIn("d.error", f, f"{name} 가 서버 문장을 안 쓴다")
        with self.subTest("e3_viewer_is_not_offered"):
            self.assertRegex(_decomment(self.parts["assignPick"]),
                             r'u\.role !== "viewer"')
        with self.subTest("e3b_only_project_members_are_offered"):
            f = _decomment(self.parts["assignPick"])
            self.assertIn("m.active", f, "만료 멤버를 거르지 않는다")
            self.assertIn("mem.has(u.name)", f, "프로젝트 멤버로 좁히지 않는다")
            self.assertRegex(self.s9, r"project_role\(_proj, new_user\)",
                             "서버(do_assign)에 멤버 검사가 없다")
            # S5 — 지금 맡은 사람이 멤버에서 빠져도 「지금 이것」으로 남는다.
            # 창이 누가 쥐고 있는지를 두고 거짓말하면 알 길이 없다.
            self.assertIn('note: "지금 이것"', f)
            # S7/S8 — 못 받은 것과 없는 것은 다른 화면이다. 없는 사실을 고치러
            # 가게 만들면 사람이 헛일을 한다.
            self.assertIn("프로젝트 목록을 받지 못했습니다", f)
            self.assertIn("멤버를 더하면 여기에 뜹니다", f)
        with self.subTest("e4_takeover_only_for_the_owner_or_admin"):
            self.assertIn("canTakeover(r)", self.parts["elsewhereRowHTML"])
            f = _decomment(self.parts["canTakeover"])
            self.assertIn("isAdmin()", f)
            self.assertIn("viewMe()", f)
        with self.subTest("e5_one_path_on_the_server"):
                self.assertIn('parsed.path == "/api/assign"', self.s9)
                self.assertIn('parsed.path == "/api/claim_takeover"', self.s9)
                # 이관 API 는 takeover_handoff 한 경로를 부르고(REQ-20260909-010),
                # 그 함수가 리스 획득(doc_lease_acquire)을 한 번만 부른다.
                i = self.s9.index('parsed.path == "/api/claim_takeover"')
                seg = self.s9[i:i + 900]
                self.assertEqual(seg.count("takeover_handoff("), 1,
                                 "이관 API 는 이관 한 경로만 부른다")
                self.assertNotIn("doc_lease_acquire(", seg)
                j = self.s9.index("def takeover_handoff(")
                fn = self.s9[j:self.s9.index("\ndef ", j + 10)]
                self.assertEqual(fn.count("doc_lease_acquire("), 1,
                                 "이관은 리스 획득 한 경로만 부른다")
                self.assertIn("takeover=True", fn)
                self.assertIn("actor=actor", fn)

            # ---- ⑥ 새 층을 만들지 않는다 -------------------------------------------
        with self.subTest("f1_no_colour_field_no_left_bar"):
            # 담당 배지 규칙은 일부러 `button.asgnb`(요소1+클래스1)로 낮다 — 스킨의
            # `.card .badge` 가 이겨야 배지 생김새가 한 벌로 남는다(css/actions.css).
            for cls in (".rvpt.elsew", ".lin", ".lincap", ".lineage",
                        "button.asgnb"):
                i = self.css.find(cls + "{")
                if i < 0:
                    i = self.css.find(cls + ",")
                self.assertGreaterEqual(i, 0, f"{cls} 규칙이 없다")
                rule = self.css[i:self.css.index("}", i)]
                self.assertNotIn("border-left", rule, f"{cls} 에 좌측 띠가 생겼다")
                self.assertNotRegex(rule, r"background:(?!\s*none)",
                                    f"{cls} 가 색면을 칠한다")
        with self.subTest("f1b_the_underline_belongs_to_the_name"):
            self.assertIn('class="bnm"', self.parts["badgeFace"],
                          "이름이 제 껍데기를 가져야 밑줄을 이름에만 줄 수 있다")
            i = self.css.find("button.asgnb{")
            self.assertGreaterEqual(i, 0, "button.asgnb 규칙이 없다")
            rule = self.css[i:self.css.index("}", i)]
            self.assertNotRegex(rule, r"text-decoration:(?!\s*none)",
                                "밑줄이 버튼에 있으면 이니셜 링 밑까지 지나간다")
            self.assertGreaterEqual(self.css.find("button.asgnb .bnm{"), 0,
                                    "밑줄은 이름(.bnm)에 선다")
        with self.subTest("f2_the_card_wears_what_it_already_has"):
            self.assertIn('class="lin"', self.parts["lineageChip"])
            self.assertIn('class="rvpt elsew"', self.parts["elsewhereRowHTML"])
            self.assertIn('class="deed"', self.parts["elsewhereRowHTML"])
            # 카드의 담당 배지는 배지 그대로다 — 새 배지를 만들지 않는다.
            self.assertIn('class="badge asgnb"', self.parts["ownerBadgeHTML"])
        with self.subTest("f3_one_function_builds_both_screens"):
            # 재료를 나눠 갖는 자리가 바뀌었다 (REQ-20260911-016): 사람이 아닌
            # 것이 만들었을 때의 **이름**은 `originFace` 하나가 짓고, 카드 칩과
            # 손 위의 글이 그것을 쓴다. 문서 머리는 기원 조각(`originBits`)까지
            # 함께 쓴다 — 그 줄만 「REQ-… 처리 중」을 링크로 세우기 때문이다.
            for name in ("lineageChip", "lineageTell"):
                self.assertIn("originFace(r", self.parts[name],
                              f"{name} 가 제 손으로 이름을 짓는다")
            self.assertIn("originBits(r", self.parts["lineageRowHTML"])
            self.assertIn("lineageRowHTML(", self.src)
            self.assertIn("${lineage}", self.src, "문서 머리에 그 줄이 서야 한다")
            self.assertIn("ownerBadgeHTML(r)", self.parts["cardHTML"])
            self.assertIn("lineageChip(r)", self.parts["cardHTML"])
        with self.subTest("f4_the_handles_are_caught_before_the_card_opens"):
            i_as = self.src.index("[data-assign]")
            i_tk = self.src.index("[data-takeover]")
            i_doc = self.src.index('closest("[data-doc]")')
            self.assertLess(i_as, i_doc)
            self.assertLess(i_tk, i_doc)
        with self.subTest("f5_a_way_to_see_it_with_your_eyes"):
            self.assertIn("function leaseProbe(", self.src)
            self.assertIn("function linProbe(", self.src)
            i = self.src.index("function stallProbe(")
            seg = self.src[i:i + 1200]
            self.assertIn("leaseProbe(rows)", seg)
            self.assertIn("linProbe(rows)", seg)

if __name__ == "__main__":
    unittest.main()
