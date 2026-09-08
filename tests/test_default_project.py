"""설치는 프로젝트를 하나 갖고 시작한다 — 기본 프로젝트 (REQ-20260908-022).

`s9 init` 이 프로젝트가 0개일 때만 하나 만들고(멱등), 「어느 것이 기본인가」는
프로젝트 문서의 `is_default` 칸에 적힌다. 자동 귀속(resolve_project ④)은
「후보가 하나뿐이면」에서 **「지정된 기본 프로젝트」**로 옮겼다 — 그래야 프로젝트가
0개인 새 설치에서도, 둘째 프로젝트를 만든 뒤에도 같은 답이 나온다.

이름(slug·표시 이름)은 아직 판정 중이라 이 시험은 글자를 박지 않고 bin/s9.py 의
상수(DEFAULT_PROJECT_SLUG·DEFAULT_PROJECT_NAME)를 참조한다.

실행: python3 tests/ --local --no-reuse default_project
"""
import importlib.machinery
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HINT = "프로젝트 미정 — 후보:"


def _load_module():
    """상수·템플릿을 읽으려는 것뿐이라 한 번만 (S9_ROOT 에 의존하지 않는 값들)."""
    spec = importlib.util.spec_from_loader(
        "s9_defproj", importlib.machinery.SourceFileLoader("s9_defproj", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class DefaultProject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.mkdtemp(prefix="s9defproj-mod-")
        os.environ["S9_ROOT"] = cls.scratch
        try:
            cls.m = _load_module()
        finally:
            os.environ.pop("S9_ROOT", None)
        cls.SLUG = cls.m.DEFAULT_PROJECT_SLUG
        cls.NAME = cls.m.DEFAULT_PROJECT_NAME

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9defproj-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.base = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox"}
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_JOB_REQ", "S9_USER",
                  "S9_PROJECT"):
            self.base.pop(k, None)

    def cli(self, *argv, env=None, check=True):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env={**self.base, **(env or {})},
                           stdin=subprocess.DEVNULL, timeout=60)
        if check:
            self.assertEqual(r.returncode, 0, " ".join(argv) + "\n" + r.stdout + r.stderr)
        return r

    # ── 자 ──────────────────────────────────────────────────────────────
    def meta_of(self, path):
        text = open(path, encoding="utf-8").read()
        fm = text.split("---", 2)[1] if text.startswith("---") else ""
        out = {}
        for line in fm.splitlines():
            m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip("'\"")
        return out

    def proj_meta(self, slug):
        return self.meta_of(os.path.join(self.root, "vault", "projects", slug + ".md"))

    def new_req(self, *extra, env=None):
        r = self.cli("new", "request", "--title", "t", "--summary", "s",
                     "--size", "S", "--goal", "g", "--body", "b", *extra, env=env)
        rid = r.stdout.split()[0]
        hit = subprocess.run(["grep", "-rl", f"id: {rid}$",
                              os.path.join(self.root, "vault", "requests")],
                             capture_output=True, text=True)
        paths = [p for p in hit.stdout.splitlines() if p]
        self.assertEqual(len(paths), 1, hit.stdout + hit.stderr)
        return r, self.meta_of(paths[0])

    def unset_default(self):
        """기본 지정이 없던 옛 저장소를 만든다 — 그 판의 규칙(④')을 재기 위해."""
        path = os.path.join(self.root, "vault", "projects", self.SLUG + ".md")
        text = open(path, encoding="utf-8").read()
        text = "\n".join(l for l in text.splitlines() if not l.startswith("is_default:"))
        open(path, "w", encoding="utf-8").write(text + "\n")

    # ── S1. 빈 vault 에서 init 하면 프로젝트가 하나 선다 ─────────────────
    def test_s1_init_creates_default_project(self):
        r = self.cli("init")
        self.assertIn(self.SLUG, r.stdout)
        meta = self.proj_meta(self.SLUG)
        self.assertEqual(meta["slug"], self.SLUG)
        self.assertEqual(meta["title"], self.NAME)
        self.assertEqual((meta.get("is_default") or "").lower(), "true")
        # 순서 제약: 사용자 등록 → 프로젝트 생성 (owner 가 users/ 에 없으면
        # contribute 가 거짓이라 프로젝트는 서 있는데 문서가 하나도 안 붙는다)
        owner = re.search(r"owner", open(
            os.path.join(self.root, "vault", "projects", self.SLUG + ".md"),
            encoding="utf-8").read())
        self.assertTrue(owner)
        self.assertTrue(os.listdir(os.path.join(self.root, "users")))
        self.assertTrue(os.path.exists(os.path.join(
            self.root, "projects", self.SLUG, "CONTEXT.md")))
        # 설치가 먼저 등록해 둔 이름을 그 사람이 다시 치는 것은 오류가 아니다 —
        # digest 는 새 설치에 `s9 user add <이름>` 을 안내한다.
        owner = os.listdir(os.path.join(self.root, "users"))[0]
        self.cli("user", "add", owner)

    # ── S2. 멱등: 이미 프로젝트가 있으면 아무 일도 없다 ──────────────────
    def test_s2_idempotent_on_existing_repo(self):
        self.cli("init")
        self.cli("project", "add", "other", "--name", "다른 것")
        before = sorted(os.listdir(os.path.join(self.root, "vault", "projects")))
        users_before = sorted(os.listdir(os.path.join(self.root, "users")))
        self.cli("init")
        self.assertEqual(
            sorted(os.listdir(os.path.join(self.root, "vault", "projects"))), before)
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "users"))),
                         users_before)
        self.assertEqual((self.proj_meta(self.SLUG).get("is_default") or "").lower(), "true")

    # ── S3. 새 설치의 첫 요청이 미정 없이 붙는다 ────────────────────────
    def test_s3_first_request_lands_on_default(self):
        self.cli("init")
        r, meta = self.new_req()
        self.assertEqual(meta.get("project"), self.SLUG)
        self.assertEqual(meta.get("project_source"), "default")
        self.assertNotIn(HINT, r.stdout)

    # ── S4. 둘째 프로젝트가 생겨도 미정으로 떨어지지 않는다 ─────────────
    def test_s4_second_project_does_not_break_it(self):
        self.cli("init")
        self.cli("project", "add", "other", "--name", "다른 것")
        r, meta = self.new_req()
        self.assertEqual(meta.get("project"), self.SLUG)
        self.assertEqual(meta.get("project_source"), "default")
        self.assertNotIn(HINT, r.stdout)

    # ── S5. 지정을 옮기면 그 뒤 문서만 따라간다 (소급 없음) ─────────────
    def test_s5_moving_the_designation(self):
        self.cli("init")
        self.cli("project", "add", "other", "--name", "다른 것")
        _, first = self.new_req()
        self.cli("project", "default", "other")
        _, second = self.new_req()
        self.assertEqual(second.get("project"), "other")
        self.assertEqual(second.get("project_source"), "default")
        self.assertEqual((self.proj_meta("other").get("is_default") or "").lower(), "true")
        self.assertIsNone(self.proj_meta(self.SLUG).get("is_default"))
        # 이미 만들어진 문서는 그대로다
        self.assertEqual(first.get("project"), self.SLUG)

    # ── S6. 명시·세션 바인딩이 기본을 이긴다 (①③ > ④) ──────────────────
    def test_s6_explicit_and_binding_win(self):
        self.cli("init")
        self.cli("project", "add", "other", "--name", "다른 것")
        _, meta = self.new_req("--project", "other")
        self.assertEqual(meta.get("project"), "other")
        self.assertEqual(meta.get("project_source"), "explicit")
        self.cli("bind", "project", "other", env={"S9_SESSION": "sess1"})
        _, meta = self.new_req(env={"S9_SESSION": "sess1"})
        self.assertEqual(meta.get("project"), "other")
        self.assertEqual(meta.get("project_source"), "session")

    # ── S7. 기본 지정이 없는 옛 저장소는 종전 규칙(하나뿐이면) 그대로 ───
    def test_s7_legacy_only_rule_survives(self):
        self.cli("init")
        self.unset_default()
        _, meta = self.new_req()
        self.assertEqual(meta.get("project"), self.SLUG)
        self.assertEqual(meta.get("project_source"), "only")

    # ── S8. 지정이 없고 후보가 여럿이면 사람이 고른다 (⑤ 보존) ──────────
    def test_s8_no_designation_many_candidates_stays_blank(self):
        self.cli("init")
        self.cli("project", "add", "other", "--name", "다른 것")
        self.unset_default()
        r, meta = self.new_req()
        self.assertEqual(meta.get("project", ""), "")
        self.assertNotIn("project_source", meta)
        self.assertIn(HINT, r.stdout)

    # ── S9. CONTEXT.md 는 앞 30줄 안에 넷을 세운다 (digest 가 30줄만 싣는다) ──
    def test_s9_context_head_carries_four_things(self):
        self.cli("init")
        head = open(os.path.join(self.root, "projects", self.SLUG, "CONTEXT.md"),
                    encoding="utf-8").read().splitlines()[:self.m.CONTEXT_HEAD]
        text = "\n".join(head)
        self.assertIn("따로 정하지 않으면 문서가 여기로 옵니다", text)   # 이 자리가 무엇인지
        self.assertIn("조직 단위가 아닙니다", text)    # 혼자서도 용도마다 더 만들 수 있다
        for section in ("## 배경", "## 용어", "## 핵심 링크"):
            self.assertIn(section, text)              # 세 칸
        self.assertIn("## 저장소 정책", text)          # PROTOCOL 19조가 지정한 자리
        self.assertIn("s9 project add", text)          # 더 만들기
        self.assertIn("s9 project set", text)          # 이름 바꾸기
        self.assertIn("s9 project default", text)      # 기본 자리 옮기기
        self.assertLessEqual(len(head), self.m.CONTEXT_HEAD)

    # ── S10. 기본 프로젝트에 contribute 못 하는 사용자는 안 붙는다 ──────
    def test_s10_non_member_does_not_get_default(self):
        self.cli("init")
        self.cli("user", "add", "alice")
        r, meta = self.new_req("--user", "alice")
        self.assertEqual(meta.get("project", ""), "")
        self.assertNotIn("project_source", meta)


if __name__ == "__main__":
    unittest.main()
