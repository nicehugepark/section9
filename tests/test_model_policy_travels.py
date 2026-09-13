"""모델 정책은 컴퓨터를 따라간다 (REQ-20260913-002, 실제 사고 2026-09-13).

맥의 무인 워커가 fable 로 떴다. 정책(`auto_resume_model=opus`)은 WSL 의
비추적 local.json 에만 살았고 — 접두 규칙 `auto_resume*` 이 스위치와 함께
정책까지 그 컴퓨터에 가뒀다 — 추적 파일로 동기화된 `last_model_choice=fable`
이 맥에서 그 빈자리를 채웠다. resolved_model 이 막으려던 조건(클릭 한 번이
워커 모델을 정한다)이 컴퓨터 경계에서 되살아난 것이다.

지키는 계약:
  ① `auto_resume_model` 은 자율 실행 스위치가 아니라 사람의 선언 — 추적 파일에 산다
  ② 추적 파일로 온 정책이 최근 선택(last_model_choice)을 이긴다
  ③ 스위치(auto_resume·apply·gh·s9code_args·worker_worktree)는 그대로 local 전용
  ④ 커밋 검사가 정책 키를 스위치로 오인하지 않는다
  ⑤ SPAWN 로그가 모델과 출처를 적는다 — 다음 사고는 transcript 없이 읽힌다

실행: python3 tests/ model_policy_travels
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"

SWITCHES = ("auto_resume", "auto_resume_apply", "auto_resume_gh",
            "s9code_args", "worker_worktree")


class ModelPolicyTravels(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9mpt-")
        self.env = {**os.environ, "S9_ROOT": self.root}
        subprocess.run([S9, "init"], capture_output=True, env=self.env)
        subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                       env=self.env, stdin=subprocess.DEVNULL)
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_mpt", importlib.machinery.SourceFileLoader("s9_mpt", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.cfgdir = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(self.cfgdir, exist_ok=True)

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(self.root, ignore_errors=True)

    def _read(self, name):
        p = os.path.join(self.cfgdir, name)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}

    def _synced(self, **keys):
        """다른 컴퓨터에서 commit 된 추적 파일이 동기화로 온 것을 흉내 낸다."""
        p = os.path.join(self.cfgdir, "settings.json")
        cur = self._read("settings.json")
        cur.update(keys)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cur, f)

    # T1. 정책 키는 local 전용이 아니고, 스위치는 여전히 local 전용이다
    def test_t1_policy_key_is_tracked_switches_are_not(self):
        self.assertFalse(self.m._local_only_key("auto_resume_model"),
                         "모델 정책이 아직 컴퓨터에 갇혀 있다")
        for k in SWITCHES:
            self.assertTrue(self.m._local_only_key(k),
                            f"{k} 는 자율 실행 스위치 — local 전용이어야 한다")

    # T2. 쓰면 추적 파일에 남는다 — 다른 컴퓨터로 간다
    def test_t2_setting_policy_lands_in_tracked_file(self):
        self.m.do_user_config_set("alice", "auto_resume_model", "opus")
        self.assertEqual(self._read("settings.json").get("auto_resume_model"),
                         "opus")
        self.assertNotIn("auto_resume_model", self._read("local.json"))

    # T3. 실제 사고 재현 — 동기화로 온 정책이 동기화로 온 최근 선택을 이긴다
    def test_t3_synced_policy_beats_synced_last_choice(self):
        self._synced(auto_resume_model="opus", last_model_choice="fable")
        self.assertFalse(os.path.exists(os.path.join(self.cfgdir, "local.json")),
                         "이 컴퓨터에는 local.json 이 없다 — 그것이 사고의 조건")
        self.assertEqual(self.m.resolved_model("alice"), ("opus", "policy"))
        self.assertEqual(self.m._spawn_model_args("alice"), ["--model", "opus"])

    # T4. 정책이 어디에도 없으면 최근 선택 — 종전 동작 보존
    def test_t4_no_policy_anywhere_falls_to_last_choice(self):
        self._synced(last_model_choice="fable")
        self.assertEqual(self.m.resolved_model("alice"), ("fable", "last"))

    # T5. 커밋 검사가 정책 키를 자율 실행 스위치로 잡지 않는다
    def test_t5_commit_gate_lets_policy_through(self):
        self._synced(auto_resume_model="opus", auto_resume_gh="on")
        hits = self.m.secret_leak(["users/alice/config/settings.json"], "",
                                  root=self.root, user="alice")
        self.assertFalse(any("auto_resume_model" in h for h in hits), hits)
        self.assertTrue(any("auto_resume_gh" in h for h in hits),
                        "스위치는 여전히 잡혀야 한다: %r" % (hits,))

    # T6. SPAWN 로그 줄이 모델과 출처를 적는다
    def test_t6_spawn_log_carries_model_and_source(self):
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        i = src.index('_auto_log(f"SPAWN({')
        line = src[i:i + 400]
        self.assertRegex(line, r"model=\{_mdl",
                         "SPAWN 로그에 모델이 없다 — 다음 사고는 transcript 를 열어야 읽힌다")
        self.assertRegex(line, r"\(\{_msrc", "모델의 출처(policy/last)가 없다")
        # 그 값은 판정 한 곳(resolved_model)에서 온다 — 두 벌 금지
        j = src.rindex("resolved_model(owner)", 0, i)
        self.assertRegex(src[j - 40:j + 30], r"_mdl, _msrc = resolved_model\(owner\)")


if __name__ == "__main__":
    unittest.main()
