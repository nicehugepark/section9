"""머신 지문 고정과 등록부 (REQ-20260902-027).

지문(uid 접미 4자)은 첫 사용 때 users/<me>/config/local.json 에 고정되고,
users/<me>/machines.json(추적) 에 {fp: {hostname, first_seen}} 로 등록된다.
pull 뒤 같은 지문을 다른 hostname 이 잡고 있으면 `s9 index rebuild` 가 경고하고
`s9 new` 가 발번을 거부한다. S9_ORIGIN 이 해제다. 레거시(접미 없음)는 손대지 않는다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ machine_fp
"""
import glob
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOST = "fp-host-a"


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMachineFp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9fp-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": HOST,
                   "S9_USER": "tester"}
        for k in ("S9_SESSION", "S9_ORIGIN"):
            cls.env.pop(k, None)
        cls.cli("init")
        cls.cli("user", "add", "tester")
        cls._saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(cls.env)
        cls.m = _load("s9_fp_mod", S9)
        cls.local = os.path.join(cls.tmp, "users", "tester", "config", "local.json")
        cls.reg = os.path.join(cls.tmp, "users", "tester", "machines.json")

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls._saved)

    @classmethod
    def cli(cls, *argv, env=None, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env or cls.env, timeout=20,
                           stdin=subprocess.DEVNULL)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                 f"{r.stdout}{r.stderr}")
        return r

    # 시험마다 같은 출발점: 고정 없음·등록부 없음·재정의 없음
    def setUp(self):
        for p in (self.local, self.reg):
            if os.path.exists(p):
                os.remove(p)
        os.environ.pop("S9_ORIGIN", None)
        os.environ["S9_MACHINE"] = HOST

    def _rj(self, p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def _registry(self, fp, host):
        with open(self.reg, "w", encoding="utf-8") as f:
            json.dump({fp: {"hostname": host, "first_seen": "2026-09-01T00:00:00+09:00"}}, f)

    def _vault_files(self):
        return sorted(glob.glob(os.path.join(self.tmp, "vault", "**", "*.md"),
                                recursive=True))

    # S1. 고정 — 첫 호출이 계산값을 local.json 에 적고, hostname 이 바뀌어도 그 값
    def test_s1_pin_on_first_use(self):
        m = self.m
        computed = m._machine_fp_compute()
        self.assertFalse(os.path.exists(self.local))
        self.assertEqual(m.machine_fp(), computed)
        self.assertEqual(self._rj(self.local).get("machine_fp"), computed)
        os.environ["S9_MACHINE"] = "fp-host-renamed"
        self.assertNotEqual(m._machine_fp_compute(), computed)   # 계산값은 바뀌는데
        self.assertEqual(m.machine_fp(), computed)                # 고정값은 그대로

    # S2. 우선순위: local.json > 계산값, S9_ORIGIN > local.json
    def test_s2_priority(self):
        m = self.m
        os.makedirs(os.path.dirname(self.local), exist_ok=True)
        with open(self.local, "w", encoding="utf-8") as f:
            json.dump({"machine_fp": "q1q1"}, f)
        self.assertNotEqual(m._machine_fp_compute(), "q1q1")
        self.assertEqual(m.machine_fp(), "q1q1")
        os.environ["S9_ORIGIN"] = "ZZ-9"
        self.assertEqual(m.machine_fp(), "zz9")
        self.assertEqual(self._rj(self.local).get("machine_fp"), "q1q1")  # 덮지 않는다

    # S3. 등록부 — {fp: {hostname, first_seen}}, 두 번 불러도 first_seen 불변
    def test_s3_registry_idempotent(self):
        m = self.m
        fp = m.machine_fp()
        reg = self._rj(self.reg)
        self.assertEqual(reg[fp]["hostname"], HOST)
        first = reg[fp]["first_seen"]
        self.assertTrue(first)
        self.assertEqual(m.machine_fp(), fp)
        self.assertEqual(m.machine_register(fp), reg[fp])
        self.assertEqual(self._rj(self.reg)[fp]["first_seen"], first)
        self.assertEqual(list(self._rj(self.reg)), [fp])

    # S4. 충돌 검지 — 다른 hostname 이 내 지문을 잡고 있으면 함수가 잡고 rebuild 가 경고
    def test_s4_conflict_detected_and_rebuild_warns(self):
        m = self.m
        self.assertIsNone(m.machine_fp_conflict())
        fp = m.machine_fp()
        self._registry(fp, "other-box")
        self.assertEqual(m.machine_fp_conflict(), (fp, "other-box"))
        # 등록부를 덮어쓰지 않는다 — 충돌은 사람이 볼 수 있어야 한다
        m.machine_fp()
        self.assertEqual(self._rj(self.reg)[fp]["hostname"], "other-box")
        r = self.cli("index", "rebuild")               # rc 0 — pull 을 막지 않는다
        self.assertIn("지문 충돌", r.stderr)
        self.assertIn("S9_ORIGIN", r.stderr)
        self.assertIn("other-box", r.stderr)
        # 충돌이 없으면 조용하다
        self._registry(fp, HOST)
        self.assertNotIn("지문 충돌", self.cli("index", "rebuild").stderr)

    # S5. 거부 — 충돌 상태의 s9 new 는 실패하고 파일을 만들지 않는다
    def test_s5_new_refused_under_conflict(self):
        fp = self.m.machine_fp()
        self._registry(fp, "other-box")
        before = self._vault_files()
        r = self.cli("new", "request", "--title", "충돌 중 발번", "--summary", "s",
                     "--size", "S", "--body", "b", expect=None)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("지문 충돌", r.stderr + r.stdout)
        self.assertIn("S9_ORIGIN", r.stderr + r.stdout)
        self.assertEqual(self._vault_files(), before)

    # S6. 해제 — S9_ORIGIN 으로 같은 머신이 다른 지문으로 발번한다
    def test_s6_origin_releases(self):
        fp = self.m.machine_fp()
        self._registry(fp, "other-box")
        env = {**self.env, "S9_ORIGIN": "zzzz"}
        r = self.cli("new", "request", "--title", "해제 후 발번", "--summary", "s",
                     "--size", "S", "--body", "b", env=env)
        self.assertRegex(r.stdout.split()[0], r"^REQ-\d{8}-\d{3}-zzzz$")
        self.assertNotIn("지문 충돌", self.cli("index", "rebuild", env=env).stderr)

    # S7. 레거시·격리 — 고정·등록은 vault 를 만지지 않고, 접미 없는 파일은 그대로다
    def test_s7_legacy_untouched(self):
        m = self.m
        import datetime
        ymd = datetime.date.today().strftime("%Y%m%d")
        d = os.path.join(self.tmp, "vault", "requests", ymd[:4], ymd[4:6])
        os.makedirs(d, exist_ok=True)
        legacy = os.path.join(d, f"REQ-{ymd}-007.md")
        body = "---\nid: REQ-%s-007\ntype: request\n---\n" % ymd
        with open(legacy, "w", encoding="utf-8") as f:
            f.write(body)
        digest = hashlib.sha1(body.encode()).hexdigest()
        before = self._vault_files()
        m.machine_fp()
        m.machine_fp_conflict()
        self.assertEqual(self._vault_files(), before)
        with open(legacy, "rb") as f:
            self.assertEqual(hashlib.sha1(f.read()).hexdigest(), digest)
        # 접미 없는 순번도 센다 (기존 next_id 계약) — 007 다음은 008
        self.assertTrue(m.next_id("REQ", "requests").startswith(f"REQ-{ymd}-008-"))
        os.remove(legacy)

    # S8. 미등록 사용자 — 고정·등록 없이 계산값만, 디렉터리도 만들지 않는다
    def test_s8_unregistered_user_no_side_effects(self):
        m = self.m
        os.environ["S9_USER"] = "ghost"
        try:
            self.assertEqual(m.machine_fp(), m._machine_fp_compute())
            self.assertIsNone(m.machine_fp_conflict())
            self.assertFalse(os.path.exists(os.path.join(self.tmp, "users", "ghost")))
        finally:
            os.environ["S9_USER"] = "tester"
        self.assertFalse(os.path.exists(self.local))
        self.assertFalse(os.path.exists(self.reg))


if __name__ == "__main__":
    unittest.main()
