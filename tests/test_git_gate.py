"""규율은 지켜지지 않을 때를 대비하지 못한다 — 기계 검사가 대비한다
(REQ-20260901-010).

2026-09-01 위임 에이전트의 `git stash` 순환이 남의 미커밋 전이·노트 113건을
작업 트리에서 걷어 갔다(REQ-20260901-004). pre-commit 훅은 커밋만 보고 작업
트리 되돌림은 못 본다 — 그래서 명령 실행 **전**의 PreToolUse(Bash) 훅이
이 저장소를 향한 파괴 명령을 거부한다. 이 파일이 지키는 성질:

  ① 파괴 명령은 exit 2 + 사유(실사고·안전 대안·의식적 우회)로 거부된다.
  ② 읽기·기록 명령과 저장소 밖 명령, `S9_GIT_OK=1` 접두는 지나간다.
  ③ 검사 고장(비JSON 입력)은 통과다 — 검사가 모든 Bash 를 막으면
     그날로 사람이 검사를 꺼 버린다.
  ④ 원천(hooks.json)에 배선이 있고, 역할 봉투 29종에 보조 문구가 선다.
  ⑤ **글은 명령이 아니다** (REQ-20260902-003): 따옴표·heredoc 안의 글에 그
     이름이 적혀 있어도 지나간다 — 다만 그 글자를 셸·인터프리터가 받으면
     그것은 명령이니 그대로 막힌다.
  ⑤' **떨어져 있는 낱말은 글이다** (REQ-20260918-009-62x6): 재는 자리가 줄글이
     아니라 argv 라, `git` 다음 낱말이 하위명령일 때만 막는다 — 인터프리터가
     받는 본문이라 지워지지 않는 글도 이 규칙으로 갈린다.
  ⑥ **커밋 검사를 끄는 한 줄도 막힌다** (REQ-20260916-005): worktree 작업자의
     프롬프트 템플릿에 든 `Bash(git commit:*)` 는 뒤에 오는 무엇이든 받아, 옵션 하나로
     s9-guard(비밀·보호 경로·role·동시 작업·파일 크기)가 통째로 지나갔다.

실행: python3 tests/ git_gate
"""
import glob
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GATE = os.path.join(ROOT, "bin", "s9-git-gate")


def run(cmd, cwd=None, raw=None, auto=False):
    """검사를 한 번 돌린다. `auto` 는 사람이 없는 자리(백그라운드 작업자 세션).

    격리: 이 스위트가 백그라운드 작업자 세션에서 돌 때 상속된 S9_AUTO_RESUME 이
    판정을 바꾸면, 같은 시험이 자리마다 다른 답을 낸다 — 늘 지운 뒤 건다."""
    payload = raw if raw is not None else json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": cmd},
         "cwd": cwd or ROOT})
    env = {k: v for k, v in os.environ.items() if k != "S9_AUTO_RESUME"}
    if auto:
        env["S9_AUTO_RESUME"] = "1"
    return subprocess.run([GATE], input=payload, capture_output=True,
                          text=True, timeout=30, env=env)


# 낱말을 이 파일에 그대로 적으면 이 시험을 **고치는 명령** 자체가 검사에
# 걸린다 — 그래서 이어 붙여 만든다. 이 한 줄이 결함의 크기를 말해 준다.
BAD = "git" + " " + "st" + "ash"


class TheGateStands(unittest.TestCase):
    def test_the_gate_stands(self):
        """① 파괴 명령 일곱 얼굴이 전부 걸린다 — 체인 속에서도."""
        with self.subTest("g1_destructive_commands_are_refused"):
            for cmd in ("git stash",
                        "git stash pop",
                        "git stash drop stash@{0}",
                        "cd sub && git stash push -m wip",
                        "git reset --hard HEAD~1",
                        "git checkout -- web/app/card.js",
                        "git checkout .",
                        "git restore web/",
                        "git clean -fd"):
                r = run(cmd)
                self.assertEqual(2, r.returncode, "안 막혔다: %s" % cmd)
                self.assertIn("113건", r.stderr, "사유에 실사고 근거가 없다")
                self.assertIn("git show", r.stderr, "안전 대안이 없다")
                self.assertIn("S9_GIT_OK=1", r.stderr, "우회 안내가 없다")
        with self.subTest("g2_reads_and_records_pass"):
                for cmd in ("git status --short",
                            "git log --oneline -5",
                            "git diff --cached",
                            "git show 0042d6dd:vault/x.md",
                            "git stash list",
                            "git stash show -p stash@{0}",
                            "git restore --staged web/app/card.js",
                            "git add -A && git commit -m x",
                            "git push origin main"):
                    r = run(cmd)
                    self.assertEqual(0, r.returncode,
                                     "막을 것이 아닌데 막았다: %s\n%s" % (cmd, r.stderr))

            # ---- ⑤ 글과 명령을 가른다 (REQ-20260902-003) ------------------------
            # 실사고: 위임 에이전트가 판정 노트에 금지 명령 이름을 적었다는 이유로
            # 두 번 막혀 산출물이 사라졌고, 리드가 그 결함을 요청으로 등록하려다
            # 같은 자리에서 또 막혔다. 검사가 글을 막으면 사람은 검사를 우회한다.
            # 낱말을 이 파일에 그대로 적으면 이 시험을 **고치는 명령** 자체가 검사에
            # 걸리므로, 이어 붙여 만든다 — 이것이 결함의 크기를 말해 준다.
        with self.subTest("g8_prose_is_not_a_command"):
            for cmd in (
                    # 노트 본문 heredoc — 실제로 막혔던 그 모양
                    'bin/s9 note REQ-1 "$(cat <<\'EOF\'\n'
                    '- **금지** — %s 는 남의 미커밋 작업을 지운다\nEOF\n)"' % BAD,
                    # 따옴표 안 인자
                    'bin/s9 note REQ-1 "그 명령(%s)은 금지다"' % BAD,
                    "bin/s9 set REQ-1 --body '%s 를 쓰지 마라'" % BAD,
                    # 인터프리터가 아닌 명령에 딸린 heredoc
                    "cat <<'EOF' > /tmp/x\n%s\nEOF" % BAD):
                r = run(cmd)
                self.assertEqual(0, r.returncode,
                                 "글을 명령으로 읽었다: %s\n%s" % (cmd, r.stderr))
        with self.subTest("g9_interpreters_are_still_read_as_commands"):
            for cmd in ('bash -c "%s"' % BAD,
                        "sh -c '%s'" % BAD,
                        "eval '%s'" % BAD,
                        "sh <<'EOF'\n%s\nEOF" % BAD,
                        "python3 - <<'PY'\nrun('%s')\nPY" % BAD):
                r = run(cmd)
                self.assertEqual(2, r.returncode,
                                 "인터프리터가 받는 글자를 놓쳤다: %s" % cmd)
        with self.subTest("g10_unparsable_falls_back_to_the_old_verdict"):
            self.assertEqual(2, run('bin/s9 note X "%s' % BAD).returncode)
        with self.subTest("g3_other_repos_are_none_of_our_business"):
            with tempfile.TemporaryDirectory(prefix="s9gate-") as td:
                self.assertEqual(0, run("git stash", cwd=td).returncode)
                self.assertEqual(
                    0, run(f"git -C {td} stash", cwd=td).returncode)
                # -C 로 이 저장소를 겨누면 밖에 있어도 걸린다
                self.assertEqual(
                    2, run(f"git -C {ROOT} stash", cwd=td).returncode)
        with self.subTest("g4_the_conscious_override_passes"):
            self.assertEqual(0, run("S9_GIT_OK=1 git stash pop").returncode)

        # ---- 인자를 다시 실행하는 명령 (REQ-20260916-004-62x6) --------------
        # `s9` 는 인터프리터가 아니라 따옴표 본문이 **글**로 지워졌는데,
        # `secret run` 하위명령은 그 글을 실제로 실행한다 — 2026-09-01 사고와
        # 같은 결과가 검사를 그대로 지나갔다.
        with self.subTest("g11_arg_reexecutors_are_read_as_commands"):
            for cmd in ('bin/s9 secret run -- sh -c "%s"' % BAD,
                        '%s/bin/s9 secret run -- bash -c "%s"' % (ROOT, BAD),
                        'timeout 60 bash -c "%s"' % BAD,
                        'stdbuf -o0 sh -c "%s"' % BAD):
                r = run(cmd)
                self.assertEqual(2, r.returncode,
                                 "받은 글자를 다시 실행하는 명령을 놓쳤다: %s" % cmd)
        with self.subTest("g12_prose_about_the_executor_still_passes"):
            # 이 결함을 **문서로 남기는 명령** 자체가 막히면, 고친 값이 없다.
            for cmd in ('bin/s9 note REQ-1 "s9 secret run -- sh -c \'%s\' 은 금지"'
                        % BAD,
                        "bin/s9 note REQ-1 --label x 'secret run 이 실행기다' "
                        "--body '%s 를 쓰지 마라'" % BAD):
                r = run(cmd)
                self.assertEqual(0, r.returncode,
                                 "글을 명령으로 읽었다: %s\n%s" % (cmd, r.stderr))
        # ---- 낱말이 떨어져 있으면 글이다 (REQ-20260918-009-62x6) -----------
        # 실사고 2026-09-18: 릴리스 노트 본문에 「망을 타는 git 셋」과
        # 「s9 stash」가 **따로** 적혀 있었을 뿐인데 그 글을 파일에 쓰는 명령이
        # 거부됐다 — 무늬의 틈(`[^|;&]*`)이 줄바꿈까지 건너뛰어 아무리 멀리
        # 떨어진 두 낱말도 한 명령으로 읽었다. 인터프리터가 받는 본문이라
        # 글로 지워지지도 않는다: 그래서 재는 자리를 줄글에서 argv 로 옮겼다.
        with self.subTest("g15_words_apart_in_a_body_are_prose"):
            body = ("python3 - <<'PY'\n"
                    "open('docs/RELEASE-NOTES.md','a').write('%s')\n"
                    "PY")
            for line in ("망을 타는 git 셋 — s9 %s 로 대신한다" % BAD.split()[1],
                         "git 의 reset 은 --hard 를 쓰지 마라",
                         "git 에서 checkout -- 로 되돌리지 마라",
                         "git 의 restore 는 작업 트리를 지운다",
                         "git 의 clean -fd 는 금지다",
                         "git 으로 commit 할 때 --no-verify 금지",
                         "git 의 설정(core.hooksPath)은 건드리지 마라"):
                r = run(body % line)
                self.assertEqual(0, r.returncode,
                                 "글을 명령으로 읽었다: %s\n%s" % (line, r.stderr))
        with self.subTest("g16_argv_reading_does_not_lose_the_real_commands"):
            # argv 로 읽어도 파이프·서브셸·전역 옵션·경로 뒤의 명령은 그대로.
            for cmd in ("echo x | %s" % BAD,
                        "(cd sub && %s)" % BAD,
                        "git -C . stash",
                        "git --no-pager stash pop",
                        "/usr/bin/git stash",
                        "git clean --force",
                        # 인터프리터 본문에 **붙어 있는** 두 낱말은 명령이다
                        "python3 - <<'PY'\nrun('%s')\nPY" % BAD):
                r = run(cmd)
                self.assertEqual(2, r.returncode, "안 막혔다: %s" % cmd)
        with self.subTest("g13_lookalike_names_are_not_interpreters"):
            # 이름 끝을 못박기 전에는 `shred`·`shutdown` 까지 인터프리터였다.
            self.assertEqual(0, run('shred -u "%s"' % BAD).returncode)
        with self.subTest("g14_the_override_does_not_work_unattended"):
            # 훅은 사람의 Bash 와 모델의 Bash 를 구별하지 못한다 — 사람이 없는
            # 자리에서는 「사람의 확인을 받아 붙인다」가 거짓이 된다.
            r = run("S9_GIT_OK=1 git stash pop", auto=True)
            self.assertEqual(2, r.returncode, "무인 세션에서 우회가 통했다")
            self.assertIn("백그라운드 작업자", r.stderr)
            self.assertIn("blocked", r.stderr, "다음에 할 것이 안 적혀 있다")
        with self.subTest("g5_a_broken_payload_does_not_block_the_world"):
            self.assertEqual(0, run("", raw="this is not json").returncode)
            self.assertEqual(0, run("", raw=json.dumps(
                {"tool_name": "Read", "tool_input": {}})).returncode)
        with self.subTest("g6_the_wiring_is_in_the_source"):
            with open(os.path.join(ROOT, "harness", "claude", "hooks.json"),
                      encoding="utf-8") as f:
                hooks = json.load(f)["hooks"]
            pre = hooks.get("PreToolUse") or []
            rows = [h for grp in pre if grp.get("matcher") == "Bash"
                    for h in grp.get("hooks", [])]
            self.assertTrue(any("s9-git-gate" in h.get("command", "")
                                for h in rows), "PreToolUse Bash 배선이 없다")
        with self.subTest("g11_commit_check_bypass_is_refused"):
            # ⑥ 커밋 검사를 끄는 한 줄 (REQ-20260916-005). 사유는 작업 트리
            # 갈래와 달라야 한다 — 「113건 유실」은 여기서 할 말이 아니다.
            for cmd in ("git commit --no-verify -m x",
                        "git commit -n -m x",
                        "git commit -an -m x",
                        "git add -A && git commit --no-verify -m x",
                        'bash -c "git commit --no-verify -m x"',
                        "git -c core.hooksPath=/dev/null commit -m x"):
                r = run(cmd)
                self.assertEqual(2, r.returncode, "안 막혔다: %s" % cmd)
                self.assertIn("s9-guard", r.stderr, "무엇이 꺼지는지가 없다")
                self.assertIn("blocked", r.stderr, "막혔을 때 갈 길이 없다")
                self.assertIn("S9_GIT_OK=1", r.stderr, "우회 안내가 없다")
        with self.subTest("g12_ordinary_commits_still_pass"):
            for cmd in ("git commit -m x",
                        "git commit -am x",
                        "git commit --amend --no-edit",
                        "git commit --no-edit --amend",
                        # 메시지 안의 옵션 이름 — `-m` 뒤 따옴표는 글이다
                        "git commit -m '-n 을 쓰지 마라'",
                        # 글 안의 옵션 이름은 명령이 아니다 (⑤ 와 같은 갈래)
                        "bin/s9 note REQ-1 '커밋에 -n 을 붙이지 마라'",
                        "bin/s9 commit -m '검사를 --no-verify 로 끄지 마라'"):
                r = run(cmd)
                self.assertEqual(0, r.returncode,
                                 "막을 것이 아닌데 막았다: %s\n%s" % (cmd, r.stderr))
            with tempfile.TemporaryDirectory(prefix="s9gate-") as td:
                self.assertEqual(0, run("git commit --no-verify -m x",
                                        cwd=td).returncode)
            self.assertEqual(
                0, run("S9_GIT_OK=1 git commit --no-verify -m x").returncode)
        with self.subTest("g7_every_envelope_carries_the_words"):
            ags = [p for p in glob.glob(os.path.join(
                ROOT, "harness", "claude", "agents", "*.md"))
                if not p.endswith("README.md")]
            self.assertGreaterEqual(len(ags), 29)
            for p in ags:
                with open(p, encoding="utf-8") as f:
                    self.assertIn("working tree 를 되돌리는 git 명령 금지", f.read(),
                                  "봉투에 금지 문구가 없다: %s" % p)

if __name__ == "__main__":
    unittest.main()
