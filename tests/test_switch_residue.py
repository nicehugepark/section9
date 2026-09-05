"""계정 전환이 남긴 잔결함 셋 (REQ-20260901-017 · 011 의 뒤).

011·014 가 착지한 직후의 실전환에서 세 가지가 어긋났다. 규명해 보니 뿌리는
서로 다른 셋이었고, 공통 조상이 하나 있었다 — **재시작 계약이 두 프로세스에
걸쳐 있는데 둘의 코드·설정 나이가 따로 논다.**

  ① 계정을 바꿨는데 헤더는 옛 계정을 찍는다. `claude_usage()` 가 홈 경로를
     하드코딩해 언제나 `~/.claude` 를 읽었다 — 캐시 열쇠까지 홈 자격증명의
     mtime 이라 프로필을 바꿔도 갱신조차 되지 않았다. 화면이 "안 바뀌었다"고
     말하니 사용자는 방금 성공한 전환을 되돌렸다.
  ② 「세션 다시 시작 중」 칩이 안 걷힌다. 완료 판정의 유일한 증거가
     `listening`(수신함 tail)인데, 그것은 첫 턴이 성공해야 생기는 2차 산물이다.
     한도로 죽은 기동 턴은 세션이 떠 있어도 영영 안 듣는다.
  ③ 재시작이 정책(opus)이 아니라 fable 로 떴다. 「유지」가 뜻한 것이 "지금
     정책"이 아니라 **래퍼가 몇 시간 전에 얼려 둔 인자**였다.

여기서 지키는 것:
  · 사용량·계정은 **그 세션의 설정 디렉토리**를 따라간다 (R1)
  · 「유지」는 지금 정책이다 — 재시작마다 다시 만든다 (R2a)
  · 래퍼도 제 코드 나이를 말한다 (R3)
  · 한도로 굳을 자리로는 미리 안 보낸다 (R4)
  · 「떠 있다」와 「듣고 있다」는 다른 사실이다 (R5)
  · `@home` 의 뜻은 한 벌이다 (R6)
  · 마커 수거가 남의 파일을 지우지 않는다 · 재시작 이력은 덮이지 않는다 (곁가지)

실행: python3 tests/ switch_residue
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)

TMP = tempfile.mkdtemp(prefix="s9switch-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_sw", importlib.machinery.SourceFileLoader("s9_mod_sw", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

with open(S9_SRC, encoding="utf-8") as _f:
    SRC = _f.read()

UPSTREAM = {"limits": [
    {"kind": "session", "group": "session", "percent": 3, "severity": "normal",
     "scope": None, "resets_at": "2026-09-01T20:00:00+00:00"},
    {"kind": "weekly_scoped", "group": "weekly", "percent": 100,
     "severity": "blocked", "resets_at": "2026-09-06T11:00:00+00:00",
     "scope": {"model": {"id": None, "display_name": "Fable 5"}}},
]}


def login(d, email, token="tok"):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, ".claude.json"), "w", encoding="utf-8") as f:
        json.dump({"oauthAccount": {"emailAddress": email}}, f)
    with open(os.path.join(d, ".credentials.json"), "w", encoding="utf-8") as f:
        json.dump({"claudeAiOauth": {"accessToken": token,
                                     "subscriptionType": "max"}}, f)
    return d


class FakeUpstream:
    """urlopen 대역 — 실제 업스트림을 때리지 않는다 (시험은 네트워크를 안 쓴다)."""

    def __init__(self, payload=None):
        self.tokens = []
        self.payload = payload if payload is not None else UPSTREAM

    def __call__(self, req, timeout=None):
        self.tokens.append(req.headers.get("Authorization", ""))
        body = json.dumps(self.payload).encode()

        class R:
            def read(self_inner):
                return body

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False
        return R()


# ---------------------------------------------------------------- R1

class TheHeaderFollowsTheSession(unittest.TestCase):
    """헤더가 찍는 계정은 **그 세션이 붙은 계정**이다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9swusage-")
        self.a = login(os.path.join(self.tmp, "A"), "a@ex.com", "tok-a")
        self.b = login(os.path.join(self.tmp, "B"), "b@ex.com", "tok-b")
        self.home = login(os.path.join(self.tmp, "home"), "home@ex.com", "tok-h")
        self.up = FakeUpstream()
        self.stack = [
            mock.patch.object(mod, "_usage_cache", {}),
            mock.patch.object(mod, "_USAGE_DIR",
                              os.path.join(self.tmp, "cache")),
            mock.patch.object(mod, "account_home_dir", lambda: self.home),
            mock.patch("urllib.request.urlopen", self.up),
        ]
        for p in self.stack:
            p.start()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def tearDown(self):
        for p in reversed(self.stack):
            p.stop()

    # R1-1. 그 계정의 자격증명으로 그 계정을 묻는다
    def test_r1_1_it_reads_the_account_it_was_asked_about(self):
        d = mod.claude_usage(self.a)
        self.assertTrue(d["ok"], d)
        self.assertEqual(d["email"], "a@ex.com")
        self.assertEqual(self.up.tokens, ["Bearer tok-a"])
        self.assertNotIn("tok-a", json.dumps(d), "토큰이 응답에 실렸다")

    # R1-2. 같은 프로세스에서 계정을 바꿔 물으면 **그 계정**이 나온다
    def test_r1_2_a_second_account_is_not_the_first_ones_cache(self):
        self.assertEqual(mod.claude_usage(self.a)["email"], "a@ex.com")
        d = mod.claude_usage(self.b)
        self.assertEqual(d["email"], "b@ex.com",
                         "캐시가 남의 계정을 돌려줬다 — 사고 ① 의 그 자리")
        self.assertEqual(self.up.tokens, ["Bearer tok-a", "Bearer tok-b"])

    # R1-3. 안 물으면 `@home` — 종전 계약 그대로
    def test_r1_3_no_argument_means_home(self):
        self.assertEqual(mod.claude_usage()["email"], "home@ex.com")

    # R1-4. 캐시 열쇠는 (설정 디렉토리, 자격증명 mtime)
    def test_r1_4_the_cache_key_is_the_pair(self):
        mod.claude_usage(self.a)
        mod.claude_usage(self.a)
        self.assertEqual(len(self.up.tokens), 1, "60초 캐시가 안 먹었다")
        mod.claude_usage(self.b)
        cred = os.path.join(self.a, ".credentials.json")
        os.utime(cred, (time.time() + 5, time.time() + 5))
        mod.claude_usage(self.a)
        self.assertEqual(self.up.tokens[-1], "Bearer tok-a",
                         "자격증명이 바뀌었는데 캐시를 그대로 썼다")
        mod.claude_usage(self.b)
        self.assertEqual(len(self.up.tokens), 3,
                         "A 의 무효화가 B 의 캐시까지 버렸다")

    # R1-5. 폴이 세션의 설정 디렉토리를 넘긴다 (계약)
    def test_r1_5_the_endpoint_asks_about_this_session(self):
        head = SRC.split('elif parsed.path == "/api/claude/usage"', 1)[1][:600]
        self.assertIn("session_cfg_dir", head,
                      "헤더가 여전히 홈 계정을 묻는다")

    # R1-6. 로그인 전 자리는 200 + ok:false (500 금지)
    def test_r1_6_a_slot_without_credentials_says_so(self):
        d = mod.claude_usage(os.path.join(self.tmp, "empty"))
        self.assertFalse(d["ok"])
        self.assertIn("자격증명", d["error"])
        self.assertEqual(self.up.tokens, [], "자격증명도 없이 업스트림을 때렸다")

    # 판정 경로는 업스트림을 기다리지 않는다 (offline)
    def test_the_decision_path_never_waits_on_the_network(self):
        d = mod.claude_usage(self.a, offline=True)
        self.assertFalse(d["ok"])
        self.assertEqual(self.up.tokens, [])
        mod.claude_usage(self.a)                       # 창을 열어 데워 두면
        self.assertTrue(mod.claude_usage(self.a, offline=True)["ok"])

    # 계정 창을 여는 순간 줄마다 데운다 (R4 의 전제)
    def test_opening_the_picker_warms_every_row(self):
        rows = [{"path": self.a, "ready": True},
                {"path": self.b, "ready": True},
                {"path": os.path.join(self.tmp, "x"), "ready": False}]
        self.assertEqual(mod.accounts_warm_usage(rows), 2)
        for _ in range(50):
            if len(self.up.tokens) >= 2:
                break
            time.sleep(0.02)
        self.assertEqual(sorted(self.up.tokens),
                         ["Bearer tok-a", "Bearer tok-b"])

    # 한도 판정: 모델 한정 100% 와 계정 전체 100% 를 가른다
    def test_the_limit_reading_is_per_model(self):
        u = mod.claude_usage(self.a)
        self.assertTrue(mod.usage_limit_hit(u, "claude-fable-5"))
        self.assertIsNone(mod.usage_limit_hit(u, "claude-opus-5[1m]"))
        self.assertIsNone(mod.usage_limit_hit({}, "claude-fable-5"),
                          "모르는 것으로 사람을 세웠다")
        whole = {"ok": True, "limits": [{"kind": "weekly_all", "percent": 100}]}
        self.assertTrue(mod.usage_limit_hit(whole, "anything"))


# ---------------------------------------------------------------- R2a

class TheRestartUsesTodaysPolicy(unittest.TestCase):
    """「유지」는 "그때 그 인자"가 아니라 "지금 정책"이다."""

    def setUp(self):
        self.cfg = {"s9code_args": "--permission-mode auto --model fable"}
        self.stack = [
            mock.patch.object(mod, "resolve_user", lambda *a, **k: "tester"),
            mock.patch.object(mod, "user_config", lambda n: dict(self.cfg)),
        ]
        for p in self.stack:
            p.start()

    def tearDown(self):
        for p in reversed(self.stack):
            p.stop()

    # R2a-1. 정책이 바뀌면 **다음 재시작부터** 그 값이 나간다
    def test_r2a_1_a_policy_change_reaches_the_next_restart(self):
        self.assertIn("fable", mod.code_base_cmd([]))
        self.cfg = {"s9code_args": "--permission-mode auto --model opus"}
        cmd = mod.code_restart_cmd([], {"resume": "full-sid", "model": ""})
        self.assertIn("opus", cmd)
        self.assertNotIn("fable", cmd,
                         "래퍼가 얼려 둔 인자로 재시작했다 — 사고 ③ 의 그 자리")
        self.assertEqual(cmd[cmd.index("--resume") + 1], "full-sid")

    # R2a-2. 마커가 모델을 말하면 그 값이 이긴다
    def test_r2a_2_the_marker_still_wins(self):
        cmd = mod.code_restart_cmd([], {"resume": "s", "model": "opus"})
        self.assertEqual(cmd.count("--model"), 1)
        self.assertIn("opus", cmd)
        self.assertNotIn("fable", cmd)

    # R2a-3. 인자를 만드는 자리는 루프 **안**이다 (계약)
    def test_r2a_3_the_arguments_are_built_inside_the_loop(self):
        body = SRC.split("        while True:\n            subprocess.run",
                         1)[1][:1200]
        self.assertIn("code_restart_cmd(", body,
                      "루프가 기동 시점 base_cmd 를 재사용한다")
        self.assertNotIn("_restart_cmd(base_cmd", body)


# ---------------------------------------------------------------- R3

class TheWrapperKnowsItsAge(unittest.TestCase):
    """래퍼도 장수 프로세스다 — 코드도 설정도 기동 시점에 언다."""

    def setUp(self):
        self.pid = os.getpid()
        for name in ("code-%d.json" % self.pid,):
            try:
                os.remove(mod._terminal_state_path(name))
            except OSError:
                pass

    def _stamp(self, mtime):
        return {"s9": {"mtime": mtime, "size": 10},
                "hook": {"mtime": mtime, "size": 20}}

    # R3-1·R3-2. 지문을 남기고, 그 뒤 코드가 바뀌면 그 사실을 말한다
    def test_r3_1_a_stamp_is_left_and_compared(self):
        with mock.patch.object(mod, "running_code_stamp",
                               lambda: self._stamp(100.0)):
            mod.wrapper_stamp_write(self.pid)
            fresh = mod.wrapper_code_age(self.pid)
        self.assertEqual(fresh["basis"], "stamp")
        self.assertFalse(fresh["stale"])
        with mock.patch.object(mod, "running_code_stamp",
                               lambda: self._stamp(200.0)):
            old = mod.wrapper_code_age(self.pid)
        self.assertTrue(old["stale"])
        self.assertIn("bin/s9", old["parts"])

    # R3-3. 지문이 없는 옛 래퍼는 **기동 시각**으로 판정한다
    #       (지문 기능이 없던 시절에 뜬 래퍼가 곧 가장 낡은 래퍼다)
    def test_r3_3_an_older_wrapper_is_judged_by_when_it_started(self):
        with mock.patch.object(mod, "running_code_stamp",
                               lambda: self._stamp(1000.0)), \
                mock.patch.object(mod, "pid_start_time", lambda p: 500.0):
            r = mod.wrapper_code_age(4242)
        self.assertEqual(r["basis"], "started")
        self.assertTrue(r["stale"])
        with mock.patch.object(mod, "running_code_stamp",
                               lambda: self._stamp(1000.0)), \
                mock.patch.object(mod, "pid_start_time", lambda p: 2000.0):
            self.assertFalse(mod.wrapper_code_age(4242)["stale"])

    # R3-4. 근거가 없으면 **낡았다고 단정하지 않는다**
    def test_r3_4_without_evidence_it_says_nothing(self):
        with mock.patch.object(mod, "pid_start_time", lambda p: 0.0):
            self.assertEqual(mod.wrapper_code_age(4242), {})
        self.assertEqual(mod.wrapper_code_age(0), {})

    # 실제로 이 프로세스의 기동 시각을 읽을 수 있다 (플랫폼 갈래 실측)
    def test_the_start_time_of_a_real_process_is_readable(self):
        born = mod.pid_start_time(os.getpid())
        self.assertTrue(0 < born <= time.time() + 1, born)

    # R3-5. 화면이 쓸 수 있게 폴과 재시작 응답에 실린다 (계약)
    def test_r3_5_the_poll_and_the_restart_reply_carry_it(self):
        head = SRC.split('elif parsed.path == "/api/chat/target"', 1)[1][:4200]
        self.assertIn('"stale_wrapper"', head)
        self.assertIn('"wrapper_pid"', head)
        body = SRC.split("def restart_session(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn('out["stale_wrapper"]', body)

    # 죽은 래퍼가 남긴 지문은 치운다 (pid 재사용으로 남의 지문을 읽지 않게)
    def test_a_dead_wrappers_stamp_is_swept(self):
        mod.wrapper_stamp_write(999001)
        p = mod._wrapper_stamp_path(999001)
        self.assertTrue(os.path.exists(p))
        mod.wrapper_stamp_sweep(alive=lambda pid: False)
        self.assertFalse(os.path.exists(p))


# ---------------------------------------------------------------- R4·R5

HOME_PROFILE = os.path.join(TMP, "claude-home")
PROFILES = os.path.join(TMP, "claude-profiles")
CWD_KEY = "-tmp-work"
WRAPPER = 515151


def asst(stop="end_turn", model="claude-fable-5"):
    return {"type": "assistant",
            "message": {"stop_reason": stop, "model": model,
                        "content": [{"type": "text", "text": "x"}]}}


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


class SessionStage(unittest.TestCase):
    """무대: 프로필 두 자리와 래퍼 하나 (test_restart_contract 와 같은 모양)."""

    usage = {}

    def setUp(self):
        os.makedirs(HOME_PROFILE, exist_ok=True)
        os.makedirs(PROFILES, exist_ok=True)
        self.kills = []
        self.usage = {}
        self.stack = [
            mock.patch.object(mod, "_pid_is_claude", lambda p: True),
            mock.patch.object(mod, "current_machine", lambda: "testbox"),
            mock.patch.object(mod, "claude_home", lambda: HOME_PROFILE),
            mock.patch.object(mod, "account_home_dir", lambda: HOME_PROFILE),
            mock.patch.object(mod, "profiles_base", lambda: PROFILES),
            mock.patch.object(mod, "user_config", lambda n: {}),
            mock.patch.object(mod, "do_user_config_set", lambda *a, **k: None),
            mock.patch.object(mod, "claude_usage", self._usage),
        ]
        for p in self.stack:
            p.start()

    def tearDown(self):
        for p in reversed(self.stack):
            p.stop()

    def _usage(self, cfg_dir=None, ttl=60, offline=False):
        return self.usage.get(os.path.abspath(cfg_dir or ""), {})

    def limited(self, cfg_dir, percent=100, name="Fable 5"):
        self.usage[os.path.abspath(cfg_dir)] = {
            "ok": True, "email": "acct@ex.com",
            "limits": [{"kind": "weekly_scoped", "percent": percent,
                        "scope_name": name,
                        "resets_at": "2026-09-06T11:00:00+00:00"}]}

    def session(self, sid, entries, profile=HOME_PROFILE, pid=None):
        full = f"{sid}-full-session-id"
        d = os.path.join(profile, "projects", CWD_KEY)
        os.makedirs(d, exist_ok=True)
        tp = os.path.join(d, full + ".jsonl")
        with open(tp, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        make_binding(sid, attach_pid=str(pid or os.getpid()),
                     transcript_path=tp, cwd="/tmp/work")
        return full, tp

    def restart(self, sid, **kv):
        with mock.patch.object(mod, "pid_ppid", lambda p: WRAPPER), \
                mock.patch.object(mod, "pid_cmdline",
                                  lambda p: "python bin/s9 code"), \
                mock.patch("os.kill",
                           lambda pid, sig: self.kills.append((pid, sig))):
            return mod.restart_session(sid, **kv)


class TheWallOnTheOtherSide(SessionStage):
    """R4 — 한도로 굳을 자리로는 보내지 않는다."""

    # R4-1·R4-3. 「유지」로 옮겨 갈 계정이 그 모델로 막혀 있으면 미리 거부한다
    def test_r4_1_a_limited_target_is_refused_before_sigterm(self):
        self.session("t1sess", [asst("end_turn", "claude-fable-5")])
        self.limited(os.path.join(PROFILES, "acct2"))
        r = self.restart("t1sess", account="acct2")
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["why_kind"], "limit_target")
        self.assertEqual(r["limit"]["model"], "Fable 5")
        self.assertEqual(r["limit"]["percent"], 100)
        self.assertEqual(self.kills, [], "거부인데 세션을 내렸다")
        self.assertFalse(os.path.exists(mod._restart_marker_path("t1sess")))

    # R4-2. 막히지 않은 자리로는 그대로 간다
    def test_r4_2_an_open_target_proceeds(self):
        self.session("t2sess", [asst("end_turn", "claude-fable-5")])
        self.limited(os.path.join(PROFILES, "acct3"), percent=40)
        self.assertTrue(self.restart("t2sess", account="acct3")["ok"])
        self.assertEqual(len(self.kills), 1)

    # R4-3(b). 나갈 모델이 다르면 그 모델로 판정한다
    def test_r4_3_the_outgoing_model_is_what_is_judged(self):
        self.session("t3sess", [asst("end_turn", "claude-fable-5")])
        self.limited(os.path.join(PROFILES, "acct4"))
        self.assertTrue(
            self.restart("t3sess", account="acct4", model="opus")["ok"],
            "막힌 것은 fable 인데 opus 로 가는 길까지 막았다")

    # R4-4. 「그래도 가기」는 이 벽도 지난다
    def test_r4_4_force_passes_this_wall_too(self):
        self.session("t4sess", [asst("end_turn", "claude-fable-5")])
        self.limited(os.path.join(PROFILES, "acct5"))
        r = self.restart("t4sess", account="acct5", force=True)
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(self.kills), 1)

    # R4-5. 모르면 막지 않는다 — 근거 없는 차단은 이유를 못 댄다
    def test_r4_5_what_is_not_known_does_not_block(self):
        self.session("t5sess", [asst("end_turn", "claude-fable-5")])
        self.assertTrue(self.restart("t5sess", account="acct6")["ok"])

    # effort 만 바꾸는 길에는 사용량을 묻지 않는다
    def test_effort_only_does_not_ask_about_usage(self):
        self.session("t6sess", [asst("end_turn", "claude-fable-5")])
        self.limited(HOME_PROFILE)
        self.assertTrue(self.restart("t6sess", effort="high")["ok"])


class AliveIsNotListening(SessionStage):
    """R5 — 「떠 있다」와 「듣고 있다」는 다른 사실이다."""

    # R5-2. tail 이 없어도(첫 턴 실패) 프로세스가 살아 있으면 떠 있는 것이다
    def test_r5_2_a_session_that_never_got_to_listen_is_still_alive(self):
        self.session("a1sess", [asst("end_turn")])
        b = read_binding("a1sess")
        with mock.patch.object(mod, "_inbox_watch_alive", lambda s: False):
            self.assertTrue(mod.chat_alive(b),
                            "떠 있는 세션을 「안 떴다」로 읽었다 — 사고 ② 의 그 자리")
            self.assertTrue(mod.chat_live(b), "live 의 뜻이 바뀌었다")

    # R5-3. 끝난 세션은 어느 신호로도 되살아나지 않는다
    def test_r5_3_an_ended_session_is_never_alive(self):
        self.session("a2sess", [asst("end_turn")])
        b = read_binding("a2sess")
        b["ended"] = "2026-09-01T16:00:00+09:00"
        self.assertFalse(mod.chat_alive(b))
        self.assertFalse(mod.chat_live(b))

    # R5-4. listening 은 여전히 tail 하나로 판정한다 (뜻이 섞이지 않았다)
    def test_r5_4_listening_still_means_the_tail(self):
        self.session("a3sess", [asst("end_turn")])
        b = read_binding("a3sess")
        with mock.patch.object(mod, "pid_alive", lambda p: False), \
                mock.patch.object(mod, "_binding_activity_paths", lambda b: []), \
                mock.patch.object(mod, "_inbox_watch_alive", lambda s: True):
            self.assertFalse(mod.chat_alive(b))
            self.assertTrue(mod.chat_live(b))

    # R5-1. 폴이 둘을 **갈라서** 싣는다 (계약)
    def test_r5_1_the_poll_carries_both(self):
        head = SRC.split('elif parsed.path == "/api/chat/target"', 1)[1][:4200]
        self.assertIn('"alive": chat_alive(b)', head)
        self.assertIn('"listening": _inbox_watch_alive(', head)


# ---------------------------------------------------------------- R6

class HomeMeansOneThing(unittest.TestCase):
    """`@home` 은 서버가 물려받은 환경이 아니라 자리로 정해진다."""

    # R6-1. CLAUDE_CONFIG_DIR 이 프로필을 가리켜도 `@home` 은 ~/.claude 다
    def test_r6_1_home_does_not_follow_an_inherited_env(self):
        tmp = tempfile.mkdtemp(prefix="s9swhome-")
        self.addCleanup(shutil.rmtree, tmp, True)
        prof = os.path.join(tmp, "profiles", "acctX")
        os.makedirs(prof, exist_ok=True)
        env = {"HOME": tmp, "CLAUDE_CONFIG_DIR": prof}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(mod.claude_home(), prof)     # 이 프로세스의 설정
            self.assertEqual(mod.account_home_dir(),
                             os.path.join(tmp, ".claude"))
            self.assertEqual(mod._profile_dir(mod.ACCOUNT_HOME_KEY),
                             os.path.join(tmp, ".claude"),
                             "서버의 @home 이 상속 환경을 따라갔다 — 그러면 "
                             "서버는 프로필로 대화를 옮기고 래퍼는 홈으로 띄운다")

    # R6-2. 목록의 `@home` 줄도 같은 자리를 말한다
    def test_r6_2_the_home_row_says_the_same_place(self):
        tmp = tempfile.mkdtemp(prefix="s9swhome2-")
        self.addCleanup(shutil.rmtree, tmp, True)
        home = login(os.path.join(tmp, ".claude"), "home@ex.com")
        prof = os.path.join(tmp, "profiles", "acctY")
        os.makedirs(prof, exist_ok=True)
        with mock.patch.dict(os.environ,
                             {"HOME": tmp, "CLAUDE_CONFIG_DIR": prof}), \
                mock.patch.object(mod, "profiles_base",
                                  lambda: os.path.join(tmp, "profiles")):
            rows = mod.account_rows(settle=False)
        row = [r for r in rows if r["key"] == mod.ACCOUNT_HOME_KEY][0]
        self.assertEqual(row["path"], os.path.abspath(home))

    # R6-3. 감시자·서버는 계정 중립으로 띄운다 (계약)
    def test_r6_3_the_dashboard_is_launched_account_neutral(self):
        head = SRC.split('"serve", "--supervise"', 1)[1][:400]
        self.assertIn('k != "CLAUDE_CONFIG_DIR"', head,
                      "프로필 세션이 띄운 서버가 그 계정을 @home 으로 삼는다")


# ---------------------------------------------------------------- 곁가지

class TheMarkerTakesOnlyItsOwn(unittest.TestCase):
    """마커 수거가 남의 파일을 지우지 않는다."""

    # X1-1. 회차 기록은 마커 수거에 지워지지 않는다
    def test_x1_1_the_attempt_counter_survives_the_sweep(self):
        n = mod._restart_attempt("x1sess", "busy")
        self.assertEqual(n, 1)
        p = mod._terminal_state_path("rtry-x1sess.json")
        self.assertTrue(os.path.exists(p), "회차 기록의 이름이 갈리지 않았다")
        # 마커 수거가 훑는 자리에 낡은 회차 기록을 두고 돌려 본다
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        d["ts"] = time.time() - mod.RESTART_FRESH_SEC - 100
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f)
        legacy = mod._terminal_state_path("restart-try-x1sess.json")
        with open(legacy, "w", encoding="utf-8") as f:
            json.dump(d, f)
        mod._consume_restart_marker()
        self.assertTrue(os.path.exists(p))
        self.assertTrue(os.path.exists(legacy),
                        "재시작 마커가 아닌 파일을 지웠다 — 회차가 1 로 돌아간다")
        self.assertEqual(mod._restart_attempt("x1sess", "busy"), 2)
        mod._restart_attempt_clear("x1sess")
        self.assertFalse(os.path.exists(p))
        self.assertFalse(os.path.exists(legacy), "옛 이름의 자리가 남았다")

    # X1-2. 제 래퍼를 지목한 진짜 마커는 그대로 소비된다
    def test_x1_2_a_real_marker_is_still_consumed(self):
        mp = mod._restart_marker_path("x2sess")
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        with open(mp, "w", encoding="utf-8") as f:
            json.dump({"wrapper_pid": os.getpid(), "resume": "full",
                       "model": "opus", "ts": time.time()}, f)
        m = mod._consume_restart_marker()
        self.assertEqual((m or {}).get("model"), "opus")
        self.assertFalse(os.path.exists(mp))


class TheLineageIsAJournal(unittest.TestCase):
    """재시작 이력은 덮이지 않는다 — 다음 조사가 읽을 자료다."""

    WRAP = 616161

    def setUp(self):
        try:
            os.remove(mod._lineage_path(self.WRAP))
        except OSError:
            pass

    # X2-1. 두 번 재시작하면 두 줄이다 (덮어쓰기가 아니다)
    def test_x2_1_two_restarts_leave_two_lines(self):
        mod._lineage_write(self.WRAP, "old1", from_pid=11)
        mod._lineage_write(self.WRAP, "old2", from_pid=22)
        recs = mod._lineage_read(mod._lineage_path(self.WRAP))
        self.assertEqual([r["from"] for r in recs], ["old1", "old2"],
                         "두 번째 재시작이 첫 번째의 흔적을 지웠다")

    # X2-2. 같은 sid 로 돌아온 재시작도 기록이 닫힌다 (900초를 떠다니지 않는다)
    def test_x2_2_a_same_sid_return_closes_the_record(self):
        make_binding("samesid", attach_pid="8801", transcript_path="")
        mod._lineage_write(self.WRAP, "samesid", from_pid=8800)
        with mock.patch.object(mod, "current_machine", lambda: "testbox"), \
                mock.patch.object(mod, "pid_alive", lambda p: True), \
                mock.patch.object(mod, "pid_ppid",
                                  lambda p: self.WRAP if p == 8801 else 1):
            self.assertEqual(mod.lineage_link(), [])
            rec = mod._lineage_read(mod._lineage_path(self.WRAP))[-1]
            self.assertEqual(rec["done"], "same-sid")
            self.assertEqual(mod.lineage_link(), [], "닫힌 기록이 다시 후보가 됐다")

    # T5 (REQ-20260902-013). 이을 때 기록의 model·ts 가 새 바인딩에
    # launch_model·launch_ts 로 남는다 — 첫 응답 전의 모델 표기가 이것을 본다
    def test_t5_link_stamps_launch_model(self):
        make_binding("lmnew", attach_pid="7801", transcript_path="")
        mod._lineage_write(self.WRAP, "lmold", from_pid=7000,
                           model="claude-fable-5-1")
        with mock.patch.object(mod, "current_machine", lambda: "testbox"), \
                mock.patch.object(mod, "pid_alive", lambda p: True), \
                mock.patch.object(mod, "pid_ppid",
                                  lambda p: self.WRAP if p == 7801 else 1):
            self.assertEqual(mod.lineage_link(), [("lmold", "lmnew")])
        rec = mod._lineage_read(mod._lineage_path(self.WRAP))[-1]
        b = read_binding("lmnew")
        self.assertEqual(b.get("launch_model"), "claude-fable-5-1")
        self.assertEqual(b.get("launch_ts"), rec["ts"])

    # T6 (REQ-20260902-013). 같은 sid 로 돌아와도 띄운 모델은 남는다
    def test_t6_same_sid_return_stamps_launch_model(self):
        make_binding("lmsame", attach_pid="8901", transcript_path="")
        mod._lineage_write(self.WRAP, "lmsame", from_pid=8900,
                           model="claude-fable-5-1")
        with mock.patch.object(mod, "current_machine", lambda: "testbox"), \
                mock.patch.object(mod, "pid_alive", lambda p: True), \
                mock.patch.object(mod, "pid_ppid",
                                  lambda p: self.WRAP if p == 8901 else 1):
            self.assertEqual(mod.lineage_link(), [])
        rec = mod._lineage_read(mod._lineage_path(self.WRAP))[-1]
        self.assertEqual(rec["done"], "same-sid")
        b = read_binding("lmsame")
        self.assertEqual(b.get("launch_model"), "claude-fable-5-1")
        self.assertEqual(b.get("launch_ts"), rec["ts"])
        # 「유지」(빈 model)는 아는 척하지 않는다
        make_binding("lmkeep", attach_pid="8911", transcript_path="")
        mod._lineage_write(self.WRAP, "lmkeep", from_pid=8910, model="")
        with mock.patch.object(mod, "current_machine", lambda: "testbox"), \
                mock.patch.object(mod, "pid_alive", lambda p: True), \
                mock.patch.object(mod, "pid_ppid",
                                  lambda p: self.WRAP if p == 8911 else 1):
            mod.lineage_link()
        self.assertNotIn("launch_model", read_binding("lmkeep"))

    # 아직 안 뜬 재시작은 닫지 않는다 — 같은 pid 면 그 세션은 옛 세션이다
    def test_a_restart_that_has_not_landed_stays_open(self):
        make_binding("notyet", attach_pid="9900", transcript_path="")
        mod._lineage_write(self.WRAP, "notyet", from_pid=9900)
        with mock.patch.object(mod, "current_machine", lambda: "testbox"), \
                mock.patch.object(mod, "pid_alive", lambda p: True), \
                mock.patch.object(mod, "pid_ppid",
                                  lambda p: self.WRAP if p == 9900 else 1):
            mod.lineage_link()
        rec = mod._lineage_read(mod._lineage_path(self.WRAP))[-1]
        self.assertNotIn("done", rec)

    # 살아 있는 계보는 최신 하나다 — 앞선 미결 기록은 대체된 것이다
    def test_only_the_newest_record_is_a_candidate(self):
        make_binding("newsid", attach_pid="7701", transcript_path="")
        mod._lineage_write(self.WRAP, "oldA", from_pid=7000)
        mod._lineage_write(self.WRAP, "oldB", from_pid=7001)
        with mock.patch.object(mod, "current_machine", lambda: "testbox"), \
                mock.patch.object(mod, "pid_alive", lambda p: True), \
                mock.patch.object(mod, "pid_ppid",
                                  lambda p: self.WRAP if p == 7701 else 1):
            self.assertEqual(mod.lineage_link(), [("oldB", "newsid")])
        recs = mod._lineage_read(mod._lineage_path(self.WRAP))
        self.assertEqual([r["done"] for r in recs], ["superseded", "linked"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
