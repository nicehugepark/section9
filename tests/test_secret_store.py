"""사용자별 비밀값 — 보관·차단·사용 (REQ-20260827-035-62x6).

사용자 요구: `users/<u>/secrets/` 를 두고 커밋 금지, Settings 에서 key/value 관리,
`external_secrets_path` 로 리포 바깥도 참조, 그리고 **클로드 모델에게 값을 노출하지
않으면서** 하네스가 그 값을 쓸 수 있게.

마지막 요구는 이 하네스 안에서 보장할 수 없고, 그 사실을 먼저 적는다. 이 세션의
모델은 사용자와 **같은 OS 계정으로 셸을 돈다** — `cat` 을 실행할 수 있는 주체가 곧
모델이다. "모델은 못 본다"고 적으면 거짓말이 되고, 거짓 안전은 없는 안전보다 나쁘다.

그래서 이 파일이 지키는 것은 **사고로 새는 길**이다: 목록에 값이 안 나오고, argv 에
안 남고, 명령 출력에서 지워지고, 커밋에 못 들어간다. 작정하고 읽는 세션은 못 막는다.

실행: python3 tests/ secret_store
"""
import os
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

VALUE = "sk-not-a-real-token-4f2b9c"


class SecretStore(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9sec-")
        self.ext = tempfile.mkdtemp(prefix="s9secext-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                    "S9_USER": "alice"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "alice")

    def cli(self, *argv, inp=None, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=30, input=inp,
                           stdin=None if inp is not None else subprocess.DEVNULL)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def secret_path(self, key):
        return os.path.join(self.root, "users", "alice", "secrets", key)

    def set_external_path(self):
        # 비밀 위치 키는 추적되지 않는 자리(local.json)에만 산다
        # (REQ-20260902-031) — settings.json 에 적으면 user_config 가
        # 읽지 않는다. 원격이 밀어 넣을 수 있는 칸에 두지 않기 위해서다.
        cfg = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(cfg, exist_ok=True)
        import json
        p = os.path.join(cfg, "local.json")
        d = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        d["external_secrets_path"] = self.ext
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f)

    # N1. stdin 으로 받아 저장하고 권한은 0600 — argv 로 받으면 ps·기록에 남는다
    def test_n1_set_from_stdin_mode_0600(self):
        self.cli("secret", "set", "TOKEN", inp=VALUE)
        p = self.secret_path("TOKEN")
        self.assertTrue(os.path.exists(p), p)
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), VALUE)
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)

    # N2. 목록은 키만 — 값은 절대 안 찍는다
    def test_n2_ls_keys_only(self):
        self.cli("secret", "set", "TOKEN", inp=VALUE)
        out = self.cli("secret", "ls")
        self.assertIn("TOKEN", out)
        self.assertNotIn(VALUE, out)

    # N3. get 은 값을 낸다 (명령 치환용)
    def test_n3_get_returns_value(self):
        self.cli("secret", "set", "TOKEN", inp=VALUE)
        self.assertIn(VALUE, self.cli("secret", "get", "TOKEN"))

    # N4. 외부 경로에만 있는 키도 잡힌다
    def test_n4_external_visible(self):
        self.set_external_path()
        with open(os.path.join(self.ext, "EXTKEY"), "w", encoding="utf-8") as f:
            f.write("ext-value-1")
        out = self.cli("secret", "ls")
        self.assertIn("EXTKEY", out)
        self.assertNotIn("ext-value-1", out)
        self.assertIn("ext-value-1", self.cli("secret", "get", "EXTKEY"))

    # N5. run 이 자리표시자를 실행 시점에 바꾼다
    def test_n5_run_substitutes(self):
        self.cli("secret", "set", "TOKEN", inp=VALUE)
        out = self.cli("secret", "run", "--", "sh", "-c",
                       "test '{{secret:TOKEN}}' = '" + VALUE + "' && echo MATCH")
        self.assertIn("MATCH", out)

    # B1. 같은 키가 양쪽에 있으면 internal 이 이긴다
    def test_b1_internal_wins(self):
        self.set_external_path()
        with open(os.path.join(self.ext, "DUP"), "w", encoding="utf-8") as f:
            f.write("from-external")
        self.cli("secret", "set", "DUP", inp="from-internal")
        self.assertIn("from-internal", self.cli("secret", "get", "DUP"))

    # B2. 외부 경로가 없어도 내부는 그대로 동작한다
    def test_b2_missing_external_is_quiet(self):
        cfgdir = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(cfgdir, exist_ok=True)
        import json
        with open(os.path.join(cfgdir, "settings.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"external_secrets_path": "/nope/does/not/exist"}, f)
        self.cli("secret", "set", "TOKEN", inp=VALUE)
        self.assertIn("TOKEN", self.cli("secret", "ls"))

    # B3. 키 이름이 경로를 벗어나면 거부한다
    def test_b3_key_must_be_a_name(self):
        for bad in ("../escape", "a/b", ""):
            self.cli("secret", "set", bad, inp=VALUE, expect=1)

    # F1. 명령이 실수로 값을 찍어도 출력에서 지운다
    def test_f1_run_redacts_output(self):
        self.cli("secret", "set", "TOKEN", inp=VALUE)
        out = self.cli("secret", "run", "--", "sh", "-c",
                       "echo leaked={{secret:TOKEN}}")
        self.assertNotIn(VALUE, out)
        self.assertIn("leaked=", out)


class CommitGuard(unittest.TestCase):
    """F2·F3·R2 — 비밀이 커밋으로 새지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9secg-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                    "S9_USER": "alice"}
        self.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=self.env,
                       timeout=20)
        subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                       env=self.env, timeout=20)

    def leak(self, staged_paths, blob=""):
        from importlib import machinery, util
        spec = util.spec_from_loader(
            "s9_secguard", machinery.SourceFileLoader(
                "s9_secguard", os.path.join(HERE, "..", "bin", "s9")))
        m = util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.secret_leak(staged_paths, blob, root=self.root)

    def _put(self, key, val):
        d = os.path.join(self.root, "users", "alice", "secrets")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, key), "w", encoding="utf-8") as f:
            f.write(val)

    # F2. 비밀 경로가 스테이지에 있으면 잡는다
    def test_f2_path_staged(self):
        self._put("TOKEN", VALUE)
        hits = self.leak(["users/alice/secrets/TOKEN"], "")
        self.assertTrue(hits, hits)

    # F3. 경로를 피해 다른 파일에 값만 붙여 넣어도 잡는다 — 실제 유출 경로다
    def test_f3_value_in_content(self):
        self._put("TOKEN", VALUE)
        hits = self.leak(["docs/note.md"], f"api key: {VALUE}\n")
        self.assertTrue(hits, hits)

    # R2. 비밀이 하나도 없으면 아무것도 막지 않는다
    def test_r2_no_secrets_no_block(self):
        self.assertFalse(self.leak(["docs/note.md"], "평범한 내용"))

    # R2b. 짧은 값은 내용 검사에서 제외한다 — "a" 같은 비밀이 온 diff 를 막는다
    def test_r2b_short_values_not_content_matched(self):
        self._put("TINY", "ab")
        self.assertFalse(self.leak(["docs/note.md"], "ab 라는 흔한 글자"))


class InstanceIgnore(unittest.TestCase):
    """R1 — 인스턴스 리포는 users/ 를 track 한다. secrets 는 거기서 빠져야 한다."""

    def test_r1_instance_gitignore_excludes_secrets(self):
        src = open(os.path.join(HERE, "..", "bin", "s9"),
                   encoding="utf-8").read()
        i = src.index("INSTANCE_TRACK_GITIGNORE")
        block = src[i:i + 800]
        self.assertIn("users/*/secrets", block, block[:400])


if __name__ == "__main__":
    unittest.main()
