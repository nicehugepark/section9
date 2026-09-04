"""규율은 지켜지지 않을 때를 대비하지 못한다 — 기계 게이트가 대비한다
(REQ-20260901-010).

2026-09-01 위임 에이전트의 `git stash` 순환이 남의 미커밋 전이·노트 113건을
작업 트리에서 걷어 갔다(REQ-20260901-004). pre-commit 훅은 커밋만 보고 작업
트리 되돌림은 못 본다 — 그래서 명령 실행 **전**의 PreToolUse(Bash) 훅이
이 저장소를 향한 파괴 명령을 거부한다. 이 파일이 지키는 성질:

  ① 파괴 명령은 exit 2 + 사유(실사고·안전 대안·의식적 우회)로 거부된다.
  ② 읽기·기록 명령과 저장소 밖 명령, `S9_GIT_OK=1` 접두는 지나간다.
  ③ 게이트 고장(비JSON 입력)은 통과다 — 게이트가 모든 Bash 를 막으면
     그날로 게이트가 뽑힌다.
  ④ 원천(hooks.json)에 배선이 있고, 역할 봉투 29종에 보조 문구가 선다.
  ⑤ **글은 명령이 아니다** (REQ-20260902-003): 따옴표·heredoc 안의 글에 그
     이름이 적혀 있어도 지나간다 — 다만 그 글자를 셸·인터프리터가 받으면
     그것은 명령이니 그대로 막힌다.

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


def run(cmd, cwd=None, raw=None):
    payload = raw if raw is not None else json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": cmd},
         "cwd": cwd or ROOT})
    return subprocess.run([GATE], input=payload, capture_output=True,
                          text=True, timeout=30)


# 낱말을 이 파일에 그대로 적으면 이 시험을 **고치는 명령** 자체가 게이트에
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
            # 같은 자리에서 또 막혔다. 문이 글을 막으면 사람은 문을 우회한다.
            # 낱말을 이 파일에 그대로 적으면 이 시험을 **고치는 명령** 자체가 게이트에
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
        with self.subTest("g7_every_envelope_carries_the_words"):
            ags = [p for p in glob.glob(os.path.join(
                ROOT, "harness", "claude", "agents", "*.md"))
                if not p.endswith("README.md")]
            self.assertGreaterEqual(len(ags), 29)
            for p in ags:
                with open(p, encoding="utf-8") as f:
                    self.assertIn("작업 트리를 되돌리는 git 명령 금지", f.read(),
                                  "봉투에 금지 문구가 없다: %s" % p)

if __name__ == "__main__":
    unittest.main()
