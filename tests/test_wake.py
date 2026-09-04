"""멈춘 것을 사람이 깨운다 — POST /api/wake (REQ-20260828-041-62x6 ②).

사용자(18:04): "in-progress 중인 카드에 상태체크 기능을 만들고 **굳이 프롬프트로
물어보지 않고 진행할 수 있게** 하는 건 어때?" REQ-20260828-036 은 보여주기 절반만
냈다 — 점의 근거를 고치고 멈춤 줄을 세웠지만, 눌러서 다시 굴리는 손잡이가 없다.

이 손잡이가 지켜야 하는 것 셋:
  ① **겹쳐 띄우지 않는다.** 이미 붙어 있는 주체가 있으면 거부한다 — 같은 파일에
     두 번째 손이 붙는 사고로 이 저장소는 네 번 데었다(REQ-20260826-021 에서는
     테스트 파일 하나가 디스크에서 사라졌다).
  ② **스폰 경로는 하나다.** `_spawn_worker` 만 지난다 — 옵트인·같은 머신·쿨다운·
     캡·킬스위치가 두 벌로 갈라지면 한 벌만 고쳐진다.
  ③ **막혔으면 막혔다고 말한다.** 오늘 spawn.log 1052줄 중 1016줄이 SKIP(cap)
     이었다. 사람이 눌렀는데 아무 일도 안 일어나고 이유도 모르는 것이 제일 나쁘다.

주의: 이 스위트는 **무인 워커를 실제로 띄우지 않는다.** 임시 ROOT 에서도
프로세스는 진짜로 뜬다 — 스폰 직전까지의 판정만 검증하고, 실제 Popen 자리는
스텁으로 막거나(단위) 킬스위치로 막는다(API).

실행: python3 tests/ wake
"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

from portpool import free_port, wait_server  # noqa: E402


def cli(env, *a, expect=0):
    r = subprocess.run([S9, *a], capture_output=True, text=True, env=env,
                       stdin=subprocess.DEVNULL, timeout=30)
    if expect is not None and r.returncode != expect:
        raise AssertionError(f"s9 {' '.join(a)}: rc={r.returncode}\n"
                             f"{r.stdout}{r.stderr}")
    return r.stdout.strip()


class NoSpawn(Exception):
    """실제 스폰 시도 = 시험 실패. 임시 ROOT 라도 프로세스는 진짜 뜬다."""


class WakeDecision(unittest.TestCase):
    """스폰 직전까지의 판정 — Popen 자리는 스텁으로 막는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9wk-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox"}
        self.env.pop("S9_SESSION", None)
        self.env.pop("S9_AUTO_RESUME_DISABLE", None)
        cli(self.env, "init")
        cli(self.env, "user", "add", "alice")
        self.rid = self.mkreq("멈춘 것")
        cli(self.env, "status", self.rid, "in-progress", "--note", "t")
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_MACHINE"] = "testbox"
        os.environ.pop("S9_AUTO_RESUME_DISABLE", None)
        spec = importlib.util.spec_from_loader(
            "s9_wk", importlib.machinery.SourceFileLoader("s9_wk", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.calls = []

    def tearDown(self):
        for k in ("S9_ROOT", "S9_MACHINE", "S9_AUTO_RESUME_DISABLE"):
            os.environ.pop(k, None)
        shutil.rmtree(self.root, ignore_errors=True)

    def _no_popen(self, *a, **kw):
        raise NoSpawn(f"무인 워커를 실제로 띄웠다: {a[:1]}")

    def wake(self, *a, **kw):
        """깨우는 동안만 Popen 을 막는다 — 판정은 보되 프로세스는 안 뜬다."""
        real = subprocess.Popen
        subprocess.Popen = self._no_popen
        try:
            return self.m.wake_request(*a, **kw)
        finally:
            subprocess.Popen = real

    def mkreq(self, title):
        return cli(self.env, "new", "request", "--title", title, "--summary",
                   "s", "--size", "S", "--user", "alice", "--goal", "g",
                   "--body", "x").split()[0]

    def stub_spawn(self, ok=True, blocked="", why=""):
        def fake(doc_id, meta, prompt, reason, allow_resume=False, out=None):
            self.calls.append({"id": doc_id, "prompt": prompt,
                               "reason": reason, "resume": allow_resume})
            if not ok and out is not None:
                out["blocked"], out["why"] = blocked, why
            return ok
        self.m._spawn_worker = fake

    # ---- W1. 멈춘 것을 깨우면 스폰 경로를 한 번 지난다 -------------------
    def test_w1_wake_spawns_once(self):
        self.stub_spawn()
        res = self.wake(self.rid, actor="alice", win=0)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["action"], "spawned")
        self.assertEqual(len(self.calls), 1, "스폰 경로가 한 번이 아니다")
        self.assertEqual(self.calls[0]["reason"], "wake",
                         "사유가 남지 않으면 spawn.log 에서 사람이 누른 것과 "
                         "워처가 띄운 것을 구별할 수 없다")
        self.assertIn(self.rid, self.calls[0]["prompt"])
        self.assertIn("--add --session", self.calls[0]["prompt"],
                      "깨운 작업자가 클레임하지 않으면 워처가 또 띄운다")
        # 무엇을 깨웠는지는 **응답의 `id`** 가 말한다 (REQ-20260830-007).
        # 창은 그 값을 머리에 주소로 달고, 본문은 사람에게 할 말만 한다 —
        # 한 창에 같은 번호가 두 번 서면 읽는 눈이 둘을 다시 맞춰 봐야 한다
        # (REQ-20260828-007 이 판정 창에서 이미 세운 규칙).
        self.assertEqual(res["id"], self.rid)
        self.assertNotIn(self.rid, res["message"],
                         "창머리가 이미 다는 주소를 본문이 또 적는다")

    # ---- W2. 이미 누가 붙어 있으면 거부 ----------------------------------
    def test_w2_busy_delegate_blocks_wake(self):
        cli(self.env, "contrib", self.rid, "--actor", "sub:designer:ab12cd34",
            "--item", "화면", "--result", "running")
        self.stub_spawn()
        res = self.wake(self.rid, actor="alice", win=0)
        self.assertFalse(res["ok"])
        self.assertEqual(res["action"], "busy")
        self.assertEqual(self.calls, [],
                         "붙어 있는데 겹쳐 띄웠다 — 같은 파일에 두 번째 손")

    # ---- W3. 아직 조용하지 않으면 거부 -----------------------------------
    def test_w3_recent_progress_blocks_wake(self):
        self.stub_spawn()
        res = self.wake(self.rid, actor="alice")   # 기본 창(15분)
        self.assertFalse(res["ok"])
        self.assertEqual(res["action"], "moving")
        self.assertEqual(self.calls, [])

    # ---- W4. 캡/쿨다운은 그 사실 그대로 응답에 --------------------------
    def _cap_day_full(self):
        d = os.path.join(self.root, "state", "auto_resume")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "_global.json"), "w") as f:
            json.dump({"day": datetime.date.today().isoformat(),
                       "day_count": 20, "hour": int(time.time() // 3600),
                       "hour_count": 0}, f)

    def _cap_wake_full(self, n=12):
        d = os.path.join(self.root, "state", "auto_resume")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "_global.json"), "w") as f:
            json.dump({"day": datetime.date.today().isoformat(),
                       "day_count": 0, "hour": int(time.time() // 3600),
                       "hour_count": 0, "wake_day_count": n,
                       "wake_hour_count": 0}, f)

    def test_w4_day_cap_is_reported(self):
        """사람이 누른 깨우기의 **자기 예산**이 다 차면 그 사실 그대로 답한다.

        전제가 바뀐 자리다 (REQ-20260828-041 라운드1). 종전엔 워처의 전역
        일일 캡(day_count 20)이 이 손잡이도 함께 막았고, 그것을 이 시험이
        정상으로 못 박고 있었다. 실측 2026-08-29: 그날 20슬롯 중 17건을 자동
        경로(rework 13 · followup 4)가 먹었고 16:48:07 이후 사람의 깨우기는
        전부 capped 였다 — **저녁마다 죽는 버튼은 없는 버튼과 같다.** 그래서
        예산을 갈랐고, 시험도 갈린 쪽을 잰다."""
        self.m.user_config = lambda o=None: {"auto_resume": True}
        self._cap_wake_full(12)
        res = self.wake(self.rid, actor="alice", win=0)
        self.assertFalse(res["ok"])
        self.assertEqual(res["action"], "capped")
        self.assertIn("12", res["message"],
                      "한도가 몇인지 안 적히면 사람이 무엇을 바꿔야 할지 모른다")

    def test_w4c_watcher_exhaustion_leaves_the_button_alive(self):
        """워처가 오늘 예산을 다 써도 사람이 누르는 손잡이는 산다."""
        self.m.user_config = lambda o=None: {"auto_resume": True}
        self._cap_day_full()
        self.stub_spawn()
        res = self.wake(self.rid, actor="alice", win=0)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["action"], "spawned")

    def test_w4b_cooldown_is_reported(self):
        """쿨다운은 '기동 중' 창(SPAWN_WIN)보다 길게 잡은 계정에서만 보인다 —
        그 안이면 busy 가 먼저 잡고 더 구체적으로 답한다."""
        self.m.user_config = lambda o=None: {"auto_resume": True,
                                             "auto_resume_cooldown_sec": 1800}
        d = os.path.join(self.root, "state", "auto_resume")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, self.m.safe_name(self.rid) + ".json"),
                  "w") as f:
            json.dump({"last": time.time() - self.m.SPAWN_WIN - 60,
                       "count": 1}, f)
        res = self.wake(self.rid, actor="alice", win=0)
        self.assertFalse(res["ok"])
        self.assertEqual(res["action"], "capped")
        self.assertIn("분", res["message"], "언제 다시 눌러도 되는지가 없다")

    # ---- W5. 옵트인이 꺼져 있으면 그렇게 말한다 --------------------------
    def test_w5_optin_off_is_reported(self):
        self.m.user_config = lambda o=None: {}
        res = self.wake(self.rid, actor="alice", win=0)
        self.assertFalse(res["ok"])
        self.assertEqual(res["action"], "off")
        # 「무엇을 켜야 하는지」를 재되 **원시 키가 아니라 화면의 낱말**로 잰다
        # (REQ-20260901-022). 종전엔 `auto_resume` 이 들어 있는지를 물었는데,
        # 그 자를 대면 서버가 사용자에게 기계 키를 외우게 하는 것이 곧 통과
        # 조건이 된다 — 화면에 그 스위치의 이름과 자리가 생긴 지금은 거꾸로다.
        # 이름과 갈 곳, 둘 다 말해야 사람이 실제로 켤 수 있다.
        # 판 제목이 주어를 지고 행은 술어만 진다 (REQ-20260902-005) — 문장도
        # 그 차례로, 「어느 판」 다음 「어느 행」을 짚어야 사람이 찾아간다.
        self.assertIn("「백그라운드 작업」", res["message"],
                      "어느 판인지가 화면의 이름으로 안 적혀 있다")
        self.assertIn("「맡기기」", res["message"],
                      "어느 행을 켜야 하는지가 안 적혀 있다")
        self.assertIn("Settings", res["message"],
                      "어디서 켜는지가 응답에 없다")

    # ---- W6. in-progress 가 아니면 거부 ----------------------------------
    def test_w6_only_in_progress(self):
        other = self.mkreq("아직 안 잡은 것")
        self.stub_spawn()
        res = self.wake(other, actor="alice", win=0)
        self.assertFalse(res["ok"])
        self.assertEqual(res["action"], "not-in-progress")
        self.assertEqual(self.calls, [])

    # ---- W7. 킬스위치는 손잡이에도 걸린다 --------------------------------
    def test_w7_kill_switch_blocks_wake(self):
        self.m.user_config = lambda o=None: {"auto_resume": True}
        os.environ["S9_AUTO_RESUME_DISABLE"] = "1"
        try:
            res = self.wake(self.rid, actor="alice", win=0)
        finally:
            os.environ.pop("S9_AUTO_RESUME_DISABLE", None)
        self.assertFalse(res["ok"])
        self.assertEqual(res["action"], "disabled",
                         "킬스위치가 켜졌는데 손잡이가 옆문이 됐다")

    # ---- W8. 없는 문서 ---------------------------------------------------
    def test_w8_missing_doc(self):
        self.stub_spawn()
        res = self.wake("REQ-19990101-001-zzzz", actor="alice", win=0)
        self.assertFalse(res["ok"])
        self.assertEqual(res["action"], "missing")
        self.assertEqual(self.calls, [])


class WakeApi(unittest.TestCase):
    """POST /api/wake — 배선과 응답 계약. 서버는 킬스위치를 켠 채 띄운다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9wka-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_AUTO_RESUME_DISABLE": "1"}
        cls.env.pop("S9_SESSION", None)
        cli(cls.env, "init")
        cli(cls.env, "user", "add", "alice")
        cls.stalled = cli(cls.env, "new", "request", "--title", "멈춘 것",
                          "--summary", "s", "--size", "S", "--user", "alice",
                          "--goal", "g", "--body", "x").split()[0]
        cls.fresh = cli(cls.env, "new", "request", "--title", "도는 것",
                        "--summary", "s", "--size", "S", "--user", "alice",
                        "--goal", "g", "--body", "x").split()[0]
        for rid in (cls.stalled, cls.fresh):
            cli(cls.env, "status", rid, "in-progress", "--note", "t")
        cls._backdate(cls.stalled)
        cli(cls.env, "index", "rebuild")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**cls.env, "S9_USER": "alice"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def _backdate(cls, rid):
        """updated 를 두 시간 전으로 — '멈춘 카드' 를 만든다."""
        import glob as _glob
        path = _glob.glob(os.path.join(cls.tmp, "vault", "requests", "*", "*",
                                       rid + ".md"))[0]
        old = (datetime.datetime.now().astimezone()
               - datetime.timedelta(hours=2)).isoformat(timespec="seconds")
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        head, sep, rest = txt.partition("\n---\n")
        head = "\n".join(f"updated: {old}" if l.startswith("updated:") else l
                         for l in head.splitlines())
        with open(path, "w", encoding="utf-8") as f:
            f.write(head + sep + rest)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def post(cls, path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{cls.port}{path}",
            data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode())
            except (ConnectionError, urllib.error.URLError):
                if attempt == 2:
                    raise
                time.sleep(0.3)

    # A1. 멈춘 카드를 깨우면 스폰 경로까지 간다 — 킬스위치가 그 앞에서 잡는다.
    def test_wake_api(self):
        """POST /api/wake — 배선과 응답 계약. 서버는 킬스위치를 켠 채 띄운다."""
        with self.subTest("a1_route_reaches_spawn_gate"):
                code, res = self.post("/api/wake", {"id": self.stalled})
                self.assertEqual(code, 409, res)
                self.assertFalse(res["ok"])
                self.assertEqual(res["action"], "disabled", res)
                self.assertEqual(res["id"], self.stalled)

            # A2. 아직 도는 카드는 거부 — 겹쳐 띄우지 않는다.
        with self.subTest("a2_route_refuses_moving"):
                code, res = self.post("/api/wake", {"id": self.fresh})
                self.assertEqual(code, 409, res)
                self.assertEqual(res["action"], "moving", res)
                self.assertTrue(res["message"])

            # A3. 없는 문서.
        with self.subTest("a3_route_missing"):
            code, res = self.post("/api/wake", {"id": "REQ-19990101-001-zzzz"})
            self.assertEqual(code, 409, res)
            self.assertEqual(res["action"], "missing", res)

if __name__ == "__main__":
    unittest.main(verbosity=2)
