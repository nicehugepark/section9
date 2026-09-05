"""옛 코드로 도는 서버가 스스로 드러난다 (REQ-20260827-059-62x6).

실사고 2026-08-27:

    16:59  대시보드 서버 기동
    20:55  질문 큐(REQ-20260827-049)를 고쳐 커밋 — 테스트 6/6 통과
    21:17~ 질문이 계속 유실됨 (QST-025·026 미답)

**채팅→질문 등록은 서버 프로세스 안에서 돈다.** 그래서 디스크의 코드를 고쳐도
16:59에 뜬 서버는 옛 코드고, 큐에 쌓지 않았다. 테스트는 디스크 코드를 직접
실행하니 전부 통과했다 — 고쳤다고 믿을 근거만 늘었다.

대시보드는 이미 배너로 정직하게 알리고 있었다(REQ-20260826-011). 그런데 그건
**사람이 화면을 볼 때만** 보인다. 리드는 화면을 안 본다 — REQ-20260827-046에서
멈춘 작업에 대해 배운 것과 같은 모양이다: **표식만으로는 약하고 주입해야 실제
장치가 된다.**

읽을 수 없으면 낡았다고 단정하지 않는다 — 근거 없는 경고는 곧 무시되고, 한 번
무시되기 시작하면 진짜일 때도 안 읽힌다(code_is_stale 과 같은 규율).

실행: python3 tests/ serve_stale
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")
HOOK_SESSION = os.path.join(HERE, "..", "bin", "s9-audit-session")

from portpool import free_port, wait_server  # noqa: E402
from s9src import serve_tail  # noqa: E402  — 소스 구간은 한 곳에서 (s9src 참조)


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod



class ServeStale(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9stale-")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        self.m = _load("s9_stale_" + os.path.basename(self.root), S9)
        self.m.ROOT = self.root
        # 규범 포트 판정(s9_port)이 물려받은 환경에 흔들리지 않게 (REQ-030-005)
        self._old_port_env = os.environ.pop("S9_PORT", None)

    def tearDown(self):
        if self._old_port_env is not None:
            os.environ["S9_PORT"] = self._old_port_env

    def stamp(self, d):
        with open(os.path.join(self.root, "state", "serve-code.json"), "w",
                  encoding="utf-8") as f:
            json.dump(d, f)

    # N1. 기동 뒤 코드가 바뀌었으면 말한다
    def test_n1_stale_reported(self):
        self.stamp({"stamp": {"mtime": 1.0, "size": 10}, "pid": os.getpid(),
                    "started": "2026-08-27T16:59:19+09:00"})
        msg = self.m.serve_stale()
        self.assertIn("옛 코드", msg)
        self.assertIn("--restart", msg, "무엇을 하라는지 말하지 않는다")

    # N2. 같은 코드면 조용하다 — 늘 켜져 있는 경고는 안 읽힌다
    def test_n2_fresh_silent(self):
        self.stamp({"stamp": self.m.code_stamp(), "pid": os.getpid()})
        self.assertEqual(self.m.serve_stale(), "")

    # B1. 서버가 안 돌면 낡을 것도 없다 — "안 돈다"는 지문 pid 죽음 +
    #     대시보드 포트에 리스너 없음이다 (REQ-20260830-005 뒤로는 죽은 pid
    #     지문의 포트 대신 규범 포트를 본다. 이 머신의 진짜 9909 리스너가
    #     시험에 새어들지 않게 B3·B4 처럼 실리스너 탐색을 막는다)
    def test_b1_dead_server_silent(self):
        self.stamp({"stamp": {"mtime": 1.0, "size": 10}, "pid": 999999999})
        self.m._port_owner_pid = lambda port: 0
        self.assertEqual(self.m.serve_stale(), "")

    # B3. 지문을 남긴 프로세스가 죽었는데 **다른 쪽이 그 포트를 물고 있으면**
    #     "최신"이라고 답하지 않는다 (REQ-20260828-007).
    #     실사고 2026-08-28 08:12: `--restart` 가 포트를 못 뺏고 물러났는데 새
    #     프로세스가 지문만 남기고 죽었고, 07:51 에 뜬 옛 서버가 계속 응답했다.
    #     그 사이 이 명령은 "최신"이라고 답했다 — 모른다고 말해야 할 자리에서
    #     안심시켰다. 안심시키는 거짓이 침묵보다 나쁘다.
    def test_b3_other_process_owns_the_port(self):
        self.stamp({"stamp": {"mtime": 1.0, "size": 10}, "pid": 999999999,
                    "port": 9909})
        self.m._port_owner_pid = lambda port: 4242
        msg = self.m.serve_stale()
        self.assertIn("4242", msg)
        self.assertIn("--restart", msg)

    # B4. 아무도 안 물고 있으면 조용하다 — 낡을 것도 없다
    def test_b4_nobody_owns_the_port(self):
        self.stamp({"stamp": {"mtime": 1.0, "size": 10}, "pid": 999999999,
                    "port": 9909})
        self.m._port_owner_pid = lambda port: 0
        self.assertEqual(self.m.serve_stale(), "")

    # B5. 죽은 pid 의 지문은 **포트까지** 불신한다 (REQ-20260830-005).
    #     실사고 2026-08-30 아침: 시험이 본 저장소 S9_ROOT 로 임시 포트에 띄운
    #     서버가 지문을 갈아쓰고 죽었다. 죽은 pid 지문의 포트(임시 포트)로
    #     실리스너를 찾으면 판정이 남의 자리로 끌려간다 — 찾을 자리는 이
    #     저장소의 대시보드 포트(state/port 또는 9909)다.
    def test_b5_dead_pid_distrusts_the_stamped_port(self):
        self.stamp({"stamp": {"mtime": 1.0, "size": 10}, "pid": 999999999,
                    "port": 18898})
        asked = []
        self.m._port_owner_pid = lambda p: asked.append(p) or 0
        self.assertEqual(self.m.serve_stale(), "")
        self.assertEqual(asked, [9909],
                         "죽은 pid 지문의 임시 포트로 실리스너를 찾았다")

    # B2. 지문 파일이 없거나 깨졌으면 단정하지 않는다
    def test_b2_no_stamp_silent(self):
        self.assertEqual(self.m.serve_stale(), "")
        with open(os.path.join(self.root, "state", "serve-code.json"), "w") as f:
            f.write("{깨진")
        self.assertEqual(self.m.serve_stale(), "")

    # N5. 지문은 **포트를 잡은 뒤에** 남긴다 (REQ-20260828-010).
    #     잡기 전에 남기면 못 잡고 죽은 프로세스의 지문이 남아, 실제로 응답하는
    #     옛 서버를 가린다. 지문은 지금 듣고 있는 쪽을 가리켜야 한다.
    def test_n5_stamp_after_bind(self):
        seg = serve_tail(open(S9_SRC, encoding="utf-8").read())
        bind = seg.index("QuietDisconnectServer((args.host")
        stamp = seg.index("serve-code.json")
        self.assertLess(bind, stamp,
                        "포트를 잡기 전에 지문을 남긴다")

    # N6. 포트를 못 잡으면 시끄럽게 죽는다 — 조용히 죽으면 성공으로 읽힌다
    def test_n6_bind_failure_is_loud(self):
        seg = serve_tail(open(S9_SRC, encoding="utf-8").read())
        self.assertIn("잡지 못했다", seg)
        self.assertIn("except OSError", seg)

    # N3. serve 가 기동 시 지문을 남긴다 — 남기지 않으면 물어볼 데가 없다
    def test_n3_serve_writes_stamp(self):
        seg = serve_tail(open(S9_SRC, encoding="utf-8").read())
        self.assertIn("serve-code.json", seg,
                      "serve 가 기동 지문을 디스크에 남기지 않는다")

    # N4. 프롬프트 훅이 매 턴 주입한다 — 배너는 화면을 볼 때만 보인다
    def test_n4_hook_injects(self):
        src = open(HOOK, encoding="utf-8").read()
        self.assertIn('"serve-stale"', src, "훅이 serve-stale 을 부르지 않는다")
        self.assertIn("{stale_serve}", src, "부르기만 하고 주입하지 않는다")


class StampWanted(unittest.TestCase):
    """지문을 남길 자격 — "이 포트가 이 저장소의 대시보드 포트인가"
    (REQ-20260830-005 (가)).

    지문 파일은 저장소당 하나뿐이다. 임시 포트로 뜬 서버(시험 등)가 그것을
    갈아쓰면 죽은 뒤 doctor·배너가 남의 지문으로 거짓말을 한다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9want-")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        self.m = _load("s9_want_" + os.path.basename(self.root), S9)
        self._old_port_env = os.environ.pop("S9_PORT", None)

    def tearDown(self):
        if self._old_port_env is not None:
            os.environ["S9_PORT"] = self._old_port_env

    # W1. 기본 워크스페이스(state/port 없음): 9909 만이 대시보드 포트다
    def test_w1_default_port_writes(self):
        self.assertTrue(self.m.serve_stamp_wanted(9909, root=self.root))
        self.assertFalse(self.m.serve_stamp_wanted(18898, root=self.root))

    # W2. state/port 가 지정한 포트는 대시보드 포트다 (인스턴스 워크스페이스)
    def test_w2_state_port_wins(self):
        with open(os.path.join(self.root, "state", "port"), "w") as f:
            f.write("9911")
        self.assertTrue(self.m.serve_stamp_wanted(9911, root=self.root))
        self.assertFalse(self.m.serve_stamp_wanted(9909, root=self.root))

    # W3. S9_PORT env 는 s9_port 와 같은 서열로 이긴다
    def test_w3_env_wins(self):
        os.environ["S9_PORT"] = "9912"
        try:
            self.assertTrue(self.m.serve_stamp_wanted(9912, root=self.root))
            self.assertFalse(self.m.serve_stamp_wanted(9909, root=self.root))
        finally:
            os.environ.pop("S9_PORT", None)

    # W4. 못 읽는 포트는 자격 없음 — 예외를 올리지 않는다
    def test_w4_garbage_port_is_false(self):
        self.assertFalse(self.m.serve_stamp_wanted(None, root=self.root))
        self.assertFalse(self.m.serve_stamp_wanted("x", root=self.root))


class TempPortNoStamp(unittest.TestCase):
    """실사고 재현 (REQ-20260830-005 (가), 실서버 클래스당 1회).

    임시 포트에 뜬 서버가 지문을 남기면, 죽은 뒤 doctor 는 죽은 포트를
    두드리며 "안 떠 있다"고 하고 배너는 남의 지문으로 말한다 — 2026-08-30
    아침 사용자가 세션이 다 죽은 줄 알고 s9 를 전부 내렸다 (REQ-20260830-004).
    """

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9tmpsrv-")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_REWORK_WATCH": "off"}
        cls.env.pop("S9_PORT", None)
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env,
                       timeout=15)
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)

    def test_r1_temp_port_leaves_no_stamp(self):
        self.assertFalse(
            os.path.exists(os.path.join(self.root, "state",
                                        "serve-code.json")),
            "임시 포트 서버가 지문을 남겼다 — 죽은 뒤 doctor·배너가 "
            "이 지문으로 거짓말을 한다")


class HookServeGuard(unittest.TestCase):
    """훅이 남의 자리에 서버를 세우지 않는다 (REQ-20260830-033).

    005 가 지문 쓰기를 serve_stamp_wanted 로 막았지만, s9-audit-session 의
    ensure_serve 는 S9_PORT env 만 있고 S9_ROOT 없는 환경에서 본 저장소
    ROOT 로 임시 포트 서버 자체를 띄울 수 있었다 — 규범 아닌 포트에 서버
    프로세스가 뜨는 것도 오염이다. 훅은 독립 실행 파일이라 판정을 최소
    복제하고, 갈라지지 않음은 계약 시험(G5 왕복)이 못박는다
    (test_platform_live H1~H4 복제 검증 선례)."""

    @classmethod
    def setUpClass(cls):
        cls.hook = _load("s9_sess_guard", HOOK_SESSION)
        cls.s9 = _load("s9_guard_cli", S9)

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9guard-")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        # 물려받은 환경에 흔들리지 않게 판정 env 를 비운다 (tdd 규율)
        self._saved = {k: os.environ.pop(k, None)
                       for k in ("S9_PORT", "S9_ROOT")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    # G1(S1). 회귀 — 짝 없이 새어든 S9_PORT 로는 세우지 않는다: 판정 0,
    #         ensure_serve 는 serve 를 Popen 하지 않고 조용히 물러난다
    def test_g1_stray_env_port_skips(self):
        with mock.patch.dict(os.environ, {"S9_PORT": "18898"}):
            self.assertEqual(self.hook._serve_port_wanted(self.root), 0)
            spawned = []
            with mock.patch.object(self.hook.subprocess, "Popen",
                                   lambda argv, **kw: spawned.append(argv)):
                self.hook.ensure_serve()
        self.assertFalse([a for a in spawned if "serve" in a],
                         "규범 아닌 포트에 서버를 세웠다 — 005 거짓 지문 "
                         "계열의 남은 문")

    # G2(S2). 정상 — env 없으면 규범 포트(state/port > 9909)다 (행동 보존)
    def test_g2_no_env_uses_canonical(self):
        self.assertEqual(self.hook._serve_port_wanted(self.root), 9909)
        with open(os.path.join(self.root, "state", "port"), "w") as f:
            f.write("9911")
        self.assertEqual(self.hook._serve_port_wanted(self.root), 9911)

    # G3(S3). 경계 — 규범과 같은 S9_PORT 는 짝 없이도 통과, S9_ROOT 와
    #         짝이면(인스턴스 봉투) 그 포트가 규범이다 (행동 보존)
    def test_g3_matching_or_paired_env_launches(self):
        with mock.patch.dict(os.environ, {"S9_PORT": "9909"}):
            self.assertEqual(self.hook._serve_port_wanted(self.root), 9909)
        with mock.patch.dict(os.environ, {"S9_PORT": "18898",
                                          "S9_ROOT": self.root}):
            self.assertEqual(self.hook._serve_port_wanted(self.root), 18898)

    # G4(S4). 쓰레기 S9_PORT 는 s9_port 와 같은 규율로 무시한다 — 현행은
    #         ValueError 가 훅 밖으로 새는 잠재 결함(훅은 시끄러우면 안 된다)
    def test_g4_garbage_env_port_ignored(self):
        with mock.patch.dict(os.environ, {"S9_PORT": "x"}):
            self.assertEqual(self.hook._serve_port_wanted(self.root), 9909)
            spawned = []
            with mock.patch.dict(os.environ, {"S9_ROOT": self.root}), \
                 mock.patch.object(self.hook.subprocess, "Popen",
                                   lambda argv, **kw: spawned.append(argv)):
                self.hook.ensure_serve()      # 예외가 새어나오면 실패
        serve = [a for a in spawned if "serve" in a]
        self.assertTrue(serve, "규범 포트로도 세우지 않았다")
        self.assertIn("9909", serve[0])

    # G5(S5). 계약(왕복) — 훅이 포트 P 로 세우기로 한 모든 env 조합에서
    #         bin/s9 serve_stamp_wanted(P, root) 도 참이다: 훅이 세운 서버는
    #         반드시 지문 자격이 있다. 복제 판정이 갈라지면 여기서 깨진다.
    def test_g5_contract_launch_implies_stamp(self):
        cases = [
            ({}, None),                                  # 기본 9909
            ({"S9_PORT": "9909"}, None),                 # 규범과 일치
            ({}, "9911"),                                # state/port 인스턴스
            ({"S9_PORT": "18898", "S9_ROOT": "SELF"}, None),   # 봉투 짝
            ({"S9_PORT": "18898"}, None),                # 남의 봉투 → 0
            ({"S9_PORT": "x"}, None),                    # 쓰레기 → 규범
        ]
        launched = 0
        for env, port_file in cases:
            root = tempfile.mkdtemp(prefix="s9guardm-")
            os.makedirs(os.path.join(root, "state"), exist_ok=True)
            if port_file:
                with open(os.path.join(root, "state", "port"), "w") as f:
                    f.write(port_file)
            env = {k: (root if v == "SELF" else v) for k, v in env.items()}
            with mock.patch.dict(os.environ, env):
                port = self.hook._serve_port_wanted(root)
                if port:
                    launched += 1
                    self.assertTrue(
                        self.s9.serve_stamp_wanted(port, root=root),
                        f"훅은 {port} 에 세우는데 s9 는 지문 자격이 없다고 "
                        f"한다 — 복제 판정이 갈라졌다 (env={env})")
        self.assertEqual(launched, 5, "세우는 조합 수가 설계와 다르다")


if __name__ == "__main__":
    unittest.main()
