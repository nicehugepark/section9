"""비밀이 **어디 있는지**도 리포에 싣지 않는다 (REQ-20260828-028 부수 발견).

REQ-20260828-012 는 화면에서 "비밀은 값도 **경로도** 주지 않는다" 고 정했다.
그런데 그 경로를 담는 `users/<u>/config/settings.json` 은 **git 이 추적한다.**
security-engineer 가 REQ-20260828-028 조사 중 발견했다.

실측(2026-08-28 19:1x): 이 저장소의 origin 은 **PUBLIC** 이고, 그 파일은
origin/main 에 이미 올라가 있다. 다행히 **공개된 판에는 그 키가 없다** —
키가 생긴 뒤로 push 를 한 적이 없어서다. 다만 그 값이 담긴 커밋이 로컬에
23개 쌓여 있어 **다음 push 한 번이면 공개된다.** 유출이 아니라 유출 직전이다.

값 자체는 안 샜다(추적 파일 전수 검색에서 자격증명 0건). 샌 것은 위치다.
DOC-20260827-006 의 기준을 그대로 적용하면 이 키는 `permissions` 와 같은
칸이다 — "그 자체가 비밀이거나 능력을 여는 것" 은 리포에 싣지 않는다.

그래서 두 겹으로 막는다:
  ① 비밀 위치 키는 추적되지 않는 자리(`config/local.json`)에 쓴다
  ② 그래도 추적 파일에 들어오면 커밋 검사가 막는다 — 규율이 아니라 장치다

실행: python3 tests/ secret_location_key
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


class SecretLocationKey(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9slk-")
        self.env = {**os.environ, "S9_ROOT": self.root}
        subprocess.run([S9, "init"], capture_output=True, env=self.env)
        subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                       env=self.env, stdin=subprocess.DEVNULL)
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_slk", importlib.machinery.SourceFileLoader("s9_slk", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.cfgdir = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(self.cfgdir, exist_ok=True)
        # 바깥 비밀 폴더는 리포 밖이어야 한다 — 안쪽 경로는 거부된다.
        self.ext = tempfile.mkdtemp(prefix="s9slk-ext-")

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(getattr(self, "ext", ""), ignore_errors=True)

    def _tracked(self):
        p = os.path.join(self.cfgdir, "settings.json")
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}

    def _local(self):
        p = os.path.join(self.cfgdir, "local.json")
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}

    # N1. 비밀 위치 키는 추적 안 되는 자리로 간다.
    def test_n1_secret_location_goes_local(self):
        self.m.do_user_config_set("alice", "external_secrets_path", self.ext)
        self.assertNotIn("external_secrets_path", self._tracked(),
                         "비밀 위치가 추적 파일에 적힌다 — push 한 번이면 공개된다")
        self.assertIn("external_secrets_path", self._local())

    # N2. 그래도 읽을 때는 하나로 보인다 — 쓰는 자리가 갈려도 읽는 값은 하나다.
    def test_n2_reads_as_one(self):
        self.m.do_user_config_set("alice", "external_secrets_path", self.ext)
        self.m.do_user_config_set("alice", "ui_skin", "calm")
        cfg = self.m.user_config("alice")
        self.assertEqual(cfg.get("external_secrets_path"), self.ext)
        self.assertEqual(cfg.get("ui_skin"), "calm")

    # N3. 보통 설정은 그대로 추적 파일에 — 머신 간에 옮겨야 한다.
    def test_n3_ordinary_key_stays_tracked(self):
        self.m.do_user_config_set("alice", "ui_skin", "calm")
        self.assertIn("ui_skin", self._tracked())
        self.assertNotIn("ui_skin", self._local())

    # B1. 지우면 양쪽에서 지워진다.
    def test_b1_clear_removes_from_local(self):
        self.m.do_user_config_set("alice", "external_secrets_path", self.ext)
        self.m.do_user_config_set("alice", "external_secrets_path", "")
        self.assertNotIn("external_secrets_path", self._local())
        self.assertEqual(self.m.user_config("alice")
                         .get("external_secrets_path", ""), "")

    # B2. **장치**: 그래도 추적 파일에 들어오면 커밋 검사가 막는다.
    def test_b2_commit_gate_blocks_it(self):
        p = os.path.join(self.cfgdir, "settings.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"external_secrets_path": "/home/me/s9-secrets"}, f)
        hits = self.m.secret_leak(["users/alice/config/settings.json"], "",
                                  root=self.root, user="alice")
        self.assertTrue(hits, "비밀 위치가 커밋에 들어가는데 검사가 침묵한다")
        self.assertTrue(any("external_secrets_path" in h for h in hits), hits)

    # B3. 위치 키가 없으면 조용하다 — 상시 경고는 곧 안 읽힌다.
    def test_b3_quiet_without_it(self):
        p = os.path.join(self.cfgdir, "settings.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"ui_skin": "calm"}, f)
        self.assertEqual(self.m.secret_leak(
            ["users/alice/config/settings.json"], "", root=self.root,
            user="alice"), [])


if __name__ == "__main__":
    unittest.main()
