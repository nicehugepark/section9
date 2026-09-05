"""중지는 세션을 쏘지 않는다 (REQ-20260830-047).

사용자 실측: "요청을 중지 시키니까 대시보드 터미널 세션도 끊기고, 실제 연결된
로컬 터미널의 세션도 종료시켜버리는구나. 이게 무슨 중지야? 끄기지."

원인: REQ-20260825-008 의 interrupt_session 이 "가드 통과 시 SIGINT 1회 =
진행 중 턴 즉시 중단"을 전제로 세션 claude 프로세스에 신호를 쐈는데, 가드
(busy·claude 판정·신선도)를 전부 통과한 상태에서도 SIGINT 는 턴 취소가 아니라
**세션 프로세스 종료**였다 (2026-08-30 22:00 sid 619e6b59 — 'Request
interrupted' 마커 없이 트랜스크립트 침묵). CC 는 Ctrl+C 를 raw 키 입력으로
다루므로 시그널 SIGINT 는 이중 확인 경로를 지나지 않는다 — 안전한 발사 창을
코드가 식별할 수 없어 **원시 자체를 제거**했다. 세션 중단은 수신함
kind=interrupt 한 길, 프로세스 kill 은 전용 headless 워커(worker_stop)뿐이다.

_transcript_busy 는 restart_session(유휴 확인 후 재기동)이 계속 쓰므로
그 판정 시험(B1~B5)은 남긴다.

실행: python3 tests/ interrupt
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import signal
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
SRC = open(S9_SRC, encoding="utf-8").read()

TMP = tempfile.mkdtemp(prefix="s9int-")
# 모듈 import 시점에만 ROOT/MACHINE 고정 — 같은 프로세스의 다른 테스트 모듈에
# 전역 env가 새지 않게 즉시 복원한다 (mod.ROOT/STATE는 import 시 캡처됨)
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_int", importlib.machinery.SourceFileLoader("s9_mod_int", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

# ROOT·STATE 는 import 시점에 굳고 machine 은 부를 때마다 환경에서 읽는다 —
# env 를 되돌리는 이 격리에서 그 둘이 어긋난다. 바인딩을 훑는 자리가 이
# 머신 것만 보게 된 뒤로(REQ-20260902-017 `_local_binding_glob`) 그
# 어긋남이 "아무 바인딩도 없다"가 됐다. env 를 열어 두면 같은 프로세스의
# 다른 시험까지 물들므로 이 모듈 안에서만 머신을 못박는다.
mod.current_machine = lambda: "testbox"

DOC = "REQ-20260830-991-62x6"


def write_transcript(entries):
    fd, path = tempfile.mkstemp(suffix=".jsonl", dir=TMP)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return path


def asst(stop, content):
    return {"type": "assistant", "message": {"stop_reason": stop,
                                             "content": content}}


class TestTranscriptBusy(unittest.TestCase):
    """B1~B5 — restart_session 의 유휴 판정 재료."""

    # B1. end_turn으로 끝난 트랜스크립트 = idle
    def test_b1_end_turn_idle(self):
        p = write_transcript([{"type": "user", "message": {"content": "해줘"}},
                              asst("end_turn", [{"type": "text", "text": "done"}])])
        self.assertFalse(mod._transcript_busy(p))

    # B2. tool_use로 끝남 = busy (도구 실행 대기/진행)
    def test_b2_tool_use_busy(self):
        p = write_transcript([asst("tool_use", [{"type": "tool_use"}])])
        self.assertTrue(mod._transcript_busy(p))

    # B3. tool_result(user 턴)로 끝남 = busy (다음 어시스턴트 응답 예정)
    def test_b3_tool_result_busy(self):
        p = write_transcript([asst("tool_use", [{"type": "tool_use"}]),
                              {"type": "user",
                               "message": {"content": [{"type": "tool_result"}]}}])
        self.assertTrue(mod._transcript_busy(p))

    # B4. 직전 중단 마커([Request interrupted…]) = idle
    def test_b4_interrupted_marker_idle(self):
        p = write_transcript([{"type": "user", "message":
                               {"content": "[Request interrupted by user]"}}])
        self.assertFalse(mod._transcript_busy(p))
        p2 = write_transcript([{"type": "user", "message": {"content": [
            {"type": "text", "text": "[Request interrupted by user]"}]}}])
        self.assertFalse(mod._transcript_busy(p2))

    # B5. 판정 불가(파일 부재·메시지 이벤트 없음·메타뿐) = idle 취급
    def test_b5_unknown_is_idle(self):
        self.assertFalse(mod._transcript_busy(os.path.join(TMP, "no.jsonl")))
        p = write_transcript([{"type": "ai-title", "aiTitle": "x"}])
        self.assertFalse(mod._transcript_busy(p))


class StopNeverShootsTheSession(unittest.TestCase):
    """S1~S3 — 중지의 세션 갈래는 어떤 프로세스 신호도 보내지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.auto = tempfile.mkdtemp(prefix="s9int-auto-", dir=TMP)
        mod._auto_dir = staticmethod(lambda: cls.auto)

    def setUp(self):
        for p in glob.glob(os.path.join(mod.STATE, "*.json")):
            os.remove(p)
        for p in glob.glob(os.path.join(self.auto, "*")):
            os.remove(p)
        mod.stop_mark_clear(DOC)
        mod.locate = lambda _i: "/fake/doc.md"
        mod.read_doc = lambda _p: ({"id": DOC, "type": "request",
                                    "status": "in-progress"}, "")

    def binding(self, sid, doc=DOC, attach_pid=0, transcript=None):
        os.makedirs(mod.STATE, exist_ok=True)
        tp = transcript or write_transcript(
            [{"type": "user", "message": {"content": "x"}}])
        b = {"machine": "testbox", "session": sid, "transcript_path": tp,
             "active_reqs": [doc] if doc else [], "ended": ""}
        if attach_pid:
            b["attach_pid"] = str(attach_pid)
        with open(os.path.join(mod.STATE, f"testbox__{sid}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(b, f)
        return b

    def inbox(self, sid):
        p = mod.chat_inbox_path(sid)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    # S1. 사고 재현 조건 — attach pid 생존·busy 트랜스크립트(가드 전부 통과
    #     상태)여도 os.kill 은 한 번도 불리지 않는다. 지시는 수신함으로.
    def test_s1_live_busy_session_gets_zero_signals(self):
        sid = "cafe0001"
        busy_tp = write_transcript([asst("tool_use", [{"type": "tool_use"}])])
        self.binding(sid, attach_pid=os.getpid(), transcript=busy_tp)
        calls = []
        with mock.patch.object(mod.os, "kill",
                               lambda pid, sig: calls.append((pid, sig))):
            r = mod.stop_request(DOC, actor="nicehugepark")
        self.assertTrue(r.get("ok"), r.get("message"))
        self.assertEqual(r.get("action"), "signaled")
        self.assertEqual(calls, [],
                         "세션 갈래가 프로세스에 신호를 보냈다 — 사고 재발 "
                         "(SIGINT 1회가 사용자의 로컬 세션을 통째로 죽였다)")
        lines = self.inbox(sid)
        self.assertTrue(lines, "지시가 수신함에 안 닿았다")
        self.assertEqual(lines[-1].get("kind"), "interrupt")
        self.assertEqual(lines[-1].get("req"), DOC)
        self.assertTrue(mod.stop_mark(DOC), "정지 표시가 없다 — 워처가 되살린다")

    # S2. 워커 갈래 보존 — 스폰 마커 pid 에만 SIGTERM. 세션 pid 는 안 건드린다.
    def test_s2_worker_branch_still_kills_the_marker_pid_only(self):
        wpid = 424242
        with open(os.path.join(self.auto, mod.safe_name(DOC) + ".json"),
                  "w", encoding="utf-8") as f:
            json.dump({"pid": wpid}, f)
        self.binding("cafe0002", attach_pid=os.getpid())
        calls = []
        alive = iter([True, False])          # SIGTERM 후 물러났다
        with mock.patch.object(mod, "_worker_alive",
                               lambda p: next(alive, False)), \
             mock.patch.object(mod, "_stop_note", lambda *a, **k: None), \
             mock.patch("time.sleep", lambda s: None), \
             mock.patch.object(mod.os, "kill",
                               lambda pid, sig: calls.append((pid, sig))):
            r = mod.stop_request(DOC, actor="nicehugepark")
        self.assertTrue(r.get("ok"), r.get("message"))
        self.assertEqual(r.get("action"), "stopped")
        self.assertEqual(calls, [(wpid, signal.SIGTERM)],
                         "워커 마커 pid 밖으로 신호가 샜다")

    # S3. 전달 실패도 신호로 격상되지 않는다 — no-recipient + 표시만.
    def test_s3_delivery_failure_never_escalates_to_a_signal(self):
        self.binding("cafe0003", attach_pid=os.getpid())
        calls = []

        def boom(*a, **k):
            raise ValueError("수신함 없음")
        with mock.patch.object(mod, "chat_send", boom), \
             mock.patch.object(mod.os, "kill",
                               lambda pid, sig: calls.append((pid, sig))):
            r = mod.stop_request(DOC, actor="nicehugepark")
        self.assertTrue(r.get("ok"), r.get("message"))
        self.assertEqual(r.get("action"), "no-recipient")
        self.assertEqual(calls, [], "전달 실패가 프로세스 신호로 격상됐다")
        self.assertTrue(mod.stop_mark(DOC))


class ThePrimitiveIsGone(unittest.TestCase):
    """S4 — SIGINT 원시가 코드베이스에서 사라졌고 되살아나지 못한다."""

    def _blk(self, name, upto="\ndef "):
        i = SRC.find(name)
        self.assertGreater(i, 0, f"{name} 이 없다")
        j = SRC.find(upto, i + 10)
        return SRC[i:j if j > i else len(SRC)]

    def test_s4a_no_interrupt_session_anywhere(self):
        self.assertFalse(hasattr(mod, "interrupt_session"),
                         "interrupt_session 이 되살아났다 — SIGINT 는 턴 취소가 "
                         "아니라 세션 종료다 (REQ-20260830-047 실측)")
        self.assertNotIn("interrupt_session", SRC)

    def test_s4b_stop_request_session_branch_has_no_signal(self):
        # 낱말 SIGINT 는 역사 설명 주석에 남는다 — 시험이 보는 것은 발신이다.
        stop = self._blk("def stop_request(")
        self.assertNotIn("os.kill", stop,
                         "stop_request 가 직접 신호를 보낸다 — 죽이는 자리는 "
                         "worker_stop 한 곳뿐이어야 한다")

    def test_s4c_api_chat_interrupt_queues_only(self):
        i = SRC.find('parsed.path == "/api/chat"')
        self.assertGreater(i, 0)
        j = SRC.find("elif parsed.path", i + 10)
        blk = SRC[i:j]
        self.assertNotIn("os.kill", blk, "Esc 경로가 프로세스에 신호를 보낸다")
        self.assertIn("chat_send", blk, "Esc 큐잉 경로가 사라졌다")

    def test_s4d_nobody_sends_sigint(self):
        # 남은 `.SIGINT` 는 핸들러 설치(수신) 둘뿐이어야 한다 — SIGINT 를
        # **보내는** kill 호출이 돌아오면 이 시험이 실측 사고를 들이민다:
        # 2026-08-30 22:00, 가드 전부 통과 후의 SIGINT 1회가 세션을 통째로
        # 죽였다. 다음에 누가 "즉시 중단"을 다시 원하면 여기부터 읽어라.
        import re
        hits = re.findall(r"kill\s*\([^)]*SIGINT", SRC)
        self.assertEqual(hits, [],
                         "SIGINT 를 보내는 kill 호출이 소스에 돌아왔다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
