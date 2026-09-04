"""깨우면 **일이 붙는다** (REQ-20260828-041 라운드2 · 서버 몫).

라운드1은 판정 함수를 유닛으로 잠갔다(tests/test_wake_reach.py, W1~W9).
그런데 사용자는 두 번째로 반려했다 — '거부하지 않는다'와 '실제로 일이 붙는다'는
다른 명제이고, 깨진 자리는 늘 뒤쪽이었다. 실측 근거:

· 15:10 wake(REQ-079): 워커가 떴는데 앉은 자리가 마지막 커밋 사본(워크트리)이라
  오늘 만든 것이 없었다. 워커가 스스로 blocked 로 물러났다 — 창은 깨웠다고 말하고
  카드는 그대로. **성공 응답이 거짓말이 된다.**
· 16:36 rework(041): 로그 0바이트·pid 사망·워크트리 소멸. 기여는 running 인 채
  좀비로 남아 다음 깨우기를 busy 로 거부했다.
· 11:04~11:39(REQ-016): 같은 REQ 에 워커가 넷 떴다. `SPAWN_WIN`(600초)과
  쿨다운(600초)이 같아서, 화면의 '기동 중' 앰버가 꺼지는 바로 그 순간 쿨다운이
  풀린다 — **도는 워커가 '멈춤'으로 읽히고 그 카드의 깨우기가 곧 중복 스폰이다.**

여기서 잠그는 것은 그 세 가지의 반대다. 진짜 워커는 절대 띄우지 않는다:
Popen 스텁 · 판정 함수 직접 호출 · 격리된 S9_ROOT.

실행: python3 tests/ wake_effect
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
SRC = open(S9, encoding="utf-8").read()


def _load(name, root=None):
    old = os.environ.get("S9_ROOT")
    if root:
        os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if old is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = old


def _fake_claude(tmp):
    """comm=claude 인 진짜 프로세스 — pid 를 지어내면 재사용 방어를 건너뛴다."""
    path = os.path.join(tmp, "claude")
    if not os.path.exists(path):
        os.symlink(shutil.which("sleep") or "/bin/sleep", path)
    return subprocess.Popen([path, "120"], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


class IsolatedVault(unittest.TestCase):
    """진짜 vault 한 벌 — 판정이 문서를 읽는 경로까지 함께 태운다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9wake2-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = {**os.environ, "S9_ROOT": self.tmp, "S9_MACHINE": "testbox",
                    "S9_USER": "tester", "S9_AUDIT": "off",
                    "S9_AUTO_RESUME_DISABLE": "1"}
        for k in ("S9_SESSION", "S9_PORT"):
            self.env.pop(k, None)
        self.s9("init")
        self.m = _load("s9wake2_" + os.path.basename(self.tmp), self.tmp)
        self.procs = []
        self.addCleanup(self._reap)

    def _reap(self):
        for p in self.procs:
            try:
                p.kill()
                p.wait(timeout=5)
            except Exception:
                pass

    def claude(self):
        p = _fake_claude(self.tmp)
        self.procs.append(p)
        for _ in range(100):
            if self.m._pid_is_claude(p.pid):
                break
            time.sleep(0.02)
        return p

    def s9(self, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=90,
                           stdin=subprocess.DEVNULL)
        if expect is not None:
            self.assertEqual(r.returncode, expect, r.stderr or r.stdout)
        return r

    def new_req(self, title="깨울 것", status="in-progress"):
        rid = self.s9("new", "request", "--title", title, "--summary", "s",
                      "--body", "b").stdout.split()[0].strip()
        if status != "open":
            self.s9("status", rid, status, "--note", "착수")
        return rid

    def age_doc(self, rid, seconds):
        """문서의 updated 를 과거로 민다 — 멈춤 시계는 updated 를 본다."""
        import datetime
        path = self.m.find_path(rid)
        meta, body = self.m.read_doc(path)
        old = (datetime.datetime.now()
               - datetime.timedelta(seconds=seconds)).astimezone()
        meta["updated"] = old.isoformat(timespec="seconds")
        self.m.write_doc(path, meta, body)
        self.m.rebuild_index(quiet=True)

    def marker(self, rid, pid=None, last=None):
        d = os.path.join(self.tmp, "state", "auto_resume")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, self.m.safe_name(rid) + ".json")
        row = {"last": time.time() if last is None else last, "count": 1}
        if pid is not None:
            row["pid"] = pid
        with open(p, "w") as f:
            json.dump(row, f)
        return p

    def row(self, rid, win=None):
        rows = self.m.catalog_with_live(
            stall_win=self.m.STALLED_WIN if win is None else win)
        return next((r for r in rows if r.get("id") == rid), None)


class TheDeadWorkerReleasesTheWork(IsolatedVault):
    """R3~R4 — 죽음의 세 모양 어느 것도 영구 running 을 남기지 않는다.

    라운드1은 `judge_health` 를 단위로 잠갔다. 여기서 태우는 것은 문서를 읽는
    실제 스캔(`agent_health`)과 되쓰기(`health_apply`)다 — 하나라도 running 이
    남으면 다음 깨우기가 busy 로 거부되고, 그것이 사용자가 본 '안된다'였다."""

    def _open_claims(self, rid):
        meta, _ = self.m.read_doc(self.m.find_path(rid))
        return [c for c in (meta.get("contributions") or [])
                if c.get("result") == "running"]

    def test_the_dead_worker_releases_the_work(self):
        """R3~R4 — 죽음의 세 모양 어느 것도 영구 running 을 남기지 않는다."""
        with self.subTest("r3a_a_vanished_transcript_ends_the_claim"):
            rid = self.new_req("기록 자리가 사라진 건")
            self.s9("contrib", rid, "--actor", "sub:frontend-developer:a1dfeb13",
                    "--item", "화면", "--result", "running",
                    "--transcript", "/tmp/does-not-exist-worktree/x.output")
            self.assertTrue(self._open_claims(rid))
            self.s9("agents", "health", "--apply")
            self.assertFalse(self._open_claims(rid),
                             "좀비 클레임이 남아 다음 깨우기를 busy 로 막는다")
        with self.subTest("r3b_a_dead_worker_pid_ends_the_claim"):
            rid = self.new_req("워커가 즉사한 건")
            p = self.claude()
            p.kill()
            p.wait(timeout=5)
            self.marker(rid, pid=p.pid)
            open(os.path.join(self.tmp, "state", "auto_resume",
                              self.m.safe_name(rid) + ".log"), "w").close()
            self.s9("contrib", rid, "--actor", "worker:auto-resume",
                    "--item", "재작업", "--result", "running")
            self.s9("agents", "health", "--apply")
            self.assertFalse(self._open_claims(rid),
                             "죽은 워커의 기여가 running 으로 남았다")
        with self.subTest("r3c_a_claim_with_no_signal_at_all_expires"):
            rid = self.new_req("신호가 없는 건")
            self.s9("contrib", rid, "--actor", "sub:designer:ab64fee2",
                    "--item", "손", "--result", "running")
            path = self.m.find_path(rid)
            meta, body = self.m.read_doc(path)
            import datetime
            old = (datetime.datetime.now() - datetime.timedelta(
                seconds=self.m.UNKNOWN_GRACE + 600)).astimezone()
            meta["contributions"][0]["started"] = old.isoformat(timespec="seconds")
            meta["contributions"][0].pop("ended", None)
            self.m.write_doc(path, meta, body)
            self.m.rebuild_index(quiet=True)
            self.s9("agents", "health", "--apply")
            self.assertFalse(self._open_claims(rid),
                             "신호 없는 클레임이 유예를 넘겨도 안 풀린다")
        with self.subTest("r3d_applying_twice_is_stable"):
            rid = self.new_req("두 번 도는 건")
            self.s9("contrib", rid, "--actor", "sub:qa:dddd4444", "--item", "검증",
                    "--result", "running", "--transcript", "/tmp/gone/x.output")
            self.s9("agents", "health", "--apply")
            self.s9("agents", "health", "--apply")
            self.assertFalse(self._open_claims(rid))
        with self.subTest("r4_after_the_claim_ends_wake_does_not_say_busy"):
            rid = self.new_req("좀비를 푼 뒤 깨울 건")
            self.s9("contrib", rid, "--actor", "sub:frontend-developer:a1dfeb13",
                    "--item", "화면", "--result", "running",
                    "--transcript", "/tmp/does-not-exist-worktree/x.output")
            self.assertTrue(self._open_claims(rid), "전제 확인: 문서는 running 이다")
            self.s9("agents", "health", "--apply")
            self.assertFalse(self._open_claims(rid))
            self.assertIsNone(self.m.delegated_running(rid))
            self.age_doc(rid, self.m.STALLED_WIN + 300)
            old = os.environ.get("S9_AUTO_RESUME_DISABLE")
            os.environ["S9_AUTO_RESUME_DISABLE"] = "1"   # 진짜 워커는 띄우지 않는다
            try:
                res = self.m.wake_request(rid, actor="tester")
            finally:
                if old is None:
                    os.environ.pop("S9_AUTO_RESUME_DISABLE", None)
                else:
                    os.environ["S9_AUTO_RESUME_DISABLE"] = old
            self.assertNotEqual(res["action"], "busy", res["message"])
            # 멈춤 판정까지 통과해 스폰 문 앞에 섰다는 것이 이 시나리오의 결론이다
            self.assertEqual(res["action"], "disabled", res["message"])
            self.assertEqual(res["mins"], 20)

class TheRunningWorkerIsNotStalled(IsolatedVault):
    """R5 + 016 패치 2 — 도는 워커와 죽은 워커를 화면·손잡이가 갈라 본다."""

    def test_the_running_worker_is_not_stalled(self):
        """R5 + 016 패치 2 — 도는 워커와 죽은 워커를 화면·손잡이가 갈라 본다."""
        with self.subTest("r5_a_dead_spawn_does_not_lock_the_handle"):
            rid = self.new_req("워커가 즉사한 건")
            p = self.claude()
            p.kill()
            p.wait(timeout=5)
            self.age_doc(rid, self.m.STALLED_DEAD_WIN + 120)   # 5분 — 15분엔 못 미친다
            self.marker(rid, pid=p.pid, last=time.time() - 60)
            r = self.row(rid)
            self.assertEqual(r.get("live_kind"), "spawn_failed", r)
            self.assertIsNotNone(r.get("stalled_mins"),
                                 "점은 멈춤인데 누를 것이 없다 — 그 조합이 반려였다")
        with self.subTest("r5b_a_live_worker_past_the_amber_window_still_holds"):
            rid = self.new_req("오래 도는 워커")
            p = self.claude()
            self.age_doc(rid, self.m.STALLED_WIN + 600)
            self.marker(rid, pid=p.pid, last=time.time() - self.m.SPAWN_WIN - 120)
            r = self.row(rid)
            self.assertEqual(r.get("live_kind"), "spawned",
                             "도는 워커가 화면에서 사라졌다")
            self.assertIsNone(r.get("stalled_mins"),
                              "도는 워커 위에 두 번째 손을 붙이라고 그린다")
            res = self.m.wake_request(rid, actor="tester")
            self.assertEqual(res["action"], "busy", res["message"])
            # 이미 하고 있다는 말이 문장에 있어야 한다 (낱말은 REQ-20260830-007 에서
            # `돌고 있다` → `진행하고 있습니다` 로 바뀌었다 — 사용자의 말로).
            self.assertIn("진행", res["message"])
        with self.subTest("r5c_a_hung_worker_eventually_lets_go"):
            rid = self.new_req("멎은 워커")
            p = self.claude()
            self.age_doc(rid, self.m.STALLED_WIN + 600)
            self.marker(rid, pid=p.pid, last=time.time() - self.m.WORKER_WIN - 60)
            r = self.row(rid)
            self.assertIsNotNone(r.get("stalled_mins"),
                                 "멎은 워커가 멈춤 표시를 영원히 감춘다")

class TheBudgetsStaySeparate(IsolatedVault):
    """R6 — 워처가 하루치를 다 써도 사람의 손잡이는 산다 (살아 있는 카운터 모양)."""

    def test_r6_the_human_branch_survives_a_full_watcher_day(self):
        d = os.path.join(self.tmp, "state", "auto_resume")
        os.makedirs(d, exist_ok=True)
        # 2026-08-29 17:41 실측 그대로의 모양: wake_* 키가 아예 없는 옛 파일
        with open(os.path.join(d, "_global.json"), "w") as f:
            json.dump({"day": time.strftime("%Y-%m-%d"), "day_count": 20,
                       "hour": int(time.time() // 3600), "hour_count": 5}, f)
        cfg = {"auto_resume": True}
        self.assertTrue(self.m._auto_cap_block("REQ-x", cfg, reason="rework"),
                        "전제 확인: 워처 갈래는 막혀 있어야 한다")
        self.assertEqual(self.m._auto_cap_block("REQ-x", cfg, reason="wake"),
                         "", "사람의 손잡이가 워처의 예산 때문에 죽는다")

    def test_r6b_spending_wake_does_not_touch_the_watcher_counter(self):
        d = os.path.join(self.tmp, "state", "auto_resume")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "_global.json"), "w") as f:
            json.dump({"day": time.strftime("%Y-%m-%d"), "day_count": 7,
                       "hour": int(time.time() // 3600), "hour_count": 1}, f)
        self.assertTrue(self.m._auto_caps_ok("REQ-y", {}, reason="wake"))
        with open(os.path.join(d, "_global.json")) as f:
            g = json.load(f)
        self.assertEqual(g["day_count"], 7, "사람이 워처의 예산을 갉아먹는다")
        self.assertEqual(g["wake_day_count"], 1)


class EveryAnswerIsAudited(IsolatedVault):
    """R7 — 다음 반려 때 '눌렀는데 안 된 것'인지 짐작하지 않는다."""

    def _wake_lines(self):
        p = os.path.join(self.tmp, "state", "auto_resume", "spawn.log")
        try:
            with open(p, encoding="utf-8") as f:
                return [l for l in f.read().splitlines() if " WAKE " in l]
        except OSError:
            return []

    def test_r7_every_branch_leaves_a_line(self):
        seen = {}
        seen["missing"] = self.m.wake_request("REQ-nope-0000", actor="tester")
        kid = self.s9("new", "knowledge", "--title", "지식", "--summary", "s",
                      "--body", "b").stdout.split()[0].strip()
        seen["not-request"] = self.m.wake_request(kid, actor="tester")
        openr = self.new_req("아직 안 집은 것", status="open")
        seen["not-in-progress"] = self.m.wake_request(openr, actor="tester")
        moving = self.new_req("방금 움직인 것")
        seen["moving"] = self.m.wake_request(moving, actor="tester")
        stalled = self.new_req("멈춘 것")
        self.age_doc(stalled, self.m.STALLED_WIN + 300)
        old = os.environ.get("S9_AUTO_RESUME_DISABLE")
        os.environ["S9_AUTO_RESUME_DISABLE"] = "1"   # 진짜 워커는 띄우지 않는다
        try:
            seen["disabled"] = self.m.wake_request(stalled, actor="tester")
        finally:
            if old is None:
                os.environ.pop("S9_AUTO_RESUME_DISABLE", None)
            else:
                os.environ["S9_AUTO_RESUME_DISABLE"] = old
        for want, res in seen.items():
            self.assertEqual(res["action"], want, res)
        lines = self._wake_lines()
        self.assertEqual(len(lines), len(seen),
                         f"감사 줄이 갈래 수와 다르다: {lines}")
        for want in seen:
            self.assertTrue(any(f"action={want}" in l for l in lines),
                            f"{want} 갈래가 감사를 지나지 않는다: {lines}")
        self.assertTrue(all("by=tester" in l for l in lines), lines)


class TheSpawnCommandIsWhatWeThink(unittest.TestCase):
    """R8 — 깨우기가 **실제로 실행하는 명령줄**을 붙잡아 읽는다.

    여기까지 와서야 '깨웠다'가 참이 된다. 진짜 워커는 띄우지 않는다:
    subprocess.Popen 을 가로채 argv·cwd·env 만 본다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9wargv-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.m = _load("s9wargv", self.tmp)
        self.m.ROOT = self.tmp
        os.makedirs(os.path.join(self.tmp, "state", "auto_resume"),
                    exist_ok=True)
        self.cfg = {"auto_resume": True, "auto_resume_apply": True,
                    "auto_resume_model": "claude-opus-5[1m]"}
        self.m.user_config = lambda _o=None: self.cfg
        self.m.resolve_user = lambda _x=None: "tester"
        self.m._auto_caps_ok = lambda *a, **k: True
        self.m._auto_mark_pid = lambda *a, **k: None
        self.m.read_binding = lambda *a, **k: {}
        self.m.resume_item_plan = lambda _i: {"pending": [], "prompt": ""}
        self.m.worker_workspace = lambda _d, _c, cwd, dec=None: (self.tmp,
                                                                  {}, "")
        # 자리 판정은 git 을 부른다(worktree list·status). 이 시험은 Popen 을
        # 통째로 가로채므로 그 git 이 가짜 Popen 에 걸린다 — 여기서 보는 것은
        # **실행되는 명령줄**이지 자리 판정이 아니다(그건 test_spawn_workspace).
        self.m.workspace_decision = lambda _d, _c, **k: {
            "kind": "main", "reason": "off", "scope": None,
            "blocking": [], "wt": ""}
        self.meta = {"id": "REQ-20260828-041-62x6", "type": "request",
                     "status": "in-progress", "user": "tester",
                     "title": "멈춘 것을 사람이 깨운다",
                     "machine": self.m.current_machine(), "session": "",
                     "project": ""}

    def capture(self):
        got = {}

        def fake(argv, **kw):
            got["argv"], got["kw"] = list(argv), kw
            return type("P", (), {"pid": 0})()

        with mock.patch("subprocess.Popen", fake):
            ok = self.m._spawn_wake("REQ-20260828-041-62x6", self.meta,
                                    mins=44, by="tester", out={})
        self.assertTrue(ok, "스폰 경로가 아예 안 불렸다")
        self.assertIn("argv", got, "Popen 을 가로채지 못했다 — 진짜로 떴을 수 있다")
        return got

    def test_r8a_the_worker_sits_where_todays_code_is(self):
        got = self.capture()
        self.assertEqual(got["kw"].get("cwd"), self.tmp,
                         "워커가 오늘 코드가 없는 자리에 앉는다")

    def test_r8b_the_model_is_pinned(self):
        """모델을 못 박지 않으면 한도 소진 시 스폰한 워커가 전부 즉사한다."""
        argv = self.capture()["argv"]
        self.assertIn("--model", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "claude-opus-5[1m]")

    def test_r8c_the_envelope_can_actually_edit(self):
        """적용 모드인데 고칠 손이 없으면 '깨웠다'가 또 거짓말이 된다."""
        argv = self.capture()["argv"]
        self.assertIn("--permission-mode", argv)
        self.assertEqual(argv[argv.index("--permission-mode") + 1],
                         "acceptEdits")
        self.assertIn("--allowedTools", argv)
        tools = argv[argv.index("--allowedTools") + 1:]
        self.assertIn("Read", tools)
        self.assertTrue(any(t.startswith("Bash(") and "bin/s9" in t
                            for t in tools),
                        f"s9 를 못 부르면 클레임도 보고도 못 한다: {tools}")

    def test_r8d_the_envelope_holds_when_apply_is_off(self):
        """옵트인하지 않은 계정에 편집 권한이 새어 나가지 않는다."""
        self.cfg["auto_resume_apply"] = False
        argv = self.capture()["argv"]
        self.assertNotIn("--permission-mode", argv)
        self.assertNotIn("acceptEdits", argv)

    def test_r8e_the_prompt_says_what_to_continue(self):
        """새로 시작하라고 읽히면 워커가 남의 일을 처음부터 다시 한다."""
        prompt = self.capture()["argv"][2]
        self.assertIn("REQ-20260828-041-62x6", prompt)
        self.assertIn(os.path.join(self.tmp, "bin", "s9") + " show", prompt)
        self.assertIn("--add --session", prompt,
                      "클레임 지시가 없으면 워처가 그 위에 또 띄운다")
        self.assertIn("44분", prompt, "왜 깨웠는지가 워커에게 안 간다")

    def test_r8f_the_environment_does_not_leak_the_lead_session(self):
        """리드의 세션 id 를 물려주면 두 주체가 같은 세션을 쓴다 (REQ-081)."""
        env = self.capture()["kw"].get("env") or {}
        self.assertEqual(env.get("S9_AUTO_RESUME"), "1",
                         "재귀 스폰 방지 표식이 없다")
        self.assertEqual(env.get("S9_USER"), "tester")
        self.assertNotIn("S9_SESSION", env)

    def test_r8g_the_kill_switch_stands_in_front_of_the_spawn(self):
        """스위치에 옆문이 나면 그것은 스위치가 아니다."""
        old = os.environ.get("S9_AUTO_RESUME_DISABLE")
        os.environ["S9_AUTO_RESUME_DISABLE"] = "1"
        try:
            out = {}
            with mock.patch("subprocess.Popen",
                            lambda *a, **k: self.fail("스위치를 뚫고 떴다")):
                self.assertFalse(self.m._spawn_wake(
                    "REQ-20260828-041-62x6", self.meta, out=out))
            self.assertEqual(out.get("blocked"), "disabled")
        finally:
            if old is None:
                os.environ.pop("S9_AUTO_RESUME_DISABLE", None)
            else:
                os.environ["S9_AUTO_RESUME_DISABLE"] = old


class TheWorktreeIsNotHandedOutBlind(unittest.TestCase):
    """R1~R2 — 오늘 만든 것이 없는 사본에 워커를 앉히지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9wdirty-")
        self._env = {k: os.environ.pop(k) for k in
                     ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
                     if k in os.environ}
        self.addCleanup(lambda: os.environ.update(self._env))
        self.addCleanup(shutil.rmtree, self.root, True)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.name", "t")
        self._git("config", "user.email", "t@t")
        os.makedirs(os.path.join(self.root, "bin"))
        with open(os.path.join(self.root, "bin", "s9"), "w") as f:
            f.write("어제 커밋한 것\n")
        self._git("add", "-A")
        self._git("commit", "-qm", "init")
        self.m = _load("s9wdirty", self.root)

    def _git(self, *a):
        subprocess.run(["git", *a], cwd=self.root, capture_output=True,
                       text=True, timeout=60)

    def test_r1_uncommitted_code_is_seen_by_name(self):
        """무엇 때문에 물러났는지 로그가 말할 수 있어야 한다 — 개수가 아니라 이름."""
        self.assertEqual(self.m.repo_code_dirty(self.root), [])
        with open(os.path.join(self.root, "bin", "s9"), "w") as f:
            f.write("오늘 고친 것\n")
        self.assertEqual(self.m.repo_code_dirty(self.root), ["bin/s9"])

    def test_r2_a_dirty_repo_never_reaches_worktree_add(self):
        """물러나는 것으로 끝나면 안 된다 — 가지를 만들다 마는 자리가 없어야 한다."""
        with open(os.path.join(self.root, "bin", "s9"), "w") as f:
            f.write("오늘 고친 것\n")
        calls = []
        self.m.worktree_add = lambda *a, **k: (calls.append(a) or (None, ""))
        logs = []
        self.m._auto_log = logs.append
        cwd, env, name = self.m.worker_workspace(
            "REQ-x", {"worker_worktree": True}, self.root)
        self.assertEqual((cwd, env, name), (self.root, {}, ""))
        self.assertEqual(calls, [], "미커밋인데 워크트리를 만들러 갔다")
        self.assertTrue(any("WT-SKIP(dirty)" in l for l in logs),
                        f"왜 본 저장소에 앉혔는지 아무 데도 안 남는다: {logs}")


class TheContractHolds(unittest.TestCase):
    """R9 — 화면이 읽는 계약은 라운드2에서도 그대로다."""

    def test_r9_shape_is_unchanged(self):
        m = _load("s9wshape")
        r = m.wake_request("REQ-does-not-exist-0000")
        self.assertEqual(set(r), {"ok", "id", "action", "mins", "message"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["action"], "missing")
        self.assertTrue(r["message"])

    def test_r9b_every_refusal_carries_a_sentence(self):
        """거부만 돌려주고 이유를 안 주면 사람은 버튼이 고장 났다고 읽는다.

        `action` 은 기계가 읽는 이름이고 사람이 읽는 것은 `message` 하나다 —
        화면은 그것을 그대로 창에 띄운다. 빈 문장이 새어 나가면 화면에는
        아무 말 없는 빈 창이 뜬다."""
        i = SRC.find("def wake_request(")
        j = SRC.find("\ndef rework_watch_tick(", i)
        blk = SRC[i:j]
        self.assertGreater(blk.count('"message"'), blk.count('"action"') - 1,
                           "사유 없는 갈래가 있다")
        self.assertNotIn('"message": ""', blk)


if __name__ == "__main__":
    unittest.main()
