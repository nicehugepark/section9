"""세션 모델 제어 테스트 (REQ-20260825-037).

CC는 실행 중 model/effort 외부 변경을 지원하지 않는다 — 같은 대화를
`claude --resume --model --effort`로 재개하는 재기동 경로를 검증한다:
session_model(트랜스크립트 모델 추출), 재시작 마커 소비, restart_session 가드.

격리: S9_ROOT=mktemp (모듈 import 시점 캡처, env 즉시 복원).
실행: python3 tests/ session_restart
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import time
import unittest
from unittest import mock
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)

TMP = tempfile.mkdtemp(prefix="s9restart-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_rst", importlib.machinery.SourceFileLoader("s9_mod_rst", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

# ROOT·STATE 는 import 시점에 굳고 machine 은 부를 때마다 환경에서 읽는다 —
# env 를 되돌리는 이 격리에서 그 둘이 어긋난다. 바인딩을 훑는 자리가 이 머신
# 것만 보게 된 뒤로(REQ-20260902-017 `_local_binding_glob`) 그 어긋남이
# 곧바로 "세션 없음/종료됨" 이 됐다. env 를 열어 두면 같은 프로세스의 다른
# 시험까지 물들므로, 이 모듈 안에서만 머신을 못박는다.
mod.current_machine = lambda: "testbox"


def write_jsonl(entries, name):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return path


def asst(stop, model="claude-fable-5"):
    return {"type": "assistant",
            "message": {"stop_reason": stop, "model": model,
                        "content": [{"type": "text", "text": "x"}]}}


def make_binding(sid, **kv):
    os.makedirs(mod.STATE, exist_ok=True)
    b = {"machine": "testbox", "session": sid, "user": "", "history": [], **kv}
    with open(os.path.join(mod.STATE, f"testbox__{sid}.json"), "w",
              encoding="utf-8") as f:
        json.dump(b, f)


class TestSessionModel(unittest.TestCase):
    # R1. 트랜스크립트 마지막 assistant의 model을 읽는다 (캐시는 mtime 기준)
    def test_r1_last_model(self):
        tp = write_jsonl([asst("tool_use", "claude-old-1"),
                          asst("end_turn", "claude-fable-5")],
                         "m1-full.jsonl")
        self.assertEqual(mod.session_model({"transcript_path": tp}),
                         "claude-fable-5")
        self.assertEqual(mod.session_model({"transcript_path": "/no/file"}), "")

    # --- 재시작 직후에는 띄운 모델이 이긴다 (REQ-20260902-013) ---------------
    # 실사고 2026-09-02 13:00: opus→fable 재시작 8초 뒤 「opus-5으로 이어집니다」.
    # 새 프로세스의 첫 응답(27초 뒤)까지 트랜스크립트는 옛 모델만 안다.

    @staticmethod
    def _stamped(stop, model, ts):
        e = asst(stop, model)
        e["timestamp"] = ts
        return e

    # T1. 마지막 모델 이벤트가 launch_ts 이전 → launch_model
    def test_t1_launch_model_wins_before_first_reply(self):
        tp = write_jsonl([self._stamped("end_turn", "claude-opus-5",
                                        "2026-09-02T04:00:23.008Z")],
                         "lm1-full.jsonl")
        b = {"transcript_path": tp, "launch_model": "claude-fable-5-1",
             "launch_ts": mod._epoch_of("2026-09-02T04:00:40.000Z")}
        self.assertEqual(mod.session_model(b), "claude-fable-5-1")

    # T2. launch_ts 이후의 새 응답이 붙으면 실제로 말한 모델이 이긴다
    def test_t2_spoken_model_wins_after_first_reply(self):
        tp = write_jsonl([self._stamped("end_turn", "claude-opus-5",
                                        "2026-09-02T04:00:23.008Z"),
                          self._stamped("end_turn", "claude-sonnet-5",
                                        "2026-09-02T04:00:50.233Z")],
                         "lm2-full.jsonl")
        b = {"transcript_path": tp, "launch_model": "claude-fable-5-1",
             "launch_ts": mod._epoch_of("2026-09-02T04:00:40.000Z")}
        # --model 이 안 먹은 경우까지 덮지 않는다 — 말한 모델이 최종이다
        self.assertEqual(mod.session_model(b), "claude-sonnet-5")

    # T3. launch_model 이 없으면 종전대로 트랜스크립트 마지막 모델
    def test_t3_no_launch_model_falls_back_to_transcript(self):
        tp = write_jsonl([self._stamped("end_turn", "claude-opus-5",
                                        "2026-09-02T04:00:23.008Z")],
                         "lm3-full.jsonl")
        self.assertEqual(mod.session_model({"transcript_path": tp}),
                         "claude-opus-5")

    # T4. timestamp 없는 옛 형식 → model_ts=0 → launch_model 이 이긴다
    def test_t4_unstamped_event_yields_to_launch_model(self):
        tp = write_jsonl([asst("end_turn", "claude-opus-5")], "lm4-full.jsonl")
        self.assertEqual(mod.transcript_read(tp).get("model_ts"), 0.0)
        b = {"transcript_path": tp, "launch_model": "claude-fable-5-1",
             "launch_ts": 1.0}
        self.assertEqual(mod.session_model(b), "claude-fable-5-1")


class TestRestartMarker(unittest.TestCase):
    # R2. 내 pid를 지목한 신선한 마커만 소비(반환+삭제), 낡은 것은 정리
    def test_r2_marker_consumption(self):
        os.makedirs(os.path.join(TMP, "state", "terminal"), exist_ok=True)
        mine = mod._restart_marker_path("rstsess")
        with open(mine, "w", encoding="utf-8") as f:
            json.dump({"wrapper_pid": os.getpid(), "resume": "full-id",
                       "model": "opus", "effort": "high",
                       "ts": time.time()}, f)
        other = mod._restart_marker_path("othersess")
        with open(other, "w", encoding="utf-8") as f:
            json.dump({"wrapper_pid": 1, "resume": "x",
                       "ts": time.time()}, f)
        stale = mod._restart_marker_path("stalesess")
        with open(stale, "w", encoding="utf-8") as f:
            json.dump({"wrapper_pid": os.getpid(), "resume": "y",
                       "ts": time.time() - mod.RESTART_FRESH_SEC - 10}, f)
        m = mod._consume_restart_marker()
        self.assertIsNotNone(m)
        self.assertEqual(m["resume"], "full-id")
        self.assertFalse(os.path.exists(mine))     # 소비 = 삭제
        self.assertTrue(os.path.exists(other))     # 남의 마커는 보존
        self.assertFalse(os.path.exists(stale))    # 낡은 마커는 정리
        os.remove(other)


class TestRestartGuards(unittest.TestCase):
    def _idle_binding(self, sid):
        tp = write_jsonl([asst("end_turn")], f"{sid}-full-session-id.jsonl")
        make_binding(sid, attach_pid=str(os.getpid()), transcript_path=tp)
        return tp

    # R3. busy 세션 거부 — 진행 중 작업 보호
    def test_r3_busy_refused(self):
        tp = write_jsonl([asst("tool_use")], "busy-full.jsonl")
        make_binding("busysess", attach_pid=str(os.getpid()),
                     transcript_path=tp)
        with mock.patch.object(mod, "_pid_is_claude", lambda p: True):
            r = mod.restart_session("busysess", model="opus")
        self.assertFalse(r["ok"])
        self.assertIn("진행 중", r["reason"])

    # R4. 래퍼 부재(부모가 s9 code 아님) → mode=manual + 정확한 재개 명령
    def test_r4_manual_mode_cmd(self):
        self._idle_binding("mansess")
        with mock.patch.object(mod, "_pid_is_claude", lambda p: True):
            r = mod.restart_session("mansess", model="opus", effort="high")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["mode"], "manual")
        # s9 code 래퍼 경유 — 1회 수동 후엔 재시작 루프가 생겨 자동화된다
        self.assertIn("s9 code --resume mansess-full-session-id", r["cmd"])
        self.assertIn("--model opus", r["cmd"])
        self.assertIn("--effort high", r["cmd"])

    # R5. effort 무효값·변경 항목 없음 거부
    def test_r5_invalid_inputs(self):
        self._idle_binding("valsess")
        with mock.patch.object(mod, "_pid_is_claude", lambda p: True):
            r = mod.restart_session("valsess", effort="ultra")
            self.assertFalse(r["ok"])
            self.assertIn("effort", r["reason"])
            r = mod.restart_session("valsess")
            self.assertFalse(r["ok"])
            self.assertIn("변경할 항목", r["reason"])

    # R6. 죽은 pid 거부
    def test_r6_dead_pid(self):
        make_binding("deadrst", attach_pid="999999999",
                     transcript_path=os.path.join(TMP, "none.jsonl"))
        r = mod.restart_session("deadrst", model="opus")
        self.assertFalse(r["ok"])


class TestWorkerModel(unittest.TestCase):
    """무인 워커 모델 고정 (REQ-20260825-080, Fable 한도 소진 실사고).

    워커를 모델 지정 없이 띄우면 계정 기본 모델을 쓴다 — 그 모델 한도가 소진되면
    스폰된 워커가 전부 즉시 죽고, 대시보드 대상 세션까지 죽은 워커로 잡혀
    모델 변경조차 불가능해진다. auto_resume_model 설정이 그 경로를 막는다."""

    # R13. 설정이 있으면 --model 인자가 붙고, 없으면 붙지 않는다
    def test_r13_model_args(self):
        with mock.patch.object(mod, "user_config",
                               lambda n: {"auto_resume_model": "opus"}):
            self.assertEqual(mod._spawn_model_args("sjpark1"),
                             ["--model", "opus"])
        with mock.patch.object(mod, "user_config", lambda n: {}):
            self.assertEqual(mod._spawn_model_args("sjpark1"), [])
        # 설정 읽기 실패가 스폰을 막아선 안 된다
        with mock.patch.object(mod, "user_config",
                               mock.Mock(side_effect=OSError)):
            self.assertEqual(mod._spawn_model_args("sjpark1"), [])

    # R14. 모든 워커 스폰 경로가 이 인자를 통과한다 (한 군데라도 빠지면 재발)
    def test_r14_all_spawn_sites_covered(self):
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        # 스폰 argv 조립 지점 — Popen 호출 형태가 아니라 argv 형태로 센다
        # (스폰 경로가 _spawn_worker 하나로 합쳐져도 계속 잡힌다)
        bare = src.count('["claude", "-p", prompt')
        covered = src.count("*_spawn_model_args(owner)")
        # 0 == 0 으로 조용히 통과하면 감시가 눈을 잃는다 — 하한을 못 박는다
        self.assertGreaterEqual(bare, 1, "워커 스폰 argv 조립 지점을 못 찾았다 "
                                         "— 패턴이 바뀌었으면 이 감시를 고쳐라")
        self.assertEqual(bare, covered, "모델 인자 없는 워커 스폰 경로가 남았다")

    # R15. <synthetic> 등 합성 모델 표기는 상태줄에 흘리지 않는다
    def test_r15_synthetic_model_ignored(self):
        tp = write_jsonl([asst("end_turn", "claude-opus-5"),
                          asst("end_turn", "<synthetic>")], "syn-full.jsonl")
        self.assertEqual(mod.session_model({"transcript_path": tp}),
                         "claude-opus-5")


class TestModelPersistence(unittest.TestCase):
    """모델 선택 지속 (REQ-20260825-080 → REQ-20260901-012 로 개정).

    대시보드 모델 변경은 재시작 마커의 --model 뿐이라 그 재개 1회에만 붙었다.
    세션이 새로 뜨거나(s9 code) 무인 워커가 스폰되면 계정 기본값으로 돌아가
    사용자가 고른 모델이 '제멋대로 되돌아가는' 것처럼 보였다 — 그래서 그
    선택을 사용자 설정 두 칸에 **승격**시켰다.

    그 승격이 반대편 사고를 만들었다: 확인차 한 번 눌러 본 fable 이 그대로
    선언된 정책이 되어(8/30 13:36 실기록) 계정 전환으로 뜬 새 창과 무인
    워커까지 fable 로 세웠고, 그 한도 소진이 2026-09-01 전환 교착의 무대가
    됐다. 이제 칸이 갈린다 — 정책은 사람만 쓰고, 1회 선택은 제 칸에 산다."""

    def _idle_binding(self, sid, user="tester"):
        tp = write_jsonl([asst("end_turn")], f"{sid}-full-session-id.jsonl")
        make_binding(sid, attach_pid=str(os.getpid()), transcript_path=tp,
                     user=user)
        return tp

    # M2. --model 만 교체하고 나머지 인자는 보존 — 중복 누적 금지
    def test_m2_args_set_model(self):
        f = mod._args_set_model
        self.assertEqual(f("--permission-mode auto", "opus"),
                         "--permission-mode auto --model opus")
        self.assertEqual(f("--permission-mode auto --model fable", "opus"),
                         "--permission-mode auto --model opus")
        self.assertEqual(f("--model=fable --verbose", "opus"),
                         "--verbose --model opus")
        self.assertEqual(f("", "opus"), "--model opus")
        # 값이 빠진 꼬리 --model 도 삼킨다 (인자 밀림 방지)
        self.assertEqual(f("--verbose --model", "opus"), "--verbose --model opus")
        self.assertEqual(f("--model opus", ""), "")

    # M5. 재시작 루프가 --model 을 두 번 넘기지 않는다 — 마커가 이긴다
    def test_m5_restart_cmd_no_duplicate_model(self):
        base = ["claude", "--permission-mode", "auto", "--model", "fable"]
        cmd = mod._restart_cmd(base, {"resume": "S1", "model": "opus",
                                      "effort": "high"})
        self.assertEqual(cmd.count("--model"), 1, cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "opus", cmd)
        self.assertIn("--permission-mode", cmd)
        self.assertEqual(cmd[cmd.index("--resume") + 1], "S1")
        self.assertIn("--effort", cmd)
        # 마커에 모델이 없으면 base 의 모델을 그대로 둔다 (기존 동작 보존)
        cmd2 = mod._restart_cmd(base, {"resume": "S1", "effort": "high"})
        self.assertEqual(cmd2[:5], base)

    # T1+T2+T3 (구 M1+M6 개정, REQ-20260901-012). 종전 계약은 "대시보드 변경이
    #     두 저장처(auto_resume_model·s9code_args)를 같은 값으로 맞춘다" 였다.
    #     그 계약이 곧 결함이었다 — 정책 칸을 대시보드가 쓰면 사용자의 선언이
    #     클릭 한 번에 지워진다. 새 계약: **정책 두 칸은 그대로, 최근 선택
    #     칸만 바뀐다.**
    def test_m1_choice_records_without_touching_policy(self):
        cfg = {"s9code_args": "--permission-mode auto --model fable",
               "auto_resume_model": "claude-opus-5[1m]"}
        writes = {}

        def fake_set(name, key, value, actor=""):
            writes[key] = value
            cfg[key] = value
        with mock.patch.object(mod, "user_config", lambda n: dict(cfg)), \
                mock.patch.object(mod, "do_user_config_set", fake_set):
            done = mod._record_model_choice("tester", "fable")
        self.assertEqual(writes.get("last_model_choice"), "fable")
        self.assertEqual(done, ["last_model_choice"])
        # 정책은 사람만 쓴다 — 대시보드가 지나간 자리에 자국이 없어야 한다
        self.assertNotIn("auto_resume_model", writes,
                         "대시보드 선택이 정책 칸을 다시 덮는다 (8/30 재발)")
        self.assertNotIn("s9code_args", writes,
                         "대시보드 선택이 기동 인자를 다시 덮는다")
        self.assertEqual(cfg["auto_resume_model"], "claude-opus-5[1m]")

    # M3. 모델 없이 effort/account 만 바꾸면 config 를 건드리지 않는다
    def test_m3_no_model_no_write(self):
        called = []
        with mock.patch.object(mod, "do_user_config_set",
                               lambda *a, **k: called.append(a)):
            self.assertEqual(mod._record_model_choice("tester", ""), [])
            self.assertEqual(mod._record_model_choice("", "opus"), [])
        self.assertEqual(called, [])

    # M4. config 쓰기 실패가 재시작을 깨뜨리지 않는다 (best-effort)
    def test_m4_write_failure_isolated(self):
        self._idle_binding("persistfail")
        with mock.patch.object(mod, "_pid_is_claude", lambda p: True), \
                mock.patch.object(mod, "do_user_config_set",
                                  mock.Mock(side_effect=OSError("read-only"))):
            r = mod.restart_session("persistfail", model="opus")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r.get("saved"), [])

    # M1(경로). restart_session 성공이 실제로 기록을 호출한다 — 최근 선택 칸에
    def test_m1b_restart_records_choice(self):
        self._idle_binding("persistok")
        writes = {}
        with mock.patch.object(mod, "_pid_is_claude", lambda p: True), \
                mock.patch.object(mod, "user_config", lambda n: {}), \
                mock.patch.object(
                    mod, "do_user_config_set",
                    lambda n, k, v, actor="": writes.__setitem__(k, v)):
            r = mod.restart_session("persistok", model="claude-opus-5[1m]")
        self.assertTrue(r["ok"], r)
        self.assertEqual(writes, {"last_model_choice": "claude-opus-5[1m]"})


class TheWrapperIsRecognisedByPlace(unittest.TestCase):
    """래퍼 판정은 **자리**로 한다 — 글자가 아무 데나 있는 것은 아니다
    (REQ-20260904-003).

    실사고 2026-09-04: 판정이 `"s9" in wcmd and "code" in wcmd` 였다. 병렬
    시험의 부모 명령줄에는 시험 파일 이름 200개가 실려 있고 그중
    `test_s9_code_args.py` 한 낱말에 두 글자가 다 있다 — 그래서 래퍼가 있다고
    믿고 SIGTERM 을 보냈고, 되살릴 래퍼가 없어 **샤드가 자기 자신을 죽였다.**

    사람의 세션도 같은 길로 간다: 부모 명령줄에 그 두 글자가 우연히 섞이면
    세션이 SIGTERM 을 맞고 그냥 죽는데 화면에는 「재시작했다」로 보인다.
    """

    def test_w1_a_real_wrapper_is_recognised(self):
        self.assertTrue(mod._is_code_wrapper(
            "python3 /home/u/section9/bin/s9 code --resume abc"))

    def test_w3_a_test_filename_is_not_a_wrapper(self):
        """이 사고를 낸 바로 그 문자열."""
        self.assertFalse(mod._is_code_wrapper(
            "python3 tests/ --smoke --jobs 4 test_s9_code_args.py test_s9_sync.py"))

    def test_w4_someone_elses_command_is_not_a_wrapper(self):
        self.assertFalse(mod._is_code_wrapper("/home/x/section9/other code-thing"))

    def test_w5_another_subcommand_is_not_a_wrapper(self):
        self.assertFalse(mod._is_code_wrapper(
            "python3 /home/u/section9/bin/s9 serve --port 9909"))

    def test_b1_the_windows_form_is_recognised(self):
        """역슬래시 경로 — 리눅스에서 읽어도 갈래로 센다 (REQ-20260903-005 형제)."""
        self.assertTrue(mod._is_code_wrapper(
            "cmd.exe /c C:\\repo\\bin\\s9.cmd code"))

    def test_b2_flags_between_are_skipped(self):
        self.assertTrue(mod._is_code_wrapper("python3 /home/u/bin/s9 --quiet code"))

    def test_nothing_is_not_a_wrapper(self):
        self.assertFalse(mod._is_code_wrapper(""))


class TestModelPolicyWins(unittest.TestCase):
    """선언과 최근 선택을 가른다 (REQ-20260901-012 P2+P4).

    "기본 모델로 fable 은 절대 안 된다" 는 사람의 선언이 시스템 어디에도
    **정책으로** 남아 있지 않았다 — 이력 줄과 사람의 기억뿐이었다. 칸을
    가르고 우선순위를 한 곳에 두면 그 문장을 기계가 지킨다."""

    def _cfg(self, **kv):
        return mock.patch.object(mod, "user_config", lambda n: dict(kv))

    # T4. 정책이 있으면 정책이 이긴다 — 최근 선택이 fable 이어도
    def test_t4_policy_beats_last_choice(self):
        with self._cfg(auto_resume_model="claude-opus-5[1m]",
                       last_model_choice="fable"):
            self.assertEqual(mod.resolved_model("tester"),
                             ("claude-opus-5[1m]", "policy"))
            self.assertEqual(mod._spawn_model_args("tester"),
                             ["--model", "claude-opus-5[1m]"])

    # T5. 정책이 없으면 최근 선택이 쓰인다 (080 이 고친 '되돌아감' 보존)
    def test_t5_last_choice_when_no_policy(self):
        with self._cfg(last_model_choice="claude-opus-5[1m]"):
            self.assertEqual(mod.resolved_model("tester"),
                             ("claude-opus-5[1m]", "last"))
        with self._cfg():
            self.assertEqual(mod.resolved_model("tester"), ("", ""))
            self.assertEqual(mod._spawn_model_args("tester"), [])

    # T6. 선언된 기동 인자도 선언이다
    def test_t6_declared_args_are_policy(self):
        with self._cfg(s9code_args="--permission-mode auto --model opus",
                       last_model_choice="fable"):
            self.assertEqual(mod.resolved_model("tester"), ("opus", "policy"))

    # T7. 8/25 취지 부활: 대시보드 클릭 하나가 워커 모델을 fable 로 못 바꾼다
    def test_t7_worker_model_not_hijacked_by_a_click(self):
        with self._cfg(auto_resume_model="claude-opus-5[1m]",
                       s9code_args="--permission-mode auto",
                       last_model_choice="fable"):
            self.assertNotIn("fable", mod._spawn_model_args("tester"))

    # T8. 명시 선언은 여전히 통한다 — 잠그는 것이 아니라 출처를 가르는 것
    def test_t8_explicit_declaration_still_rules(self):
        with self._cfg(auto_resume_model="fable"):
            self.assertEqual(mod._spawn_model_args("tester"),
                             ["--model", "fable"])

    # T12. 기동 경로 실측: s9 code 의 계정 기본 인자가 정책 모델로 선다
    def test_t12_code_launch_args_use_policy(self):
        with self._cfg(s9code_args="--permission-mode auto --model fable",
                       auto_resume_model="claude-opus-5[1m]"):
            self.assertEqual(
                mod.code_launch_args("tester"),
                ["--permission-mode", "auto", "--model", "claude-opus-5[1m]"])
        # 정책도 최근 선택도 없으면 선언된 인자를 그대로 쓴다
        with self._cfg(s9code_args="--permission-mode auto"):
            self.assertEqual(mod.code_launch_args("tester"),
                             ["--permission-mode", "auto"])
        with self._cfg():
            self.assertEqual(mod.code_launch_args("tester"), [])

    # 읽는 자리가 하나인지 감시 — 두 벌이 되면 한 벌만 고쳐진다
    def test_the_read_sites_go_through_one_judgement(self):
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertEqual(src.count('get("auto_resume_model"'), 1,
                         "정책 칸을 판정 밖에서 또 읽는다")
        self.assertEqual(src.count('get("last_model_choice"'), 2,
                         "최근 선택 칸을 판정·기록 밖에서 또 만진다")


class TestRestartUiContract(unittest.TestCase):
    """대시보드 마크업 계약 (반려 재작업): 모델 라벨은 미상이어도 항상 보이고,
    구버전 serve(404)는 정확한 사유로 안내하며, 진단 플래그로 자가 검증 가능."""
    @classmethod
    def setUpClass(cls):
        with open(index_path(),
                  encoding="utf-8") as f:
            cls.html = f.read()

    # R7. 모델 미상 폴백 라벨 — 라벨 실종이 "실행부터 실패"로 보이던 결함
    def test_r7_model_label_always_visible(self):
        self.assertIn("ccmodelbtn", self.html)
        self.assertIn("model?", self.html)

    # R8. 구버전 serve의 404를 "서버 연결 실패"로 오진하지 않는다
    def test_r8_stale_serve_404_reason(self):
        self.assertIn("재시작 API 없음", self.html)

    # R9. ?nosse 진단 플래그 — 터미널 탭 헤드리스 캡처(자가 검증) 경로 유지
    def test_r9_nosse_diag_flag(self):
        self.assertIn("nosse", self.html)

    # R11 (REQ-20260825-045): ultracode는 숨은 기능이 아니어야 한다 —
    #      패널에 설명 + 키워드 삽입 버튼이 있고, effort와 구분해 안내한다.
    def test_r11_ultracode_documented(self):
        self.assertIn("mpuc", self.html)
        self.assertIn("ultracode", self.html)
        self.assertIn("다중 에이전트", self.html)

    # R12 (REQ-20260825-047): 재시작 진행 표시 — 스피너+경과초가 살아 있고
    #      복귀 시 완료 줄로 교체된다("멈춘 듯" 보이던 정적 안내 대체)
    def test_r12_restart_progress_indicator(self):
        self.assertIn("termRestartDone", self.html)
        self.assertIn("cc-restart", self.html)
        self.assertIn("재시작 완료", self.html)

    # R10 (실사고): 모델 선택지에 fable 누락 → opus로 바꾼 뒤 되돌아갈 수 없었다.
    #      claude --help의 별칭(fable/opus/sonnet)이 모두 선택 가능해야 한다.
    #      REQ-20260827-079 로 인라인 패널이 판정 대화상자의 "고르는 변형"으로
    #      바뀌면서 선택지의 출처가 MODELS 배열이 됐다 — 계약은 그대로다.
    def test_r10_model_choices_include_fable(self):
        import re as _re
        m = _re.search(r"const MODELS = \[([\s\S]*?)\];", self.html)
        self.assertIsNotNone(m, "모델 선택지 정의를 찾을 수 없다")
        choices = _re.findall(r'\["([a-z]+)"', m.group(1))
        for alias in ("fable", "opus", "sonnet"):
            self.assertIn(alias, choices)


if __name__ == "__main__":
    unittest.main(verbosity=2)
