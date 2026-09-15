"""프로필의 성·이름과 full name 을 짓는 한 자리 (REQ-20260915-029-62x6 · -030-62x6).

주인 지시 2026-09-15 16:04: 「사용자의 id 외에 이름이 필요하다… 성과 이름 항목을
만들어 주고, 최초 설치할 때 id와 성 이름을 받은 후에 카드에서 이름으로 보여줘.」

계약은 셋이다.
- profile.md 에 `first_name`(이름)·`last_name`(성) 이 선다. 사람이 직접 쓴
  `display` 가 있으면 그것이 이긴다.
- full name 을 짓는 자리는 **함수 하나**(`user_full_name`) — 호출부가 제 손으로
  잇지 못하게 한다. 이름이 하나도 없으면 빈 문자열이고, id 로 재시도를 미루는 것은
  부르는 쪽의 몫이다.
- 첫 실행은 id 를 받은 **뒤** 성·이름을 묻는다(`first_run_person_name`). 비우면
  건너뛰고 등록은 그대로 간다 — 이름이 없다고 등록이 끊기면 안 된다.

실행: python3 tests/test_user_full_name.py
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

from portpool import free_port, wait_server  # noqa: E402


class FullNamePure(unittest.TestCase):
    """순수 함수 — 프로세스를 띄우지 않는다 (모듈 로드 1회)."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_loader(
            "s9_ufn", importlib.machinery.SourceFileLoader("s9_ufn", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    # S2. 사람이 직접 쓴 display 가 성·이름을 이긴다
    def test_s2_display_wins(self):
        self.assertEqual(self.m.user_full_name(
            {"display": "타치코마", "first_name": "길동", "last_name": "홍"}),
            "타치코마")

    # S3. 한글 이름은 성+이름을 공백 없이 — 그 사람의 말 순서다
    def test_s3_korean_order(self):
        self.assertEqual(
            self.m.user_full_name({"first_name": "길동", "last_name": "홍"}),
            "홍길동")

    # S4. 로마자 이름은 이름+공백+성
    def test_s4_latin_order(self):
        self.assertEqual(
            self.m.user_full_name({"first_name": "Gildong", "last_name": "Hong"}),
            "Gildong Hong")

    # S5. 한쪽만 있으면 그 한쪽 / 하나도 없으면 빈 문자열 (id 로 잇지 않는다)
    def test_s5_partial_and_empty(self):
        self.assertEqual(self.m.user_full_name({"first_name": "길동"}), "길동")
        self.assertEqual(self.m.user_full_name({"last_name": "Hong"}), "Hong")
        self.assertEqual(self.m.user_full_name({}), "")
        self.assertEqual(self.m.user_full_name({"name": "nicehugepark"}), "")
        self.assertEqual(self.m.user_full_name(None), "")

    # S7. 줄바꿈·제어문자·길이 — frontmatter 를 훼손할 값은 경계에서 막는다
    def test_s7_person_name_validation(self):
        ok = self.m.person_name_ok
        self.assertTrue(ok("홍"))
        self.assertTrue(ok("van der Berg"))
        self.assertTrue(ok(""))            # 비움은 허용 — 이름은 선택이다
        self.assertFalse(ok("홍\n길동"))
        self.assertFalse(ok("a\tb"))
        self.assertFalse(ok("x" * 65))

    # S10. 회귀: 이름 칸이 없던 예전 프로필도 그대로 읽힌다
    def test_s10_legacy_profile(self):
        self.assertEqual(self.m.user_full_name({"name": "alice", "display": "앨리스"}),
                         "앨리스")

    # ── 030: 첫 실행이 이름을 묻는다 ────────────────────────────────────────
    # S1. id 뒤에 성·이름을 묻고 답한 값이 (이름, 성) 으로 돌아온다
    def test_030_s1_asks_after_id(self):
        asked = []

        def ask(q):
            asked.append(q)
            return "홍" if len(asked) == 1 else "길동"

        self.assertEqual(self.m.first_run_person_name(ask), ("길동", "홍"))
        self.assertEqual(len(asked), 2)

    # S2. 비우면 건너뛴다 — 등록은 그대로 간다
    def test_030_s2_blank_skips(self):
        self.assertEqual(self.m.first_run_person_name(lambda q: ""), ("", ""))
        self.assertEqual(self.m.first_run_person_name(lambda q: "   "), ("", ""))

    # S3. 한글은 한글 그대로 (id 규칙은 id 에만 적용된다)
    def test_030_s3_hangul_kept(self):
        answers = iter(["박", "성진"])          # 성 → 이름 순으로 묻는다
        first, last = self.m.first_run_person_name(lambda _q: next(answers))
        self.assertEqual((first, last), ("성진", "박"))
        self.assertFalse(self.m.user_name_ok("성진"))   # id 로는 여전히 못 쓴다

    # S5. 이미 불릴 이름이 있는 사람(attach)에게는 다시 묻지 않는다
    def test_030_s5_known_person_not_asked(self):
        def never(_q):
            raise AssertionError("이미 이름이 있는 사람에게 다시 물었다")

        self.assertEqual(
            self.m.first_run_person_name(never, profile={"display": "타치코마"}),
            ("", ""))
        self.assertEqual(
            self.m.first_run_person_name(never,
                                         profile={"first_name": "길동",
                                                  "last_name": "홍"}),
            ("", ""))

    # S4. 못 쓸 값은 그 자리에서 되묻고, 끝내 못 정하면 빈 값
    def test_030_s4_retries_then_gives_up(self):
        said = []
        self.assertEqual(
            self.m.first_run_person_name(lambda q: "홍\n길동", out=said.append,
                                         tries=2),
            ("", ""))
        self.assertTrue(said, "못 쓸 이름이면 까닭을 말해야 한다")


class ProfileNamesIO(unittest.TestCase):
    """프로필 쓰기·읽기와 API — CLI 1회 + 서버 1회 (클래스당)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9name-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "NAMEBOX",
                   "S9_USER": "alice", "S9_REWORK_WATCH": "off"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "alice", "--first-name", "길동",
                "--last-name", "홍")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        try:
            cls.srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.srv.kill()

    @classmethod
    def cli(cls, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=20, stdin=subprocess.DEVNULL)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                 f"{r.stdout}{r.stderr}")
        return r

    def profile(self, name):
        with open(os.path.join(self.tmp, "users", name, "profile.md"),
                  encoding="utf-8") as f:
            return f.read()

    def api(self, path, payload=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = (urllib.request.Request(
            url, data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"})
            if payload is not None else url)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                return json.loads(e.read().decode())
            except (ConnectionError, urllib.error.URLError):
                if attempt == 2:
                    raise
                time.sleep(0.3)

    # S1. add 가 성·이름을 프로필에 세운다
    def test_s1_add_writes_names(self):
        txt = self.profile("alice")
        self.assertRegex(txt, r"(?m)^first_name: 길동$")
        self.assertRegex(txt, r"(?m)^last_name: 홍$")

    # S6. update 로 고칠 수 있고 변경이 Notes 에 남는다
    def test_s6_update_changes_and_audits(self):
        self.cli("user", "add", "bob")
        self.cli("user", "update", "bob", "--first-name", "Gildong",
                 "--last-name", "Hong")
        txt = self.profile("bob")
        self.assertRegex(txt, r"(?m)^first_name: Gildong$")
        self.assertRegex(txt, r"(?m)^last_name: Hong$")
        self.assertTrue(re.search(r"updated .*first_name", txt), txt)

    # S7b. 경계는 CLI 에서도 선다 — 줄바꿈이 든 이름은 거부
    def test_s7b_cli_rejects_bad_name(self):
        r = self.cli("user", "update", "bob", "--first-name", "a\nb", expect=None)
        self.assertNotEqual(r.returncode, 0)

    # S8. /api/whoami 가 {user, first_name, last_name, full} 을 함께 싣는다
    def test_s8_whoami_carries_names(self):
        d = self.api("/api/whoami")
        self.assertEqual(d["user"], "alice")
        self.assertEqual(d["first_name"], "길동")
        self.assertEqual(d["last_name"], "홍")
        self.assertEqual(d["full"], "홍길동")

    # S9. /api/users 의 각 항목도 같은 세 칸을 싣는다
    def test_s9_users_api_carries_names(self):
        d = self.api("/api/users")
        row = {u["name"]: u for u in d["users"]}["alice"]
        self.assertEqual(row["first_name"], "길동")
        self.assertEqual(row["last_name"], "홍")
        self.assertEqual(row["full"], "홍길동")

    # S9c. 카드가 id 대신 세울 이름 표 — /api/boot 의 names
    def test_s9c_boot_names_table(self):
        d = self.api("/api/boot")
        self.assertEqual(d["names"].get("alice"), "홍길동")
        self.assertEqual(d["whoami"]["full"], "홍길동")
        # 이름이 없는 사람은 표에 없다 — 화면은 그때 id 를 그대로 쓴다
        self.cli("user", "add", "dave", expect=None)
        self.assertNotIn("dave", self.api("/api/boot")["names"])

    # S9b. 화면에서 고친다 — /api/user/update 가 성·이름을 받는다
    def test_s9b_update_api(self):
        self.cli("user", "add", "carol")
        res = self.api("/api/user/update",
                       {"name": "carol", "first_name": "영희", "last_name": "김"})
        self.assertTrue(res.get("ok"), res)
        row = {u["name"]: u for u in self.api("/api/users")["users"]}["carol"]
        self.assertEqual(row["full"], "김영희")


if __name__ == "__main__":
    unittest.main(verbosity=2)
