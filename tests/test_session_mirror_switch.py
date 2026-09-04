"""세션 시작·종료 미러도 끄기 스위치를 본다 (REQ-20260827-077-62x6).

REQ-20260827-042 는 "나는 대화 기록을 쓰지 않는다"는 스위치를 만들었다. 그런데
**매 턴 미러만** 그 스위치를 봤다. 세션 시작·종료 훅은 보지 않고 무조건
`shutil.copyfile` 로 전체를 복사했다 — 껐다고 믿는 사용자의 디스크에 세션마다
전체 사본이 하나씩 생겼다. 껐는데 남는 기록은 스위치가 아예 없는 것보다 나쁘다.

같은 자리에 "늘어난 만큼만 쓴다"(REQ-20260827-039)도 없었다. 8MB 세션이면
시작에 8MB, 종료에 또 8MB.

원인은 하나다 — **미러 구현이 두 벌이었다.** 그래서 이 테스트는 "세션 훅도
스위치를 본다"만 보지 않고, 구현이 다시 갈라지지 않는지(=자기 copyfile 을 갖지
않는지)까지 본다. 갈라지면 언젠가 한쪽만 고쳐진다.

곁들여 (나): `SYNC_DATA_PATHS` 에서 streams 를 뺀다. 지금은 .gitignore 도 막고
있어 겹쳐 보이지만, 방어가 하나뿐이면 그 한 줄이 사라지는 날 문서 하나 만들
때마다 157MB 가 자동 커밋된다.

실행: python3 tests/ session_mirror_switch
"""
import importlib.machinery
import importlib.util
import json
import os
import signal
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
SESSION_HOOK = os.path.join(HERE, "..", "bin", "s9-audit-session")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9smx-")
        # S9_PORT=1: 세션 시작 훅의 ensure_serve 가 **사용자 대시보드 포트**에
        # 서버를 띄우지 못하게 막는다 (REQ-20260828-001). 이게 없으면 훅이
        # 9909 에 감시자를 세우고, 그 서버의 작업공간은 이 임시 디렉토리라
        # 사람이 보는 화면이 404 또는 테스트 시점의 옛 화면으로 바뀐다.
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_MACHINE": "testbox", "S9_USER": "alice",
                    "S9_PORT": "1"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "alice")

    def tearDown(self):
        """훅이 세운 감시자를 거둔다 — 자기가 띄운 것은 자기가 치운다.

        `--supervise` 는 자식이 죽어도 되살리므로, 못 띄우는 포트를 줬다고
        저절로 사라지지 않는다(포기까지 십수 분 돈다).
        """
        lock = os.path.join(self.root, "state", "serve-guard.1.lock")
        try:
            with open(lock, encoding="utf-8") as f:
                pid = int(f.read().split()[0])
        except (OSError, ValueError, IndexError):
            return
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    def cli(self, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=30)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def set_cfg(self, **kw):
        d = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "settings.json")
        cur = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                cur = json.load(f)
        cur.update(kw)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cur, f)

    def transcript(self, body="a\n"):
        p = os.path.join(self.root, "sess-9999.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        return p

    @property
    def mirrored(self):
        # 사람별 자리 (REQ-20260827-078)
        return os.path.join(self.root, "users", "alice", "streams",
                            "sess-9999.jsonl")

    def call_mirror(self, tp):
        """세션 훅의 mirror() 를 그 훅이 실제로 도는 환경에서 부른다."""
        old = os.environ.get("S9_ROOT")
        os.environ.update({"S9_ROOT": self.root, "S9_USER": "alice"})
        try:
            return _load("s9_sm_hook", SESSION_HOOK).mirror(tp)
        finally:
            if old is None:
                os.environ.pop("S9_ROOT", None)
            else:
                os.environ["S9_ROOT"] = old


class Switch(Base):
    """스위치가 세션 훅에도 듣는가."""

    # N1. 기본은 켜짐 — 지금 동작 그대로 미러가 생긴다
    def test_n1_default_on_mirrors(self):
        self.assertEqual(self.call_mirror(self.transcript()), "full")
        self.assertTrue(os.path.exists(self.mirrored))

    # N2. 꺼 두면 **아무것도 쓰지 않는다** — 이것이 이 REQ 의 본체다
    def test_n2_off_writes_nothing(self):
        self.set_cfg(stream_mirror="off")
        self.assertEqual(self.call_mirror(self.transcript()), "off")
        self.assertFalse(os.path.exists(self.mirrored),
                         "껐는데 세션 훅이 사본을 남겼다")

    # N3. 두 번째부터는 늘어난 만큼만 — 시작·종료에 전체를 두 번 쓰지 않는다
    def test_n3_incremental_not_full_copy(self):
        tp = self.transcript()
        self.assertEqual(self.call_mirror(tp), "full")     # 세션 시작
        self.assertEqual(self.call_mirror(tp), "skip")     # 자란 게 없다
        with open(tp, "a", encoding="utf-8") as f:
            f.write("b\n")
        self.assertEqual(self.call_mirror(tp), "append")   # 세션 종료
        with open(self.mirrored, encoding="utf-8") as f:
            self.assertEqual(f.read(), "a\nb\n")

    # R1. 설정이 깨져 있어도 켜진 것으로 본다 — 기록을 남기는 쪽이 안전하다
    def test_r1_broken_config_is_on(self):
        d = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "settings.json"), "w") as f:
            f.write("{ not json")
        self.assertEqual(self.call_mirror(self.transcript()), "full")


class EndToEnd(Base):
    """훅을 통째로 돌려 본다 — 함수가 있어도 불리지 않으면 없는 것이다."""

    def run_hook(self, event, tp):
        data = {"session_id": "sess-9999-aaaa-bbbb", "transcript_path": tp,
                "cwd": self.root, "source": "test"}
        return subprocess.run(
            ["python3", SESSION_HOOK, event], input=json.dumps(data),
            capture_output=True, text=True, env=self.env, timeout=60)

    # N4. 켜져 있으면 세션 시작 훅이 미러를 만든다
    def test_n4_hook_mirrors_when_on(self):
        self.run_hook("start", self.transcript())
        self.assertTrue(os.path.exists(self.mirrored))

    # N5. 꺼져 있으면 훅을 돌려도 streams/ 자체가 생기지 않는다.
    #     디렉토리만 만들어 두는 것도 "껐다"와 어긋난다.
    def test_n5_hook_silent_when_off(self):
        self.set_cfg(stream_mirror="off")
        r = self.run_hook("start", self.transcript())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.mirrored),
                         "껐는데 세션 시작 훅이 사본을 남겼다")


class NoSecondImplementation(unittest.TestCase):
    """결함의 원인은 구현이 두 벌이었다는 것 — 다시 갈라지면 여기서 깨진다."""

    @classmethod
    def setUpClass(cls):
        with open(SESSION_HOOK, encoding="utf-8") as f:
            cls.src = f.read()

    def test_no_own_copyfile(self):
        # 주석·docstring 에는 옛 구현 이야기가 남아 있어도 된다. 막는 것은
        # **부르는 코드**다 — 그래서 import 와 호출 두 가지를 본다.
        self.assertNotIn("import shutil", self.src,
                         "세션 훅이 자기 복사 구현을 되찾았다 — "
                         "스위치·증분이 또 한쪽만 고쳐진다")
        self.assertNotIn("copyfile(", self.src,
                         "세션 훅이 파일을 직접 복사한다")

    def test_reuses_stop_hook(self):
        self.assertIn("s9-audit-response", self.src)
        self.assertIn("mirror_transcript", self.src)


class SyncPaths(unittest.TestCase):
    """(나) 두 겹 방어 — .gitignore 말고도 한 겹이 더 있어야 한다."""

    def test_streams_not_in_sync_paths(self):
        m = _load("s9_sm_mod", S9)
        self.assertNotIn("streams", m.SYNC_DATA_PATHS,
                         "이벤트 커밋 대상에 대화 원문이 남아 있다 — "
                         ".gitignore 한 줄이 사라지면 157MB 가 자동 커밋된다")
        # 지켜야 할 것은 계속 지킨다 — 위 검사가 목록을 비워도 통과하면 안 된다
        for p in ("vault", "users", "projects"):
            self.assertIn(p, m.SYNC_DATA_PATHS)
        # 세션 바인딩은 track 해제 (REQ-20260902-026) — 담당은 문서 lease 가 나른다
        self.assertNotIn("state/sessions", m.SYNC_DATA_PATHS)


if __name__ == "__main__":
    unittest.main()
