"""인스턴스는 빈 자리에서 시작한다 (REQ-20260908-039-62x6 · -043-62x6).

주인 지적 2026-09-08: 「vault 에서 section9 프로젝트의 문서들을 다 가져가는 건
싫은데 말이지... 아무것도 없이 깨끗하게 시작하는 방법은 없나?」

재현으로 확인한 것(2026-09-08): `s9 instance init` 이 만든 인스턴스에 이 저장소의
문서 **1390건**과 남의 프로필 4개가 그대로 들어왔다. 원인은 `git clone <ROOT>` 이
「업스트림은 코드만 track 한다」는 전제 위에 있었는데, 이 저장소는 vault·users·
projects 를 track 한다는 것(REQ-20260827-036). 그래서 인스턴스는 코드가 아니라
**이 저장소의 기억 전체**를 물려받았고, 파일을 나중에 지워도 이력에는 남았다.

고정하는 계약 다섯.
1. 작업 트리에 남의 문서가 **하나도** 없다.
2. **이력에도** 없다 — 지운 것과 애초에 없던 것은 다르다.
3. 코드는 다 있다 — 사용자는 이 저장소 하나만 알면 된다.
4. 업그레이드는 merge 가 아니라 **코드 경로만** 받는다. merge 는 이력이 갈라져
   성립하지 않고, 성립하면 그 순간 지운 문서가 되살아난다.
5. 인스턴스가 track 하지 말아야 할 세 줄(streams·users/*/streams·
   users/*/config/local.json)이 .gitignore 에 있다 — 업스트림이 그 줄을 둔 값은
   대화 기록 158MB 이력 재작성이었다(REQ-20260827-047).

실행: python3 tests/ instance_clean
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(HERE, "..", "bin", "s9")


def sh(*argv, cwd=None, env=None):
    return subprocess.run(list(argv), cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=180)


class CleanStart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="s9clean-")
        cls.origin = os.path.join(cls.base, "work.git")
        sh("git", "init", "-q", "--bare", cls.origin)
        cls.target = os.path.join(cls.base, "inst")
        cls.env = {k: v for k, v in os.environ.items()
                   if k not in ("S9_ROOT", "S9_SESSION", "S9_AUTO_RESUME")}
        r = sh(S9, "instance", "init", cls.origin, "--dir", cls.target,
               env=cls.env)
        assert r.returncode == 0, r.stdout + r.stderr
        cls.out = r.stdout

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def _git(self, *a):
        return sh("git", *a, cwd=self.target).stdout

    # ① 작업 트리에 남의 문서가 없다
    def test_no_documents_came_along(self):
        found = []
        for base, _d, names in os.walk(os.path.join(self.target, "vault")):
            found += [n for n in names if n.endswith(".md")]
        self.assertEqual(found, [], "남의 문서가 따라왔다 — 2026-09-08 그 자리")
        self.assertEqual(os.listdir(os.path.join(self.target, "users")), [],
                         "남의 프로필이 따라왔다")

    def test_nothing_data_is_tracked_yet(self):
        ls = self._git("ls-files", "vault", "users", "projects").strip()
        self.assertEqual(ls, "", "빈 자리인데 데이터가 track 돼 있다")

    # ② 이력에도 없다 — 지운 것과 애초에 없던 것은 다르다
    def test_the_history_has_no_documents_either(self):
        names = self._git("log", "--all", "--name-only", "--format=")
        stray = [l for l in names.splitlines()
                 if l.startswith(("vault/", "users/"))]
        self.assertEqual(stray[:5], [],
                         "이력에 남의 문서가 남았다 — 파일을 지워도 이력은 남는다")

    def test_it_starts_with_one_commit(self):
        n = self._git("rev-list", "--count", "HEAD").strip()
        self.assertEqual(n, "1", f"첫 commit 이 하나가 아니다({n})")

    def test_the_branch_is_main(self):
        # 베이스가 어디에 서 있든 인스턴스의 가지는 main 이다 (REQ-20260905-012)
        self.assertEqual(self._git("rev-parse", "--abbrev-ref", "HEAD").strip(),
                         "main")

    def test_the_borrowed_branch_name_is_gone(self):
        names = self._git("branch", "--format=%(refname:short)").split()
        self.assertEqual(names, ["main"], "첫 commit 에 쓴 임시 가지가 남았다")

    # ③ 코드는 다 있다
    def test_the_code_is_all_there(self):
        for rel in ("bin/s9", "bin/s9.py", "web/index.html", "harness",
                    "docs", "pyproject.toml"):
            self.assertTrue(os.path.exists(os.path.join(self.target, rel)), rel)
        n = len([x for x in os.listdir(os.path.join(self.target, "tests"))
                 if x.endswith(".py")])
        self.assertGreater(n, 100, f"시험이 {n}개뿐이다 — 코드가 덜 왔다")

    def test_the_skeleton_is_made(self):
        for d in ("vault", "users", "index", "state"):
            self.assertTrue(os.path.isdir(os.path.join(self.target, d)), d)

    # ⑤ 인스턴스가 담지 말아야 할 세 줄
    def test_the_gitignore_carries_what_upstream_learned(self):
        gi = open(os.path.join(self.target, ".gitignore"), encoding="utf-8").read()
        for line in ("streams/", "users/*/streams/",
                     "users/*/config/local.json"):
            self.assertIn(line, gi,
                          f"{line} 이 없다 — 인스턴스를 쓰기 시작하면 그것이 담긴다")
        self.assertNotIn("\nvault/", gi, "데이터는 track 한다 — 그것이 인스턴스다")

    def test_the_upstream_leftovers_are_swept(self):
        refs = self._git("for-each-ref", "--format=%(refname)",
                         "refs/remotes/upstream").strip()
        self.assertEqual(refs, "",
                         "업스트림 원격 추적 가지가 남았다 — `git log --all` 에 "
                         "남의 문서가 그대로 보인다")

    # ④ 업그레이드는 코드 경로만 받는다
    def test_upgrade_brings_code_and_leaves_documents_alone(self):
        # 업스트림을 이 저장소로 돌려 놓는다(네트워크 없이 잰다)
        sh("git", "remote", "set-url", "upstream", ROOT, cwd=self.target)
        # 인스턴스에 문서 하나를 만들고, 코드 하나를 흠집 낸다
        env = {**self.env, "S9_ROOT": self.target}
        r = sh(S9, "new", "request", "--title", "인스턴스 요청", "--summary", "s",
               "--goal", "g", "--size", "S", "--user", "alice", "--body", "b",
               env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        mine = [n for _b, _d, ns in os.walk(os.path.join(self.target, "vault"))
                for n in ns if n.endswith(".md")]
        self.assertTrue(mine, "준비가 틀렸다 — 인스턴스에 문서가 안 생겼다")
        scar = os.path.join(self.target, "bin", "s9_env.py")
        with open(scar, "a", encoding="utf-8") as f:
            f.write("\n# 흠집\n")
        sh("git", "add", "-A", cwd=self.target)
        sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
           "흠집", cwd=self.target)

        # **이 저장소의 코드**로 잰다 — 인스턴스 안의 bin/s9 는 clone 시점의 것이라
        # (닭이 먼저냐 달걀이 먼저냐) 아직 이 명령을 모른다. 실제 사용에서는
        # 새로 만든 인스턴스가 이 코드를 갖고 태어난다.
        import importlib.machinery
        import importlib.util
        prev = os.environ.get("S9_ROOT")
        os.environ["S9_ROOT"] = self.target
        try:
            spec = importlib.util.spec_from_loader(
                "s9_upg", importlib.machinery.SourceFileLoader("s9_upg", S9))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            self.assertEqual(m.instance_upgrade(root=self.target), 0)
        finally:
            if prev is None:
                os.environ.pop("S9_ROOT", None)
            else:
                os.environ["S9_ROOT"] = prev
        self.assertNotIn("# 흠집", open(scar, encoding="utf-8").read(),
                         "업스트림의 코드로 되돌아오지 않았다")
        still = [n for _b, _d, ns in os.walk(os.path.join(self.target, "vault"))
                 for n in ns if n.endswith(".md")]
        self.assertEqual(sorted(still), sorted(mine),
                         "업그레이드가 인스턴스의 문서를 건드렸다")
        # 그리고 남의 문서를 되살리지 않는다 — merge 였다면 1390건이 돌아온다
        self.assertLess(len(still), 5, "업스트림의 문서가 되살아났다")

    def test_the_upstream_vault_is_untouched(self):
        """인스턴스에서 만든 문서는 그 저장소에만 생긴다 — 업스트림은 그대로다."""
        before = len([n for _b, _d, ns in os.walk(os.path.join(ROOT, "vault"))
                      for n in ns if n.endswith(".md")])
        env = {**self.env, "S9_ROOT": self.target}
        r = sh(S9, "new", "request", "--title", "여기서만 산다", "--summary", "s",
               "--goal", "g", "--size", "S", "--user", "alice", "--body", "b",
               env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = len([n for _b, _d, ns in os.walk(os.path.join(ROOT, "vault"))
                     for n in ns if n.endswith(".md")])
        self.assertEqual(after, before,
                         "인스턴스의 요청이 업스트림 vault 에 생겼다")

    def test_a_non_empty_target_is_refused(self):
        """대상 자리가 비어 있지 않으면 거부한다 — 남의 파일 위에 짓지 않는다."""
        occupied = os.path.join(self.base, "occupied")
        os.makedirs(occupied, exist_ok=True)
        with open(os.path.join(occupied, "있던것.txt"), "w") as f:
            f.write("x")
        r = sh(S9, "instance", "init", self.origin, "--dir", occupied,
               env=self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("비어있지 않다", r.stdout + r.stderr)
        self.assertTrue(os.path.exists(os.path.join(occupied, "있던것.txt")),
                        "거부하면서 남의 파일을 건드렸다")

    def test_upgrade_refuses_where_there_is_no_upstream(self):
        # 업스트림 자신에서는 돌지 않는다 — 그냥 pull 하면 되는 자리다.
        # 가르는 것은 `.s9-sync`(업스트림도 갖고 있다)가 아니라 upstream remote 다.
        bare = os.path.join(self.base, "no-upstream")
        os.makedirs(bare, exist_ok=True)
        sh("git", "init", "-q", bare)
        r = sh(S9, "instance", "upgrade",
               env={**self.env, "S9_ROOT": bare}, cwd=bare)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("인스턴스가 아니다", r.stdout + r.stderr)

    # 안내문이 없는 명령을 가리키면 사람은 없는 것을 찾는다 (REQ-20260907-024)
    def test_the_guide_names_a_command_that_exists(self):
        self.assertIn("s9 instance upgrade", self.out)
        self.assertNotIn("git merge upstream/main", self.out,
                         "merge 를 안내한다 — 그것이 성공하면 지운 문서가 되살아난다")


if __name__ == "__main__":
    unittest.main()
