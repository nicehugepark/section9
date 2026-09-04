"""멈춘 것을 사람이 깨우는 손잡이 — 화면 몫 (REQ-20260828-041-62x6).

사용자(18:04): "in-progress 중인 카드나 문서에 상태체크 기능을 만들고 **굳이
프롬프트로 물어보지 않고 진행할 수 있게** 하는건 어때?"

REQ-20260828-036 은 그 물음의 **보여주기 절반**만 냈다 — 점의 근거를 고치고,
멈춤 줄을 세우고, 열 머리에 수를 붙였다. 화면은 "멈췄다"고 말할 수 있게 됐지만
사람이 거기서 할 수 있는 일은 없었다. 그래서 사용자는 하루에 다섯 번 리드에게
"이거 진짜 도는 거냐"를 물어야 했다. 이 파일은 나머지 절반의 계약이다.

계약은 여섯이다.

  ① **손잡이는 멈춤 줄에만.** 멈춘 카드가 아니면 뜨지 않는다. 판정은 화면이
     다시 하지 않는다 — 서버가 행에 실어 준 `stalled_mins` 를 읽을 뿐이다
     (REQ-20260828-036 이 세운 규칙: 두 벌이면 한 벌만 고쳐진다).
  ② **보드와 문서가 한 함수로 짓는다.** 같은 행동이 두 화면에 각자 글자를
     가지면 한쪽만 고쳐진다 — REQ-20260828-007 이 그 이유로 세 번 반려됐다.
  ③ **화면이 이유를 짓지 않는다.** 서버가 준 `message` 를 그대로 띄운다.
     `action` 으로 문구를 갈라 쓰는 순간 같은 말이 서버와 화면 두 벌이 된다.
  ④ **`ok=false` 는 오류가 아니라 설명이다.** `capped`(한도 소진)·`busy`(이미
     붙어 있음)·`moving`(아직 멈춘 게 아님)은 정상적인 답이다 — 붉은 실패의
     옷을 입히면 사람은 고장으로 읽고 다시 누르지 않는다.
  ⑤ **연타는 막고 실패는 다시 누를 수 있다.** 도는 중에는 눌리지 않지만, 못
     깨운 것을 다시 못 누르게 잠그는 것은 벌주는 화면이다.
  ⑥ **새 층을 만들지 않는다.** 색면 하이라이트·세로 띠·새 경고 배지 없이,
     카드가 이미 쓰는 행동 줄(.acts)과 행위 버튼(.deed)을 그대로 입는다.

실행: python3 tests/ wake_handle
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

# 서버가 돌려주는 action 값 전부 (bin/s9 wake_request 의 계약). 화면은 이 낱말
# 중 **어느 것도** 알아서는 안 된다 — 알기 시작하면 문구가 두 벌이 된다.
ACTIONS = ("spawned", "busy", "moving", "capped", "off", "disabled",
           "elsewhere", "no-cli", "not-request", "not-in-progress")


def _grab(src, name):
    m = re.search(r"function %s\([^)]*\)\{[\s\S]*?\n\}" % name, src)
    assert m, name
    return m.group(0)


class WakeHandle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.stall = _grab(cls.src, "stallHTML")
        # 손잡이가 사실 줄을 떠나 id 줄의 벨트로 갔다 (REQ-20260830-040 규칙 4).
        # 계약은 그대로다 — 짓는 자리가 하나이고, 안 멈춘 행에는 빈 문자열이
        # 오며, 카드와 문서가 같은 함수를 부른다. 보는 덩어리만 넓힌다.
        cls.handle = "\n".join([cls.stall, _grab(cls.src, "wakeBtnHTML"),
                                _grab(cls.src, "driftBtnHTML"),
                                _grab(cls.src, "deedBeltHTML")])
        # 답을 창으로 옮기는 자리가 wakeDlg 로 갈라졌고(REQ-20260829-030), 그
        # 앞에 **창이 설지를 가르는 자리**(wakeAnswer)가 한 겹 더 섰다
        # (REQ-20260830-049). 진단이 사람이 누를 때와 **같은 함수**를 부르게
        # 하려는 것이라, 이 시험이 보는 "깨우기의 길"은 셋을 합한 것이다.
        cls.wake = "\n".join([_grab(cls.src, "wakeDoc"),
                              _grab(cls.src, "wakeAnswer"),
                              _grab(cls.src, "wakeDlg")])
        cls.card = _grab(cls.src, "cardHTML")
        cls.doc = _grab(cls.src, "openDoc") if "function openDoc(" in cls.src \
            else cls.src

    # ---------- ① 손잡이는 멈춤 줄에만 ----------

    def test_the_handle_keeps_its_six_contracts(self):
        """여섯 계약을 한 자리에서 — 멈춤 줄에만·한 함수로·서버 문장 그대로·거절은 설명·연타는 막되 실패는 재시도·새 층 없음."""
        with self.subTest("the_handle_lives_in_the_id_belt"):
            self.assertIn("data-wake=", self.handle, "손잡이를 짓는 자리가 없다")
            # 그리는 자리는 둘뿐이다 — 글리프 갈래(wakeBtnHTML)와 낱말 갈래
            # (driftBtnHTML). paintWake 의 `[data-wake="…"]` 는 이미 그려진 것을
            # **찾는** 자리라 세지 않는다.
            self.assertEqual(len(re.findall(r'data-wake="\$\{esc\(', self.src)), 2,
                             "손잡이를 그리는 자리가 여럿이다 — 한 벌만 고쳐진다")
            # 낱말은 상수 한 곳에서 온다 (REQ-20260829-024 라운드4) — 글자를 짓는
            # 자리와 다시 칠하는 자리 두 곳에 두었더니 개명 한 번에 갈렸다.
            self.assertIn("WAKE_LABEL", self.handle)
        with self.subTest("a_card_that_is_not_stalled_has_no_handle"):
            m = re.search(r"const stall\s*=([\s\S]{0,200}?);\n", self.card)
            self.assertIsNotNone(m, "카드가 멈춤 줄을 다는 자리가 없다")
            self.assertIn("stallHTML", m.group(1))
            self.assertIn("stallState(r)", self.stall, "줄 짓는 함수가 판정을 안 지난다")
            self.assertIn("stallState(r)", _grab(self.src, "wakeBtnHTML"),
                          "손잡이가 판정을 안 지난다")
            for name in ("slowRowHTML", "stoppedRowHTML", "wakeBtnHTML", "deedBeltHTML"):
                self.assertIn('return "";', _grab(self.src, name),
                              "%s 가 안 멈춘 행에 빈 문자열을 안 돌려준다" % name)
        with self.subTest("the_screen_never_measures_the_minutes_itself"):
                state = _grab(self.src, "stallState")
                self.assertIn("r.stalled_mins", state, "판정이 서버가 준 분을 안 읽는다")
                self.assertIn("st.mins", self.stall, "줄이 그 분을 안 옮긴다")
                for banned in ("Date.now() -", "getTime()", "fromisoformat"):
                    self.assertNotIn(banned, self.stall,
                                     "멈춤 줄이 나이를 스스로 재고 있다: %s" % banned)

            # ---------- ② 보드와 문서가 한 함수 ----------
        with self.subTest("board_and_document_say_the_same_word"):
                calls = re.findall(r"stallHTML\(", self.src)
                self.assertGreaterEqual(len(calls), 3,
                                        "짓는 자리(1) + 부르는 자리(보드·문서)가 없다")
                self.assertIn("stallHTML(r)", self.card, "보드 카드가 안 부른다")
                self.assertIn("stallHTML(stallDoc)", self.src, "문서 화면이 안 부른다")
                # 조각이 둘이 된 뒤로도 **둘 다** 같은 함수에서 온다 (REQ-20260830-040) —
                # 벨트를 문서에서 빼면 문서 화면만 손잡이를 잃는다.
                self.assertIn("deedBeltHTML(r)", self.card, "보드 카드가 벨트를 안 부른다")
                # 문서는 낱말 얼굴(wordy)로 부른다 (REQ-20260830-046) — 함수는 같다.
                self.assertIn("deedBeltHTML(stallDoc, true)", self.src,
                              "문서 화면이 벨트를 안 부른다")
                # 문서 화면은 **자기 조건을 갖지 않는다** (REQ-20260828-041 2차) —
                # 카탈로그 행을 넘길 뿐이고, 멈춤인지는 stallState 한 곳이 답한다.
                self.assertNotIn("srow", self.src.split("const stallRow")[1][:200],
                                 "문서 화면이 다시 판정한다")
                # 행동은 머리 띠(docActs, 붙박이)로, 사실 줄은 그 아래 흐름으로
                # (REQ-20260830-046) — 멈춤 줄이 실제로 놓이는 계약은 그대로다.
                # 재는 것은 **자리**이지 붙어 있음이 아니다 (REQ-20260902-021 이 사이에
                # 혈통 줄 하나를 세웠다): 사실 줄은 붙박이 띠 **밖**, 그 바로 아래 흐름에
                # 놓인다. `${docActs}</div>` 가 .dhead 를 닫는 자리이고 그 뒤 흐름의
                # 머리 몇 조각 안에 멈춤 줄이 있어야 한다.
                flow = self.src.split("${docActs}</div>")[1][:200]
                self.assertIn("${stallRow}", flow,
                              "문서 화면에 멈춤 줄이 실제로 놓이지 않는다")

            # ---------- ③ 화면이 이유를 짓지 않는다 ----------
        with self.subTest("the_screen_shows_the_server_sentence_verbatim"):
            self.assertIn("d.message", self.wake, "서버 문장을 안 쓴다")
            self.assertIn('title: d.message', self.wake,
                          "서버 문장이 창의 본문에 서지 않는다")
        with self.subTest("the_screen_does_not_branch_on_action"):
                self.assertNotIn("d.action", self.wake, "화면이 action 을 읽는다")
                for a in ACTIONS:
                    self.assertNotIn('"%s"' % a, self.wake,
                                     "화면이 서버의 사유 낱말을 알고 있다: %s" % a)

            # ---------- ④ 거절은 오류가 아니다 ----------
        with self.subTest("a_refusal_is_not_painted_as_a_failure"):
                self.assertIn("stop: false", self.wake, "거절이 실패의 옷을 입는다")
                self.assertNotIn('cap: "실패"', self.wake)
                # 눈썹 잉크는 kind 가 아니라 stop 이 정한다
                cap = re.search(r'<span class="dlgcap\$\{([^}]*)\}', self.src)
                self.assertIsNotNone(cap, "창머리 잉크를 정하는 자리를 못 찾았다")
                self.assertIn("o.stop", cap.group(1),
                              "알림이면 무엇이든 붉어진다 — 설명도 고장으로 읽힌다")

            # ---------- ⑤ 연타는 막고 실패는 다시 ----------
        with self.subTest("no_double_press_but_a_failure_can_be_pressed_again"):
            self.assertIn("if (wokePending(id)) return;", self.wake,
                          "같은 카드를 연타할 수 있다")
            self.assertIn("wokeAt.set(id, Date.now())", self.wake)
            # 실패·거절이면 표식을 지운다 = 다시 누를 수 있다
            self.assertEqual(len(re.findall(r"wokeAt\.delete\(id\)", self.wake)), 2,
                             "못 깨운 뒤에 다시 누를 수 없다")
            self.assertIn("if (!d.ok){ wokeAt.delete(id); paintWake(id); }",
                          self.wake, "거절 뒤 손잡이가 잠긴 채로 남는다")
            # 도는 중 표시는 서버 왕복을 기다리지 않는다
            self.assertIn("paintWake(id);\n  let d", self.wake,
                          "누른 순간 화면이 답하지 않는다")
            # 영영 잠기지 않는다 — 스폰이 조용히 죽어도 풀린다
            self.assertIn("WOKE_HOLD", self.src, "표식이 만료되지 않는다")
        with self.subTest("the_running_state_says_it_is_running"):
                # 낱말이 「깨우기」에서 「이어가기」로 바뀌었다 (REQ-20260829-024 반려:
                # "깨우기, 세우기 라는 용어가 너무 어색한데"). 계약은 그대로다 —
                # 누른 뒤의 얼굴이 자기가 도는 중임을 말해야 한다.
                self.assertIn("WAKE_GOING", self.handle)
                self.assertIn("이어가는 중…", self.src)
                # 잠금은 `disabled` 가 아니라 `aria-disabled` 다 (REQ-20260831-009) —
                # `disabled` 는 눌린 손잡이에서 포커스를 걷어 키보드 손을 떨어뜨린다.
                self.assertIn("DEED_BUSY", self.handle,
                              "다시 그려도 도는 중인 손잡이가 되살아난다")
                self.assertIn('const DEED_BUSY = \' aria-disabled="true"\'', self.src,
                              "잠금 표시가 한 곳에서 오지 않는다")
                self.assertNotRegex(self.handle, r'\?\s*" disabled"',
                                    "눌린 손잡이를 아직 disabled 로 잠근다")

            # ---------- ⑥ 새 층 없음 ----------
        with self.subTest("it_reuses_the_button_the_card_already_has"):
            # 이제 글리프는 id 줄의 벨트에, 낱말 갈래만 자기 줄(.deedrow.wordy)에
            # 선다 (REQ-20260830-040) — 입은 옷은 그대로다.
            self.assertIn('class="deedrow wordy"', self.stall)
            self.assertIn('class="acts deedbelt"', self.handle)
            self.assertIn('class="acts wakerow"', self.handle)
            # `deed wake` 뒤에 상태 갈래(`ico`·`busy`)가 붙는다 (REQ-20260830-032:
            # 손잡이 얼굴이 글리프로 바뀌었다). 계약은 낱말 그대로가 아니라 **입은
            # 옷**이다 — 카드가 이미 쓰는 .deed 를 그대로 입었는가.
            self.assertRegex(self.handle, r'class="deed wake[ `$]')
            # 새 배지·색면·띠를 만들지 않는다
            m = re.search(r"\.acts\.wakerow\{([^}]*)\}", self.src)
            self.assertIsNotNone(m, ".acts.wakerow 규칙이 없다")
            for banned in ("background", "animation", "border-left"):
                self.assertNotIn(banned, m.group(1),
                                 "깨우기 줄이 %s 로 새 층을 만든다" % banned)
            self.assertNotIn("wakebanner", self.src)
        with self.subTest("calm_skin_does_not_lose_the_row"):
                self.assertRegex(
                    self.src,
                    r'\[data-skin="calm"\] \.card>\.deedrow\{order:3\}',
                    "calm 스킨에서 손잡이 줄이 카드 맨 위로 올라간다")

            # ---------- 배선 ----------
        with self.subTest("one_road_to_the_server"):
            self.assertEqual(len(re.findall(r'"/api/wake"', self.src)), 1,
                             "깨우기를 부르는 자리가 여럿이다")
            self.assertIn('method: "POST"', self.wake)
            self.assertIn("withAs({id})", self.wake, "대리 사용자가 안 실린다")
        with self.subTest("enter_presses_the_handle_not_the_card"):
            m = re.search(r'addEventListener\("keydown", e => \{[\s\S]{0,700}?'
                          r'closest\(\'\[role="button"\]\'\)', self.src)
            self.assertIsNotNone(m, "role=button 컨트롤의 Enter 핸들러를 못 찾았다")
            self.assertIn('t.closest("button,a[href],summary")', m.group(0),
                          "카드 안의 진짜 버튼이 Enter 를 빼앗긴다 — "
                          "키보드로는 손잡이 대신 문서가 열린다")
        with self.subTest("the_handle_is_not_the_card"):
            m = re.search(r'closest\("\[data-wake\]"\);\n\s*if \(wk\)\{([^\n]*)',
                          self.src)
            self.assertIsNotNone(m, "깨우기 클릭을 잡는 자리가 없다")
            self.assertIn("stopPropagation", m.group(1),
                          "깨우기를 누르면 문서까지 열린다")
            self.assertIn("wakeDoc(wk.dataset.wake)", m.group(1))

def _css(src):
    """주석을 걷어낸 CSS 만 — 주석은 고쳐 낸 옛 값을 근거로 인용한다."""
    return re.sub(r"/\*[\s\S]*?\*/", " ", src)


def _rules(src):
    """(셀렉터, 선언) 짝 — 손잡이를 건드리는 규칙만 훑는다."""
    out = []
    for m in re.finditer(r"([^{}@]+)\{([^{}]*)\}", src):
        out.append((" ".join(m.group(1).split()), m.group(2)))
    return out


class ThePaintIsNotTheTarget(unittest.TestCase):
    """손이 닿는 상자와 **칠해지는 원**은 다른 것이다 (REQ-20260830-043 2차 반려).

    사용자: "레이아웃이 여전히 안맞다" — 캡처는 손이 카드에 얹힌 화면이었고,
    거기서 검은 원이 식별자의 마지막 글자를 파고들었다.

    뿌리는 hover 가 **과녁 전체**(27px)를 칠한 것이다. 글리프 손잡이는 27px
    과녁 안에 11px 그림을 담고, 벨트는 그 남는 흰 자리만큼을 음수 여백으로
    되돌려 잉크 사이를 줄의 눈금에 맞춘다 — 그러니 상자를 통째로 칠하면 되돌린
    만큼이 그대로 글자를 덮는다. 쉬는 얼굴만 재고 끝내서 두 번 반려됐다.

    그래서 계약은 셋이다.
      ① 과녁은 안 줄인다 (min-width/min-height 27px).
      ② 칠은 안쪽 원에만 든다 (padding + background-clip:content-box).
      ③ 그 클립을 되돌리는 `background` 단축을 손잡이에 쓰지 않는다.
    """

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.css = _css(f.read())
        cls.rules = _rules(cls.css)
        cls.belt = [(s, d) for s, d in cls.rules
                    if "deedbelt" in s or "deed.ico" in s]

    def test_the_paint_stays_inside_the_target(self):
        """칠은 과녁 안에 머문다 — 과녁을 깎지 않고, 마스크가 키보드 링을 먹지 않는다."""
        with self.subTest("the_target_is_not_shaved"):
            hit = [d for s, d in self.rules if s.endswith(".acts button.deed.ico")]
            self.assertTrue(hit, "글리프 손잡이의 과녁 규칙이 없다")
            self.assertIn("min-width:27px", hit[0])
            self.assertIn("min-height:27px", hit[0])
        with self.subTest("the_paint_is_clipped_into_the_target"):
            shaper = [d for s, d in self.belt
                      if "mask-image" in d and "none" not in d]
            self.assertEqual(len(shaper), 1,
                             "원의 모양을 정하는 관문이 하나가 아니다 — "
                             "스킨마다 사본이 생기면 한쪽만 고쳐진다")
            self.assertRegex(shaper[0], r"mask-image:radial-gradient\(circle",
                             "원을 radial-gradient mask 로 정하지 않는다")
            self.assertIn("-webkit-mask-image:radial-gradient(circle", shaper[0],
                          "webkit 접두가 없으면 옛 엔진에서 원이 사라진다")
            self.assertRegex(shaper[0], r"padding:\d+px",
                             "안여백이 없으면 그림이 과녁 한가운데에 안 선다")
            self.assertIn("border-radius:999px", shaper[0],
                          "mask 를 모르는 브라우저의 안전선이자, cobalt·slate 의 "
                          "각진 라운드가 원을 모난 알약으로 만드는 것을 막는 못이다")
        with self.subTest("the_keyboard_ring_survives_the_mask"):
            off = [d for s, d in self.belt
                   if "focus-visible" in s and "mask-image:none" in d]
            self.assertTrue(off, "초점 얼굴이 mask 를 끄지 않는다 — 링이 잘린다")
            self.assertIn("background-clip:content-box", off[0],
                          "mask 를 끄면 원을 그릴 것이 없다 — 그 얼굴에서는 "
                          "테두리 라운드가 원을 맡아야 한다")
        with self.subTest("no_shorthand_undoes_the_clip"):
            for sel, dec in self.belt:
                self.assertNotRegex(
                    dec, r"(^|;)\s*background\s*:",
                    "손잡이 규칙이 background 단축을 쓴다 (%s) — "
                    "낱개 속성(background-color/-image)으로 쓰라" % sel)
        with self.subTest("the_pull_is_written_once"):
            pulls = [(s, d) for s, d in self.rules
                     if "deedbelt" in s and re.search(r"margin(-left)?\s*:[^;]*-\d", d)]
            self.assertEqual(len(pulls), 1,
                             "벨트의 왼쪽 당김이 %d 곳에 적혀 있다: %s"
                             % (len(pulls), [s for s, _ in pulls]))
        with self.subTest("the_focus_ring_rounds_the_circle_not_the_target"):
            ring = [d for s, d in self.belt if "focus-visible" in s]
            self.assertTrue(ring, "글리프 손잡이의 포커스 링 규칙이 없다")
            self.assertIn("outline-offset:-6px", ring[0])
        with self.subTest("an_inverted_card_inverts_the_chip_too"):
            inv = [d for s, d in self.belt
                   if '[data-skin="terminal"]' in s and ".card:hover" in s]
            self.assertTrue(inv, "반전된 카드 위에서 칩을 뒤집는 규칙이 없다")
            self.assertTrue(any("background-color:var(--bg)" in d for d in inv),
                            "반전 카드에서 칩이 배경색에 묻힌다")

class TheWindowStandsOnlyForExceptions(unittest.TestCase):
    """성공을 알리는 창은 자격이 없다 (REQ-20260830-049, designer 판정 A안).

    이어가기는 비파괴·자동·되돌림 가능(⏸)이다. 누른 손 아래에서 ▶ 가 ⏸ 로
    서는 것이 이미 답인데, 그 위에 판을 하나 더 세우면 원인과 결과가 공간적으로
    끊기고 **창이 자기가 가리키는 그 카드를 가린다**(designer 실측 캡처). 게다가
    이 화면에서 창은 「물음 아니면 거절」의 신호로 학습돼 있어(중단하기 확인 ·
    닿지 못했습니다 · 이어가지 않음), 아무 문제도 없는데 문제의 옷을 입고
    나타난다. 카드 사실 줄의 규율(REQ-20260830-040 「예외만 말한다」)을 창에
    그대로 옮긴다.

    계약은 넷이다.
      ① 성공에 덧붙일 **예외 사실(`note`)이 없으면 창은 서지 않는다.**
      ② 실패·대기(`ok=false`)의 창은 그대로 선다 — 읽을 이유가 실제로 있다.
      ③ 갈래(워크스페이스)는 화면이 다시 판정하지 않는다 — 서버가 할 말을
         가졌는가 하나만 읽는다(bin/s9 `_wake_note` 가 유일한 판정처).
      ④ 급이 다른 두 말은 슬롯도 둘이다 — `message` 는 제목(.dlgt),
         `note` 는 부가(.dlgs). 화면이 한 문자열을 마침표로 쪼개지 않는다.
    """

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.answer = _grab(cls.src, "wakeAnswer")
        cls.dlg = _grab(cls.src, "wakeDlg")

    # ---------- ① 성공은 조용하다 ----------

    def test_the_window_stands_only_for_exceptions(self):
        """창은 예외에만 선다 — 평범한 성공에는 안 뜨고, 거절은 여전히 선다."""
        with self.subTest("a_plain_success_raises_no_window"):
            self.assertRegex(
                self.answer, r"if\s*\(d\.ok\s*&&\s*!d\.note\)\s*return",
                "예외 사실 없는 성공이 아직 창을 세운다 — 카드의 ▶→⏸ 가 이미 답이다")
        with self.subTest("the_click_goes_through_the_verdict_not_around_it"):
                doc = _grab(self.src, "wakeDoc")
                self.assertIn("wakeAnswer(id, d)", doc,
                              "누른 길이 판정을 건너뛰고 창을 짓는다")
                self.assertNotIn("wakeDlg(id, d)", doc)
                # 진단(diag.js `?dlg=wakespawn…`)도 같은 자리를 지난다
                self.assertNotIn("wakeDlg(\"REQ-", self.src,
                                 "진단이 판정을 건너뛰고 창을 직접 짓는다 — 캡처가 "
                                 "사람이 보는 화면을 비추지 못한다")

            # ---------- ② 실패·대기의 창은 남는다 ----------
        with self.subTest("a_refusal_still_stands"):
                self.assertIn("d.ok &&", self.answer,
                              "성공 여부를 보지 않고 창을 없앤다 — 거절까지 조용해진다")
                self.assertIn("return wakeDlg(id, d);", self.answer,
                              "판정을 지난 답이 창으로 서지 않는다")

            # ---------- ③ 갈래는 화면이 짓지 않는다 ----------
        with self.subTest("the_screen_never_re_reads_the_workspace"):
                for w in ("workspace", "worktree", "kind ===", "WS_MEANS"):
                    self.assertNotIn(w, self.answer,
                                     "창을 세울지를 화면이 갈래로 판정한다: %s" % w)

            # ---------- ④ 두 말은 슬롯도 둘 ----------
        with self.subTest("two_slots_for_two_ranks_of_speech"):
            self.assertIn("title: d.message", self.dlg, "제목 칸이 없다")
            self.assertIn("desc: d.note", self.dlg,
                          "부가 사실이 설 슬롯이 없다 — 한 슬롯에 겹치면 강조가 둘")
        with self.subTest("the_screen_does_not_split_the_sentence_itself"):
            for bad in (".split(", "indexOf(\".\")", "lastIndexOf(\".\")"):
                self.assertNotIn(bad, self.dlg + self.answer,
                                 "화면이 서버 문장을 손으로 쪼갠다: %s" % bad)

class ThePressedHandKeepsItsPlace(unittest.TestCase):
    """누른 손은 그 자리에 남는다 (REQ-20260831-009).

    049 로 성공 경로의 창이 사라지자 키보드 손이 갈 곳을 잃었다. CDP 실측:
    ▶ 에 포커스를 주고 누르면 `activeAfter=BODY` — 눌린 단추를 `disabled` 로
    만드는 순간 브라우저가 포커스를 걷고, 이어지는 재그리기가 그 단추 개체
    자체를 지운다. 창이 있던 동안에는 창이 landmark 노릇을 했지만 이제 없다.

    잠금을 지는 것은 원래 `wokePending`/`stopPending` 이지 `disabled` 가
    아니다 — 누르는 자리 둘이 그 관문을 먼저 지난다. 그러니 계약은 셋이다.
      ① 잠금은 **보이되 닿는** `aria-disabled` 로 말한다 (포커스가 남는다).
      ② 연타 관문은 그대로다 — 잠금 표시를 바꾼다고 두 번 나가면 안 된다.
      ③ 재그리기를 건너 손이 같은 카드의 손잡이로 돌아온다. 다만 **내 자리였을
         때만**, 그리고 **창이 서 있지 않을 때만** — 창이 서면 손은 창의 것이다.
    """

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.face = _grab(cls.src, "faceDeed")
        cls.keep = _grab(cls.src, "keepDeedFocus")
        cls.doc = _grab(cls.src, "wakeDoc")

    # ---------- ① 잠금은 포커스를 걷지 않는다 ----------

    def test_the_pressed_hand_keeps_its_place(self):
        """누른 손은 제자리를 지킨다 — 잠금이 초점을 빼앗지 않고 다시 그려도 살아남는다."""
        with self.subTest("the_lock_no_longer_takes_the_focus_away"):
            self.assertNotIn("b.disabled", self.face,
                             "눌린 손잡이를 아직 disabled 로 잠근다 — 브라우저가 "
                             "포커스를 걷어 키보드 손이 body 로 떨어진다")
            self.assertIn('setAttribute("aria-disabled", "true")', self.face)
            self.assertIn('removeAttribute("aria-disabled")', self.face,
                          "잠금이 풀려도 표시가 남는다")
        with self.subTest("the_lock_is_written_once"):
            self.assertIn('const DEED_BUSY = \' aria-disabled="true"\'', self.src)
            self.assertNotRegex(self.src, r'\$\{going \? " disabled" : ""\}',
                                "아직 disabled 로 그리는 손잡이가 남아 있다")
        with self.subTest("the_paint_follows_the_new_lock"):
                css = _css(self.src)
                for who in ("wake", "stop"):
                    self.assertIn('button.%s[aria-disabled="true"]' % who, css,
                                  "%s 의 눌린 얼굴이 새 잠금 표시를 안 본다" % who)
                    self.assertNotIn("button.%s[disabled]" % who, css,
                                     "%s 규칙이 아직 옛 표시를 본다" % who)

            # ---------- ② 연타 관문은 그대로 ----------
        with self.subTest("the_double_press_gate_is_untouched"):
                self.assertIn("if (wokePending(id)) return;", self.doc)
                self.assertIn("if (stopPending(id)) return;", _grab(self.src, "stopDoc"))

            # ---------- ③ 재그리기를 건너 자리가 남는다 ----------
        with self.subTest("the_focus_crosses_the_redraw"):
            self.assertIn("await keepDeedFocus(id, () => refreshCatalog(true))",
                          self.doc, "재그리기가 손잡이를 갈아 끼우는데 손이 "
                                    "따라가지 않는다")
        with self.subTest("it_only_returns_a_hand_that_was_there"):
            self.assertIn("if (!mine || held.isConnected) return;", self.keep,
                          "남의 자리를 빼앗거나, 멀쩡한 자리를 다시 잡는다")
        with self.subTest("an_open_window_owns_the_hand"):
            self.assertIn(".dlgbox", self.keep,
                          "창이 서 있는지 보지 않고 포커스를 가져간다")

class TheMarkSharesOneStage(unittest.TestCase):
    """점의 좌표계는 층이다 — 무대·맥박·마크 (REQ-20260831-012/006/016).

    세 지적(마크 종류별 좌표 차이 · ⏸ 호버 비대칭 · 파동 중심 이탈)의 뿌리는
    전부 층이 안 갈린 것이었다: 얼굴이 무대를 건드리거나, 맥박이 box-shadow 로
    마크 뒤에서 배어 나오거나, 글리프 눈금이 화소와 안 맞았다. 계약은 셋이다.
      ① 무대(.livedot 상자·정렬)는 얼굴이 못 건드린다.
      ② 맥박은 무대와 동심인 ::after 링이다 — box-shadow 금지.
      ③ 글리프는 viewBox 한 칸 = .gly 한 화소(11↔11px), 좌표는 정수다.
    상세 근거: DOC-20260831-003 「작은 마크의 좌표 함정 셋」.
    """

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.rules = _rules(_css(cls.src))
        cls.dot = [(s, d) for s, d in cls.rules if ".livedot" in s]

    def test_the_mark_shares_one_stage(self):
        """마크는 한 무대를 쓴다 — 동심원 맥박과 픽셀 격자."""
        with self.subTest("no_face_touches_the_stage"):
            for sel, dec in self.dot:
                if "::after" in sel or not re.search(r"\.livedot\.", sel):
                    continue  # 무대 자신과 맥박은 제 몫이다
                for prop in ("width:", "height:", "position:", "display:",
                             "margin", "top:", "left:", "transform-origin:"):
                    self.assertNotIn(prop, dec,
                                     "얼굴이 무대를 건드린다 (%s ← %s) — 종류마다 "
                                     "좌표가 갈리던 그 길이다" % (sel, prop))
        with self.subTest("the_pulse_is_a_concentric_ring"):
            for sel, dec in self.dot:
                self.assertNotIn("box-shadow", dec,
                                 "맥박이 그림자다 (%s) — 속 빈 마크에서 색면으로 "
                                 "배어 나오고 하드코딩 색이 얼굴과 어긋난다" % sel)
            ring = [d for s, d in self.dot if s.endswith(".livedot::after")]
            self.assertEqual(len(ring), 1, "맥박 링이 한 벌이 아니다")
            self.assertIn("top:50%", ring[0])
            self.assertIn("left:50%", ring[0])
            self.assertIn("transform:translate(-50%,-50%)", ring[0],
                          "50%+translate 가 아니면 상자가 부모보다 커지는 순간 "
                          "margin:auto 가 가운데를 포기한다 (CSS 2.1 §10.3.7, "
                          "REQ-20260831-016 실측 +3.2px)")
            self.assertIn("@keyframes livering", self.src)
            # 이름이 주석(경위 기록)에 남는 것은 허용 — 살아 있는 정의·호출만 막는다
            self.assertNotIn("@keyframes livepulse", self.src,
                             "옛 그림자 맥박이 되살아났다")
            self.assertNotRegex(self.src, r"animation:\s*livepulse",
                                "옛 그림자 맥박을 다시 부른다")
        with self.subTest("the_glyph_grid_is_the_pixel_grid"):
            boxes = {}
            for name in ("GLYPH_PLAY", "GLYPH_PAUSE"):
                m = re.search(r"const %s = ([\s\S]*?;)" % name, self.src)
                self.assertIsNotNone(m, name)
                v = re.search(r'viewBox="0 0 (\d+) (\d+)"', m.group(1))
                self.assertIsNotNone(v, "%s 에 정수 viewBox 가 없다" % name)
                self.assertEqual(v.group(1), v.group(2),
                                 "%s 의 눈금이 정사각이 아니다" % name)
                boxes[name] = int(v.group(1))
            self.assertEqual(len(set(boxes.values())), 1,
                             "▶ 와 ⏸ 가 서로 다른 눈금을 쓴다: %s" % boxes)
            n = next(iter(boxes.values()))
            pause = re.search(r"const GLYPH_PAUSE = ([\s\S]*?;)", self.src).group(1)
            for v in re.findall(r'(?<=[\s"])(?:x|y|width|height)="([^"]+)"', pause):
                self.assertRegex(v, r"^\d+$",
                                 "⏸ 좌표 %s 가 정수가 아니다 — 화소 격자에서 "
                                 "내린다" % v)
            seen = 0
            for sel, dec in self.rules:
                if sel.endswith(" .gly"):
                    seen += 1
                    self.assertIn("width:%dpx" % n, dec,
                                  "%s 의 상자가 viewBox %d칸과 1:1 이 아니다"
                                  % (sel, n))
                    self.assertIn("height:%dpx" % n, dec, sel)
            self.assertTrue(seen, ".gly 의 상자를 정하는 규칙이 없다")

class NoFaceSplitsOnColourAlone(unittest.TestCase):
    """색만으로 갈리는 얼굴은 없다 — 앰버 폐지의 회귀 (DOC-20260831-005).

    「직접 작업 중」과 「자동 작업 기동 중」은 지름·채움·링·맥박이 **완전히
    같은 원반**이었고 색만 달랐다 — 여덟 중 색만으로 갈리는 유일한 쌍이었고,
    그 검증 페이지가 스스로 머리에 "색은 **둘째** 신호"라 적어 둔 채였다
    (s9-design 7절 직접 위반). 게다가 앰버가 실제로 가르던 것은 「자동 vs
    사람」이 아니라 「아직 안 집었다 vs 집었다」였다 — 같은 프로세스가 제
    생애 동안 두 색을 다 지났다.

    그래서 그 갈래는 초록 축의 ○(살아는 있으나 아직 이 요청을 안 맡음)으로
    흡수했다. 여기 못박는 것은 넷이다: 앰버가 없다 · spawn 이 제 규칙을 갖지
    않는다(sess 와 한 줄) · 맥박은 두 얼굴뿐이다 · 그러고도 spawn 과 on 은
    색을 빼고도 갈린다.
    """

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.css = _css(cls.src)
        cls.dot = [(s, d) for s, d in _rules(cls.css) if ".livedot" in s]

    def test_no_face_splits_on_colour_alone(self):
        """색만으로 갈리는 얼굴은 없다 — 두 초록이 색 없이도 갈린다."""
        with self.subTest("the_amber_ink_is_gone"):
            self.assertNotIn("--dot-auto", self.css,
                             "앰버 토큰이 살아 있다 — 폐지된 축이다")
            for sel, dec in self.dot:
                self.assertNotIn("d97706", dec.lower(),
                                 "%s 에 앰버가 하드코딩돼 있다" % sel)
        with self.subTest("the_new_face_has_no_rule_of_its_own"):
            own = [s for s, _ in self.dot
                   if ".spawn" in s and "::after" not in s and ".sess" not in s]
            self.assertEqual([], own,
                             "spawn 이 제 규칙을 되찾았다: %s" % own)
            shared = [d for s, d in self.dot if ".sess" in s and ".spawn" in s]
            self.assertEqual(1, len(shared),
                             "sess 와 spawn 이 한 규칙에 서지 않는다")
            self.assertIn("--dot-live", shared[0],
                          "기동 중 얼굴이 초록 축(--dot-live)을 안 쓴다")
        with self.subTest("only_two_faces_breathe"):
            beating = sorted(s for s, d in self.dot
                             if "::after" in s and "animation:livering" in d)
            self.assertEqual([".livedot.on::after,.livedot.busy::after"], beating,
                             "맥박을 쓰는 얼굴이 on·busy 둘이 아니다: %s" % beating)
        with self.subTest("the_two_greens_still_differ_without_colour"):
            def dec(pred):
                hit = [d for s, d in self.dot if pred(s)]
                self.assertTrue(hit, "규칙을 못 찾았다")
                return hit[0]
            on = dec(lambda s: s.endswith(".livedot.on"))
            ring = dec(lambda s: ".sess" in s and ".spawn" in s)
            self.assertIn("background:currentColor", on)
            self.assertIn("background:transparent", ring)
            self.assertIn("border:1.5px", ring,
                          "속 빈 얼굴의 테가 없으면 색을 뺐을 때 사라진다")

if __name__ == "__main__":
    unittest.main(verbosity=2)
