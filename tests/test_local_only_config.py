"""자율 실행을 여는 설정은 이 머신의 것이다 (REQ-20260902-031).

`users/<u>/config/settings.json` 은 git 이 추적한다. 그 안에 `auto_resume_apply`·
`auto_resume_gh`·`s9code_args`·`worker_worktree` 가 살면, 인스턴스 리포에 push
권한이 있는 누구나 **남의 머신** 워커 권한과 기동 인자를 켤 수 있다(white-hacker
검토 시나리오 3). 세 겹으로 막는다:
  ① 쓰는 자리 — 그 키는 config/local.json(비추적)으로 간다
  ② 읽는 자리 — 추적 파일에 실려 온 그 키는 읽지 않는다 (원격이 다시 밀어 넣어도)
  ③ 커밋 검사 — 그래도 추적 파일에 들어오면 막는다

실행: python3 tests/ local_only_config
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

AUTO = ("auto_resume", "auto_resume_apply", "auto_resume_gh",
        "s9code_args", "worker_worktree")


class LocalOnlyConfig(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9loc-")
        self.env = {**os.environ, "S9_ROOT": self.root}
        subprocess.run([S9, "init"], capture_output=True, env=self.env)
        subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                       env=self.env, stdin=subprocess.DEVNULL)
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_loc", importlib.machinery.SourceFileLoader("s9_loc", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.cfgdir = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(self.cfgdir, exist_ok=True)

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(self.root, ignore_errors=True)

    def _tracked(self):
        p = os.path.join(self.cfgdir, "settings.json")
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}

    def _local(self):
        p = os.path.join(self.cfgdir, "local.json")
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}

    def _push_remote(self, **keys):
        """원격 push 를 흉내 낸다 — 추적 파일에 키가 실려 온다."""
        p = os.path.join(self.cfgdir, "settings.json")
        cur = self._tracked()
        cur.update(keys)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cur, f)

    # L1. 쓰면 local.json 에만 남는다
    def test_l1_autonomy_keys_go_local(self):
        for k in AUTO:
            self.m.do_user_config_set("alice", k, "on" if k != "s9code_args"
                                      else "--permission-mode auto")
        for k in AUTO:
            self.assertNotIn(k, self._tracked(), f"{k} 가 추적 파일에 적힌다")
            self.assertIn(k, self._local())

    # L2. 핵심 — 원격이 밀어 넣어도 읽지 않는다
    def test_l2_remote_pushed_switch_is_ignored(self):
        self._push_remote(auto_resume="on", auto_resume_apply="on",
                          auto_resume_gh="on", s9code_args="--dangerously-x",
                          ui_skin="calm")
        cfg = self.m.user_config("alice")
        for k in ("auto_resume", "auto_resume_apply", "auto_resume_gh",
                  "s9code_args"):
            self.assertNotIn(k, cfg, f"추적 파일의 {k} 가 읽혔다 — 원격 스위치")
        self.assertEqual(cfg.get("ui_skin"), "calm")   # 취향은 그대로 온다
        # local.json 의 값은 읽힌다 — 이 머신의 주인이 정한 것
        self.m.do_user_config_set("alice", "auto_resume", "on")
        self.assertEqual(self.m.user_config("alice").get("auto_resume"), "on")

    # L3. 이전 — 추적 파일에 남은 값을 옮기고 지운다, 멱등, local 이 이긴다
    def test_l3_migration_moves_and_is_idempotent(self):
        self._push_remote(auto_resume_apply="on", s9code_args="--model opus",
                          ui_skin="calm")
        with open(os.path.join(self.cfgdir, "local.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"s9code_args": "--model fable"}, f)
        moved = self.m.migrate_local_only_config("alice")
        self.assertEqual(moved, ["auto_resume_apply", "s9code_args"])
        self.assertEqual(self._tracked(), {"ui_skin": "calm"})
        loc = self._local()
        self.assertEqual(loc.get("auto_resume_apply"), "on")
        self.assertEqual(loc.get("s9code_args"), "--model fable")  # local 이 이긴다
        self.assertEqual(self.m.migrate_local_only_config("alice"), [])
        self.assertEqual(self.m.migrate_local_only_config(""), [])

    # L4. 표시 취향은 추적 파일에 남는다
    def test_l4_preferences_stay_tracked(self):
        for k, v in (("ui_skin", "calm"), ("timezone", "Asia/Seoul"),
                     ("pref_말투", "짧게")):
            self.m.do_user_config_set("alice", k, v)
            self.assertIn(k, self._tracked())
            self.assertNotIn(k, self._local())

    # L5. 장치 — 추적 파일에 들어오면 커밋 검사가 잡는다
    def test_l5_commit_gate_catches_it(self):
        self._push_remote(auto_resume_gh="on")
        hits = self.m.secret_leak(["users/alice/config/settings.json"], "",
                                  root=self.root, user="alice")
        self.assertTrue(any("auto_resume_gh" in h for h in hits), hits)
        self.assertTrue(any("자율 실행" in h for h in hits), hits)

    # L6. 지우면 local 에서도 지워진다
    def test_l6_clear_removes_local(self):
        self.m.do_user_config_set("alice", "auto_resume_apply", "on")
        self.m.do_user_config_set("alice", "auto_resume_apply", "")
        self.assertNotIn("auto_resume_apply", self._local())
        self.assertNotIn("auto_resume_apply", self.m.user_config("alice"))


if __name__ == "__main__":
    unittest.main()
