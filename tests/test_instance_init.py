"""s9 instance init 테스트 (REQ-20260824-053, 플로우 DOC-20260824-003).

업스트림-인스턴스 구조: 인스턴스는 데이터를 track하고, 업스트림 merge로
하네스를 업그레이드한다. 네트워크 없이 로컬 bare 리포를 origin으로 검증.

실행: python3 tests/test_instance_init.py
"""
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
PHOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")


def sh(*argv, cwd=None, env=None, inp=None):
    return subprocess.run(list(argv), cwd=cwd, env=env, input=inp,
                          capture_output=True, text=True, timeout=60)


class DetachedBase(unittest.TestCase):
    """I7. 베이스가 detached HEAD 여도 인스턴스는 main 가지로 서고 push 된다.

    원격 CI(tests/remote_run.py)는 베이스를 `checkout -f <sha>` 로 놓고 돈다 —
    그 클론에는 가지가 없어 `push -u origin main` 이 「src refspec main does not
    match any」로 섰다(원격 리눅스 실측 2026-09-06). 인스턴스의 가지는 베이스가 어디에
    서 있든 main 이다.
    """
    def test_detached_base_still_pushes_main(self):
        base = tempfile.mkdtemp(prefix="s9inst-detached-")
        root = os.path.join(base, "base")
        sh("git", "clone", "-q", os.path.join(HERE, ".."), root)
        sh("git", "checkout", "-q", "--detach", cwd=root)
        self.assertEqual(sh("git", "branch", "--show-current", cwd=root).stdout.strip(), "")
        origin = os.path.join(base, "work.git")
        sh("git", "init", "-q", "--bare", origin)
        target = os.path.join(base, "org-work")
        env = {**os.environ, "S9_ROOT": root}
        for k in ("S9_SESSION", "S9_AUTO_RESUME"):
            env.pop(k, None)
        r = sh(os.path.join(root, "bin", "s9"), "instance", "init", origin, "--dir", target, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("⑤ push 완료", r.stdout)
        self.assertEqual(sh("git", "branch", "--show-current", cwd=target).stdout.strip(), "main")
        self.assertIn("main", sh("git", "--git-dir", origin, "branch").stdout)


class IdentityNotCopied(unittest.TestCase):
    """I8. 인스턴스는 남의 신원을 물려받지 않는다 (REQ-20260921-015-62x6).

    `instance init` 은 업스트림 카피의 user.name·user.email 을 새 저장소로 복사했다.
    인스턴스는 만든 사람 A 가 남에게 건네는 저장소라, 받은 사람 B 의 commit 이 A 로
    선다 — 그 메일이 GitHub 에 등록된 실주소면 GitHub 이 A 의 계정으로 귀속해 감사
    이력이 거짓이 된다(security-engineer 판정 2026-09-21, REQ-20260921-004-62x6).

    복사의 원천이 저장소 **로컬** 값일 때가 특히 그렇다 — 전역 신원이 없는 컴퓨터에
    사다리가 박아 두는 값이 바로 거기 있다(REQ-20260921-011-62x6). 그래서 이 시험의
    업스트림 카피는 로컬에 A 의 신원이 박힌 모양으로 세운다.

    신원이 있는 컴퓨터(M1)와 아무 데도 없는 컴퓨터(M2)를 가르려고 `GIT_CONFIG_GLOBAL`·
    `GIT_CONFIG_SYSTEM` 을 돌려 놓는다 — 이 시험이 사람의 `~/.gitconfig` 를 읽지도
    쓰지도 않게 하는 자리이기도 하다.
    """

    @classmethod
    def setUpClass(cls):
        # 물려받은 GIT_* 를 전부 턴다 — 이 시험이 commit 의 저자를 재는데, 커밋 훅
        # 안에서 도는 회차는 GIT_AUTHOR_*·GIT_INDEX_FILE 을 환경에 달고 온다.
        # 환경의 값이 `-c user.name=…` 을 이기므로, 털지 않으면 같은 코드가 어디서
        # 돌았느냐에 따라 결과가 갈린다(실측 2026-09-21: 단독 통과·훅 안에서 실패).
        cls.genv = {k: v for k, v in os.environ.items()
                    if not k.startswith(("S9_", "GIT_")) and k != "EMAIL"}
        cls.base = tempfile.mkdtemp(prefix="s9inst-ident-")
        cls.up = os.path.join(cls.base, "upstream")
        sh("git", "clone", "-q", os.path.normpath(os.path.join(HERE, "..")), cls.up,
           env=cls.genv)
        sh("git", "checkout", "-q", "-B", "main", cwd=cls.up, env=cls.genv)
        sh("git", "config", "user.name", "alpha-maker", cwd=cls.up, env=cls.genv)
        sh("git", "config", "user.email", "alpha@example.com", cwd=cls.up, env=cls.genv)

    def _init(self, name, global_cfg):
        origin = os.path.join(self.base, name + ".git")
        sh("git", "init", "-q", "--bare", origin, env=self.genv)
        target = os.path.join(self.base, name)
        env = {**self.genv, "S9_ROOT": self.up,
               "GIT_CONFIG_GLOBAL": global_cfg, "GIT_CONFIG_SYSTEM": os.devnull}
        # 이 저장소의 bin/s9 로 잰다 — 업스트림 카피 안의 코드는 clone 시점의 것이라
        # 아직 이 고침을 모른다(실제 사용에서는 새 코드가 이 명령을 돈다).
        r = sh(S9, "instance", "init", origin, "--dir", target, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return target, r, env

    def _local(self, target, key):
        return sh("git", "config", "--local", "--get", key, cwd=target,
                  env=self.genv).stdout.strip()

    def test_m1_upstream_identity_is_not_copied(self):
        """M1. 전역 신원이 있는 컴퓨터 — 업스트림의 값이 인스턴스로 건너오지 않는다."""
        gcfg = os.path.join(self.base, "global-beta")
        with open(gcfg, "w", encoding="utf-8") as f:
            f.write("[user]\n\tname = beta-user\n\temail = beta@example.com\n")
        target, _r, env = self._init("beta-work", gcfg)
        cfg = open(os.path.join(target, ".git", "config"), encoding="utf-8").read()
        self.assertNotIn("alpha@example.com", cfg, "업스트림의 메일이 복사됐다")
        self.assertNotIn("alpha-maker", cfg, "업스트림의 이름이 복사됐다")
        self.assertEqual(self._local(target, "user.email"), "")
        # 그리고 이 컴퓨터의 신원이 그대로 쓰인다 — 막힌 것은 복사이지 commit 이 아니다
        self.assertEqual(
            sh("git", "config", "--get", "user.email", cwd=target, env=env).stdout.strip(),
            "beta@example.com")

    def test_m2_ladder_fills_the_empty_slot_not_the_upstream_value(self):
        """M2. 신원이 아무 데도 없는 컴퓨터 — 사다리가 고른 값이 서고, 업스트림의 값은 안 온다.

        박을 것이 없어 이 자리를 비워 두면 인스턴스의 문서 commit 이 신원 부재로
        거부된다 — 막는 것은 복사이지 commit 이 아니다.
        """
        target, r, env = self._init("orphan-work", os.devnull)
        cfg = open(os.path.join(target, ".git", "config"), encoding="utf-8").read()
        self.assertNotIn("alpha@example.com", cfg, "업스트림의 메일이 복사됐다")
        self.assertNotIn("alpha-maker", cfg, "업스트림의 이름이 복사됐다")
        self.assertTrue(self._local(target, "user.email"), "commit 할 신원이 없다")
        self.assertTrue(self._local(target, "user.name"), "commit 할 신원이 없다")
        self.assertIn("git 이름:", r.stdout)
        self.assertIn("⑤ push 완료", r.stdout)
        # 첫 commit 은 사람이 아니라 이 명령의 이름으로 선다. HEAD 가 아니라 뿌리
        # commit 을 묻는다 — init 직후 문서 이벤트가 commit 을 하나 더 얹을 수 있다.
        self.assertEqual(
            sh("git", "log", "--max-parents=0", "--format=%an <%ae>",
               cwd=target, env=self.genv).stdout.strip(),
            "s9-instance <s9@local>")
        # 그리고 그 값으로 다음 commit 이 실제로 선다
        with open(os.path.join(target, "docs", "ident-probe.md"), "w",
                  encoding="utf-8") as f:
            f.write("신원 확인용\n")
        sh("git", "add", "docs/ident-probe.md", cwd=target, env=env)
        c = sh("git", "commit", "-q", "-m", "ident probe", cwd=target, env=env)
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)
        self.assertNotIn("alpha",
                         sh("git", "log", "-1", "--format=%an <%ae>",
                            cwd=target, env=self.genv).stdout)


class TestInstanceInit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="s9inst-")
        cls.origin = os.path.join(cls.base, "work.git")   # 사설 리포(로컬 bare)
        sh("git", "init", "-q", "--bare", cls.origin)
        cls.target = os.path.join(cls.base, "org-work")
        cls.env = {**os.environ}
        cls.env.pop("S9_ROOT", None)
        cls.env.pop("S9_SESSION", None)
        # 무인 워커 세션 상속분 격리 — 훅이 auto-resume 턴으로 오인해
        # REQ 생성을 건너뛴다 (i4/i5가 단독 실행에서만 깨지던 원인)
        cls.env.pop("S9_AUTO_RESUME", None)
        r = sh(S9, "instance", "init", cls.origin, "--dir", cls.target,
               env=cls.env)
        assert r.returncode == 0, r.stdout + r.stderr
        cls.out = r.stdout

    # I1. 기본: 클론·리모트·gitignore 전환·초기 커밋·푸시
    def test_test_instance_init(self):
        """TestInstanceInit 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("i1_layout"):
                r = sh("git", "remote", "-v", cwd=self.target)
                self.assertIn("upstream", r.stdout)
                self.assertIn(f"origin\t{self.origin}", r.stdout)
                gi = open(os.path.join(self.target, ".gitignore")).read()
                self.assertNotIn("vault/", gi)          # 데이터 track
                # 세션 바인딩도 이 머신 것 — 담당은 문서 lease 가 나른다 (REQ-20260902-026)
                self.assertNotIn("!state/sessions", gi)
                self.assertIn("state/*", gi)            # chat inbox 등은 로컬
                log = sh("git", "log", "--oneline", cwd=self.target).stdout
                self.assertIn("instance init", log)
                self.assertIn("⑤ push 완료", self.out)
                # 코드도 함께 들어 있다 (사용자는 이 리포만 알면 된다)
                self.assertTrue(os.path.exists(
                    os.path.join(self.target, "bin", "s9")))
                self.assertTrue(os.path.exists(
                    os.path.join(self.target, "web", "index.html")))

            # I2. 데이터 track: 인스턴스에서 만든 REQ 문서가 git에 추적된다.
            # REQ-20260824-048 이후 문서 이벤트가 즉시 commit→push 되므로
            # 스테이징 예정(add -An)이 아니라 추적 여부(ls-files)로 검증한다.
        with self.subTest("i2_data_tracked"):
                env = {**self.env, "S9_ROOT": self.target}
                r = sh(S9, "new", "request", "--title", "인스턴스 요청",
                       "--summary", "s", "--goal", "g", "--size", "S",
                       "--user", "alice", "--body", "b", env=env)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                st = sh("git", "add", "-An", cwd=self.target).stdout
                ls = sh("git", "ls-files", cwd=self.target).stdout
                self.assertIn("vault/requests", st + ls)
                self.assertNotIn("\nindex/", "\n" + st + "\n" + ls)  # 파생물은 여전히 제외

            # I3. 푸시 불가(원격 미존재) → 단계별 가이드 출력, 비정상 종료 아님
        with self.subTest("i3_push_fail_guide"):
                tgt = os.path.join(self.base, "no-remote")
                r = sh(S9, "instance", "init",
                       os.path.join(self.base, "없는리포.git"), "--dir", tgt,
                       env=self.env)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("push 실패", r.stdout)
                self.assertIn("github.com/new", r.stdout)
                self.assertIn("git push -u origin main", r.stdout)

            # I4. 훅 cwd 감지: S9_ROOT 없이 cwd=인스턴스 → REQ가 인스턴스 vault에 생성
        with self.subTest("i4_hook_cwd_detection"):
                # 인스턴스는 빈 자리에서 시작하므로 users/ 도 비어 있다
                # (REQ-20260908-039). 훅은 등록되지 않은 계정의 말을 기록하지
                # 않으므로(REQ-20260906-074) 사람이 먼저 선다 — 실제로는
                # `s9 code` 첫 실행이 이 등록을 한다.
                sh(S9, "user", "add", "alice",
                   env={**self.env, "S9_ROOT": self.target})
                payload = {"session_id": "instsess-full", "cwd": self.target,
                           "prompt": "인스턴스에서 대시보드 스킨을 추가해줘"}
                r = sh(PHOOK, env=self.env, inp=json.dumps(payload))
                self.assertEqual(r.returncode, 0, r.stderr)
                ls = sh(S9, "ls", env={**self.env, "S9_ROOT": self.target}).stdout
                self.assertIn("스킨", ls)

            # I5. 회귀: cwd가 s9 루트가 아니면 명시 S9_ROOT 유지(감지 미발동)
        with self.subTest("i5_no_detection_outside_root"):
                sandbox = tempfile.mkdtemp(prefix="s9plain-")
                env = {**self.env, "S9_ROOT": sandbox, "S9_USER": "tester"}
                sh(S9, "init", env=env)
                sh(S9, "user", "add", "tester", env=env)   # 미등록 계정은 기록하지 않는다 (REQ-20260906-074)
                payload = {"session_id": "plainsess-x", "cwd": "/tmp",
                           "prompt": "샌드박스 대시보드에 새 시계 위젯을 추가해줘"}
                r = sh(PHOOK, env=env, inp=json.dumps(payload))
                self.assertEqual(r.returncode, 0, r.stderr)
                ls = sh(S9, "ls", env=env).stdout
                self.assertIn("샌드박스", ls)

            # I6. 업그레이드: 업스트림 커밋 → 인스턴스가 **코드 경로만** 수령
            # (REQ-20260908-039). 예전엔 `git merge upstream/main` 이었다 —
            # 이제 인스턴스의 이력은 업스트림과 갈라져 있어(orphan) merge 가
            # 성립하지 않고, 성립하면 그 순간 업스트림의 문서가 되살아난다.
        with self.subTest("i6_upgrade_takes_code_only"):
            up = os.path.join(self.base, "upstream-copy")
            sh("git", "clone", "-q", os.path.join(HERE, ".."), up)
            # 베이스가 detached HEAD(원격 CI)면 클론도 가지가 없어 아래 commit 이
            # main 에 안 실린다 — 업스트림의 가지는 main 이다 (원격 리눅스 실측 2026-09-06)
            sh("git", "checkout", "-q", "-B", "main", cwd=up)
            marker = os.path.join(up, "docs", "upgrade-marker.md")
            with open(marker, "w") as f:
                f.write("업그레이드 확인용\n")
            sh("git", "add", "docs/upgrade-marker.md", cwd=up)
            sh("git", "-c", "user.name=t", "-c", "user.email=t@t",
               "commit", "-q", "-m", "harness upgrade", cwd=up)
            sh("git", "remote", "set-url", "upstream", up, cwd=self.target)
            # 인스턴스 안의 bin/s9 는 clone 시점의 것이라 이 명령을 아직 모를 수
            # 있다 — 이 저장소의 코드로 잰다(실제 사용에서는 새 인스턴스가 이
            # 코드를 갖고 태어난다).
            import importlib.machinery
            import importlib.util
            prev = os.environ.get("S9_ROOT")
            os.environ["S9_ROOT"] = self.target
            try:
                spec = importlib.util.spec_from_loader(
                    "s9_upg2",
                    importlib.machinery.SourceFileLoader("s9_upg2", S9))
                m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(m)
                self.assertEqual(m.instance_upgrade(root=self.target), 0)
            finally:
                if prev is None:
                    os.environ.pop("S9_ROOT", None)
                else:
                    os.environ["S9_ROOT"] = prev
            self.assertTrue(os.path.exists(
                os.path.join(self.target, "docs", "upgrade-marker.md")),
                "업스트림의 코드가 안 왔다")
            # 그리고 업스트림의 문서는 오지 않는다 — merge 였다면 왔을 것이다
            up_docs = []
            for base, _d, names in os.walk(os.path.join(self.target, "vault")):
                up_docs += [n for n in names if n.startswith("DOC-2026082")]
            self.assertEqual(up_docs, [], "업스트림의 문서가 함께 왔다")

if __name__ == "__main__":
    unittest.main(verbosity=2)
