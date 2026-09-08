"""프로젝트 경계의 두 자리 — 이동 권한과 가시성 (REQ-20260908-032 · -026).

**032 (이동)**: `do_set` 의 project 이동이 새 프로젝트의 contribute 만 보고 옛
프로젝트를 안 봤다. 그래서 B 의 contributor 가 A 의 문서를 B 로 끌어와 `doc_visible`
의 멤버 갈래를 통과시켜 **열람을 스스로 부여**했다(confused deputy). 이제 옛
프로젝트가 등록돼 있으면 그쪽 contribute(또는 문서를 만든 사람·시스템 admin)도
요구한다.

**026 (가시성)**: 프로젝트가 붙은 문서를 활성 멤버에게만 보여 주어, 두 vault 가
만나 같은 slug 가 충돌하고 사람이 한쪽을 택하면 진 쪽 사용자의 화면에서 **자기가
쓴 문서가 사라졌다**. 이제 만든 사람은 비멤버여도 본다 — 다만 셋을 닫는다:
creator **원 필드만**(담당 user 폴백을 쓰면 비멤버가 옛 문서를 자기에게 assign 해
열람을 스스로 부여한다) · PRJ 문서는 예외 밖 · 보임 ≠ 권한.

격리: S9_ROOT=mktemp. 실행: python3 tests/ project_access_gate
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
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9")
MACHINE = "TESTMACH"
RE_ID = re.compile(r"REQ-\d{8}-\d{3,}(?:-[0-9a-z]{4})?")

from portpool import free_port, wait_server  # noqa: E402

ROOT_U, ALICE, BOB, CAROL, MAL, VIC = "root", "alice", "bob", "carol", "mal", "vic"


class ProjectAccessGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9pag-")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": MACHINE,
                   "S9_REWORK_WATCH": "off"}
        for k in ("S9_SESSION", "S9_USER", "S9_SYNC"):
            cls.env.pop(k, None)
        cli = cls._cli
        cli("init")
        cli("user", "add", ROOT_U, "--role", "admin")
        for u in (ALICE, BOB, CAROL, MAL):
            cli("user", "add", u, user=ROOT_U)
        cli("user", "add", VIC, "--role", "viewer", user=ROOT_U)
        # pa = alice 의 프로젝트, pb = bob 의 프로젝트
        cli("project", "add", "pa", "--name", "PA", "--user", ALICE)
        cli("project", "add", "pb", "--name", "PB", "--user", BOB)
        cli("project", "member", "pa", "add", CAROL, "--role", "contributor",
            "--user", ALICE)
        cli("project", "member", "pa", "add", VIC, "--role", "contributor",
            "--user", ALICE)

        def mk(title, user=ALICE, project="pa"):
            r = cli("new", "request", "--title", title, "--summary", "s",
                    "--goal", "g", "--body", "b", "--project", project, user=user)
            return RE_ID.search(r.stdout).group(0)

        cls.d_attack = mk("attack target")     # 032 S2·S6 · 026 S1
        cls.d_move = mk("legit move")          # 032 S1
        cls.d_ghost = mk("ghost project")      # 032 S3
        cls.d_creator = mk("creator move")     # 032 S4
        cls.d_admin = mk("admin move")         # 032 S5
        cls.d_old = mk("old doc")              # 026 S2 (creator 필드 없는 옛 문서)
        # 026 S4: 관찰 계정(viewer)은 문서를 새로 쓰지 못한다 — 그래서 vic 이
        # 관찰 계정이 되기 **전에** 쓴 문서를 흉내 낸다(creator 원 필드 = vic).
        cls.d_vic = mk("viewer doc")
        # 옛 문서 흉내: creator 필드를 지우고 담당을 mal 로 넘긴다.
        # mal 은 pa 의 멤버였을 때 담당을 넘겨받고, 그 뒤 프로젝트에서 빠진다 —
        # 담당(user)만 남는다. creator 필드까지 없는 옛 문서라면 doc_creator() 의
        # user 폴백이 곧 「만든 사람」이 되어 mal 이 열람을 되찾는다(막아야 할 자리).
        cli("project", "member", "pa", "add", MAL, "--role", "contributor",
            "--user", ALICE)
        cli("assign", cls.d_old, MAL, "--why", "handoff", user=ALICE)
        cli("project", "member", "pa", "rm", MAL, "--user", ALICE)
        cls._strip_creator(cls.d_old)
        # 미등록 프로젝트 흉내: 등록된 적 없는 slug 를 문서에 박는다.
        cls._set_front(cls.d_ghost, "project", "ghostproj")
        cls._set_front(cls.d_vic, "creator", VIC)
        # 두 vault 가 만난 뒤의 자리를 만든다: alice·vic 은 자기가 쓴 문서를
        # pa 에 남긴 채 멤버에서 빠진다(owner 를 root 에 넘기고 나온다).
        cli("project", "member", "pa", "add", ROOT_U, "--role", "owner",
            "--user", ALICE)
        cli("project", "member", "pa", "rm", ALICE, "--user", ROOT_U)
        cli("project", "member", "pa", "rm", VIC, "--user", ROOT_U)
        cli("index", "rebuild", user=ROOT_U)

    @classmethod
    def _cli(cls, *argv, user=None, expect=0):
        e = dict(cls.env)
        if user:
            e["S9_USER"] = user
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=e, timeout=30, stdin=subprocess.DEVNULL)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                 f"{r.stdout}{r.stderr}")
        return r

    @classmethod
    def _path(cls, doc_id):
        for base, _dirs, files in os.walk(os.path.join(cls.root, "vault")):
            for f in files:
                if f.startswith(doc_id):
                    return os.path.join(base, f)
        raise AssertionError(f"문서 파일을 못 찾았다: {doc_id}")

    @classmethod
    def _strip_creator(cls, doc_id):
        p = cls._path(doc_id)
        with open(p, encoding="utf-8") as f:
            txt = f.read()
        out = [l for l in txt.splitlines(True) if not l.startswith("creator:")]
        with open(p, "w", encoding="utf-8") as f:
            f.write("".join(out))

    @classmethod
    def _set_front(cls, doc_id, key, val):
        p = cls._path(doc_id)
        with open(p, encoding="utf-8") as f:
            lines = f.read().splitlines(True)
        for i, l in enumerate(lines):
            if l.startswith(key + ":"):
                lines[i] = f"{key}: {val}\n"
                break
        with open(p, "w", encoding="utf-8") as f:
            f.write("".join(lines))

    @classmethod
    def mod(cls):
        """s9 모듈을 이 시험의 vault 로 적재 — doc_access 를 직접 부른다."""
        if getattr(cls, "_mod", None) is None:
            keep = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE", "S9_USER")}
            os.environ["S9_ROOT"] = cls.root
            os.environ["S9_MACHINE"] = MACHINE
            os.environ.pop("S9_USER", None)
            try:
                loader = importlib.machinery.SourceFileLoader("s9pagmod", S9)
                spec = importlib.util.spec_from_loader("s9pagmod", loader)
                m = importlib.util.module_from_spec(spec)
                loader.exec_module(m)
                cls._mod = m
            finally:
                for k, v in keep.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        return cls._mod

    def meta(self, doc_id):
        m = self.mod()
        return m.read_doc(m.locate(doc_id))[0]

    def project_of(self, doc_id):
        return (self.meta(doc_id).get("project") or "").strip()

    @classmethod
    def tearDownClass(cls):
        for p in getattr(cls, "srvs", []):
            p.terminate()
        for p in getattr(cls, "srvs", []):
            p.wait(timeout=5)
        shutil.rmtree(cls.root, ignore_errors=True)

    # ── 032. 이동 권한 ──────────────────────────────────────────────────
    def test_move_gate(self):
        cli = self._cli
        with self.subTest("S2 공격: pb 의 contributor 가 pa 의 문서를 pb 로"):
            r = cli("set", self.d_attack, "--project", "pb", user=BOB, expect=None)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("pa", r.stdout + r.stderr)
            self.assertEqual(self.project_of(self.d_attack), "pa")

        with self.subTest("S6 공격: 프로젝트 없음으로 빼는 것도 옛 권한을 요구"):
            r = cli("set", self.d_attack, "--project", "", user=BOB, expect=None)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self.project_of(self.d_attack), "pa")

        with self.subTest("S7 회귀: 새 프로젝트 권한 부족은 그대로 거절"):
            # alice 는 이 문서를 만든 사람이라 옛 쪽 검사는 지나가지만,
            # pb 의 멤버가 아니라 새 쪽에서 막힌다 — 기존 거절 그대로.
            r = cli("set", self.d_attack, "--project", "pb", user=ALICE, expect=None)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("pb", r.stdout + r.stderr)
            self.assertEqual(self.project_of(self.d_attack), "pa")

        with self.subTest("S1 정상: 양쪽 다 contributor 면 옮겨진다"):
            cli("project", "member", "pb", "add", CAROL, "--role", "contributor",
                "--user", BOB)
            cli("set", self.d_move, "--project", "pb", user=CAROL)
            self.assertEqual(self.project_of(self.d_move), "pb")

        with self.subTest("S3 경계: 옛 프로젝트가 미등록이면 비강제"):
            cli("set", self.d_ghost, "--project", "pb", user=BOB)
            self.assertEqual(self.project_of(self.d_ghost), "pb")

        with self.subTest("S5 경계: 시스템 admin 은 우회"):
            cli("set", self.d_admin, "--project", "pb", user=ROOT_U)
            self.assertEqual(self.project_of(self.d_admin), "pb")

        with self.subTest("S4 경계: 만든 사람은 비멤버여도 자기 문서를 옮긴다"):
            cli("set", self.d_creator, "--project", "", user=ALICE)
            self.assertEqual(self.project_of(self.d_creator), "")


    # ── 026. 가시성 ─────────────────────────────────────────────────────
    def test_creator_visibility(self):
        m = self.mod()
        attack = self.meta(self.d_attack)

        with self.subTest("S1 비멤버 creator 는 보인다"):
            self.assertEqual(m.doc_access(attack, ALICE), "creator-outside")
            self.assertTrue(m.doc_visible(attack, ALICE))

        with self.subTest("S2 assign 으로 받은 옛 문서는 안 보인다"):
            old = self.meta(self.d_old)
            self.assertEqual(old.get("user"), MAL)
            self.assertNotIn("creator", old)
            self.assertFalse(m.doc_visible(old, MAL))
            # catalog row(표시용 creator 는 user 폴백)로도 같은 답이어야 한다
            row = [r for r in m.load_catalog() if r["id"] == self.d_old][0]
            self.assertEqual(row.get("creator"), MAL)   # 표시값은 폴백
            self.assertFalse(m.doc_visible(row, MAL))   # 판정은 원 필드

        with self.subTest("S3 PRJ 문서에는 예외가 없다"):
            prj = [r for r in m.all_projects() if r.get("slug") == "pa"][0]
            self.assertEqual(prj.get("creator"), ALICE)
            self.assertFalse(m.doc_visible(prj, ALICE))

        with self.subTest("S4 viewer 는 observe 가 만료돼도 자기 문서를 본다"):
            self._cli("user", "config", VIC, "observe", "pa", user=ROOT_U)
            self._cli("user", "config", VIC, "observe_until", "2020-01-01",
                     user=ROOT_U)
            vic_doc = self.meta(self.d_vic)
            self.assertEqual(vic_doc.get("creator"), VIC)
            self.assertFalse(m.doc_visible(attack, VIC))     # 남의 문서는 안 보인다
            self.assertTrue(m.doc_visible(vic_doc, VIC))     # 자기 문서는 보인다

        with self.subTest("S5 회귀: 비멤버·비creator 는 안 보이고 멤버·admin 은 본다"):
            self.assertFalse(m.doc_visible(attack, MAL))
            self.assertTrue(m.doc_visible(attack, CAROL))    # pa contributor
            self.assertEqual(m.doc_access(attack, CAROL), "member")
            self.assertTrue(m.doc_visible(attack, ROOT_U))
            self.assertEqual(m.doc_access(attack, ROOT_U), "admin")

        with self.subTest("S6 보임 ≠ 권한: 보여도 contribute 는 여전히 없다"):
            self.assertTrue(m.doc_visible(attack, ALICE))
            self.assertFalse(m.project_can("pa", ALICE, "contribute"))
            self.assertEqual(m.project_role("pa", ALICE), "")

    # ── S7. 서버가 까닭을 실어 보낸다 ───────────────────────────────────
    def test_api_marks_outside_project(self):
        port = free_port()
        type(self).srvs = [subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(port)],
            env={**self.env, "S9_USER": ALICE},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
        wait_server(port)

        def get(doc_id):
            url = (f"http://127.0.0.1:{port}/api/doc?"
                   + urllib.parse.urlencode({"id": doc_id}))
            try:
                with urllib.request.urlopen(url, timeout=10) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode())

        code, d = get(self.d_attack)
        self.assertEqual(code, 200, d)
        self.assertEqual(d.get("outside_project"), "pa")
        # 프로젝트 경계 밖에서 보이는 문서(미등록 프로젝트 = 정책 부재)에는
        # 표시가 붙지 않는다 — 그 사람은 비멤버라서 보는 것이 아니다.
        code, d2 = get(self.d_ghost)
        self.assertEqual(code, 200, d2)
        self.assertNotIn("outside_project", d2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
