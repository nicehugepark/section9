"""세션을 고를 수 없다 (REQ-20260829-023 · 20260827-079 반려).

세 가지가 한 뿌리에서 나왔다.

① **끝난 세션이 화면에서 살아 있어 보였다.** `chat_live()` 는 attach pid 생존
   ·활동 신선도만 보고 `ended` 를 안 봤다. 그래서 `/api/chat/target?sid=X` 가
   끝난 세션을 `live: true` 로 보고했고, 프런트의 자동 폴백은 `!live` 일 때만
   도니 고정이 풀리지 않았다. 화면은 `target 02e5bc69 · idle` 이라 말하는데
   보내면 "라이브 클로드 세션이 없다" 가 났다 — 두 자리가 서로 다른 말을 했다.
   다른 호출자는 전부 `not b.get("ended")` 를 손으로 덧붙여 있었다(4544 줄의
   `live = chat_live(b) and not b.get("ended")`). 손으로 덧붙이는 규칙은
   언젠가 빠진다 — 판정을 `chat_live` 안으로 넣어 빠질 자리를 없앤다.

② **고를 길이 없었다.** 대상은 자동 선택뿐이라, 살아 있는 세션이 여럿이거나
   붙잡은 것이 죽었을 때 사람이 다른 세션을 지목할 수단이 없었다.
   `session_rows()` 가 고를 수 있는 줄을 준다.

③ **깨우기가 계정을 안 들고 갔다.** `wake_session()` 은 `CLAUDE_CONFIG_DIR`
   없이 `s9 code` 를 띄워 언제나 기본 계정으로 돌아왔다. 계정을 바꾸려는데
   붙어 있는 세션이 없으면 "세션을 깨운 뒤 다시 눌러 주세요" 였고, 깨우면
   또 옛 계정이었다 — 사람이 빠져나갈 수 없는 고리였다.

실행: python3 tests/ session_pick
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import tempfile
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from unittest import mock
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9pick-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ.update({"S9_ROOT": TMP, "S9_MACHINE": "testbox"})
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_pick", importlib.machinery.SourceFileLoader("s9_mod_pick", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _write(sid, **kw):
    """세션 바인딩 한 장 — STATE 에 실제 파일로 둔다."""
    os.makedirs(mod.STATE, exist_ok=True)
    b = {"machine": "testbox", "session": sid, "user": "tester",
         "entry": "code", "ended": "", "attach_pid": "",
         "transcript_path": os.path.join(TMP, sid + ".jsonl")}
    b.update(kw)
    with open(os.path.join(mod.STATE, f"testbox__{sid}.json"), "w",
              encoding="utf-8") as f:
        json.dump(b, f)
    tp = b.get("transcript_path") or ""
    if tp:
        with open(tp, "w", encoding="utf-8") as f:
            f.write("{}\n")
    return b


class TestEndedIsNotLive(unittest.TestCase):
    """① 끝난 세션은 어느 자리에서도 살아 있다고 말하지 않는다."""

    # P1. ended 가 서 있으면 pid 가 살아 있어도 live 가 아니다.
    #     실사고: attach pid 는 SessionEnd 뒤에도 잠깐 남는다 — 그 틈에
    #     화면이 "idle" 을 그렸고 보내기는 "세션 없다" 를 냈다.
    def test_p1_ended_binding_is_never_live(self):
        b = {"session": "deadsess", "ended": "1", "attach_pid": str(os.getpid())}
        self.assertFalse(mod.chat_live(b))

    # P2. 같은 바인딩에서 ended 만 걷으면 live 다 — ended 하나가 가른다는
    #     것을 붙잡는다(pid 생존 판정 자체를 망가뜨린 것이 아니다).
    def test_p2_same_binding_without_ended_is_live(self):
        b = {"session": "livesess", "ended": "", "attach_pid": str(os.getpid())}
        self.assertTrue(mod.chat_live(b))

    # P3. 신선한 활동이 있어도 ended 를 이기지 못한다.
    def test_p3_fresh_activity_does_not_revive_ended(self):
        b = _write("freshend", ended="1")
        os.utime(b["transcript_path"], None)
        self.assertFalse(mod.chat_live(b))


class TestSessionRows(unittest.TestCase):
    """② 고를 수 있는 줄 — 사람이 대상을 지목할 수 있어야 한다."""

    def setUp(self):
        for f in os.listdir(mod.STATE) if os.path.isdir(mod.STATE) else []:
            os.remove(os.path.join(mod.STATE, f))

    # P4. 살아 있는 세션과 끝난 세션이 함께 나오되, 끝난 것은 그렇게 표시된다.
    #     끝난 세션을 목록에서 지우지 않는다 — 방금까지 보던 대상이 말없이
    #     사라지면 "내가 뭘 잘못했나" 가 된다. 지우는 게 아니라 접는다.
    def test_p4_lists_live_and_ended_with_marks(self):
        _write("aliveone", attach_pid=str(os.getpid()))
        _write("endedone", ended="1")
        rows = mod.session_rows()
        by = {r["sid"]: r for r in rows}
        self.assertIn("aliveone", by)
        self.assertIn("endedone", by)
        self.assertTrue(by["aliveone"]["live"])
        self.assertFalse(by["endedone"]["live"])
        self.assertTrue(by["endedone"]["ended"])

    # P5. 살아 있는 줄이 먼저 온다 — 고를 수 있는 것이 위다.
    def test_p5_live_rows_come_first(self):
        _write("zzended", ended="1")
        _write("aalive", attach_pid=str(os.getpid()))
        rows = mod.session_rows()
        live_ix = [i for i, r in enumerate(rows) if r["live"]]
        dead_ix = [i for i, r in enumerate(rows) if not r["live"]]
        self.assertTrue(live_ix and dead_ix)
        self.assertLess(max(live_ix), min(dead_ix))

    # P6. 수신 대기(tail) 중인 세션은 살아 있는 것들 중에서도 맨 위다 —
    #     사람의 말을 지금 소화할 수 있는 세션이 첫 후보여야 한다.
    def test_p6_listening_outranks_merely_live(self):
        _write("quietone", attach_pid=str(os.getpid()))
        _write("hearsyou", attach_pid=str(os.getpid()))
        with mock.patch.object(mod, "_inbox_watch_alive",
                               lambda s: s == "hearsyou"):
            rows = mod.session_rows()
        self.assertEqual(rows[0]["sid"], "hearsyou")
        self.assertTrue(rows[0]["listening"])

    # P7. 줄마다 사람이 고를 근거가 붙는다 — 누구의 세션인지·언제 움직였는지.
    def test_p7_row_carries_who_and_when(self):
        _write("withwho", attach_pid=str(os.getpid()), user="nicehugepark")
        r = [x for x in mod.session_rows() if x["sid"] == "withwho"][0]
        self.assertEqual(r["user"], "nicehugepark")
        self.assertTrue(r["last"])          # ISO 시각 — 빈 문자열이 아니다


class TestWakeCarriesAccount(unittest.TestCase):
    """③ 깨우기는 고른 계정으로 뜬다 — 안 그러면 빠져나갈 수 없는 고리다."""

    # P8. 계정을 주면 실행 명령이 그 계정의 설정 디렉토리를 들고 간다.
    def test_p8_wake_with_account_sets_config_dir(self):
        with mock.patch.object(mod, "chat_target", lambda *_a, **_k: None), \
             mock.patch.dict(os.environ, {"S9_WAKE_DRYRUN": "1"}):
            r = mod.wake_session(account="새-계정")
        self.assertTrue(r["ok"], r)
        self.assertIn("CLAUDE_CONFIG_DIR=", r["cmd"])
        self.assertIn("새-계정", r["cmd"])

    # P9. 기본 계정(@home)은 아무것도 덧붙이지 않는다 — 집으로 돌아오는 문에
    #     환경변수를 달면 그 문이 다른 문이 된다.
    def test_p9_home_account_adds_nothing(self):
        with mock.patch.object(mod, "chat_target", lambda *_a, **_k: None), \
             mock.patch.dict(os.environ, {"S9_WAKE_DRYRUN": "1"}):
            r = mod.wake_session(account=mod.ACCOUNT_HOME_KEY)
        self.assertTrue(r["ok"], r)
        self.assertNotIn("CLAUDE_CONFIG_DIR=", r["cmd"])

    # P10. 계정 없이 부르면 종전 그대로다 (회귀 방지).
    def test_p10_no_account_behaves_as_before(self):
        with mock.patch.object(mod, "chat_target", lambda *_a, **_k: None), \
             mock.patch.dict(os.environ, {"S9_WAKE_DRYRUN": "1"}):
            r = mod.wake_session()
        self.assertTrue(r["ok"], r)
        self.assertNotIn("CLAUDE_CONFIG_DIR=", r["cmd"])
        self.assertIn("s9", r["cmd"])

    # P11. 이미 살아 있는 세션이 있으면 계정을 줘도 창을 새로 열지 않는다 —
    #      계정을 바꾸는 길은 재시작이지 두 번째 창이 아니다.
    def test_p11_refuses_when_live_even_with_account(self):
        with mock.patch.object(mod, "chat_target",
                               lambda *_a, **_k: {"session": "livesess"}), \
             mock.patch.object(mod, "chat_live", lambda *_a, **_k: True):
            r = mod.wake_session(account="새-계정")
        self.assertFalse(r["ok"])
        self.assertIn("살아있는 세션", r["reason"])


INDEX = index_path()


class TestPickerScreen(unittest.TestCase):
    """④ 화면 — 사람이 손으로 고를 수 있어야 비로소 "변경이 된다"."""

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    # P12. 상태줄의 대상 세션이 눌린다 — 누를 수 있으면 눌리게 보여야 한다.
    def test_p12_target_sid_is_a_handle(self):
        st = self._fn("termStatus")
        self.assertIn("ccsidbtn", st, "대상 세션에 손잡이가 없다")
        self.assertRegex(st, r'ccsidbtn[^`]*cursor:pointer',
                         "누를 수 있어 보이지 않는다")
        self.assertRegex(
            self.src, r'closest\("\.ccsidbtn"\)\)\s*termSessionPick',
            "눌러도 세션 고르기 창이 열리지 않는다")

    # P13. 대상 바꾸기에는 확인 한 걸음을 두지 않는다.
    #      REQ-20260829-017 이 모델·계정 창에 확인을 세운 것은 그것이 **대화를
    #      끊는** 일이라서다. 대상 바꾸기는 세션을 안 건드리고 다시 눌러
    #      돌아오면 그만이라, 여기까지 확인을 붙이면 그 한 걸음이 뜻을 잃는다.
    def test_p13_switching_view_needs_no_confirm_step(self):
        self.assertNotIn("confirm", self._fn("sessShape"),
                         "되돌리기 쉬운 일에 확인을 붙였다")

    # P14. 끝난 세션은 목록에 남되 고를 수 없다 — 무덤에 다시 붙는 것이
    #      이 요청의 결함 그 자체였다. 그렇다고 지우지도 않는다.
    def test_p14_ended_rows_stay_but_cannot_be_picked(self):
        it = self._fn("sessItems")
        self.assertIn("off: !r.live", it, "끝난 세션을 고를 수 있다")
        self.assertIn("끝났습니다", it, "끝났다는 사실이 줄에 안 적힌다")
        # 남기는 것은 **지금 보고 있는** 무덤 하나뿐이다 — 그 줄에만 "말없이
        # 사라지면 안 된다"가 닿는다. 남의 무덤은 고를 수 있는 줄을 묻는다.
        self.assertIn("r.live || r.sid === cur", self._fn("sessShape"),
                      "끝난 세션이 목록을 채운다")

    # P15. 고른 뒤 목록을 믿지 않고 서버에 다시 묻는다 — 창을 연 시점의
    #      사진을 믿고 붙으면 죽은 세션 고정을 손으로 다시 만드는 셈이다.
    def test_p15_reasks_the_server_before_attaching(self):
        fn = self._fn("termSessionPick")
        self.assertIn("/api/chat/target?sid=", fn, "붙기 전에 다시 묻지 않는다")
        self.assertIn("termAttach", fn, "고른 세션에 붙지 않는다")

    # P16. 세션이 없을 때 계정 창이 막다른 길이 아니다.
    #      실사고: "세션을 깨운 뒤 다시 눌러 주세요" → 깨우면 또 옛 계정.
    def test_p16_no_session_is_not_a_dead_end(self):
        self.assertNotIn("세션을 깨운 뒤 다시 시도해 주세요",
                         self.src, "막다른 문구가 남아 있다")
        sh = self._fn("acctShape")
        self.assertIn('st === "nosession"', sh, "시작하기 처지를 안 가른다")
        self.assertIn("그 계정으로 시작", sh, "시작 버튼의 이름이 없다")
        # 고른 줄의 낱말도 함께 간다 — 바꿀 것이 없는 창이 "바꿀 것"이라 적으면
        # 화면이 자기가 무슨 일을 하는지 틀리게 말한다.
        self.assertIn('pickNote: wake ? "시작할 것"', sh, "고른 줄이 '바꿀 것'이라 적힌다")
        self.assertIn("o.pickNote", self._fn("s9choose"), "창이 그 낱말을 안 읽는다")

    # P17. 세션이 없어도 로그인된 계정은 고를 수 있다 (읽기용 목록이 아니다).
    def test_p17_ready_accounts_are_pickable_without_a_session(self):
        self.assertIn("off: !r.ready || (!live && !wake)",
                      self._fn("acctItems"), "세션이 없으면 전부 흐려진다")

    # P18. 붙어 있는 세션이 없으면 어느 줄도 "지금 이것"이 아니다 —
    #      아무것도 안 붙어 있는데 한 줄이 ● 를 달면 이미 정답처럼 읽힌다.
    def test_p18_nothing_is_current_when_nothing_is_attached(self):
        it = self._fn("acctItems")
        self.assertIn("cur: !!r.current && !wake", it, "안 붙었는데 ● 가 선다")
        self.assertIn('(r.current && !wake) ? "지금 이것"', it,
                      "안 붙었는데 '지금 이것' 이 붙는다")

    # P19. 그 확인은 고른 계정을 실어 깨우기로 간다 — 재시작으로 가면 서버가
    #      "세션 없음" 으로 거부하고, 사용자는 창이 시킨 대로 했는데 거부만 받는다.
    def test_p19_confirm_wakes_with_the_chosen_account(self):
        sw = self._fn("claudeAccountSwitch")
        self.assertIn("sessionWake(picked.key", sw, "세션이 없을 때 깨우지 않는다")
        self.assertLess(sw.index("sessionWake(picked.key"),
                        sw.index("sessionRestart(d && d.sid"),
                        "재시작으로 먼저 가 거부를 받는다")
        wk = self._fn("sessionWake")
        self.assertIn("/api/session/wake", wk, "깨우기를 부르지 않는다")
        self.assertIn("account ? {account} : {}", wk, "고른 계정을 안 실어 보낸다")

    # P21. 갈 곳이 없을 때 고르는 창이 막다른 길이 되지 않는다 — 붙잡은 것이
    #      죽었고 살아 있는 줄이 하나도 없는 상태가 이 요청을 낸 그 화면이다.
    def test_p21_picker_offers_a_way_out_when_nowhere_to_go(self):
        sh = self._fn("sessShape")
        self.assertIn("somewhere", sh, "갈 곳이 있는지 안 따진다")
        self.assertIn("SESS_FOOT", sh, "갈 곳이 없을 때 나가는 문이 없다")
        # 앞에 `waiting ||` 이 붙어도(REQ-20260902-065: 받는 중에는 없다고
        # 말하지 않는다) 계약은 그대로다 — 갈 곳이 있으면 발치가 빈다.
        self.assertIn('somewhere ? ""', sh,
                      "갈 곳이 있는데도 깨우기를 나란히 세운다")
        self.assertIn('data-act="wake"', self.src, "깨우기 손잡이가 없다")
        self.assertIn('picked.act === "wake"', self._fn("termSessionPick"),
                      "깨우기를 눌러도 아무 일도 안 일어난다")

    # P20. 손 없이 볼 수 있는 진단 주소가 있다 — 누르지 않으면 볼 수 없는
    #      화면은 이 길로만 캡처된다.
    def test_p20_diagnostic_addresses_exist(self):
        for k in ("sessions:", "sessdead:", "sessnone:", "acctwake:"):
            self.assertIn(k, self.src, f"진단 주소 {k} 가 없다")
        self.assertIn('m[1] === "sesslive"', self.src,
                      "실서버로 여는 진단 주소가 없다")
        # 그림을 따로 그리지 않는다 — 진단도 실제 함수가 창을 짓는다
        self.assertIn("sessions: sessShape(", self.src,
                      "진단이 실제 함수를 안 쓴다 (그림이 실제와 갈린다)")


if __name__ == "__main__":
    unittest.main()
