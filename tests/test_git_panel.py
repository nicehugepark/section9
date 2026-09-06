"""화면에서 pull·push — 판정과 명령의 모양 (REQ-20260901-023-62x6).

이 판은 화면 문제이기 전에 **안전 문제**다. 리드가 못박은 제약 넷은 문장이
아니라 **코드의 모양**이어야 하고, 그것을 지키는 것이 이 시험이다.

  ① 화면이 commit 하지 않는다.
  ② 도는 일이 있으면 손대지 않는다.
  ③ pull 은 고치던 파일이 없을 때만 — 치워 두었다 되돌리는 명령은 화면이
     **부를 수조차 없다**(2026-09-01 실사고: 그 명령이 남의 미커밋 작업
     113건을 걷어 갔다, REQ-20260901-004).
  ④ 갈라진 갈래는 화면이 합치지 않는다 — 앞으로만 붙이는 방식 고정.

**갈래를 모의 객체로 재현하지 않는다.** 진짜 저장소를 임시로 세우고(원격도
임시 bare) 각 상태를 실제로 만든 뒤에 잰다 — 「앞으로만 붙이는 방식」이
정말로 지켜지는지는 git 이 답할 일이지 흉내가 답할 일이 아니다.

실행: python3 tests/ git_panel
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


def git(cwd, *argv, check=True):
    r = subprocess.run(["git", *argv], cwd=cwd, capture_output=True,
                       text=True, timeout=60)
    if check and r.returncode != 0:
        raise AssertionError("git %s 실패: %s" % (" ".join(argv),
                                                 r.stderr or r.stdout))
    return r


class GitPanelBase(unittest.TestCase):
    """작업 저장소 하나 · bare 원격 하나 · 남의 clone 하나.

    모듈은 **한 번만** 싣는다(20,000줄 파일이라 부담이 크다) — 대신 `ROOT` 로
    잡히는 자리를 시험마다 비우고 다시 세운다. 그래서 경로는 고정이고 내용만
    갈린다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9git-")
        cls.work = os.path.join(cls.tmp, "work")
        os.makedirs(cls.work)
        os.environ["S9_ROOT"] = cls.work
        os.environ.setdefault("S9_USER", "tester")
        name = "s9git_" + os.path.basename(cls.tmp)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- 저장소 세우기 ----------------------------------------------------
    def setUp(self):
        m = self.m
        self.remote = os.path.join(self.tmp, "remote.git")
        self.other = os.path.join(self.tmp, "other")
        for p in (self.work, self.remote, self.other):
            shutil.rmtree(p, ignore_errors=True)
        os.makedirs(self.work)
        git(self.tmp, "init", "-q", "--bare", self.remote)
        git(self.work, "init", "-q", "-b", "main", ".")
        git(self.work, "config", "user.email", "t@example.com")
        git(self.work, "config", "user.name", "tester")
        self.write("a.txt", "one\n")
        git(self.work, "add", "a.txt")
        git(self.work, "commit", "-q", "-m", "첫 줄")
        git(self.work, "remote", "add", "origin", self.remote)
        git(self.work, "push", "-q", "-u", "origin", "main")
        # 판정은 값싼 자리에서 바꿔 끼운다 — 이 시험이 재는 것은 git 의 상태다
        m._GIT_ASKED["at"] = 0.0
        self._role = m.user_role
        m.user_role = lambda n: "admin" if n == "boss" else "member"
        self.addCleanup(setattr, m, "user_role", self._role)

    def write(self, rel, text, cwd=None):
        p = os.path.join(cwd or self.work, rel)
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def clone_other(self):
        git(self.tmp, "clone", "-q", self.remote, self.other)
        git(self.other, "config", "user.email", "o@example.com")
        git(self.other, "config", "user.name", "other")

    def push_from_other(self, text="두 번째 줄\n", name="b.txt"):
        if not os.path.isdir(self.other):
            self.clone_other()
        self.write(name, text, cwd=self.other)
        git(self.other, "add", name)
        git(self.other, "commit", "-q", "-m", "남이 올린 " + name)
        git(self.other, "push", "-q", "origin", "main")

    def commit_here(self, name="c.txt", text="내 줄\n"):
        self.write(name, text)
        git(self.work, "add", name)
        git(self.work, "commit", "-q", "-m", "내가 만든 " + name)

    def state(self, ask=False, actor="boss", proxy=""):
        return self.m.git_state(ask_remote=ask, actor=actor, proxy_for=proxy)

    def record(self):
        """부른 git 명령을 그대로 적어 둔다 — 「무엇을 안 불렀나」도 계약이다."""
        m, calls, real = self.m, [], self.m.git_run

        def spy(argv, timeout=25):
            calls.append(list(argv))
            return real(argv, timeout=timeout)
        m.git_run = spy
        self.addCleanup(setattr, m, "git_run", real)
        return calls


class TheDistanceIsRead(GitPanelBase):
    """A. 상태 읽기 — 셈과 작업 트리가 단추 옆에 이미 서 있다 (리드 제약 6)."""

    def test_s1_same(self):
        st = self.state()
        self.assertTrue(st["repo"])
        self.assertEqual((st["ahead"], st["behind"], st["dirty_n"]), (0, 0, 0))
        self.assertEqual(st["upstream"], "origin/main")
        self.assertFalse(st["can"]["pull"]["ok"])
        self.assertFalse(st["can"]["push"]["ok"])
        for side in ("pull", "push"):
            self.assertIn("없습니다", st["can"][side]["why"])

    def test_s2_push_only(self):
        self.commit_here()
        st = self.state()
        self.assertEqual((st["ahead"], st["behind"]), (1, 0))
        self.assertTrue(st["can"]["push"]["ok"])
        self.assertEqual(st["can"]["push"]["why"], "")
        self.assertFalse(st["can"]["pull"]["ok"])
        self.assertEqual([c["title"] for c in st["push_commits"]],
                         ["내가 만든 c.txt"])

    def test_s3_pull_only(self):
        self.push_from_other()
        st = self.state(ask=True)
        self.assertEqual((st["ahead"], st["behind"]), (0, 1))
        self.assertTrue(st["can"]["pull"]["ok"])
        self.assertFalse(st["can"]["push"]["ok"])
        self.assertEqual([c["title"] for c in st["pull_commits"]],
                         ["남이 올린 b.txt"])

    def test_s4_diverged_is_never_merged_by_the_screen(self):
        self.push_from_other()
        self.commit_here()
        st = self.state(ask=True)
        self.assertTrue(st["ahead"] and st["behind"])
        for side in ("pull", "push"):
            self.assertFalse(st["can"][side]["ok"])
            self.assertIn("합치는 일은 화면이 하지 않습니다",
                          st["can"][side]["why"])
            # 셈은 상태 줄이 든다 — 사유가 같은 것을 두 번 적지 않는다
            self.assertNotIn("push 할 것", st["can"][side]["why"])
            # 막힌 자리에서만 터미널로 보낸다 — 칠 글자를 정확히 준다
            self.assertIn("git pull --rebase", st["can"][side]["why"])

    def test_s5_dirty_names_the_files_and_stops_pull(self):
        self.push_from_other()
        self.write("a.txt", "고치던 중\n")
        st = self.state(ask=True)
        self.assertEqual(st["dirty_n"], 1)
        self.assertEqual(st["dirty"], ["a.txt"])
        self.assertFalse(st["can"]["pull"]["ok"])
        self.assertIn("고치던 파일이 1개", st["can"]["pull"]["why"])
        self.assertIn("commit 한 뒤에", st["can"]["pull"]["why"])

    def test_s5b_untracked_does_not_lock_the_repo_forever(self):
        """미추적 파일은 세지 않는다 — 이 저장소에는 늘 있다(state/sessions).

        세는 순간 pull 은 영영 안 열린다. 앞으로만 붙이는 병합을 실제로 막는
        것은 추적 파일의 변경이고, 미추적이 정말 덮일 때는 git 이 거절해 그
        문장이 화면에 선다."""
        self.push_from_other()
        self.write("state/sessions/new.json", "{}\n")
        st = self.state(ask=True)
        self.assertEqual(st["dirty_n"], 0)
        self.assertTrue(st["can"]["pull"]["ok"])

    def test_s6_running_jobs_hold_both_hands(self):
        """도는 일은 **지어낸 숫자가 아니라** 헤더 칩이 쓰는 그 숫자다."""
        d = os.path.join(self.work, "state", "jobs")
        os.makedirs(d, exist_ok=True)
        import time
        with open(os.path.join(d, "t.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "테스트", "pid": os.getpid(),
                       "started": time.time(), "hint": "python"}, f)
        st = self.state(ask=True)
        self.assertEqual(st["jobs"], 1)
        for side in ("pull", "push"):
            self.assertFalse(st["can"][side]["ok"])
            self.assertIn("실행 중인 작업 1건", st["can"][side]["why"])
        self.assertIn("끝나면 push", st["can"]["push"]["why"])
        self.assertIn("끝나면 pull", st["can"]["pull"]["why"])

    def test_s7_only_admin_may_touch_the_repository(self):
        self.commit_here()
        st = self.state(actor="member1")
        self.assertFalse(st["admin"])
        for side in ("pull", "push"):
            self.assertFalse(st["can"][side]["ok"])
            self.assertIn("admin", st["can"][side]["why"])
        # 읽기는 막지 않는다 — 거리를 아는 데는 위험이 없다
        self.assertEqual(st["ahead"], 1)

    def test_s8_nobody_changes_the_repository_by_proxy(self):
        self.commit_here()
        st = self.state(proxy="user1")
        for side in ("pull", "push"):
            self.assertFalse(st["can"][side]["ok"])
            self.assertIn("@user1 시점", st["can"][side]["why"])

    def test_s9_no_upstream_hands_the_command_over(self):
        git(self.work, "remote", "remove", "origin")
        st = self.state()
        self.assertEqual(st["upstream"], "")
        for side in ("pull", "push"):
            self.assertFalse(st["can"][side]["ok"])
            self.assertIn("git push -u origin main", st["can"][side]["why"])

    def test_s9b_not_a_repository(self):
        shutil.rmtree(os.path.join(self.work, ".git"))
        st = self.state()
        self.assertFalse(st["repo"])
        self.assertIn("git 저장소가 아닙니다", st["can"]["pull"]["why"])

    def test_s10_the_cheap_side_never_asks_the_remote(self):
        """값싼 것과 비싼 것을 갈라 잰다 — 판이 열려 있는 동안 도는 폴은
        원격을 두드리지 않는다(며칠 열어 두면 하루 2,880번이 된다)."""
        calls = self.record()
        self.state(ask=False)
        self.assertEqual([c for c in calls if c[0] == "fetch"], [],
                         "ask_remote=0 인데 원격에 물었다")
        calls.clear()
        self.state(ask=True)
        self.assertEqual([c[:2] for c in calls if c[0] == "fetch"],
                         [["fetch", "--quiet"]])

    def test_s10b_the_age_is_never_hidden(self):
        self.assertEqual(self.state()["asked_sec"], -1)
        st = self.state(ask=True)
        self.assertGreaterEqual(st["asked_sec"], 0)
        self.assertTrue(st["remote_ok"])


class TheHandsActuallyMove(GitPanelBase):
    """B. 실행 — 그리고 **누른 순간 다시 판정한다**."""

    def test_s11_pull_fast_forwards(self):
        self.push_from_other()
        res = self.m.git_do("pull", actor="boss")
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(res["state"]["behind"], 0)
        self.assertEqual(res["state"]["ahead"], 0)
        self.assertEqual(res["files"], ["b.txt"])
        self.assertIn("파일 1개가 바뀌었습니다", res["said"])
        self.assertEqual([c["title"] for c in res["commits"]],
                         ["남이 올린 b.txt"])
        self.assertTrue(os.path.exists(os.path.join(self.work, "b.txt")))

    def test_s11b_a_web_change_says_to_refresh(self):
        self.push_from_other(name="web/app/x.js", text="// 새 조각\n")
        res = self.m.git_do("pull", actor="boss")
        self.assertTrue(res["ok"], res.get("error"))
        self.assertIn("화면을 새로 고치면", res["said"])

    def test_s12_push_moves_the_remote(self):
        self.commit_here()
        head = git(self.work, "rev-parse", "HEAD").stdout.strip()
        res = self.m.git_do("push", actor="boss")
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(
            git(self.remote, "rev-parse", "refs/heads/main").stdout.strip(),
            head, "원격의 main 이 안 움직였다")
        self.assertEqual(res["state"]["ahead"], 0)
        self.assertIn("origin/main", res["said"])

    def test_s13_the_gate_judges_again_at_the_moment_of_the_press(self):
        """화면이 「할 수 있다」고 그린 뒤에 트리가 더러워졌으면 거절한다 —
        그리고 그 문장은 **누르기 전 사유와 같은 글자**다."""
        self.push_from_other()
        ready = self.state(ask=True)
        self.assertTrue(ready["can"]["pull"]["ok"])
        self.write("a.txt", "그 사이에 고쳤다\n")
        res = self.m.git_do("pull", actor="boss")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"],
                         res["state"]["can"]["pull"]["why"],
                         "거절 문장과 사유 줄이 두 벌이다")
        self.assertIn("고치던 파일이 1개", res["error"])

    def test_s13b_a_press_without_the_right_is_refused(self):
        self.commit_here()
        res = self.m.git_do("push", actor="member1")
        self.assertFalse(res["ok"])
        self.assertIn("admin", res["error"])
        self.assertEqual(
            git(self.remote, "rev-parse", "refs/heads/main").stdout.strip(),
            git(self.work, "rev-parse", "HEAD~1").stdout.strip(),
            "거절했는데 원격이 움직였다")

    def test_s15_pull_runs_only_as_fast_forward(self):
        self.push_from_other()
        calls = self.record()
        self.m.git_do("pull", actor="boss")
        ran = [c for c in calls if c[0] in ("pull", "push")]
        self.assertEqual(ran, [["pull", "--ff-only"]])

    def test_s15b_a_press_never_commits_or_puts_anything_aside(self):
        """한 번 누르는 동안 화면이 부른 git 명령 **전부**를 본다 —
        `add`·`commit`·치우는 명령이 하나도 없어야 한다 (리드 제약 1·3)."""
        self.push_from_other()
        calls = self.record()
        self.m.git_do("pull", actor="boss")
        self.commit_here()
        self.m.git_do("push", actor="boss")
        flat = {tok for c in calls for tok in c}
        for banned in ("add", "commit", "stash", "checkout", "reset",
                       "restore", "clean", "rebase", "merge"):
            self.assertNotIn(banned, flat,
                             "화면이 %s 를 불렀다: %s" % (banned, calls))

    def test_s16_a_failure_says_why(self):
        """원격이 사라진 자리 — 빈 실패는 만들지 않는다."""
        shutil.rmtree(self.remote)
        st = self.state(ask=True)
        self.assertFalse(st["remote_ok"])
        self.assertTrue(st["remote_error"], "왜 못 물었는지가 비어 있다")
        self.assertIn("GitHub", st["remote_error"])
        self.assertFalse(st["can"]["pull"]["ok"])
        self.assertEqual(st["can"]["pull"]["why"], st["remote_error"])
        res = self.m.git_do("pull", actor="boss")
        self.assertFalse(res["ok"])
        self.assertTrue(res["error"])


class TheScreenCannotEvenSpeakTheDangerousWords(GitPanelBase):
    """S14. 제약 ①③④ 는 문장이 아니라 **코드의 모양**이다.

    다음 사람이 `--force` 를 한 번 붙여 보는 순간, 실행이 아니라 이 시험이
    먼저 막는다."""

    def test_s14_forbidden_subcommands_never_reach_git(self):
        for verb in ("add", "commit", "stash", "checkout", "switch", "reset",
                     "restore", "clean", "rebase", "merge", "cherry-pick",
                     "revert", "worktree", "branch", "tag", "rm", "mv"):
            with self.assertRaises(ValueError, msg="%s 가 지나갔다" % verb):
                self.m.git_run([verb])

    def test_s14b_forbidden_flags_never_reach_git(self):
        for argv in (["push", "--force"], ["push", "-f"],
                     ["pull", "--rebase"], ["pull", "--autostash"],
                     ["fetch", "--quiet", "origin", "--prune"],
                     ["log", "--force"]):
            with self.assertRaises(ValueError,
                                   msg="%s 가 지나갔다" % " ".join(argv)):
                self.m.git_run(argv)

    def test_s14c_the_network_three_have_an_exact_shape(self):
        for argv in (["pull"], ["pull", "origin", "main"],
                     ["push", "origin", "main"], ["push", "-u"],
                     ["fetch"], ["fetch", "origin"]):
            with self.assertRaises(ValueError,
                                   msg="%s 가 지나갔다" % " ".join(argv)):
                self.m.git_run(argv)
        # 지나가야 하는 모양 셋
        self.assertEqual(self.m.git_run(["pull", "--ff-only"]).returncode, 0)
        self.assertEqual(self.m.git_run(["push"]).returncode, 0)
        self.assertEqual(
            self.m.git_run(["fetch", "--quiet", "origin"]).returncode, 0)

    def test_s14d_an_unknown_verb_is_refused(self):
        for verb in ("daemon", "credential", "config", "help"):
            with self.assertRaises(ValueError):
                self.m.git_run([verb])


class TheCaptureDoorTellsTheTruth(GitPanelBase):
    """헤드리스 캡처 갈래(`?git=`)는 **상태만** 지어낸다.

    판정과 문장은 진짜 `git_can` 을 지나므로, 캡처에 뜬 사유는 실제로 사람이
    만날 그 글자다 — 거울이 옛 문장을 들고 있으면 캡처가 거짓을 증언한다."""

    def test_every_demo_state_passes_the_real_gate(self):
        for name in self.m.GIT_DEMO:
            st = self.m.git_state(demo=name)
            self.assertEqual(st["can"], self.m.git_can(st),
                             "%s 갈래의 판정이 진짜 문 밖에서 만들어졌다" % name)

    def test_the_six_faces_are_all_reachable(self):
        want = {"same": (False, False), "push": (False, True),
                "pull": (True, False), "split": (False, False),
                "dirty": (False, True), "jobs": (False, False),
                "denied": (False, False)}
        for name, (p, s) in want.items():
            st = self.m.git_state(demo=name)
            self.assertEqual((st["can"]["pull"]["ok"], st["can"]["push"]["ok"]),
                             (p, s), "%s 갈래의 얼굴이 다르다" % name)


class TheScreenSideKeepsItsPromises(unittest.TestCase):
    """C. 화면 몫의 계약 — 주석으로 지킬 수 없는 것을 시험으로 지킨다."""

    @classmethod
    def setUpClass(cls):
        import re
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "web", "app", "repo.js"),
                  encoding="utf-8") as f:
            cls.raw = f.read()
        # 주석에는 금지어가 **근거로** 인용돼 있다 — 코드만 본다
        body = re.sub(r"/\*[\s\S]*?\*/", " ", cls.raw)
        cls.code = re.sub(r"(?m)^\s*//.*$", " ", body)

    def test_s22_the_screen_never_reaches_for_the_dangerous_verbs(self):
        """화면이 위험한 갈래를 부르는 자리가 0이다.

        서버가 이미 막지만(GIT_FORBIDDEN), 화면이 그 이름을 들고 있으면 다음
        사람이 「서버에 갈래를 하나 더 열면 되겠네」로 읽는다. 부를 생각조차
        없는 것이 이 화면의 모양이다."""
        import re
        for bad in ("commit", "stash", "reset", "restore", "clean",
                    "checkout", "--force", "--rebase"):
            self.assertNotIn("/api/git/" + bad, self.code)
            self.assertNotIn("git " + bad, self.code,
                             "화면이 「git %s」를 들고 있다" % bad)
        # 부르는 자리는 둘뿐이다
        self.assertEqual(
            sorted(set(re.findall(r'"/api/git/" \+ (\w+)', self.code))
                   | set(re.findall(r'"/api/git/(\w+)"', self.code))),
            ["what"], "서버로 나가는 자리가 하나가 아니다")

    def test_the_lock_keeps_the_keyboard_hand(self):
        """잠금은 `disabled` 가 아니라 `aria-disabled` 다 (REQ-20260831-009) —
        `disabled` 는 포커스를 걷어 키보드 손이 사유에 못 닿는다."""
        self.assertIn('setAttribute("aria-disabled"', self.code)
        self.assertNotIn(".disabled = ", self.code)
        # 사유는 낭독기에도 들린다 — 단추가 그 자리를 가리킨다
        self.assertIn("aria-describedby", self.code)
        self.assertIn('role="status"', self.code)

    def test_one_bowl_bites_only_once(self):
        """구역을 갈아도 `#sview` 는 살아남는다 — 표가 없으면 판을 다시 열
        때마다 손잡이가 한 벌씩 더 물리고, 한 번 누른 push 가 창을 둘 연다."""
        self.assertIn("host.dataset.gwired", self.code)

    def test_the_poll_cleans_itself_up(self):
        """live follow 규율 — 화면이 보일 때·요소가 있을 때만 돈다."""
        self.assertIn("document.hidden", self.code)
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "web", "app", "app.js"),
                  encoding="utf-8") as f:
            self.assertIn("gitStopPoll()", f.read(),
                          "탭을 떠날 때 걷는 자리가 없다")

    def test_the_confirm_only_guards_the_way_out(self):
        """push 만 확인 창을 지난다 — 되돌릴 수 있는 쪽에 마찰을 물리지 않는다."""
        self.assertIn("gitAskPush", self.code)
        self.assertNotIn("gitAskPull", self.code)
        self.assertIn('what === "push" && !(await gitAskPush', self.code)


if __name__ == "__main__":
    unittest.main()
