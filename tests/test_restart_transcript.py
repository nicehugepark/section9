"""재시작 뒤 계정 전환 거부 (REQ-20260910-009).

section9 을 껐다 켠 직후 계정 창에서 다른 계정을 고르면 「이 세션의 대화
기록을 찾지 못해 계정을 바꾸지 않았습니다」가 뜨고 전환이 되지 않았다.
까닭은 둘이다.

① 바인딩의 `transcript_path` 는 훅이 적는데, SessionStart 훅은 그 파일이
   이미 있을 때만 적는다 — 신생 세션은 첫 턴 전까지 파일이 없어 빈 칸이다.
   `restart_session` 은 그 빈 칸을 「기록이 없다」로 읽고 거부했다.
② 찾아보더라도 `~/.claude/projects` 한 자리만 봤다. 계정을 한 번 바꾼
   세션의 기록은 그 프로필(`~/.claude-profiles/<계정>/projects`) 아래에 산다.

격리: S9_ROOT=mktemp, 계정 자리(account_home_dir·profiles_base)는 임시
디렉토리로 갈아 끼운다 — 실제 `~/.claude` 에 파일을 만들지 않는다.
실행: python3 tests/ restart_transcript
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

TMP = tempfile.mkdtemp(prefix="s9rsttp-")
HOME_CFG = os.path.join(TMP, "claude-home")
HOME_PROJ = os.path.join(HOME_CFG, "projects")
PROFILES = os.path.join(TMP, "claude-profiles")
CWD_KEY = "-tmp-work"                       # claude 가 cwd 로 짓는 디렉토리 이름

_prev = {k: os.environ.get(k)
         for k in ("S9_ROOT", "S9_MACHINE", "S9_CLAUDE_PROJECTS")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
os.environ["S9_CLAUDE_PROJECTS"] = HOME_PROJ
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_rsttp", importlib.machinery.SourceFileLoader("s9_mod_rsttp", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

# ROOT 는 import 시점에 굳고 machine·환경은 부를 때마다 읽는다 — 이 모듈
# 안에서만 못박는다(test_session_restart 와 같은 격리).
mod.current_machine = lambda: "testbox"


def _asst(stop="end_turn", model="claude-fable-5"):
    return {"type": "assistant",
            "message": {"stop_reason": stop, "model": model,
                        "content": [{"type": "text", "text": "x"}]}}


def write_transcript(root, full):
    """<root>/<cwd키>/<전체id>.jsonl 하나를 만든다."""
    d = os.path.join(root, CWD_KEY)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, full + ".jsonl")
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(_asst(), ensure_ascii=False) + "\n")
    return p


def make_binding(sid, **kv):
    os.makedirs(mod.STATE, exist_ok=True)
    b = {"machine": "testbox", "session": sid, "user": "", "history": [], **kv}
    with open(os.path.join(mod.STATE, f"testbox__{sid}.json"), "w",
              encoding="utf-8") as f:
        json.dump(b, f)
    return b


class Base(unittest.TestCase):
    """계정 자리를 임시 디렉토리로 갈아 끼우고, 실행 중인 claude 로 답하게 한다."""

    def setUp(self):
        os.makedirs(HOME_PROJ, exist_ok=True)
        os.makedirs(PROFILES, exist_ok=True)
        os.environ["S9_CLAUDE_PROJECTS"] = HOME_PROJ
        self.addCleanup(os.environ.pop, "S9_CLAUDE_PROJECTS", None)
        for name, fn in (("account_home_dir", lambda: HOME_CFG),
                         ("profiles_base", lambda: PROFILES),
                         ("_pid_is_claude", lambda p: True),
                         # 대상 계정의 한도 조회는 이 시험의 관심이 아니다
                         ("usage_limit_hit", lambda *a, **k: None),
                         # 세션이 어느 설정 디렉토리로 떠 있는지는 ps 가 아니라
                         # 시험이 정한다 (기본: 홈 계정)
                         ("session_cfg_dir", lambda b: HOME_CFG)):
            p = mock.patch.object(mod, name, fn)
            p.start()
            self.addCleanup(p.stop)

    def restart(self, sid, **kv):
        return mod.restart_session(sid, **kv)


class TheRecordIsFoundWhenTheBindingIsEmpty(Base):
    """바인딩이 비어 있어도 기록을 찾아낸다 — 빈 칸은 「없다」가 아니다."""

    def test_it_is_found_in_the_home_account(self):
        full = "78c0656e-1111-2222-3333-444444444444"
        write_transcript(HOME_PROJ, full)
        make_binding("78c0656e", attach_pid=str(os.getpid()))
        r = self.restart("78c0656e", account="second@ex.com")
        self.assertTrue(r.get("ok"), r)
        self.assertIn(f"--resume {full}", r["cmd"])
        self.assertTrue(r.get("resumed_conversation"))

    def test_it_is_found_in_the_profile_of_another_account(self):
        """계정을 한 번 바꾼 세션의 기록은 그 프로필 아래에 산다."""
        full = "aa11bb22-1111-2222-3333-444444444444"
        write_transcript(os.path.join(PROFILES, "first@ex.com", "projects"),
                         full)
        make_binding("aa11bb22", attach_pid=str(os.getpid()))
        r = self.restart("aa11bb22", account="second@ex.com")
        self.assertTrue(r.get("ok"), r)
        self.assertIn(f"--resume {full}", r["cmd"])

    def test_the_session_config_dir_is_searched_too(self):
        """프로필 자리 밖의 설정 디렉토리도 그 세션이 쓰는 자리면 찾는다."""
        full = "cc33dd44-1111-2222-3333-444444444444"
        other = os.path.join(TMP, "elsewhere-cfg")
        write_transcript(os.path.join(other, "projects"), full)
        self.assertEqual(mod._discover_transcript("cc33dd44"), "")
        self.assertEqual(mod._discover_transcript("cc33dd44", other),
                         os.path.join(other, "projects", CWD_KEY,
                                      full + ".jsonl"))

    def test_an_empty_id_finds_nothing(self):
        """id 가 없으면 아무것도 찾지 않는다 — 남의 기록을 집는 길을 막는다."""
        write_transcript(HOME_PROJ, "ee55ff66-1111-2222-3333-444444444444")
        self.assertEqual(mod._discover_transcript(""), "")

    def test_the_found_path_is_written_back_to_the_binding(self):
        """찾은 경로는 바인딩에 남는다 — 같은 자리를 두 번 헤매지 않는다."""
        full = "beef0001-1111-2222-3333-444444444444"
        tp = write_transcript(HOME_PROJ, full)
        make_binding("beef0001", attach_pid=str(os.getpid()))
        self.restart("beef0001", account="second@ex.com")
        b = mod.read_binding("testbox", "beef0001") or {}
        self.assertEqual(b.get("transcript_path"), tp)

    def test_a_path_that_no_longer_exists_is_searched_again(self):
        """바인딩의 경로가 디스크에 없으면 다시 찾는다."""
        full = "beef0002-1111-2222-3333-444444444444"
        tp = write_transcript(HOME_PROJ, full)
        make_binding("beef0002", attach_pid=str(os.getpid()),
                     transcript_path=os.path.join(TMP, "gone.jsonl"))
        got, gotfull = mod._session_transcript(
            mod.read_binding("testbox", "beef0002"))
        self.assertEqual(got, tp)
        self.assertEqual(gotfull, full)


class ASessionWithNoConversationIsNotRefused(Base):
    """아직 한 마디도 오가지 않은 세션은 막지 않는다 — 잃을 대화가 없다."""

    def test_the_account_change_goes_through(self):
        make_binding("f00d0001", attach_pid=str(os.getpid()))
        r = self.restart("f00d0001", account="second@ex.com")
        self.assertTrue(r.get("ok"), r)
        self.assertTrue(r.get("fresh_session"))
        self.assertNotIn("--resume", r["cmd"])
        self.assertFalse(r.get("resumed_conversation"))

    def test_the_old_refusal_is_gone(self):
        """「트랜스크립트 없음」으로 되돌아가지 않는다 (회귀)."""
        make_binding("f00d0002", attach_pid=str(os.getpid()))
        r = self.restart("f00d0002", account="second@ex.com")
        self.assertNotEqual(r.get("why_kind"), "no_resume")
        self.assertNotIn("트랜스크립트 없음", str(r.get("reason") or ""))

    def test_a_recorded_path_with_no_file_yet_goes_through_as_fresh(self):
        """a95d4c80 뒤에 남았던 구멍 — 이제 열렸다 (REQ-20260910-054-t8rc).

        대화 기록 파일은 첫 프롬프트가 지나야 생기고, 훅은 그보다 앞서 경로를
        적는다(a95d4c80). 그 사이의 계정 전환은 `_ensure_resumable` 이
        「대상 계정에 이 대화의 기록이 없고, 옮길 원본도 없다」로 막아, 사람은
        문구만 바뀐 같은 벽을 만났다. 이제 그 갈래는 거부가 아니라
        **fresh_session** 이다 — 이을 대화가 없으니 지킬 것도 없다.
        """
        make_binding("f00d0006", attach_pid=str(os.getpid()),
                     transcript_path=os.path.join(
                         HOME_PROJ, CWD_KEY,
                         "f00d0006-1111-2222-3333-444444444444.jsonl"))
        r = self.restart("f00d0006", account="second@ex.com")
        self.assertTrue(r.get("ok"), r)
        self.assertTrue(r.get("fresh_session"))
        self.assertNotIn("--resume", r.get("cmd", ""))

    def test_a_model_only_change_goes_through_too(self):
        make_binding("f00d0003", attach_pid=str(os.getpid()))
        r = self.restart("f00d0003", model="claude-opus-5")
        self.assertTrue(r.get("ok"), r)
        self.assertIn("--model claude-opus-5", r["cmd"])


class TheOtherRefusalsStand(Base):
    """열어 준 것은 이 한 갈래뿐이다 — 나머지 가드는 그대로다."""

    def test_a_dead_session_is_still_refused(self):
        self.assertFalse(mod.restart_session("no-such-session",
                                             account="second@ex.com").get("ok"))

    def test_a_dead_pid_is_still_refused(self):
        make_binding("f00d0004", attach_pid="999999999")
        self.assertFalse(self.restart("f00d0004", model="opus").get("ok"))

    def test_a_busy_turn_is_still_refused(self):
        full = "beef0003-1111-2222-3333-444444444444"
        d = os.path.join(HOME_PROJ, CWD_KEY)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, full + ".jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(_asst("tool_use"), ensure_ascii=False) + "\n")
        make_binding("beef0003", attach_pid=str(os.getpid()))
        r = self.restart("beef0003", model="opus")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("why_kind"), "busy")

    def test_nothing_to_change_is_still_refused(self):
        make_binding("f00d0005", attach_pid=str(os.getpid()))
        self.assertFalse(self.restart("f00d0005").get("ok"))


if __name__ == "__main__":
    unittest.main()
