"""작업자를 낡은 자리에 앉히지 않는다 (REQ-20260829-028-62x6).

실측 2026-08-29 16:51. 워크트리 아홉이 살아 있었고 방금 뜬 셋이 전부
`3e029be`(11:54) 를 가리켰다 — 그 뒤 다섯 시간 동안 본 저장소에 **2,638줄이
미커밋으로 쌓였다**(web/index.html 1,276줄 · bin/s9 · 새 시험 일곱). 그래서 그
작업자들은 오늘 오후에 만든 것이 하나도 없는 자리에 앉아 있었고, 고칠 코드를
못 찾아 아무것도 못 하고 물러났다(REQ-20260827-079·REQ-20260828-041).

워크트리는 **마지막 커밋의 체크아웃**이지 작업 트리의 복사가 아니다. 그러니
판정은 하나다 — *기준선이 신선할 때만 갈라 준다.* 다만 "저장소가 더러우면
거부"는 이 저장소에서 상수 True 라 무인 작업자가 영영 안 뜬다(그건 오늘의 다른
병이다). 그래서 **거부가 아니라 자리 바꾸기**다: 코드가 더러우면 본 저장소로
보내고, 겹치면 천장 있는 대기를 시킨다.

같은 날 둘째 실측: `worker_worktree_name()` 이 매 스폰에 `int(time.time())` 을
붙여 재스폰이 곧 새 워크트리였다 — 한 문서가 워크트리를 넷까지 만들었다.
셋째: `_worktree_autocommit` 이 `git commit` 의 반환코드를 안 봐서, 게이트가
거부해도 성공으로 보이고 sweep 이 30초마다 무한히 다시 불렀다.

격리: S9_ROOT=mktemp 에 진짜 git 저장소 + `s9 init`.
실행: python3 tests/ spawn_workspace
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _git(cwd, *a):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    return subprocess.run(["git", *a], cwd=cwd, env=env, capture_output=True,
                          text=True)


_REAL_POPEN = subprocess.Popen


def _spawn_patch(seen=None, pid=999998):
    """워커 스폰만 가로챈다.

    `subprocess.Popen` 을 통째로 막으면 판정이 부르는 `subprocess.run` 의 git
    까지 함께 죽는다 — 자리 판정은 `git worktree list` 와 `git status` 위에
    서 있다. 워커 스폰만 `start_new_session=True` 를 쓰므로 그것으로 가른다.
    """
    def fake(argv, **kw):
        if not kw.get("start_new_session"):
            return _REAL_POPEN(argv, **kw)
        if seen is not None:
            seen["argv"], seen["cwd"] = argv, kw.get("cwd")
            seen["env"] = kw.get("env") or {}
        return mock.Mock(pid=pid)
    return mock.patch("subprocess.Popen", side_effect=fake)


def _load(name="s9sw"):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Repo(unittest.TestCase):
    """진짜 git 저장소 + 진짜 문서 위에서 판정한다.

    `declared_scope` 는 문서 본문에서 **실재하는 파일 경로**만 읽으므로,
    가짜 문서로는 이 판정을 시험할 수 없다.
    """

    @classmethod
    def setUpClass(cls):
        # git 훅 안에서 돌면 GIT_DIR 이 환경에 실려 와 임시 저장소를 만지려던
        # git 이 **본 저장소**를 만진다 (test_worker_worktree 가 겪은 그것).
        cls._git_env = {k: v for k, v in os.environ.items()
                        if k.startswith("GIT_")}
        for k in cls._git_env:
            os.environ.pop(k, None)
        cls.root = tempfile.mkdtemp(prefix="s9spw-")
        _git(cls.root, "init", "-q", "-b", "main")
        _git(cls.root, "config", "user.name", "t")
        _git(cls.root, "config", "user.email", "t@t")
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "testbox"
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_AUTO_RESUME_DISABLE"):
            os.environ.pop(k, None)
        cls.env = {**os.environ}

        def cli(*argv, sess=None):
            env = dict(cls.env)
            if sess:
                env["S9_SESSION"] = sess
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=env, timeout=30)
            if r.returncode != 0:
                raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
            return r.stdout
        cls.cli = staticmethod(cli)

        cli("init")
        cli("user", "add", "alice")
        cli("user", "config", "alice", "auto_resume", "on")
        cli("user", "config", "alice", "auto_resume_cooldown_sec", "0")
        cli("user", "config", "alice", "auto_resume_global_per_hour", "50")
        cli("user", "config", "alice", "auto_resume_global_per_day", "100")
        cli("user", "config", "alice", "worker_worktree", "on")

        # 이 저장소의 코드 자리 — 문서가 이름을 대면 실재해야 스코프로 읽힌다.
        for rel, txt in (("bin/s9", "#!/usr/bin/env python3\n"),
                         ("web/index.html", "<html></html>\n"),
                         ("tests/test_x.py", "x = 1\n"),
                         ("harness/side.md", "곁가지\n")):
            p = os.path.join(cls.root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(txt)
        _git(cls.root, "add", "-A")
        _git(cls.root, "commit", "-qm", "init")

        def req(title, body):
            doc = cli("new", "request", "--title", title, "--summary", "t",
                      "--goal", "t", "--size", "S", "--user", "alice",
                      "--body", body).split()[0]
            cli("status", doc, "in-progress", "--note", "t")
            return doc
        cls.doc_none = req("scope-none", "무엇을 고칠지 말하지 않은 요청이다.")
        cls.doc_tests = req("scope-tests", "tests/test_x.py 를 고쳐라.")
        cls.doc_web = req("scope-web", "web/index.html 의 카드를 고쳐라.")
        cls.doc_bin = req("scope-bin", "bin/s9 의 스폰 관문을 고쳐라.")
        cls.doc_side = req("scope-side", "harness/side.md 를 고쳐라.")
        cls.m = _load()

    @classmethod
    def tearDownClass(cls):
        try:
            for w in (cls.m.worktree_list() or []):
                _git(cls.root, "worktree", "remove", "--force", w["path"])
        except Exception:
            pass
        os.environ.pop("S9_ROOT", None)
        os.environ.pop("S9_MACHINE", None)
        os.environ.update(cls._git_env)
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        self.on = {"worker_worktree": True}
        self.addCleanup(self._clean)

    def _clean(self):
        """저장소를 커밋된 상태로 되돌리고 워크트리·리스·표식을 거둔다."""
        for w in (self.m.worktree_list() or []):
            _git(self.root, "worktree", "remove", "--force", w["path"])
        _git(self.root, "branch", "--format=%(refname:short)")
        for b in (_git(self.root, "for-each-ref", "--format=%(refname:short)",
                       "refs/heads/wt").stdout or "").split():
            _git(self.root, "branch", "-D", b)
        # **코드만** 되돌린다. `checkout -- .` 은 index/catalog.jsonl 까지
        # 커밋 시점(문서가 하나도 없던 때)으로 되돌려 뒤 시험의 카탈로그를
        # 비운다 — 데이터는 이 저장소에서 되돌릴 대상이 아니다.
        _git(self.root, "checkout", "--", "bin", "web", "tests", "harness")
        for d in ("state/worktree_owners", "state/file_leases",
                  "state/spawn_wait"):
            shutil.rmtree(os.path.join(self.root, d), ignore_errors=True)

    def dirty(self, rel, text="더럽힌다\n"):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a") as f:
            f.write(text)
        return rel

    def decide(self, doc):
        return self.m.workspace_decision(doc, self.on)


class Decision(Repo):
    """A. 자리 판정 — 워크트리냐 본 저장소냐."""

    # W1. 깨끗하면 워크트리다 — 격리는 공짜일 때 쓴다.
    def test_w1_clean_repo_gets_a_worktree(self):
        d = self.decide(self.doc_tests)
        self.assertEqual(d["kind"], "worktree", d)
        self.assertEqual(d["reason"], "fresh", d)

    # W2. 코드가 더러우면 본 저장소다 — **오늘의 사고 그 자체**.
    def test_w2_dirty_code_sends_the_worker_home(self):
        self.dirty("bin/s9")
        self.assertEqual(self.decide(self.doc_none)["kind"], "main")

    # W3. 데이터만 더러운 것은 워크트리를 막지 않는다.
    #     S9_ROOT 가 본 저장소를 가리키므로 기준선과 무관하다 — 그것까지
    #     세면 이 저장소는 늘 더럽고 판정은 상수가 된다.
    def test_w3_dirty_data_does_not_block(self):
        self.dirty("vault/scratch.md")
        self.dirty("state/scratch.json", "{}\n")
        d = self.decide(self.doc_tests)
        self.assertEqual(d["kind"], "worktree", d)

    # W4. 스코프를 모르는데 코드가 더러우면 본 저장소다.
    #     추측하지 않는다 — 틀리는 방향이 비대칭이다.
    def test_w4_unknown_scope_is_conservative(self):
        self.dirty("harness/side.md")
        d = self.decide(self.doc_none)
        self.assertEqual(d["kind"], "main", d)
        self.assertEqual(d["reason"], "dirty-unknown", d)

    # W5. 등뼈가 더러우면 겹치지 않아도 본 저장소다 — 시험이 `../bin/s9` 를
    #     읽고 화면 검증이 살아 있는 서버를 보므로 검증이 거짓말을 한다.
    def test_w5_dirty_spine_beats_a_disjoint_scope(self):
        self.dirty("web/index.html")
        d = self.decide(self.doc_tests)
        self.assertEqual(d["kind"], "main", d)
        self.assertEqual(d["reason"], "dirty-spine", d)

    # W6. 화면 작업은 깨끗해도 본 저장소다 — 9909 는 본 저장소를 읽는다.
    def test_w6_screen_work_stays_home(self):
        d = self.decide(self.doc_web)
        self.assertEqual(d["kind"], "main", d)
        self.assertEqual(d["reason"], "live-verify", d)

    # W7. 자기 도구를 고치는 일은 본 저장소다 — 샌드박스가 범위를 자른다.
    def test_w7_self_edit_stays_home(self):
        d = self.decide(self.doc_bin)
        self.assertEqual(d["kind"], "main", d)
        self.assertEqual(d["reason"], "self-edit", d)

    # W8. 쌓이면 새로 만들지 않는다 — 쌓임 자체가 신호다.
    def test_w8_a_pile_of_worktrees_stops_new_ones(self):
        fake = [{"path": f"/nowhere/{i}", "branch": f"wt/{i}"}
                for i in range(self.m.WORKTREE_MAX)]
        with mock.patch.object(self.m, "worktree_list", lambda: fake):
            d = self.decide(self.doc_tests)
        self.assertEqual(d["kind"], "main", d)
        self.assertEqual(d["reason"], "worktree-pile", d)

    # W9. 한 문서에 둘째 워크트리를 만들지 않는다.
    #     — 오늘 w-829-011 이 넷이 된 그 자리.
    def test_w9_one_worktree_per_document(self):
        cwd, _e, name = self.m.worker_workspace(self.doc_tests, self.on,
                                                self.root)
        self.assertTrue(name, "첫 워크트리를 못 만들었다")
        with open(os.path.join(cwd, "wip.txt"), "w") as f:
            f.write("아직 쓰는 중\n")     # dirty — 잃을 것이 있다
        before = len(self.m.worktree_list())
        d = self.decide(self.doc_tests)
        self.assertEqual(d["reason"], "worktree-exists", d)
        self.assertEqual(d["kind"], "main", d)
        cwd2, _e2, name2 = self.m.worker_workspace(self.doc_tests, self.on,
                                                   self.root)
        self.assertEqual(name2, "")
        self.assertEqual(cwd2, self.root)
        self.assertEqual(len(self.m.worktree_list()), before,
                         "한 문서가 워크트리를 둘 만들었다")

    # W9b. 이름에 시간을 넣지 않는다 — 재스폰이 곧 새 워크트리이던 원인.
    def test_w9b_the_name_is_stable_for_a_document(self):
        a = self.m.worker_worktree_name(self.doc_tests)
        time.sleep(1.05)
        b = self.m.worker_worktree_name(self.doc_tests)
        self.assertEqual(a, b, "스폰마다 이름이 달라진다 — 워크트리가 쌓인다")

    # W9c. 주인이 죽고 남길 것도 없는 자리는 되쓴다(거두고 새로).
    def test_w9c_a_dead_and_empty_worktree_is_recycled(self):
        _cwd, _e, name = self.m.worker_workspace(self.doc_tests, self.on,
                                                 self.root)
        self.m.worktree_owner_write(name, {"doc": self.doc_tests,
                                           "pid": 999999,
                                           "created": time.time() - 86400})
        d = self.decide(self.doc_tests)
        self.assertEqual(d["kind"], "worktree", d)

    # W10. 오늘의 재현 — 스코프가 등뼈면 스폰이 본 저장소를 준다.
    def test_w10_the_spawn_gate_sends_todays_case_home(self):
        self.dirty("bin/s9")
        meta = {"user": "alice", "machine": "testbox", "title": "t"}
        seen = {}
        with _spawn_patch(seen):
            ok = self.m._spawn_worker(self.doc_none, meta, "p", "rework")
        self.assertTrue(ok, "스폰 자체가 막혔다")
        self.assertEqual(seen["cwd"], self.root,
                         "미커밋 코드가 있는데 워크트리에 앉혔다")

    # W11. 스코프가 겹치지 않으면 갈라 준다 — 격리를 공짜로 버리지 않는다.
    def test_w11_disjoint_scope_still_gets_a_worktree(self):
        self.dirty("harness/side.md")
        d = self.decide(self.doc_tests)
        self.assertEqual(d["kind"], "worktree", d)
        self.assertEqual(d["reason"], "fresh-outside", d)

    # W12. 겹치면 본 저장소다 — 사본에 없는 것을 고치라고 시킬 수 없다.
    def test_w12_overlapping_scope_stays_home(self):
        self.dirty("harness/side.md")
        d = self.decide(self.doc_side)
        self.assertEqual(d["kind"], "main", d)
        self.assertEqual(d["reason"], "dirty-overlap", d)


class Leases(Repo):
    """B. 본 저장소 방벽 — 워크트리를 안 쓰면 격리가 사라진다.

    이미 있는 것은 복구(`snapshot_dirty`)와 커밋 게이트(`concurrent_gate`)뿐이고
    **예방이 없다.** 그것을 스폰 시점 파일 리스로 세운다.
    """

    def spawn(self, doc, seen=None, meta=None):
        out = {}
        meta = meta or {"user": "alice", "machine": "testbox", "title": "t"}
        with _spawn_patch(seen):
            ok = self.m._spawn_worker(doc, meta, "프롬프트", "rework", out=out)
        return ok, out

    # L1. 스폰이 리스를 건다.
    def test_l1_a_spawn_takes_a_lease(self):
        self.dirty("web/index.html")           # 본 저장소로 보낸다
        ok, out = self.spawn(self.doc_tests)
        self.assertTrue(ok, out)
        lease = self.m.lease_read(self.doc_tests)
        self.assertTrue(lease, "리스를 걸지 않았다")
        self.assertIn("tests/test_x.py", lease.get("paths") or [])
        self.assertEqual(lease.get("pid"), 999998)

    # L2. 겹치면 **거부가 아니라 기다린다** — 거부는 오늘의 병을 되살린다.
    def test_l2_an_overlap_waits(self):
        self.dirty("web/index.html")
        self.m.lease_take("REQ-other-holder", ["tests/test_x.py"],
                          pid=os.getpid())
        ok, out = self.spawn(self.doc_tests)
        self.assertFalse(ok)
        self.assertEqual(out.get("blocked"), "waiting", out)
        self.assertIn("REQ-other-holder", out.get("why", ""))

    # L3. 죽은 손은 파일을 잡지 못한다 — 교착을 만들지 않는다.
    def test_l3_a_dead_holder_holds_nothing(self):
        self.dirty("web/index.html")
        self.m.lease_take("REQ-dead-holder", ["tests/test_x.py"], pid=999999)
        ok, out = self.spawn(self.doc_tests)
        self.assertTrue(ok, out)

    # L4. 기다림에 천장이 있다 — 천장 없는 큐는 교착의 다른 이름이다.
    def test_l4_waiting_has_a_ceiling(self):
        self.dirty("web/index.html")
        self.m.lease_take("REQ-other-holder", ["tests/test_x.py"],
                          pid=os.getpid())
        self.m._wait_mark(self.doc_tests, "held", "테스트가 심은 오래된 대기",
                          since=time.time() - self.m.LEASE_WAIT_MAX_SEC - 60)
        ok, out = self.spawn(self.doc_tests)
        self.assertTrue(ok, out)
        self.assertIn("WAIT-CEILING", self.spawn_log())

    # L5. 동시 워커 수에 천장이 있다.
    def test_l5_inflight_has_a_ceiling(self):
        self.dirty("web/index.html")
        rows = [{"id": "REQ-a", "pid": 1, "age": 1},
                {"id": "REQ-b", "pid": 2, "age": 1}]
        with mock.patch.object(self.m, "live_workers", lambda: rows):
            ok, out = self.spawn(self.doc_tests)
        self.assertFalse(ok)
        self.assertEqual(out.get("blocked"), "waiting", out)

    # L6. **대기는 한도를 깎지 않는다** — 판정이 `_auto_caps_ok` 뒤에 있으면
    #     대기 한 번마다 예산이 사라져 30분 뒤엔 띄울 수 없다.
    def test_l6_waiting_does_not_spend_the_budget(self):
        self.dirty("web/index.html")
        self.m.lease_take("REQ-other-holder", ["tests/test_x.py"],
                          pid=os.getpid())
        gp = os.path.join(self.root, "state", "auto_resume", "_global.json")
        before = open(gp).read() if os.path.exists(gp) else ""
        ok, _out = self.spawn(self.doc_tests)
        self.assertFalse(ok)
        after = open(gp).read() if os.path.exists(gp) else ""
        self.assertEqual(before, after, "대기 한 번에 일일 한도가 깎였다")

    # L7. 워커가 자기 차례를 안다 — 리스가 스케줄러 안에만 있으면
    #     워커는 그것을 모르고 옆 파일을 만진다.
    def test_l7_the_worker_is_told_its_files(self):
        self.dirty("web/index.html")
        seen = {}
        ok, out = self.spawn(self.doc_tests, seen=seen)
        self.assertTrue(ok, out)
        prompt = " ".join(str(a) for a in seen["argv"])
        self.assertIn("tests/test_x.py", prompt,
                      "받은 파일을 워커에게 말하지 않았다")

    # L8. 스코프를 모르면 붙잡지도 붙잡히지도 않는다 — 모르는 것으로
    #     남을 막으면 워커 하나가 전부를 세운다.
    def test_l8_unknown_scope_neither_holds_nor_is_held(self):
        self.dirty("bin/s9")
        self.m.lease_take("REQ-other-holder", ["tests/test_x.py"],
                          pid=os.getpid())
        ok, out = self.spawn(self.doc_none)
        self.assertTrue(ok, out)
        self.assertFalse(self.m.lease_read(self.doc_none),
                         "모르는 스코프로 리스를 잡았다")

    def spawn_log(self):
        try:
            with open(os.path.join(self.root, "state", "auto_resume",
                                   "spawn.log"), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""


class CommitDiscipline(Repo):
    """C. 커밋 규율 — 사람이 없을 때 나는 커밋이 문제다."""

    # C1. 스폰 경로는 본 저장소를 커밋하지 않는다.
    #     `git add -A` 는 "내 변경"이 아니라 "그 파일의 지금 상태"를 담는다.
    def test_c1_spawning_never_commits_the_main_repo(self):
        self.dirty("web/index.html")
        head = _git(self.root, "rev-parse", "HEAD").stdout.strip()
        with _spawn_patch():
            self.m._spawn_worker(self.doc_tests,
                                 {"user": "alice", "machine": "testbox",
                                  "title": "t"}, "p", "rework")
        self.assertEqual(head,
                         _git(self.root, "rev-parse", "HEAD").stdout.strip(),
                         "스폰이 본 저장소에 커밋했다")
        self.assertEqual(_git(self.root, "diff", "--cached",
                              "--name-only").stdout.strip(), "",
                         "스폰이 남의 파일을 스테이징했다")
        self.assertIn("web/index.html", self.m.repo_code_dirty(),
                      "스폰이 남의 미커밋 편집을 삼켰다")

    # C2. 자동 커밋의 실패가 보인다 — 지금은 30초마다 조용히 실패하며
    #     무한히 되풀이되고, 그 로그가 진짜 신호를 덮는다.
    def test_c2_a_failing_autocommit_gives_up_and_says_so(self):
        cwd, _e, name = self.m.worker_workspace(self.doc_tests, self.on,
                                                self.root)
        hook = os.path.join(self.root, ".git", "hooks", "pre-commit")
        os.makedirs(os.path.dirname(hook), exist_ok=True)
        with open(hook, "w") as f:
            f.write("#!/bin/sh\necho '게이트가 거부한다' >&2\nexit 1\n")
        os.chmod(hook, 0o755)
        self.addCleanup(lambda: os.path.exists(hook) and os.remove(hook))
        with open(os.path.join(cwd, "worker.txt"), "w") as f:
            f.write("워커가 만든 것\n")
        own = {"doc": self.doc_tests, "pid": 999999,
               "created": time.time() - 86400}
        self.m.worktree_owner_write(name, own)

        for _ in range(self.m.AUTOCOMMIT_MAX_TRIES):
            self.m._worktree_autocommit(name, self.m.worktree_owner_read(name))
        own = self.m.worktree_owner_read(name)
        self.assertEqual(own.get("autocommit_tries"),
                         self.m.AUTOCOMMIT_MAX_TRIES, own)
        self.assertTrue(own.get("autocommit_error"),
                        "실패를 삼켰다 — 사유가 어디에도 없다")

        # 네 번째는 아예 시도하지 않는다 (무한 반복 금지)
        head = _git(cwd, "rev-parse", "HEAD").stdout
        self.m._worktree_autocommit(name, self.m.worktree_owner_read(name))
        self.assertEqual(self.m.worktree_owner_read(name).get(
            "autocommit_tries"), self.m.AUTOCOMMIT_MAX_TRIES,
            "포기한 뒤에도 계속 시도한다")
        self.assertEqual(head, _git(cwd, "rev-parse", "HEAD").stdout)

        rows = self.m.undelivered_requests()
        self.assertTrue(any("자동 보존" in (r.get("detail") or "")
                            for r in rows), rows)


class Reaping(Repo):
    """D. 거두기 — 남길 것이 있으면 지우지 않는다. 다만 조용히 쌓이지도 않는다."""

    # S2. 주인이 죽고 하루가 지난 dirty 워크트리는 **지워지지 않고**
    #     경과 시간과 함께 사람 앞에 올라온다.
    def test_s2_a_stale_worktree_is_raised_not_removed(self):
        cwd, _e, name = self.m.worker_workspace(self.doc_tests, self.on,
                                                self.root)
        with open(os.path.join(cwd, "left.txt"), "w") as f:
            f.write("남은 것\n")
        self.m.worktree_owner_write(
            name, {"doc": self.doc_tests, "pid": 999999,
                   "created": time.time() - self.m.WORKTREE_STALE_SEC - 3600,
                   "autocommit_tries": self.m.AUTOCOMMIT_MAX_TRIES,
                   "autocommit_error": "게이트가 거부한다"})
        self.assertEqual(self.m.worktree_sweep(), [])
        self.assertTrue(os.path.isdir(cwd), "남길 것이 있는데 지웠다")
        rows = [r for r in self.m.undelivered_requests()
                if r.get("id") == self.doc_tests]
        self.assertTrue(rows, "묵은 워크트리가 사람 앞에 안 올라온다")
        self.assertIn("시간", rows[0].get("detail", ""),
                      f"경과 시간이 없다: {rows[0]}")


class Visible(Repo):
    """E. 사람이 볼 자리 — 말없이 다르게 동작하면 다음 사람이 또 헤맨다."""

    def spawn(self, doc):
        with _spawn_patch():
            return self.m._spawn_worker(doc, {"user": "alice",
                                              "machine": "testbox",
                                              "title": "t"}, "p", "rework")

    # V1. 로그에 자리와 사유가 남는다. 기존 SPAWN(...) 토큰은 건드리지 않는다 —
    #     운영 grep 과 기존 시험이 그 형태를 읽는다.
    def test_v1_the_log_says_where_and_why(self):
        self.dirty("harness/side.md")
        self.assertTrue(self.spawn(self.doc_none))
        log = open(os.path.join(self.root, "state", "auto_resume",
                                "spawn.log"), encoding="utf-8").read()
        self.assertIn(f"WORKSPACE(main) {self.doc_none} reason=dirty-unknown",
                      log)
        self.assertIn(f"SPAWN(fresh) {self.doc_none}", log,
                      "기존 로그 토큰이 사라졌다")

    # V2. 상태 파일이 자리를 싣는다 — 화면까지 새 통로가 필요 없다.
    def test_v2_the_marker_carries_the_workspace(self):
        self.dirty("web/index.html")
        self.assertTrue(self.spawn(self.doc_tests))
        with open(os.path.join(self.root, "state", "auto_resume",
                               self.m.safe_name(self.doc_tests) + ".json")) as f:
            sp = json.load(f)
        self.assertEqual((sp.get("workspace") or {}).get("kind"), "main", sp)
        self.assertEqual((sp.get("workspace") or {}).get("reason"),
                         "dirty-spine", sp)

    # V3. 손잡이의 답은 **두 칸**이고, 자리 말은 예외일 때만 선다.
    def test_v3_wake_says_the_place_only_when_it_is_an_exception(self):
        """자리 이름(`본 저장소`·`워크트리`)은 깃을 아는 사람의 말이라 창에
        세우지 않는다 (REQ-20260830-007). 뜻도 **말할 것이 있을 때만** 선다
        (REQ-20260830-049): main 갈래의 「바로 보입니다」는 기대대로인 사실이라
        말할 것이 없고, 없는 `note` 가 곧 "창을 세우지 마라"는 답이다. 여기에
        빈 문자열이라도 실리면 화면은 창을 세우고, 그 창이 자기가 가리키는
        카드를 가린다.

        경계: 여기서 지키는 것은 **자리 말이 사라지지 않는 것**이다 — 워크트리
        갈래에서 `note` 가 비면 워크트리에서 고친 화면을 9909 에서 영영 찾는
        그 헛수고가 돌아온다(V3 의 본래 이유)."""
        self.dirty("web/index.html")
        with _spawn_patch():
            res = self.m.wake_request(self.doc_tests, actor="tester", win=0)
        self.assertTrue(res.get("ok"), res)
        # 제목은 한 절 — 갈래 문장이 섞여 들어오지 않는다.
        self.assertEqual(res["message"], self.m.WAKE_SPAWNED_KO, res)
        self.assertNotIn("note", res,
                         "말할 것이 없는 갈래(main)가 부가 칸을 실었다 — "
                         "빈 칸 하나가 창을 세운다")
        for word in ("본 저장소", "워크트리"):
            self.assertNotIn(word, res["message"],
                             "창에 깃 낱말이 그대로 섰다")

    def test_v3b_the_worktree_branch_keeps_its_one_extra_line(self):
        """워크트리 갈래만 창이 선다 — 부가 한 줄이 그 창의 존재 이유다.

        여기서는 저장소를 더럽히지 않는다: 깨끗하면 워커가 워크트리에 앉고
        (Decision W1), 그 마커를 읽어 부가 줄이 실린다 — 갈래를 손으로 심지
        않고 실제 경로를 그대로 지난다."""
        with _spawn_patch():
            res = self.m.wake_request(self.doc_tests, actor="tester", win=0)
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(res["message"], self.m.WAKE_SPAWNED_KO, res)
        self.assertEqual(res.get("note"),
                         self.m.WS_MEANS_KO["worktree"] + ".", res)
        for word in ("본 저장소", "워크트리", "커밋", "사본"):
            self.assertNotIn(word, res["note"],
                             "부가 줄에 사용자 세계 밖의 낱말이 섰다: %s" % word)

    # V4. 대기는 실패처럼 보이지 않는다 — 누가 무엇을 잡고 있는지 말한다.
    def test_v4_wake_reports_waiting_not_failure(self):
        self.dirty("web/index.html")
        self.m.lease_take("REQ-other-holder", ["tests/test_x.py"],
                          pid=os.getpid())
        with _spawn_patch():
            res = self.m.wake_request(self.doc_tests, actor="tester", win=0)
        self.assertEqual(res.get("action"), "waiting", res)
        self.assertIn("REQ-other-holder", res.get("message", ""))

    # V5. 카드가 읽을 통로 — in-progress 행이 자리를 싣는다.
    def test_v5_the_catalog_row_carries_the_workspace(self):
        self.dirty("web/index.html")
        self.assertTrue(self.spawn(self.doc_tests))
        row = next((r for r in self.m.catalog_with_live()
                    if r.get("id") == self.doc_tests), None)
        self.assertIsNotNone(row)
        self.assertEqual((row.get("workspace") or {}).get("kind"), "main", row)

    # V6. 되찾는 값을 보인다 — 강제가 아니라 유인이다.
    def test_v6_worktree_ls_says_how_to_get_isolation_back(self):
        self.dirty("bin/s9")
        r = subprocess.run([S9, "worktree", "ls"], capture_output=True,
                           text=True, env=dict(self.env), timeout=30)
        self.assertIn("bin/s9", r.stdout, r.stdout + r.stderr)
        self.assertIn("commit", r.stdout, r.stdout)


if __name__ == "__main__":
    unittest.main()
