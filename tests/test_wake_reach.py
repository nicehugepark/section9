"""깨우기가 사람 손에 닿는다 (REQ-20260828-041 라운드1 · 서버 몫).

두 번 반려됐다. 유닛 66건이 통과하는데 사람 앞에서만 안 됐고, 그 이유는 유닛
밖의 **운영 조건이 동시에 닫혀 있었기** 때문이다. 실측(2026-08-29 16:5x):

· `/api/catalog` 의 in-progress 6건 전부 `stalled_mins=None` → 화면에 깨우기
  버튼이 **한 개도 그려지지 않는다.** 버튼이 없으니 '기능이 없다'로 읽힌다.
· 그중 REQ-041 자신은 좀비 클레임이었다: 사라진 워크트리를 가리키는
  transcript 때문에 `judge_health` 가 'unknown' 을 내고, `health_apply` 는
  unknown 을 되쓰지 않아 `result: running` 이 영원히 남는다. 그 running 이
  `delegated_live` 를 참으로 만들어 버튼도 없애고 wake 도 `busy` 로 거부한다.
· 카드의 점은 어제 22:36 에 기록된 stalled 기여를 근거로 오늘도 정지였다 —
  `_contrib_state` 에 시간 한도가 없다. '멈췄다고 적혔는데 못 깨우는 카드'다.
· 오늘 스폰 20슬롯 중 17건을 자동 경로(rework·followup)가 먹었고, 16:48 이후
  사람이 누르는 깨우기는 전부 capped 였다. 사람 손잡이가 무인 워처와 예산을
  다투는 설계 자체가 결함이다.
· 스폰이 성공해도 워커가 마지막 커밋 사본(워크트리)에 앉아 오늘 만든 미커밋
  코드가 없어 blocked 로 물러났다 — 성공 응답이 거짓말이 된다.

실행: python3 tests/ wake_reach
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

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
SRC = open(S9_SRC, encoding="utf-8").read()


def _load(name="s9wake", root=None):
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


def _iso(m, ago):
    import datetime
    return (datetime.datetime.now()
            - datetime.timedelta(seconds=ago)).isoformat(timespec="seconds")


class TheDeadClaimLetsGo(unittest.TestCase):
    """W1~W3 — 죽은 서브에이전트가 요청을 영구히 붙잡지 않는다."""

    def setUp(self):
        self.m = _load("s9wake_h")

    def test_w1_a_vanished_transcript_is_a_failure_not_unknown(self):
        """등록된 기록 자리가 사라졌으면 그건 '모른다'가 아니라 '끝났다'다.

        워크트리가 거둬지면 그 안에서 돌던 서브에이전트의 transcript 경로가
        통째로 사라진다. 종전엔 unknown 이라 health_apply 가 되쓰지 않았고,
        문서의 running 이 영원히 남아 그 REQ 는 보이지도 깨워지지도 않았다."""
        st, why = self.m.judge_health("sub:frontend-developer:a1dfeb13",
                                      age=None, gone=True)
        self.assertEqual(st, "failed", why)
        self.assertTrue(why)
        # 경로를 아예 등록하지 않은 것은 여전히 unknown 이다 — 둘은 다른 사실이다
        self.assertEqual(self.m.judge_health("sub:x:1", age=None)[0], "unknown")

    def test_w2_an_unknown_claim_expires(self):
        """신호가 없는 클레임도 유예 뒤에는 멈춘 것으로 판정된다.

        wake_effect r3c 와 한 벌이되 층이 다르다: 여기는 judge_health 의
        유예 경계값(유닛 — 60초는 안 죽이고 7200초는 죽인다), r3c 는
        --apply 통합 경로. 접지 않는다 (REQ-20260830-029 정독)."""
        self.assertEqual(
            self.m.judge_health("sub:x:1", age=None, claim_age=60)[0],
            "unknown", "유예 안에서는 섣불리 죽이지 않는다")
        st, why = self.m.judge_health("sub:x:1", age=None, claim_age=7200)
        self.assertEqual(st, "stalled", why)

    def test_w2b_health_apply_rewrites_the_expired_claim(self):
        """되쓰지 않으면 다음 세션이 문서를 읽고 또 '진행 중'을 본다."""
        i = SRC.find("def agent_health(")
        j = SRC.find("\ndef health_apply(", i)
        self.assertGreater(j, i)
        blk = SRC[i:j]
        self.assertIn("claim_age", blk, "기여의 나이를 판정에 안 넘긴다")
        self.assertIn("gone", blk, "기록 자리 소멸을 판정에 안 넘긴다")

    def test_w3_delegated_running_checks_the_actor_is_alive(self):
        """판정이 두 벌이면 agents health 는 stalled, 손잡이는 busy 라고 답한다."""
        meta = {"contributions": [
            {"actor": "sub:frontend-developer:a1dfeb13", "item": "화면",
             "result": "running", "started": _iso(self.m, 600),
             "transcript": "/tmp/gone-worktree-does-not-exist/x.jsonl"}]}
        self.m.locate = lambda _i: "/fake/doc.md"
        self.m.read_doc = lambda _p: (meta, "")
        self.assertIsNone(
            self.m.delegated_running("REQ-x"),
            "기록 자리가 사라진 기여가 아직도 클레임으로 인정된다")
        # 살아 있는 기여는 그대로 클레임이다
        live = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        live.write(b"{}\n")
        live.close()
        self.addCleanup(os.unlink, live.name)
        meta["contributions"][0]["transcript"] = live.name
        self.assertIsNotNone(self.m.delegated_running("REQ-x"),
                             "살아 있는 위임까지 풀어 버렸다 — 중복 스폰이 난다")


class TheDotAndTheHandleAgree(unittest.TestCase):
    """W4~W5 — 점이 '멈췄다'고 그린 카드에는 반드시 눌러 볼 것이 있다."""

    def setUp(self):
        self.m = _load("s9wake_d")
        # 이 클래스는 **점과 손잡이의 짝**만 본다. 판정에는 축이 하나 더 있고
        # (어느 문서인지 모르는 서브에이전트가 붙어 있나 — REQ-20260829-036)
        # 그 축은 이 기계의 살아 있는 세션을 읽으므로, 여기 두면 시험 결과가
        # "지금 리드가 무엇을 시켜 놨나"에 따라 흔들린다. 그 축은
        # test_stall_trust 가 격리된 루트에서 따로 본다.
        self.m.unassigned_hands = lambda *_a, **_k: []

    def test_w4_yesterdays_contribution_does_not_paint_todays_dot(self):
        """어제 22:36 의 stalled 가 오늘 점을 계속 정지로 칠했다."""
        meta = {"contributions": [
            {"actor": "sub:designer:ab64fee2", "result": "stalled",
             "reason": "180초째 진전 없음", "ended": _iso(self.m, 80000)}]}
        self.assertEqual(self.m._contrib_state(meta), {},
                         "한도 밖으로 늙은 기여가 아직 요약에 남는다")
        meta["contributions"][0]["ended"] = _iso(self.m, 300)
        self.assertEqual(self.m._contrib_state(meta).get("state"), "stalled")

    def test_w4c_the_summary_carries_its_own_clock(self):
        """요약은 색인에 굳는다 — 시계를 함께 싣지 않으면 어제가 오늘이 된다.

        문서가 안 바뀌면 색인도 안 바뀐다. `_contrib_state` 안의 한도만으로는
        이미 굳은 판정을 늙게 할 수 없어서, 카드를 그리는 자리가 읽는 시점의
        시계를 다시 댈 수 있어야 한다."""
        meta = {"contributions": [
            {"actor": "sub:designer:ab64fee2", "result": "stalled",
             "ended": _iso(self.m, 300)}]}
        ag = self.m._contrib_state(meta)
        self.assertTrue(ag.get("at"), "판정의 시각이 요약에 없다")
        self.assertIsNotNone(self.m._iso_age(ag["at"]))
        i = SRC.find("def catalog_with_live(")
        j = SRC.find("\ndef display_tz(", i)
        self.assertIn("_iso_age", SRC[i:j],
                      "카드를 그리는 자리가 굳은 판정의 나이를 안 잰다")

    def test_w4b_an_open_claim_outranks_a_dead_one(self):
        """살아 있는 리드가 붙어 있는데 죽은 서브 하나로 점을 끄면 안 된다."""
        meta = {"contributions": [
            {"actor": "sub:designer:ab64fee2", "result": "stalled",
             "ended": _iso(self.m, 300)},
            {"actor": "lead:claude", "result": "running",
             "started": _iso(self.m, 60)}]}
        self.assertEqual(self.m._contrib_state(meta).get("open"), 1,
                         "요약이 '아직 열린 기여가 있다'를 말하지 않는다")

    def test_w5_a_stopped_dot_row_is_wakeable(self):
        """live_kind=stalled 인 행은 stall_mins 가 숫자를 낸다."""
        now = time.time()
        self.m.delegated_live = lambda *_a, **_k: False
        row = {"id": "REQ-x", "status": "in-progress",
               "live_kind": "stalled", "updated": _iso(self.m, 400),
               "agent_state": {"state": "stalled", "at": _iso(self.m, 400)}}
        self.assertIsNotNone(
            self.m.stall_mins(row, now, self.m.STALLED_WIN),
            "점은 '멈췄다'고 그리는데 깨울 손잡이가 없다")
        # 방금 움직인 행까지 깨우면 일하는 손 위에 두 번째 손이 붙는다
        row["updated"] = _iso(self.m, 20)
        self.assertIsNone(self.m.stall_mins(row, now, self.m.STALLED_WIN))

    def test_w5c_a_lead_still_writing_is_not_overrun(self):
        """죽음이 기록된 뒤에도 문서가 움직였으면 누군가 아직 쥐고 있다.

        서브 하나가 죽어도 리드는 계속 노트를 쓸 수 있다. 그때까지 잣대를
        좁히면 일하는 손 위에 두 번째 손이 붙는다 — 이 저장소가 네 번 덴
        사고이고, 한 번은 테스트 파일이 디스크에서 사라졌다."""
        now = time.time()
        self.m.delegated_live = lambda *_a, **_k: False
        row = {"id": "REQ-x", "status": "in-progress",
               "live_kind": "stalled", "updated": _iso(self.m, 200),
               "agent_state": {"state": "stalled", "at": _iso(self.m, 900)}}
        self.assertIsNone(self.m.stall_mins(row, now, self.m.STALLED_WIN),
                          "죽음 기록 뒤에도 움직인 문서를 멈췄다고 했다")

    def test_w5b_a_running_row_is_not_wakeable(self):
        now = time.time()
        self.m.delegated_live = lambda *_a, **_k: False
        row = {"id": "REQ-y", "status": "in-progress",
               "updated": _iso(self.m, 400)}
        self.assertIsNone(self.m.stall_mins(row, now, self.m.STALLED_WIN),
                          "아직 조용하지 않은데 멈췄다고 한다")


class ThePersonHasTheirOwnBudget(unittest.TestCase):
    """W6 — 사람이 누른 손잡이는 무인 워처와 예산을 나눠 쓰지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9wcap-")
        self.m = _load("s9wake_c", self.root)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.g = self.m._auto_global_path()

    def _global(self, **kw):
        import datetime
        base = {"day": datetime.date.today().isoformat(), "day_count": 0,
                "hour": int(time.time() // 3600), "hour_count": 0}
        base.update(kw)
        with open(self.g, "w") as f:
            json.dump(base, f)

    def test_w6_watcher_exhaustion_does_not_kill_the_button(self):
        """오늘 20/20 을 워처가 다 써도 사람의 깨우기는 산다."""
        self._global(day_count=20, hour_count=6)
        self.assertTrue(self.m._auto_cap_block("REQ-a", {}),
                        "워처는 막혀야 한다")
        self.assertEqual(self.m._auto_cap_block("REQ-a", {}, reason="wake"), "",
                         "사람이 누른 깨우기가 워처의 소진에 함께 막힌다")

    def test_w6b_the_human_budget_is_finite_and_says_so(self):
        self._global(wake_day_count=99)
        why = self.m._auto_cap_block("REQ-b", {}, reason="wake")
        self.assertTrue(why)
        # 사람이 읽을 사유여야 한다 — 무엇이 바닥났는지가 낱말로 서야
        # `capped` 라는 코드 이름 말고 사람이 읽을 것이 남는다.
        # (REQ-20260830-007 에서 `깨우기 한도` → `깨울 수 있는 횟수` 로 풀었다.)
        # 낱말이 「깨우기」에서 「이어가기」로 바뀌었다 (REQ-20260829-024 라운드4
        # 반려). 계약은 그대로다 — 사람이 읽을 수 있는 사유여야 한다.
        self.assertIn("이어갈 수 있는 횟수", why, "사람이 읽을 사유가 아니다")

    def test_w6c_wake_spends_the_human_counter_only(self):
        self._global()
        self.assertTrue(self.m._auto_caps_ok("REQ-c", {}, reason="wake"))
        with open(self.g) as f:
            g = json.load(f)
        self.assertEqual(g.get("day_count", 0), 0,
                         "사람의 깨우기가 워처 예산을 먹었다")
        self.assertEqual(g.get("wake_day_count", 0), 1)

    def test_w6d_the_per_request_cooldown_still_holds(self):
        """같은 요청에 겹쳐 띄우는 것은 예산과 무관하게 막는다."""
        self._global()
        self.assertTrue(self.m._auto_caps_ok("REQ-d", {}, reason="wake"))
        self.assertTrue(self.m._auto_cap_block("REQ-d", {}, reason="wake"))


class TheWorkerSitsWhereTheCodeIs(unittest.TestCase):
    """W7 — 워크트리가 오늘 코드를 갖지 못하면 주지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9wwt-")
        self._env = {k: os.environ.pop(k) for k in
                     ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
                     if k in os.environ}
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.name", "t")
        self._git("config", "user.email", "t@t")
        os.makedirs(os.path.join(self.root, "bin"))
        with open(os.path.join(self.root, "bin", "a.py"), "w") as f:
            f.write("one\n")
        self._git("add", "-A")
        self._git("commit", "-qm", "init")
        self.m = _load("s9wake_w", self.root)

    def tearDown(self):
        for w in (self.m.worktree_list() or []):
            self._git("worktree", "remove", "--force", w["path"])
        os.environ.update(self._env)
        shutil.rmtree(self.root, ignore_errors=True)

    def _git(self, *a):
        subprocess.run(["git", *a], cwd=self.root, capture_output=True,
                       text=True, timeout=60)

    def test_w7_a_clean_repo_still_gets_a_worktree(self):
        cwd, env, name = self.m.worker_workspace(
            "REQ-x", {"worker_worktree": True}, self.root)
        self.assertTrue(name)
        self.assertNotEqual(cwd, self.root)
        self.assertEqual(env.get("S9_ROOT"), self.root)

    def test_w7b_uncommitted_code_keeps_the_worker_in_the_main_repo(self):
        """워크트리는 마지막 커밋 사본이다 — 오늘 만든 것이 거기 없다.

        실사고: 15:10 의 깨우기 스폰은 실제로 떴지만 고쳐야 할 코드가 그 자리에
        없어 워커가 '오늘 것을 되돌린다'며 blocked 로 물러났다. 창은 깨웠다고
        말하고 카드는 그대로였다 — 성공 응답이 거짓말이 됐다."""
        with open(os.path.join(self.root, "bin", "a.py"), "w") as f:
            f.write("오늘 만든 것\n")
        cwd, env, name = self.m.worker_workspace(
            "REQ-y", {"worker_worktree": True}, self.root)
        self.assertEqual(name, "", "미커밋 코드가 없는 사본에 워커를 앉혔다")
        self.assertEqual(cwd, self.root)
        self.assertEqual(env, {})

    def test_w7c_dirty_data_dirs_do_not_block_the_worktree(self):
        """state/·vault/ 는 S9_ROOT 로 본 저장소를 함께 쓴다 — 사본 문제가 아니다."""
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        with open(os.path.join(self.root, "state", "x.json"), "w") as f:
            f.write("{}")
        cwd, _e, name = self.m.worker_workspace(
            "REQ-z", {"worker_worktree": True}, self.root)
        self.assertTrue(name, "데이터 자리의 변경까지 워크트리를 막았다")
        self.assertNotEqual(cwd, self.root)


class TheContractHolds(unittest.TestCase):
    """W8~W9 — 감사 로그는 남기고, 화면이 읽는 계약은 그대로."""

    def test_w8_wake_is_audited(self):
        i = SRC.find("def _wake_audit(")
        j = SRC.find("\ndef rework_watch_tick(", i)
        self.assertGreater(j, i, "감사 한 줄을 남기는 자리가 없다")
        self.assertIn("_auto_log", SRC[i:j],
                      "사람이 눌렀는지 다음 반려 때 또 짐작하게 된다")
        w = SRC[SRC.find("def wake_request("):j]
        self.assertGreaterEqual(w.count("_wake_audit"), 3,
                                "거부 갈래가 감사를 지나지 않는다")

    def test_w9_the_response_shape_is_unchanged(self):
        m = _load("s9wake_r")
        r = m.wake_request("REQ-does-not-exist-0000")
        self.assertEqual(set(("ok", "id", "action", "mins", "message"))
                         - set(r), set())
        self.assertFalse(r["ok"])
        self.assertEqual(r["action"], "missing")


if __name__ == "__main__":
    unittest.main()
