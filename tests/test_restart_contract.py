"""전환·재시작의 거부 계약과 3단 재시작 (REQ-20260901-011).

실사고 2026-09-01: fable 한도가 소진된 세션에서 대시보드만으로는 모델도 계정도
바꿀 수 없었다. 셋이 겹쳤다.

  ① 한도로 굳은 턴이 「진행 중」으로 읽혀 모든 전환이 거부됐다.
  ② 유일한 탈출구(「중단하고 바꾸기」)가 **소진된 그 모델**을 써야 소화되는
     지시라 원리상 수렴할 수 없었다 — 사람이 빠져나갈 문이 없었다.
  ③ 계정 전환 재시작은 대상 프로필에 그 대화가 없어 이어받지 못했는데,
     그것을 **SIGTERM 을 쏜 뒤에야** 알았다. 화면은 90초를 기다리다
     「세션이 돌아온 것을 확인하지 못했습니다」를 냈다.

여기서 지키는 계약 넷:
  · 갈래에 이름이 있다 — why_kind("busy"|"limit"|"no_resume") · limit · attempt
  · 한도 갈래는 거부가 아니라 진행이다 (멈출 것이 없으니 멈추라고 하지 않는다)
  · 거부 갈래에도 문이 있다 — force(「그래도 바꾸기」), 잃는 것을 응답이 말한다
  · 못 이어받으면 **죽이기 전에** 거부하고, 이어받을 수 있으면 옮겨 준다

실행: python3 tests/ restart_contract
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)

TMP = tempfile.mkdtemp(prefix="s9rcontract-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_rc", importlib.machinery.SourceFileLoader("s9_mod_rc", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

HOME_PROFILE = os.path.join(TMP, "claude-home")
PROFILES = os.path.join(TMP, "claude-profiles")
CWD_KEY = "-tmp-work"
WRAPPER = 424242

LIMIT_TEXT = ("You've reached your Fable 5 limit. "
              "Run /usage-credits to continue or switch models with /model.")


def asst(stop="end_turn", model="claude-fable-5", text="x", **kv):
    return {"type": "assistant",
            "message": {"stop_reason": stop, "model": model,
                        "content": [{"type": "text", "text": text}]}, **kv}


def limit_event():
    return asst(stop="stop_sequence", model="<synthetic>", text=LIMIT_TEXT,
                error="rate_limit", apiErrorStatus=429)


def transcript(profile_dir, full, entries):
    d = os.path.join(profile_dir, "projects", CWD_KEY)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, full + ".jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return p


def make_binding(sid, **kv):
    os.makedirs(mod.STATE, exist_ok=True)
    b = {"machine": "testbox", "session": sid, "user": "tester",
         "history": [], **kv}
    with open(os.path.join(mod.STATE, f"testbox__{sid}.json"), "w",
              encoding="utf-8") as f:
        json.dump(b, f)
    return b


def read_binding(sid):
    with open(os.path.join(mod.STATE, f"testbox__{sid}.json"),
              encoding="utf-8") as f:
        return json.load(f)


class RestartCase(unittest.TestCase):
    """모든 시험이 같은 무대를 쓴다 — 프로필 두 자리와 래퍼 하나."""

    def setUp(self):
        os.makedirs(HOME_PROFILE, exist_ok=True)
        os.makedirs(PROFILES, exist_ok=True)
        self.kills = []
        self.stack = [
            mock.patch.object(mod, "_pid_is_claude", lambda p: True),
            # S9_MACHINE 은 모듈 로드 시점에만 세워진다 — 실행 중 조회는
            # 진짜 호스트 이름으로 가므로 여기서 무대 이름으로 못 박는다
            mock.patch.object(mod, "current_machine", lambda: "testbox"),
            mock.patch.object(mod, "claude_home", lambda: HOME_PROFILE),
            # `@home` 의 자리 (REQ-20260901-017 R6)
            mock.patch.object(mod, "account_home_dir", lambda: HOME_PROFILE),
            # 사용량은 이 무대의 관심사가 아니다 (REQ-20260901-017 R4) —
            # 실기계의 계정 상태가 이 시험의 판정에 새어 들어오면 안 된다.
            mock.patch.object(mod, "claude_usage", lambda *a, **k: {}),
            mock.patch.object(mod, "profiles_base", lambda: PROFILES),
            mock.patch.object(mod, "user_config", lambda n: {}),
            mock.patch.object(mod, "do_user_config_set",
                              lambda *a, **k: None),
        ]
        for p in self.stack:
            p.start()

    def tearDown(self):
        for p in reversed(self.stack):
            p.stop()

    def wrapper_mode(self):
        """이 세션이 재시작 루프(s9 code) 밑에 있는 것으로 본다."""
        return (mock.patch.object(mod, "pid_ppid", lambda p: WRAPPER),
                mock.patch.object(mod, "pid_cmdline",
                                  lambda p: "python bin/s9 code"),
                mock.patch("os.kill",
                           lambda pid, sig: self.kills.append((pid, sig))))

    def session(self, sid, entries, profile=HOME_PROFILE):
        full = f"{sid}-full-session-id"
        tp = transcript(profile, full, entries)
        make_binding(sid, attach_pid=str(os.getpid()), transcript_path=tp,
                     cwd="/tmp/work")
        return full, tp

    def restart(self, sid, **kv):
        a, b, c = self.wrapper_mode()
        with a, b, c:
            return mod.restart_session(sid, **kv)


class TheRefusalHasAName(RestartCase):
    """갈래에 이름이 있다 — 화면이 무엇을 말할지 서버가 알려 준다."""

    # S8. busy 거부에 why_kind 가 실린다
    def test_s8_busy_carries_its_kind(self):
        self.session("s8sess", [asst("tool_use")])
        r = self.restart("s8sess", model="opus")
        self.assertFalse(r["ok"])
        self.assertEqual(r["why_kind"], "busy")
        self.assertIn("진행 중", r["reason"])
        self.assertEqual(self.kills, [], "거부인데 SIGTERM 이 나갔다")

    # S9. 같은 사유로 연속 몇 번째인가 — 세는 것은 서버다
    def test_s9_attempt_counts_and_resets(self):
        self.session("s9sess", [asst("tool_use")])
        got = [self.restart("s9sess", model="opus")["attempt"]
               for _ in range(3)]
        self.assertEqual(got, [1, 2, 3],
                         "네 번째 같은 벽을 화면이 알아볼 수 없다")
        # 한 번 지나가면 회차는 0 으로 돌아간다
        self.session("s9sess", [asst("end_turn")])
        self.assertTrue(self.restart("s9sess", model="opus")["ok"])
        self.session("s9sess", [asst("tool_use")])
        self.assertEqual(self.restart("s9sess", model="opus")["attempt"], 1)

    # S10+S21. 한도 갈래는 **거부가 아니라 진행**이다 (실사고 그 모양)
    def test_s10_limit_proceeds_with_its_name(self):
        self.session("s10sess", [asst("end_turn"), limit_event()])
        r = self.restart("s10sess", model="opus")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["why_kind"], "limit")
        self.assertEqual(r["limit"]["model"], "Fable 5")
        self.assertEqual(len(self.kills), 1, "진행인데 재시작이 안 나갔다")

    # S21(b). 사람이 네 번 시도해 합성 응답이 쌓여도 같다 — 수렴하지 않던 자리
    def test_s21_repeated_limit_events_still_pass(self):
        self.session("s21sess", [asst("end_turn")] + [limit_event()] * 4)
        self.assertTrue(self.restart("s21sess", account="@home")["ok"])

    # S22. 보호는 남는다 — 진짜 도는 턴에는 SIGTERM 이 나가지 않는다
    def test_s22_a_running_turn_is_still_protected(self):
        self.session("s22sess", [asst("tool_use")])
        self.restart("s22sess", model="opus")
        self.assertEqual(self.kills, [])


class TheDoorThatIsAlwaysOpen(RestartCase):
    """거부 갈래에도 문이 있다 — 오판정 하나가 교착이 되지 않는다."""

    # S11. force 는 진행하고, 잃는 것을 말한다
    def test_s11_force_proceeds_and_says_the_cost(self):
        self.session("s11sess", [asst("tool_use")])
        r = self.restart("s11sess", model="opus", force=True)
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["forced"])
        self.assertTrue(r["discarded_turn"],
                        "하던 턴을 버린다는 사실을 응답이 말하지 않는다")
        self.assertEqual(len(self.kills), 1)

    # S12. 기본값은 여전히 보호 쪽 — 명시해야 끊긴다
    def test_s12_without_force_nothing_changes(self):
        self.session("s12sess", [asst("tool_use")])
        self.assertFalse(self.restart("s12sess", model="opus")["ok"])
        self.assertEqual(self.kills, [])

    # 유휴 세션에 force 를 줘도 버릴 턴은 없다 — 거짓 경고를 만들지 않는다
    def test_force_on_an_idle_session_discards_nothing(self):
        self.session("s11bsess", [asst("end_turn")])
        r = self.restart("s11bsess", model="opus", force=True)
        self.assertTrue(r["ok"], r)
        self.assertFalse(r["discarded_turn"])


class BeforeYouKillTheSession(RestartCase):
    """못 이어받으면 **죽이기 전에** 거부하고, 이어받을 수 있으면 옮겨 준다."""

    def _acct_dir(self, name):
        return os.path.join(PROFILES, name, "projects", CWD_KEY)

    # S13. F — 이어받을 수 없으면 SIGTERM 전에 거부한다
    def test_s13_no_resume_refuses_before_sigterm(self):
        full, tp = self.session("s13sess", [asst("end_turn")])
        os.remove(tp)          # 원본도 없고 대상에도 없다
        r = self.restart("s13sess", account="acct2")
        self.assertFalse(r["ok"])
        self.assertEqual(r["why_kind"], "no_resume")
        self.assertEqual(self.kills, [],
                         "이어질 수 있는지 모르는 채로 세션을 내렸다")
        self.assertFalse(os.path.exists(mod._restart_marker_path("s13sess")))

    # S14. E — 대화 기록을 대상 계정으로 옮기고 진행한다
    def test_s14_the_conversation_is_carried_over(self):
        full, tp = self.session("s14sess", [asst("end_turn")])
        r = self.restart("s14sess", account="acct2")
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["resume_copied"])
        dest = os.path.join(self._acct_dir("acct2"), full + ".jsonl")
        self.assertTrue(os.path.isfile(dest),
                        "대상 계정이 이 대화를 못 찾는다 (No conversation found)")
        with open(dest, encoding="utf-8") as f:
            self.assertIn("end_turn", f.read())
        self.assertEqual(len(self.kills), 1)

    # S15. E 는 덮지 않는다 — 대상 쪽 기록이 더 나중일 수 있다
    def test_s15_an_existing_conversation_is_not_overwritten(self):
        full, tp = self.session("s15sess", [asst("end_turn")])
        d = self._acct_dir("acct3")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, full + ".jsonl"), "w", encoding="utf-8") as f:
            f.write("KEEP\n")
        r = self.restart("s15sess", account="acct3")
        self.assertTrue(r["ok"], r)
        self.assertFalse(r["resume_copied"])
        with open(os.path.join(d, full + ".jsonl"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "KEEP\n")

    # S16. 되돌아가는 길도 같은 규칙이다 — 한 방향만 되는 문을 만들지 않는다
    def test_s16_the_way_back_home_works_too(self):
        acct_home = os.path.join(PROFILES, "acct4")
        full, tp = self.session("s16sess", [asst("end_turn")],
                                profile=acct_home)
        r = self.restart("s16sess", account="@home")
        self.assertTrue(r["ok"], r)
        self.assertTrue(os.path.isfile(os.path.join(
            HOME_PROFILE, "projects", CWD_KEY, full + ".jsonl")))

    # force 는 이 문도 지난다 — 다만 대화가 안 이어진다는 사실을 말한다
    def test_forcing_past_no_resume_says_the_conversation_is_lost(self):
        full, tp = self.session("s13bsess", [asst("end_turn")])
        os.remove(tp)
        r = self.restart("s13bsess", account="acct5", force=True)
        self.assertTrue(r["ok"], r)
        self.assertFalse(r["resumed_conversation"])
        self.assertTrue(r["discarded_conversation"])
        # 못 찾을 sid 를 넘기면 claude 가 뜨자마자 죽는다 — 안 넘긴다
        with open(mod._restart_marker_path("s13bsess"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["resume"], "")
        self.assertNotIn("--resume", r["cmd"])


class TheSessionKeepsItsLineage(RestartCase):
    """G — `--resume` 은 새 sid 를 만든다. 옛↔새를 잇는 실은 서버가 준다."""

    # S17. 재시작이 계보 기록을 남긴다
    #      (REQ-20260901-017: 파일은 이제 래퍼당 **이력**이다 — 덮어쓰기가
    #       아니라 append 라, 마지막 줄이 방금 그 재시작이다)
    def test_s17_a_restart_leaves_a_thread(self):
        self.session("s17sess", [asst("end_turn")])
        self.assertTrue(self.restart("s17sess", model="opus")["ok"])
        rec = mod._lineage_read(mod._lineage_path(WRAPPER))[-1]
        self.assertEqual(rec["from"], "s17sess")
        self.assertEqual(rec["wrapper_pid"], WRAPPER)

    # S18. 새 세션이 뜨면 양쪽 바인딩이 서로를 안다 (멱등)
    def test_s18_both_ends_learn_each_other(self):
        self.session("s18old", [asst("end_turn")])
        self.assertTrue(self.restart("s18old", model="opus")["ok"])
        make_binding("s18new", attach_pid="777", transcript_path="")
        with mock.patch.object(mod, "pid_ppid",
                               lambda p: WRAPPER if p == 777 else 1):
            self.assertEqual(mod.lineage_link(), [("s18old", "s18new")])
            self.assertEqual(mod.lineage_link(), [], "계보 기록이 소비되지 않았다")
        self.assertEqual(read_binding("s18new")["resumed_from"], "s18old")
        self.assertEqual(read_binding("s18old")["resumed_to"], "s18new")

    # S18(b). 잡고 있던 일도 함께 건넌다 — 미클레임으로 보이면 워처가 겹쳐 스폰한다
    def test_s18b_the_claim_crosses_over(self):
        self.session("s18bold", [asst("end_turn")])
        b = read_binding("s18bold")
        b["active_reqs"] = ["REQ-20260901-011-62x6"]
        b["claim_at"] = {"REQ-20260901-011-62x6": "2026-09-01T14:00:00+09:00"}
        with open(os.path.join(mod.STATE, "testbox__s18bold.json"), "w",
                  encoding="utf-8") as f:
            json.dump(b, f)
        self.assertTrue(self.restart("s18bold", model="opus")["ok"])
        make_binding("s18bnew", attach_pid="779", transcript_path="")
        with mock.patch.object(mod, "pid_ppid",
                               lambda p: WRAPPER if p == 779 else 1):
            mod.lineage_link()
        nb = read_binding("s18bnew")
        self.assertEqual(nb["active_reqs"], ["REQ-20260901-011-62x6"])
        self.assertIn("REQ-20260901-011-62x6", nb["claim_at"])

    # 새 세션이 제 클레임을 이미 가졌으면 덮지 않는다
    def test_an_existing_claim_is_not_overwritten(self):
        self.session("s18cold", [asst("end_turn")])
        b = read_binding("s18cold")
        b["active_reqs"] = ["REQ-A"]
        with open(os.path.join(mod.STATE, "testbox__s18cold.json"), "w",
                  encoding="utf-8") as f:
            json.dump(b, f)
        self.assertTrue(self.restart("s18cold", model="opus")["ok"])
        make_binding("s18cnew", attach_pid="780", transcript_path="",
                     active_reqs=["REQ-B"])
        with mock.patch.object(mod, "pid_ppid",
                               lambda p: WRAPPER if p == 780 else 1):
            mod.lineage_link()
        self.assertEqual(read_binding("s18cnew")["active_reqs"], ["REQ-B"])

    # S20. 낡은 기록은 잇지 않고 닫는다 — 엉뚱한 세션이 남의 계보를 물지 않는다
    #      (REQ-20260901-017: 파일을 지우는 대신 그 줄을 `done` 으로 닫는다 —
    #       이력은 남고, 다시 후보가 되지는 않는다. 파일 자체는 래퍼가 죽을 때
    #       `wrapper_stamp_sweep` 이 치운다.)
    def test_s20_a_stale_thread_is_cut(self):
        import time as _t
        p = mod._lineage_path(WRAPPER)
        mod._lineage_write(WRAPPER, "s20old")
        recs = mod._lineage_read(p)
        recs[-1]["ts"] = _t.time() - mod.LINEAGE_FRESH_SEC - 10
        mod._lineage_rewrite(p, recs)
        make_binding("s20new", attach_pid="778", transcript_path="")
        with mock.patch.object(mod, "pid_ppid",
                               lambda p: WRAPPER if p == 778 else 1):
            self.assertEqual(mod.lineage_link(), [])
        self.assertEqual(mod._lineage_read(p)[-1]["done"], "expired")
        self.assertNotIn("resumed_from", read_binding("s20new"))
        # 닫힌 기록은 다시 후보가 되지 않는다 (다음 폴이 물지 않는다)
        with mock.patch.object(mod, "pid_ppid",
                               lambda p: WRAPPER if p == 778 else 1):
            self.assertEqual(mod.lineage_link(), [])

    # S19. 폴이 그 실을 실어 준다 (화면의 sid 못박기를 풀 재료)
    def test_s19_the_poll_carries_the_thread(self):
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        head = src.split('elif parsed.path == "/api/chat/target"', 1)[1][:4200]
        self.assertIn("lineage_link()", head,
                      "폴이 계보를 잇지 않으면 옛 sid 에 못 박힌 화면이 "
                      "성공한 재시작을 「돌아오지 않음」으로 센다")
        self.assertIn('"resumed_from"', head)
        self.assertIn('"resumed_to"', head)


if __name__ == "__main__":
    unittest.main(verbosity=2)
