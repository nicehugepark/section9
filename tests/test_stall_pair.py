"""점과 손잡이는 한 벌이다 — 화면 몫 라운드2 (REQ-20260828-041-62x6, 2차 반려).

사용자가 같은 기능을 두 번 반려했다: "안된다 이 기능도."

라운드1이 서버에서 두 시계를 합쳤다(`stall_mins` 가 live_kind 를 읽는다). 화면에는
그때 **두 개의 갈래**가 남아 있었다.

  ① `!bl.length` — 카드만 가진 관문. 선행 대기 줄이 선 요청은 카드에서 멈춤 줄과
     손잡이를 통째로 잃었는데, 문서 화면은 그 관문을 몰라 같은 요청에 손잡이를
     줬다. **같은 요청이 두 자리에서 다른 말을 한다** — 판정 단추가 세 번
     반려됐던 그 결함(REQ-20260828-007)과 같은 모양이다.
  ② 점은 `live_kind` 를, 손잡이는 `stalled_mins` 를 각자 읽었다. 서버가 둘을
     한 벌로 만들어도 화면이 두 필드를 따로 읽는 한, 한쪽만 서는 조합이 남는다
     — 그것이 사용자가 본 "멈췄다고 적혔는데 누를 게 없는 카드"다.

그래서 계약은 하나로 줄인다: **멈춤 술어는 `stallState(r)` 하나뿐이고, 점·줄·
손잡이·열 머리 수·정렬이 전부 그 하나를 먹는다.** 술어가 하나면 어긋날 자리가
없다 — 이 저장소가 판정 버튼에서 세 번, 멈춤 표시에서 두 번 배운 것이다.

실행: python3 tests/ stall_pair
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


def _find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node", "/root/.vscode-server/bin/*/node"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


NODE = _find_node()


def _code(js):
    """주석을 걷어낸 코드만 — 주석은 옛 필드 이름을 근거로 인용한다."""
    js = re.sub(r"/\*[\s\S]*?\*/", " ", js)
    return re.sub(r"(?m)^\s*//.*$", " ", js)


def _server_src():
    """서버 원문 — 화면이 베껴 가진 상수가 원본과 갈라지지 않았는지 대조한다.

    임계를 화면에도 두는 것은 서버가 그 수를 행에 실어 주지 않기 때문이다
    (REQ-20260830-040). 베낀 값은 언젠가 갈라지므로, 갈라지는 순간 이 시험이
    잡는다 — 근원(서버가 실어 보내기)이 열리면 이 대조는 없어진다."""
    with open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8") as f:
        return f.read()


def _grab(src, name):
    m = re.search(r"\nfunction %s\([^)]*\)\{[\s\S]*?\n\}" % name, src)
    assert m, name
    return m.group(0)


class StallOnePredicate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.state = _code(_grab(cls.src, "stallState"))
        cls.stall = _grab(cls.src, "stallHTML")
        # 손잡이는 사실 줄을 떠나 id 줄의 벨트로 갔다 (REQ-20260830-040 규칙 4) —
        # 짓는 자리는 여전히 한 곳씩이라, 술어 하나라는 계약은 그대로다.
        cls.belt = _grab(cls.src, "deedBeltHTML") + _grab(cls.src, "wakeBtnHTML") \
            + _grab(cls.src, "driftBtnHTML") + _grab(cls.src, "stopBtnHTML")
        cls.card = _code(_grab(cls.src, "cardHTML"))
        cls.col = _code(_grab(cls.src, "colHTML"))
        cls.board = _grab(cls.src, "renderBoard")
        cls.demo = _grab(cls.src, "stallProbe")
        cls.democ = _code(cls.demo)
        # 문서 화면의 멈춤 줄이 사는 자리 (loadDoc 안)
        cls.doc = _code(cls.src[cls.src.index("async function loadDoc("):])

    # ---------- F1. 술어는 하나 ----------
    def test_f1_single_predicate_exists(self):
        self.assertIn("function stallState(", self.src,
                      "멈춤 술어를 짓는 자리가 없다")
        # 술어는 서버가 준 두 신호를 **함께** 읽는다
        self.assertIn("stalled_mins", self.state, "술어가 분을 안 읽는다")
        self.assertIn("live_kind", self.state, "술어가 점의 근거를 안 읽는다")

    def test_f1_card_does_not_judge_again(self):
        """카드는 판정하지 않고 술어를 부른다 — 필드를 직접 재판정하면 두 벌이 된다."""
        self.assertIn("stallState(r)", self.card, "카드가 술어를 안 부른다")
        self.assertNotIn("stalled_mins", self.card,
                         "카드가 아직 stalled_mins 를 직접 판정한다 (술어가 두 벌)")

    def test_f1_document_does_not_judge_again(self):
        seg = self.doc[:self.doc.index("stallHTML") + 400] \
            if "stallHTML" in self.doc else self.doc
        self.assertIn("stallHTML(", seg, "문서 화면이 멈춤 줄을 안 짓는다")
        self.assertNotIn("stalled_mins", seg,
                         "문서 화면이 아직 stalled_mins 를 직접 판정한다")

    # ---------- F2. 카드와 문서가 같은 답 ----------
    def test_f2_no_blocker_gate_on_card(self):
        """선행 대기 줄이 있어도 손잡이를 뺏지 않는다.

        원래 규칙은 '같은 사실을 두 줄로 말하지 않는다'였고 옳다. 그러나 그 관문이
        지운 것은 문장 하나가 아니라 **행동 하나**였다 — 그리고 문서 화면은 그
        관문을 몰라서, 같은 요청이 카드에선 못 깨우고 문서에선 깨워졌다.
        선행 대기(관계)와 멈춤(시계)은 다른 사실이기도 하다: 선행이 안 끝난 채로
        아무도 안 붙어 있는 요청이야말로 사람이 깨워야 하는 것이다.
        """
        m = re.search(r"const stall\s*=([\s\S]{0,300}?);\n", self.card)
        self.assertTrue(m, "멈춤 줄을 짓는 자리가 없다")
        self.assertNotIn("bl.length", m.group(1),
                         "선행 대기가 아직 멈춤 손잡이를 지운다 (카드·문서 비대칭)")

    def test_f2_both_call_the_same_builder(self):
        self.assertIn("stallHTML(", self.card)
        self.assertIn("stallHTML(", self.doc)

    # ---------- F3. 그려 놓고 못 누르는 카드가 없다 ----------
    def test_f3_stopped_dot_always_has_a_handle(self):
        """정지 마크가 서는 조건 = 손잡이가 서는 조건.

        문(멈췄나?)은 서버가 지금 다시 잰 `stalled_mins` 하나가 연다. 색인에 굳은
        작업자 기록(`live_kind`)은 문 안에서 **얼굴만** 고른다 — 어제의 정지가
        오늘 카드를 칠하고 손잡이는 없던 자리가 그것이다.
        """
        self.assertIn("stalled_mins", self.state, "문을 여는 것이 서버의 분이 아니다")
        self.assertIn("spawn_failed", self.state, "얼굴을 고르는 자리가 없다")
        self.assertIn("face", self.state, "얼굴을 돌려주지 않는다")
        # 손잡이를 짓는 자리는 **둘, 그리고 각각 하나**다 (REQ-20260830-040):
        # 글리프는 벨트(wakeBtnHTML), 낱말 갈래는 자기 줄(driftBtnHTML).
        wake = _code(_grab(self.src, "wakeBtnHTML"))
        drift = _code(_grab(self.src, "driftBtnHTML"))
        self.assertEqual(1, wake.count('data-wake="'),
                         "글리프 ▶ 를 짓는 자리가 하나가 아니다")
        self.assertEqual(1, wake.count('data-restart="'),
                         "중단해 둔 것을 되돌리는 자리가 하나가 아니다")
        self.assertEqual(1, drift.count('data-wake="'),
                         "낱말 손잡이를 짓는 자리가 하나가 아니다")
        # 그리지 않는 행에는 빈 문자열 — 부르는 쪽이 조건을 따로 갖지 않게 한다
        for name in ("stoppedRowHTML", "slowRowHTML", "deedBeltHTML"):
            self.assertIn('return "";', _grab(self.src, name),
                          "%s 가 빈 문자열을 안 돌려준다 — 조건이 두 벌이 된다" % name)

    # ---------- F9. 선은 그룹 위 하나 (REQ-20260830-040 규칙 5) ----------
    def test_f9_calm_draws_one_hairline_above_the_group(self):
        """calm 은 사실 줄마다 헤어라인 + 23px 을 얹었다 — 줄이 둘만 돼도 카드가
        카드가 아니게 됐다(실측 210px, 같은 열의 open 카드 90px).

        선이 나누는 것은 "메타 이야기와 상태 이야기"이지 상태 이야기 **안**이
        아니다 — 안은 간격이 나눈다. 첫 줄만 선을 갖는다."""
        css = self.src[self.src.index('[data-skin="calm"]'):]
        i = css.find('.card>.rvpt ~ .rvpt')
        self.assertGreater(i, 0, "둘째 줄부터 선을 지우는 규칙이 없다")
        rule = css[i:css.index("}", i)]
        for want in ("border-top:0", "padding-top:0"):
            self.assertIn(want, rule.replace(" ", ""),
                          "둘째 줄이 아직 %s 를 안 지운다" % want)
        # 네 조합을 다 덮는다 — 사실 줄은 .rvpt 이거나 .deedrow(낱말 갈래)다
        for sel in (".card>.rvpt ~ .deedrow", ".card>.deedrow ~ .rvpt",
                    ".card>.deedrow ~ .deedrow"):
            self.assertIn(sel, css, "%s 조합이 빠져 선이 두 번 그어진다" % sel)

    # ---------- F4. 거꾸로도 한 벌 ----------
    def test_f4_handle_implies_stopped_dot(self):
        """분이 실린 행의 점은 멈춤 모양이다 — 손잡이만 있고 점은 조용한 카드 금지."""
        i = self.card.index("livedot")
        self.assertIn("stallState(r)", self.card[:i],
                      "점을 고르기 전에 멈춤 술어를 읽지 않는다")
        # 옛 갈래: 멈춤인데 속 빈 회색 원(off)으로 그리던 자리 — off 는 이제
        # "모름"(스트림 조용함)에만 남는다. 멈춤을 그리는 off 는 없어야 한다.
        for mm in re.finditer(r'livedot off" title="([^"]*)"', self.card):
            self.assertNotIn("진전이 없다", mm.group(1),
                             "멈춤이 아직 .livedot.off(모름의 마크)로 그려진다")
        seg = self.card[i - 600 if i > 600 else 0:]
        on = seg.index("livedot on")
        stopped = seg.index("dot-stopped")
        self.assertLess(stopped, on,
                        "초록 점멸이 멈춤보다 먼저 걸린다 — 멈춘 것이 초록으로 뛴다")

    # ---------- F5. 화면은 분을 짓지 않는다 ----------
    def test_f5_screen_never_computes_minutes(self):
        for name, body in (("stallState", self.state), ("stallHTML", self.stall)):
            self.assertNotIn("Date.now()", body,
                             f"{name} 가 스스로 시계를 본다 — 분은 서버 것이다")
            self.assertNotIn("60000", body, f"{name} 가 분을 계산한다")

    # ---------- F6. 진단 파라미터 ----------
    def test_f6_stall_param_faces(self):
        self.assertIn("?stall=", self.src, "진단 파라미터가 문서화되지 않았다")
        for face in ("stallkind", "stalldep", "stallhold"):
            self.assertIn(face, self.democ, f"{face} 얼굴이 없다")
        head = self.src[self.src.index("/* ?stall=<분>"):]
        self.assertIn("spawn_failed", head[:600],
                      "죽음 얼굴을 부르는 법이 적혀 있지 않다")

    def test_f6_param_is_inert_without_query(self):
        m = re.search(r"if \(!m[^\n]*\) return rows;", self.democ)
        self.assertTrue(m, "파라미터가 없을 때 행을 그대로 돌려주지 않는다")

    def test_f6_param_goes_through_the_real_screen(self):
        """그림을 따로 그리지 않는다 — 진짜 카탈로그 행에 얹어 진짜 함수를 지난다."""
        self.assertIn("stallProbe(fresh)", self.src, "stallProbe 를 부르는 자리가 없다")
        for banned in ("data-wake", "rvpt", "livedot"):
            self.assertNotIn(banned, self.democ,
                             "진단용이 화면을 따로 그린다 — 보고 고친 것이 "
                             "화면이 아니게 된다")

    def test_f6_the_handle_can_be_pressed_headlessly(self):
        """?stallpress=<id> 가 **진짜 wakeDoc 을 부른다** — 창을 지어 세우지 않는다.

        거절 창(사용자가 "붉게 뜨면 반려"라고 판정해야 하는 그 창)은 손이 있어야
        열린다. 두 번 올라간 이 기능의 그 창을 아무도 눈으로 본 적이 없었다.
        """
        m = re.search(r"function stallPressProbe\(\)\{[\s\S]*?\n\}", self.src)
        self.assertTrue(m, "손잡이를 눌러 보는 자리가 없다")
        self.assertIn("wakeDoc(", m.group(0),
                      "진짜 누르는 함수를 안 부른다 — 그림을 세우면 고친 것이 "
                      "화면이 아니게 된다")
        self.assertNotIn("s9dlg", m.group(0), "진단이 창을 따로 짓는다")

    # ---------- F8. 열 머리와 정렬도 같은 술어 ----------
    def test_f8_column_count_uses_predicate(self):
        self.assertIn("stallState(", self.col,
                      "열 머리의 '멈춤 N' 이 다른 술어를 쓴다")
        self.assertNotIn("stalled_mins", self.col)

    def test_f8_sort_uses_predicate(self):
        seg = self.board[self.board.index("in-progress"):]
        self.assertIn("stallState(", seg,
                      "in-progress 정렬이 다른 술어를 쓴다")


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- 실제로 돌린다

STUBS = """
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const shortId = s => String(s).slice(0, 17);
const SCOLOR = {}, SYS_TAGS = new Set(), PICKED_MARK = "*";
const expanded = new Set();
const tagHue = () => 0, prioHTML = () => "", fmtElapsed = () => "0s";
const fmtWhen = iso => "오늘 16:45";
const rvClamped = (cap, tx) => `<div class="rvpt">${cap}</div>`;
// 작업 자리 칩(REQ-20260829-030)은 이 시험의 관심사가 아니다 — prioHTML 과 같이
// 비워 둔다. 자리 표시의 계약은 tests/test_workspace_chip.py 가 따로 붙잡는다.
const wsChip = () => "";
const rvLabel = s => s;
/* 담당 축이 카드에 들어왔다 (REQ-20260902-021) — 이 시험의 관심사는 아니지만
   cardHTML 이 그 조각들을 부르므로 재료를 세워 준다. 이 컴퓨터의 이름을 주면
   「다른 컴퓨터」 줄은 서지 않는다(행에 lease 가 없으니 어차피 안 선다) —
   진행 축의 판정이 종전 그대로인지가 이 파일이 재는 것이다. */
const TERMINAL = new Set(["done", "cancelled"]);
const viewMe = () => "u", isAdmin = () => false;
const dlink = (id, inner) => `<a href="#">${inner}</a>`;
globalThis.window = {__whoami: {machine: "THIS-PC"}};
const DEP_DEAD = new Set(["done", "cancelled"]);
let CAT = [];
const catFind = id => CAT.find(r => r.id === id) || null;
function liveBlockers(r){
  if (!r || DEP_DEAD.has(r.status)) return [];
  return (r.blocked_by || []).map(catFind).filter(b => b && !DEP_DEAD.has(b.status));
}
"""


def _const(src, name):
    """`const NAME = …;` 선언 한 덩어리를 원문 그대로 떠 온다 (여러 줄 허용)."""
    m = re.search(r"^const %s\s*=[\s\S]*?;\n" % re.escape(name), src, re.M)
    if not m:
        raise AssertionError("원문에 const %s 선언이 없다" % name)
    return m.group(0)


@unittest.skipUnless(NODE, "node 없음 — 실행 검증 생략")
class StallRendersTheSame(unittest.TestCase):
    """정적 검사는 '조건이 한 곳인가'를 보고, 여기서는 **그려서** 확인한다."""

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def render(self, rows, pre=""):
        g = lambda n: _grab(self.src, n)
        script = "\n".join([
            STUBS,
            g("fmtStall"), g("fmtLast"),
            "const wokeAt = new Map(); const WOKE_HOLD = 180000;",
            # 세우기 손잡이가 같은 함수 안에서 그려진다 (REQ-20260829-024) —
            # 그리지 않는 행에는 빈 문자열이 오므로 이 시험의 판정은 그대로다.
            "const stopAt = new Map(); const STOP_HOLD = 20000;",
            # 손잡이의 낱말은 상수 한 곳에서 온다 (REQ-20260829-024 라운드4)
            'const WAKE_LABEL = "이어가기", WAKE_GOING = "이어가는 중…";',
            'const STOP_LABEL = "중단하기", STOP_GOING = "중단 중…";',
            # 셋째 낱말과 두 글리프는 **원문에서 떠 온다** (REQ-20260830-032).
            # 여기에 베껴 두면 두 벌이 되고, 손잡이가 바뀔 때 한 벌만 고쳐진다 —
            # 이 파일이 낱말 상수를 한 곳에 모은 바로 그 이유다. 글리프는 카드와
            # 문서가 같은 그림을 그리는지 보는 이 시험의 판정 대상이기도 하다.
            _const(self.src, "DRIFT_LABEL"),
            _const(self.src, "GLYPH_PLAY"),
            _const(self.src, "GLYPH_PAUSE"),
            # 눌린 손잡이의 잠금 표시도 원문에서 (REQ-20260831-009) — 이 시험이
            # 재는 것이 바로 "되돌아온 ▶ 가 잠겨 있나"라, 베끼면 판정이 거짓이 된다.
            _const(self.src, "DEED_BUSY"),
            g("wokePending"), g("stopPending"), g("stallState"),
            # 세우기 손잡이의 네 갈래 (REQ-20260830-035) — 문안 표와 공용
            # 조각도 원문에서 떠 온다. 베끼면 두 벌이 되고, 갈래 하나가 카드에만
            # 서고 문서엔 안 서는 것을 못 잡는다.
            _const(self.src, "STOP_HOLD_LABEL"),
            _const(self.src, "STOP_ASK_TAIL"),
            _const(self.src, "STOP_KIND"),
            _const(self.src, "SLOW_WIN"), _const(self.src, "DRIFT_TIP"),
            # 막 뜬 백그라운드 작업의 손 위 글 (REQ-20260831-025) — 점의 사다리에서
            # cardHTML 이 부르는 조각이라, 목록에 없으면 그 갈래에 닿는 행이
            # 들어오는 날 render 가 통째로 멎는다(이 파일 위 주석의 그 규율).
            _const(self.src, "SPAWN_TAIL"), g("spawnTell"),
            g("jobBit"), g("factTail"), g("heldState"),
            # 판정 큐의 한 줄 (REQ-20260831-015) — 카드가 부르는 조각이라
            # 여기 없으면 render 가 통째로 멎는다. 낱말 상수도 원문에서 떠 온다.
            _const(self.src, "JQ_AHEAD"), _const(self.src, "JQ_CHURN"),
            g("judgeQueueHTML"),
            # 담당 축 (REQ-20260902-021) — 진행 축 사다리의 맨 위(「다른 컴퓨터」)와
            # 메타 줄의 조각을 카드가 부른다. 목록에 없으면 render 가 통째로
            # 멎는다(이 파일 위 주석의 그 규율).
            _const(self.src, "LEASE_TTL"), _const(self.src, "docCreator"),
            g("originWho"), g("originBits"), g("lineageTell"), g("lineageChip"),
            g("badgeFace"), g("ownerBadgeHTML"),
            g("leaseElsewhere"), g("canTakeover"), g("elsewhereRowHTML"),
            g("slowRowHTML"), g("stoppedRowHTML"),
            g("stopBtnHTML"), g("holdTell"), g("holdTellHTML"),
            g("wakeBtnHTML"), g("driftBtnHTML"),
            g("deedBeltHTML"), g("holdLockHTML"), g("stallHTML"),
            g("cardHTML"),
            "CAT = %s;" % json.dumps(rows),
            # 눌린 직후의 기억 상태를 세우는 자리 — 서버 왕복 없이 그 얼굴만 본다
            pre,
            # 문서 화면이 짓는 자리와 **같은 표현식** — 조각이 둘이 된 뒤로도
            # 둘 다 같은 함수에서 온다 (REQ-20260830-040).
            "const out = CAT.map(r => ({id: r.id, card: cardHTML(r),"
            "  row: stallHTML(catFind(r.id)), belt: deedBeltHTML(catFind(r.id)),"
            "  tell: holdTellHTML(catFind(r.id)), lock: holdLockHTML(catFind(r.id)),"
            # 문서 머리 띠의 얼굴 — 같은 함수, wordy 인자만 참 (REQ-20260830-046)
            "  docbelt: deedBeltHTML(catFind(r.id), true)}));",
            "console.log(JSON.stringify(out));",
        ])
        p = subprocess.run([NODE, "-e", script], capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(p.returncode, 0, "node 실행 실패:\n" + p.stderr[-2000:])
        return {o["id"]: o for o in json.loads(p.stdout.strip().splitlines()[-1])}


    ROWS = [
        # 멈춘 것 — 손잡이가 서야 한다
        {"id": "REQ-A", "type": "request", "status": "in-progress",
         "title": "멈춘 것", "user": "u", "stalled_mins": 45,
         "updated": "2026-08-29T16:45:00+09:00"},
        # 멈췄고 **선행 대기도 있는** 것 — 2차 반려가 뒤집은 자리
        {"id": "REQ-B", "type": "request", "status": "in-progress",
         "title": "멈췄고 선행도 있다", "user": "u", "stalled_mins": 30,
         "blocked_by": ["REQ-D"], "updated": "2026-08-29T16:45:00+09:00"},
        # 죽음이 기록된 것 — 채운 사각
        {"id": "REQ-C", "type": "request", "status": "in-progress",
         "title": "죽었다", "user": "u", "stalled_mins": 12,
         "live_kind": "spawn_failed", "live_reason": "프로세스 종료",
         "updated": "2026-08-29T16:45:00+09:00"},
        # 안 멈춘 것 — 손잡이도 점도 없어야 한다
        {"id": "REQ-D", "type": "request", "status": "open",
         "title": "선행", "user": "u"},
        # 도는 중 — 초록
        {"id": "REQ-E", "type": "request", "status": "in-progress",
         "title": "돈다", "user": "u", "live": True, "live_age": 3},
        # ---- 세우기 네 갈래 (REQ-20260830-035) — 카드와 문서가 같아야 한다 ----
        # 창이 맡은 것: 정상이므로 **줄은 서지 않고** ⏸ 만 id 줄에 선다
        {"id": "REQ-F", "type": "request", "status": "in-progress",
         "title": "창이 맡았다", "user": "u",
         "stoppable": {"kind": "session", "session": "abcd1234"}},
        # 나눠 맡은 일손이 붙은 것 — 역시 정상
        {"id": "REQ-G", "type": "request", "status": "in-progress",
         "title": "일손이 붙었다", "user": "u",
         "stoppable": {"kind": "agent", "session": "abcd1234", "agent": "a1"}},
        # 아무도 없는 것: 줄도 없고 ⏸ 하나만
        {"id": "REQ-H", "type": "request", "status": "in-progress",
         "title": "조용하다", "user": "u", "stoppable": {"kind": "idle"}},
        # 멈췄고 창도 맡고 있는 것 — ▶ 와 ⏸ 가 한 벨트에 나란히 서는 유일한 자리
        {"id": "REQ-I", "type": "request", "status": "in-progress",
         "title": "멈췄는데 창이 맡고 있다", "user": "u", "stalled_mins": 40,
         "updated": "2026-08-29T16:45:00+09:00",
         "stoppable": {"kind": "session", "session": "abcd1234"}},
        # 임계 **미만**으로 도는 백그라운드 작업 — 정상이라 줄이 없어야 한다 (규칙 3)
        {"id": "REQ-K", "type": "request", "status": "in-progress",
         "title": "막 시작한 백그라운드 작업", "user": "u",
         "worker": {"pid": 1, "age": 180},
         "jobs": [{"name": "테스트", "mins": 3}],
         "stoppable": {"kind": "worker"}},
        # 임계 **초과** — 「오래 걸림」 줄이 서고 잡 조각이 그 꼬리로 붙는다
        {"id": "REQ-L", "type": "request", "status": "in-progress",
         "title": "오래 도는 백그라운드 작업", "user": "u",
         "worker": {"pid": 2, "age": 1500},
         "jobs": [{"name": "테스트", "mins": 20}],
         "stoppable": {"kind": "worker"}},
        # 사람이 중단해 둔 것 — 진행 축의 맨 위
        {"id": "REQ-M", "type": "request", "status": "in-progress",
         "title": "중단해 뒀다", "user": "u",
         "stopped": {"at": 0, "by": "u", "age": 600},
         "stoppable": {"kind": "idle"}},
        # 붙어 있으나 조용한 것 — 손길 사실은 줄이 아니라 신원 문장으로 간다
        {"id": "REQ-N", "type": "request", "status": "in-progress",
         "title": "붙어 있는데 조용하다", "user": "u", "stall_state": "attached",
         "hand_mins": 3, "quiet_mins": 34,
         "stoppable": {"kind": "session", "session": "abcd1234"}},
    ]

    # 진행 축이 세울 수 있는 캡션은 셋뿐이다 (규칙 1·2). 「진행 중」·「담당」·
    # 「손길」 캡션이 이 목록에 없는 것이 이 개정의 전부다.
    AXIS_CAPS = ("중단", "멈춤", "오래 걸림")
    DEAD_CAPS = ("진행 중", "담당", "손길", "맡은 손")

    @staticmethod
    def _caps(html):
        return re.findall(r'<span class="rvcap">([^<]*)</span>', html)

    # ---------- 규칙 1·2: 줄 자격과 「축마다 하나」 ----------
    def test_normal_progress_says_nothing_in_letters(self):
        """정상은 줄이 아니다 — 점과 툴팁이 말한다.

        「진행 중 자동 작업 0분째」·「담당 없음」·「맡은 창 일하는 중」·
        「손길 3분 전 · 34분째 조용」은 전부 in-progress 열 이름과 점이 이미 한
        말이었다. 그 넷이 카드마다 한 줄씩 서면서 다듬어 둔 카드가 다시
        어지러워졌다 (사용자 반려, REQ-20260830-040)."""
        out = self.render(self.ROWS)
        for rid in ("REQ-F", "REQ-G", "REQ-H", "REQ-K", "REQ-N"):
            caps = self._caps(out[rid]["row"])
            self.assertEqual([], caps,
                             "%s: 정상인데 사실 줄이 섰다 (%s)" % (rid, caps))

    def test_the_progress_axis_never_stands_twice(self):
        """진행 축은 카드마다 최대 한 줄이다 — 사다리 밖에서 따로 서는 갈래가
        있으면 그 자리가 곧 지난번 반려 화면이다."""
        out = self.render(self.ROWS)
        for rid, o in out.items():
            caps = self._caps(o["row"])
            self.assertLessEqual(len(caps), 1,
                                 "%s: 진행 축에 줄이 %d 개다 (%s)"
                                 % (rid, len(caps), caps))
            for c in caps:
                self.assertIn(c, self.AXIS_CAPS,
                              "%s: 자격 없는 캡션 「%s」가 줄로 섰다" % (rid, c))

    def test_the_dead_captions_are_gone_from_the_whole_card(self):
        out = self.render(self.ROWS)
        for rid, o in out.items():
            for c in self.DEAD_CAPS:
                self.assertNotIn('<span class="rvcap">%s</span>' % c, o["card"],
                                 "%s: 폐지된 캡션 「%s」가 아직 선다" % (rid, c))

    def test_the_ladder_puts_the_human_stop_on_top(self):
        """중단 > 멈춤 > 오래 걸림. 사람이 자기 손으로 한 것이 가장 구체적이다."""
        out = self.render(self.ROWS)
        self.assertEqual(["중단"], self._caps(out["REQ-M"]["row"]))
        self.assertEqual(["멈춤"], self._caps(out["REQ-A"]["row"]))
        self.assertEqual(["오래 걸림"], self._caps(out["REQ-L"]["row"]))

    def test_the_relation_axis_still_stands_beside_the_progress_axis(self):
        """선행 대기(관계)와 멈춤(시계)은 다른 축이라 함께 선다 —
        REQ-20260828-041 2차 반려가 확정한 자리는 그대로다."""
        b = self.render(self.ROWS)["REQ-B"]["card"]
        self.assertIn("선행 대기", b, "선행 대기 줄이 사라졌다")
        self.assertIn("30분째 진전 없음", b)
        self.assertIn("data-wake=", b, "선행 대기가 손잡이를 먹었다")

    # ---------- 규칙 3: 임계는 서버의 수 하나 ----------
    def test_the_slow_line_reuses_the_server_window(self):
        """화면이 새 임계를 짓지 않는다 — 서버의 STALLED_WIN 을 그대로 쓴다.

        두 수가 갈라지면 카드가 `s9 stalled` 와 다른 말을 하게 된다."""
        m = re.search(r"^STALLED_WIN\s*=\s*(\d+)", _server_src(), re.M)
        self.assertTrue(m, "서버에 STALLED_WIN 이 없다")
        j = re.search(r"^const SLOW_WIN\s*=\s*(\d+)", self.src, re.M)
        self.assertTrue(j, "화면에 SLOW_WIN 이 없다")
        self.assertEqual(m.group(1), j.group(1),
                         "화면의 임계(%s)가 서버의 멈춤 창(%s)과 다르다"
                         % (j.group(1), m.group(1)))

    def test_a_young_worker_gets_no_line(self):
        out = self.render(self.ROWS)
        self.assertEqual("", out["REQ-K"]["row"],
                         "임계 미만인데 「오래 걸림」 줄이 섰다")
        self.assertIn("오래 걸림", out["REQ-L"]["row"])

    # ---------- 규칙 2 꼬리: 잡 조각은 자기 줄을 갖지 않는다 ----------
    def test_the_job_bit_rides_the_winning_line(self):
        out = self.render(self.ROWS)
        self.assertIn("· 테스트 20분째", out["REQ-L"]["row"],
                      "잡 조각이 이긴 줄의 꼬리로 안 붙었다")

    def test_a_line_never_shows_a_broken_tail(self):
        """꼬리는 하나뿐이다 (REQ-20260830-043 사용자 실측).

        사용자 캡처: 「멈춤 42분째 진전 없음 · 마지막 20:39 · 테스트 …」.
        조각을 무게순으로 잇고 넘치면 뒤부터 잘리게 두었는데, **잘린 조각은
        정보가 아니라 고장으로 읽힌다** — 무엇이 몇 분째인지 하나도 말하지
        못하면서 자리만 먹는다. 자르는 대신 고른다."""
        rows = [dict(r) for r in self.ROWS]
        for r in rows:
            if r["id"] == "REQ-A":
                r["jobs"] = [{"name": "테스트", "mins": 20}]
        out = self.render(rows)
        row = out["REQ-A"]["row"]
        self.assertEqual(1, row.count(" · "),
                         "멈춤 줄에 꼬리가 둘 이상이다: %s" % row)
        self.assertIn("· 테스트 20분째", row, "이긴 꼬리가 잡 조각이 아니다")
        # 손 위의 글(title)은 "마지막으로 바뀐 지"를 그대로 쓰므로 본문만 본다
        body = row[row.index("</span>"):]
        self.assertNotIn("마지막", body,
                         "되풀이 조각(마지막 HH:MM)이 아직 자리를 먹는다")
        # 떨어진 조각은 사라지지 않는다 — 신원 문장이 그대로 나른다
        self.assertIn("테스트 20분째", out["REQ-A"]["tell"])

    def test_the_evidence_for_the_word_handle_outranks_every_other_tail(self):
        """「고친 것 있음」은 낱말 손잡이의 **근거**라 어떤 꼬리보다 앞선다 —
        빠지면 버튼만 다른 이름으로 서는 근거 없는 손잡이가 된다."""
        rows = [dict(r) for r in self.ROWS]
        for r in rows:
            if r["id"] == "REQ-A":
                r["commit_drift"] = True
                r["jobs"] = [{"name": "테스트", "mins": 20}]
        row = self.render(rows)["REQ-A"]["row"]
        self.assertIn("· 고친 것 있음", row)
        self.assertEqual(1, row.count(" · "), "꼬리가 둘 이상이다: %s" % row)

    def test_a_lone_line_still_shows_its_context(self):
        """후보가 하나뿐이면 그것이 선다 — 규칙이 조각을 굶기지 않는다."""
        row = self.render(self.ROWS)["REQ-A"]["row"]
        self.assertIn("· 마지막 ", row, "붙일 자리가 있는데 꼬리가 비었다")

    def test_the_job_bit_without_a_line_goes_to_the_tell(self):
        """이긴 줄이 없으면 잡은 줄을 짓지 않고 신원 문장으로 간다."""
        out = self.render(self.ROWS)
        self.assertEqual("", out["REQ-K"]["row"], "잡이 혼자 줄을 세웠다")
        self.assertIn("테스트 3분째", out["REQ-K"]["tell"],
                      "잡 조각이 신원 문장에도 없다 — 사실이 통째로 사라졌다")

    def test_the_quiet_hand_survives_without_a_line(self):
        """손길 줄은 폐지됐지만 그 사실은 남는다 — "조용함을 감추지 않는다"
        (REQ-20260830-019)의 뜻은 신원 문장이 진다."""
        o = self.render(self.ROWS)["REQ-N"]
        self.assertEqual("", o["row"], "손길이 아직 줄을 세운다")
        self.assertIn("34분째 조용", o["tell"], "조용함이 통째로 사라졌다")

    # ---------- 규칙 4: 손잡이는 id 줄의 벨트에 · 그리고 하나뿐 ----------
    # 상태 × 노출 (REQ-20260830-042 designer 표). 값은 벨트에 서야 하는 속성이고,
    # "" 는 벨트가 아예 없어야 한다는 뜻이다.
    BELT = {"REQ-A": "data-wake=", "REQ-B": "data-wake=", "REQ-C": "data-wake=",
            "REQ-D": "", "REQ-E": "",
            "REQ-F": "data-stop=", "REQ-G": "data-stop=", "REQ-H": "",
            "REQ-I": "data-stop=", "REQ-K": "data-stop=", "REQ-L": "data-stop=",
            "REQ-M": "data-restart=", "REQ-N": "data-stop="}
    HANDLES = ("data-wake=", "data-stop=", "data-restart=")

    def test_the_belt_shows_one_handle_chosen_by_state(self):
        """단추는 상태를 따른다 (REQ-20260830-042).

        사용자: "이미 play, pause를 동시에 실행이 가능한 상태라는게 모순적이다.
        상태에 따라 버튼을 노출시키는게 어때?"

        붙어 있으면 끊는 쪽(⏸), 아니면 잇는 쪽(▶), 어느 쪽도 아니면 아무것도.
        관문은 벨트 한 곳이라 두 단추 함수는 서로를 모른다."""
        out = self.render(self.ROWS)
        for rid, want in self.BELT.items():
            belt = out[rid]["belt"]
            for h in self.HANDLES:
                n = belt.count(h)
                self.assertEqual(n, 1 if h == want else 0,
                                 "%s: 벨트에 %s 가 %d 개다 (기대: %s)"
                                 % (rid, h, n, want or "없음"))
            if not want:
                self.assertEqual("", belt, "%s: 빈 벨트가 아니다" % rid)

    def test_play_and_pause_never_stand_together(self):
        """▶ 와 ⏸ 는 같은 카드에 함께 서지 않는다 — 사용자가 모순이라 부른 그 그림.

        ▶⏸ 는 "한 축의 두 방향, 하나만 참"이라는 약속을 그림 자체로 한다.
        idle 갈래에 같은 ⏸ 를 준 순간 그 약속이 깨졌고(도는 것이 없는데 중단
        단추가 있다), 여기가 그 약속을 지키는 자리다."""
        out = self.render(self.ROWS)
        for rid, o in out.items():
            card = o["card"]
            play = "data-wake=" in card or "data-restart=" in card
            pause = "data-stop=" in card
            self.assertFalse(play and pause,
                             "%s: ▶ 와 ⏸ 가 한 카드에 함께 섰다" % rid)

    def test_the_lock_moved_to_the_document(self):
        """idle 의 잠금은 사라진 것이 아니라 문서로 옮겼다.

        지금 내리는 행위가 아니라 앞으로에 대한 **정책**이라 층이 다르다.
        길은 새로 파지 않는다 — 같은 stop 경로의 idle 갈래를 그대로 쓴다."""
        out = self.render(self.ROWS)
        lock = out["REQ-H"]["lock"]
        self.assertIn("자동 이어받기 끄기", lock, "문서에 낱말 단추가 없다")
        self.assertIn('data-kind="idle"', lock, "idle 갈래로 안 간다")
        self.assertIn("data-stop=", lock, "기존 stop 경로를 안 쓴다")
        # 카드에는 서지 않는다 — 카드의 한 결정은 "지금 이어갈까" 하나다
        self.assertNotIn("자동 이어받기 끄기", out["REQ-H"]["card"])
        # 붙어 있는 카드에는 잠글 것이 없다
        for rid in ("REQ-F", "REQ-L"):
            self.assertEqual("", out[rid]["lock"],
                             "%s: 붙어 있는데 잠금 단추가 섰다" % rid)

    def test_a_held_document_offers_no_lock(self):
        """이미 사람이 중단해 둔 문서에 「중단해 두기」가 또 서면 ▶ 와 나란히
        반대 방향 두 단추가 된다 — 042 가 카드에서 걷어낸 그 모순이 낱말로
        갈아입고 문서에 옮겨 와 있었다 (REQ-20260830-046 designer ④)."""
        rows = [{"id": "REQ-HELD", "type": "request", "status": "in-progress",
                 "title": "중단해 둔 것", "user": "u",
                 "stopped": {"age": 600},
                 "stoppable": {"kind": "idle", "claimed": False},
                 "updated": "2026-08-30T21:00:00+09:00"}]
        out = self.render(rows)
        self.assertEqual("", out["REQ-HELD"]["lock"],
                         "중단해 둔 문서에 잠금 단추가 또 섰다 — 잠글 것이 없다")
        self.assertIn("data-restart=", out["REQ-HELD"]["belt"],
                      "중단해 둔 문서의 벨트에 「이어가기」가 없다")

    def test_the_document_belt_wears_words(self):
        """문서의 글리프는 낱말을 입는다 (REQ-20260830-046) — 낱말 없는 11px
        회색 글리프는 행동으로 읽히지 않았다("버튼의 위치가 너무 눈에 띄지
        않는다"의 절반). 카드는 원형(ico) 그대로고, 조건은 얼굴 인자 하나다."""
        out = self.render(self.ROWS)
        att = out["REQ-F"]     # 붙어 있는 것 — ⏸
        self.assertIn("wgly", att["docbelt"], "문서 벨트가 낱말 얼굴이 아니다")
        self.assertIn('<span class="lbl">중단하기</span>', att["docbelt"],
                      "문서 ⏸ 에 낱말이 없다")
        self.assertIn("ico", att["belt"], "카드 벨트가 원형 얼굴을 잃었다")
        self.assertNotIn("lbl", att["belt"], "카드 글리프에 낱말이 붙었다")
        idle = out["REQ-A"]    # 멈춘 것 — ▶
        self.assertIn('<span class="lbl">이어가기</span>', idle["docbelt"],
                      "문서 ▶ 에 낱말이 없다")

    def test_a_stalled_card_always_offers_something_to_press(self):
        """멈췄다고 그려 놓고 누를 것이 없는 카드는 없다 (REQ-20260828-041).

        배타 노출로 **어느** 단추가 서는지는 바뀌었지만(붙어 있으면 ⏸), 정지
        마크가 선 카드에 손잡이가 있어야 한다는 계약은 그대로다."""
        out = self.render(self.ROWS)
        for rid, o in out.items():
            if "dot-stopped" not in o["card"]:
                continue
            self.assertTrue(any(h in o["card"] for h in self.HANDLES)
                            or "끝났는지 확인" in o["card"],
                            "%s: 정지 마크는 섰는데 누를 것이 없다" % rid)

    def test_the_handles_live_in_the_id_belt(self):
        """▶·⏸ 는 사실 줄이 아니라 id 줄에 선다 (규칙 4).

        사실 줄에 붙어 있는 동안 손잡이의 자리는 카드마다 달랐다 — 멈춤 줄·
        진행 중 줄·담당 줄·빈 줄. 자리가 사실을 따라다니면 매번 찾아야 하고,
        좁은 칸에서는 그 27px 이 문장에서 빼앗은 폭이라 멈춤 줄이 잘렸다."""
        out = self.render(self.ROWS)
        for rid in ("REQ-A", "REQ-I", "REQ-M", "REQ-L", "REQ-F"):
            card, belt = out[rid]["card"], out[rid]["belt"]
            self.assertIn("deedbelt", belt, "%s: 벨트가 없다" % rid)
            self.assertIn(belt, card, "%s: 카드가 벨트를 안 싣는다" % rid)
            # 벨트는 id 줄 **안**에 있다 — 제목보다 앞이고, 사실 줄보다 앞이다.
            idrow = card[card.index('<div class="id"'):]
            self.assertLess(idrow.index("deedbelt"), idrow.index('class="t"'),
                            "%s: 벨트가 id 줄을 벗어났다" % rid)
            # 사실 줄에는 손잡이가 남아 있지 않다
            for h in self.HANDLES:
                self.assertNotIn(h, out[rid]["row"],
                                 "%s: 손잡이가 아직 사실 줄에 붙어 있다" % rid)

    def test_the_word_handle_keeps_its_own_row(self):
        """낱말 손잡이 「끝났는지 확인」만은 자기 줄을 지킨다 — 87px 를 id 줄에
        얹으면 식별자를 밀어낸다. 그리고 그 카드의 벨트는 비어 있다."""
        rows = [dict(r) for r in self.ROWS]
        for r in rows:
            if r["id"] == "REQ-A":
                r["commit_drift"] = True
        out = self.render(rows)
        row, belt = out["REQ-A"]["row"], out["REQ-A"]["belt"]
        self.assertIn("deedrow wordy", row, "낱말 손잡이가 자기 줄을 잃었다")
        self.assertIn("끝났는지 확인", row)
        self.assertEqual("", belt,
                         "낱말 갈래인데 벨트에 글리프가 또 섰다 — 한 카드에 둘이다")

    def test_the_pause_name_is_one_word_in_every_attached_branch(self):
        """붙어 있는 갈래 셋의 ⏸ 이름은 하나다 (ux-writer 뼈대).
        갈린 것은 붙지 않은 갈래의 낱말뿐이다 — 「중단해 두기」."""
        out = self.render(self.ROWS)
        for rid in ("REQ-F", "REQ-G", "REQ-I", "REQ-L", "REQ-N"):
            self.assertIn('aria-label="중단하기"', out[rid]["card"],
                          "%s: ⏸ 의 이름이 「중단하기」가 아니다" % rid)

    # ---------- 규칙 4의 필수 조건: 신원은 툴팁 전용이 아니다 ----------
    def test_identity_reaches_a_reader_without_a_pointer(self):
        """신원이 줄에서 내려간 대가로 낭독기가 그것을 잃으면 안 된다 —
        designer 가 이 개정을 통과시키며 단 조건이다. 손잡이가 없는 카드
        (조용한 것)에서도 살아 있어야 한다 — 거기가 가장 말이 없는 카드다."""
        out = self.render(self.ROWS)
        want = {"REQ-F": "맡은 창", "REQ-G": "일손", "REQ-H": "담당하는 것이 없습니다",
                "REQ-L": "백그라운드 작업이 이 요청을 맡아"}
        for rid, w in want.items():
            tell = out[rid]["tell"]
            self.assertIn('class="vh"', tell,
                          "%s: 시각적 숨김 문장이 없다 (툴팁 전용은 접근성 후퇴)" % rid)
            self.assertIn(w, tell, "%s: 신원 문장에 「%s」가 없다" % (rid, w))
            self.assertIn(tell, out[rid]["card"], "%s: 카드가 그것을 안 싣는다" % rid)
        # 손 위의 글은 식별자가 진다 — 벨트는 상자가 버튼뿐이라 과녁이 못 된다
        self.assertRegex(out["REQ-F"]["card"], r'<span class="idn" title="[^"]*맡은 창')

    # ---------- 배타가 새로 만드는 유일한 결함 ----------
    def test_pressing_one_handle_clears_the_other_memory(self):
        """한쪽을 누르면 반대편 눌림 기억을 지운다 (REQ-20260830-042 designer).

        배타가 서면 한 자리에서 얼굴이 바뀐다(▶ → 몇 초 뒤 ⏸). 두 기억이 따로
        살면 ▶ 를 누른 뒤 곧바로 ⏸ 로 중단했을 때 되돌아온 ▶ 가 남은 3분 잠금
        때문에 죽어 있다 — 방금 자기가 중단한 것을 다시 못 켠다."""
        def body(name):
            i = self.src.index("async function %s(" % name)
            return _code(self.src[i:self.src.index("\n}", i)])
        wake, stop = body("wakeDoc"), body("stopDoc")
        self.assertIn("stopAt.delete(id)", wake, "▶ 가 반대편 기억을 안 지운다")
        self.assertIn("wokeAt.delete(id)", stop, "⏸ 가 반대편 기억을 안 지운다")

    def test_the_returning_handle_is_not_locked(self):
        """⏸ 를 누른 직후의 기억 상태로 그려도 ▶ 는 눌린다."""
        # stopDoc 이 실제로 하는 두 줄을 그대로 세운다
        out = self.render(self.ROWS,
                          pre='wokeAt.delete("REQ-A");'
                              ' stopAt.set("REQ-A", Date.now());')
        # 잠금 표시는 `aria-disabled` 다 (REQ-20260831-009) — `disabled` 로
        # 잠그면 눌린 손잡이가 포커스를 잃어 키보드 손이 자기 자리를 잃는다.
        self.assertNotIn("aria-disabled", out["REQ-A"]["belt"],
                         "되돌아온 ▶ 가 잠겨 있다 — 방금 중단한 것을 못 켠다")
        # 지우지 않았다면 잠겼을 것이다 — 이 시험이 무엇을 잡는지 스스로 보인다
        out2 = self.render(self.ROWS,
                           pre='wokeAt.set("REQ-A", Date.now());'
                               ' stopAt.set("REQ-A", Date.now());')
        self.assertIn('aria-disabled="true"', out2["REQ-A"]["belt"],
                      "잠금 자체가 사라졌다 — 연타 보호가 없다")
        self.assertNotRegex(out2["REQ-A"]["belt"], r'(?<!-)\bdisabled\b(?!=)',
                            "아직 disabled 로 잠근다 — 포커스가 걷힌다")

    # ---------- 카드와 문서는 같은 조각을 쓴다 ----------
    def test_card_and_document_render_the_same_pieces(self):
        """조각이 둘로 나뉜 뒤로도 두 화면은 같은 함수에서 온다.
        여기가 갈라지면 같은 요청이 카드에선 못 깨우고 문서에선 깨워진다."""
        out = self.render(self.ROWS)
        for r in self.ROWS:
            o = out[r["id"]]
            for part in ("row", "tell", "belt"):
                if o[part]:
                    self.assertIn(o[part], o["card"],
                                  "%s: 카드와 문서의 %s 조각이 다르다"
                                  % (r["id"], part))
            if not o["belt"]:
                self.assertNotIn("data-wake=", o["card"],
                                 "%s: 문서엔 없는 손잡이가 카드엔 있다" % r["id"])

    def test_the_dot_tells_the_same_story_as_the_line(self):
        """점과 글이 어긋나지 않는다 — 어긋나면 사람은 **둘 다** 안 믿는다.

        (손잡이와의 한 벌 계약은 배타 노출로 갈래가 늘어, 위
        test_a_stalled_card_always_offers_something_to_press 가 이어받았다.)"""
        out = self.render(self.ROWS)
        self.assertIn("dot-stopped mild", out["REQ-A"]["card"])
        # 문장은 REQ-20260831-005 문구 확정본 — 「도중에 멎었다」는 5(멈춤)·
        # 7(중단해 둠)과 같은 낱말을 안 쓰는 죽음의 제 이름이다
        self.assertIn('livedot dot-stopped" title="이 요청을 맡았던 일이 도중에 멎었습니다',
                      out["REQ-C"]["card"])
        self.assertIn("livedot on", out["REQ-E"]["card"])
        for rid in ("REQ-A", "REQ-B", "REQ-C"):
            self.assertIn("dot-stopped", out[rid]["card"])
            self.assertIn("진전 없음", out[rid]["row"])

    def test_a_quiet_row_says_nothing(self):
        out = self.render(self.ROWS)
        for rid in ("REQ-D", "REQ-E"):
            self.assertNotIn("멈춤", out[rid]["card"], "%s 가 멈췄다고 말한다" % rid)
            self.assertEqual("", out[rid]["row"])

    # ---------- 낱말 (REQ-20260830-039) ----------
    def test_no_coined_word_reaches_the_screen(self):
        """조어 「맡은 손」과 반려어 잔재는 문안 표에도 화면에도 없다.

        그린 것만 보면 확인 창 문안(ask)이 빠져나가므로 표 전문을 함께 읽는다.
        유지 판정 낱말(맡은 창·일손)은 여기 없다 — 재론 금지 근거가
        REQ-20260830-039 문서에 있다."""
        out = self.render(self.ROWS)
        table = _code(_const(self.src, "STOP_KIND"))
        for w in ("맡은 손", "세워 두", "손길이 없", "붙어 있는 손길"):
            self.assertNotIn(w, table, "문안 표에 「%s」가 남아 있다" % w)
        for rid, o in out.items():
            self.assertNotIn("맡은 손", o["card"],
                             "%s: 화면에 조어 「맡은 손」이 섰다" % rid)

    def test_the_idle_branch_speaks_of_a_named_owner(self):
        """idle 갈래의 개념어는 「담당」이다 (039 리드 확정)."""
        table = _code(_const(self.src, "STOP_KIND"))
        self.assertIn("담당하는 것이 없습니다", table)
        # 「~어 두다」 꼴은 유지하되 동사가 「끄다」로 갔다 (REQ-20260901-005) —
        # 반려어 「세워 두다」 계열이 돌아오지 않는지는 어휘 게이트가 함께 잰다.
        self.assertIn("꺼 두면", table, "정책 툴팁이 끄기 문법을 잃었다")
