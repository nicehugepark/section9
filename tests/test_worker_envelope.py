"""권한 목록이 경계가 되려면, 목록 안에 범용 실행기가 없어야 한다
(REQ-20260916-004-62x6).

실제 결함 2026-09-16(보안 축 점검): 무인 작업자의 권한 목록은
`Read · Glob · Grep · Bash(<ROOT>/bin/s9:*)` 한 줄짜리였다. 읽기만 하는
자리라고 적어 두고, 그 안에 **무엇이든 실행하는 길**이 있었다 —
`s9 secret run -- sh -c '<명령>'` 은 치환한 argv 를 그대로 실행한다.
적용 모드(auto_resume_apply)를 켜지 않아도 열려 있던 길이다.

같은 결의 둘이 더 있었다:
  · `Bash(cp <ROOT>/web/:*)` 는 출처만 묶고 **목적지가 자유**였다 —
    워크스페이스에서 만든 파일을 저장소 밖(`~/.claude/settings.json`)으로
    옮길 수 있었다.
  · `s9 code -- <claude 인자>` · `s9 resume <sid> -p '<프롬프트>'` ·
    `s9 config apply --with-permissions` · `s9 user config <사람>
    auto_resume_apply on` 은 **다음 세션의 권한 목록을 스스로 고르는** 길이다.

이 파일이 지키는 성질:
  ① 목록은 하위명령 단위다 — 명령 이름 한 줄(`Bash(<s9>:*)`)은 없다.
  ② 실행기·권한을 바꾸는 하위명령은 목록 밖이고, 작업자가 실제로 쓰는
     하위명령(show·status·note·last·claim·commit·shot·worktree)은 안이다.
  ③ 등록된 하위명령 **전부**가 허용/거부 중 한쪽에 분류돼 있다 — 새
     하위명령을 더하면 분류할 때까지 이 시험이 실패한다(목록이 조용히
     낡는 것을 막는 자리).
  ④ 적용 모드에도 목적지가 자유로운 복사가 없다.
  ⑤ 옛 계약은 그대로다: 읽기 셋 · 적용 모드는 acceptEdits · gh 는 따로.

실행: python3 tests/ worker_envelope
"""
import importlib.util
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9_SRC = os.path.join(ROOT, "bin", "s9.py")


def load_s9():
    spec = importlib.util.spec_from_file_location("s9mod_envelope", S9_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class WorkerEnvelope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_s9()
        cls.s9bin = "/tmp/s9root/bin/s9"
        cls.tools = cls.mod.worker_s9_tools(cls.s9bin)
        with open(S9_SRC, encoding="utf-8") as f:
            cls.src = f.read()

    # ---- ① 목록은 하위명령 단위다 -------------------------------------
    def test_n1_the_list_is_per_subcommand(self):
        """줄마다 하위명령 하나 — 그래야 빠진 이름이 막히는 쪽으로 틀린다."""
        self.assertTrue(self.tools, "s9 줄이 하나도 없다")
        for t in self.tools:
            m = re.fullmatch(r"Bash\(%s ([a-z][a-z-]*):\*\)"
                             % re.escape(self.s9bin), t)
            self.assertIsNotNone(m, "하위명령 한 줄의 모양이 아니다: %s" % t)

    def test_b2_no_whole_binary_line(self):
        """`Bash(<s9>:*)` 한 줄이 살아 있으면 위의 모든 줄이 장식이 된다."""
        self.assertNotIn("Bash(%s:*)" % self.s9bin, self.tools)
        self.assertNotIn('f"Bash({s9bin}:*)"', self.src,
                         "명령 이름 통짜 줄이 소스에 남아 있다")

    # ---- ② 실행기는 밖, 일감은 안 ---------------------------------------
    def test_n2_no_general_purpose_executor(self):
        """작업자가 부를 수 있는 것 중 임의 명령을 실행하는 길이 없다."""
        allowed = set(self.mod.WORKER_ALLOWED_SUBCOMMANDS)
        for sub in ("secret", "tunnel", "code", "resume", "config", "user",
                    "account", "env", "uninstall", "instance", "github",
                    "release", "reset", "purge"):
            self.assertNotIn(sub, allowed, "실행기·권한 변경이 목록 안에 있다: %s" % sub)
            self.assertIn(sub, self.mod.WORKER_DENIED_SUBCOMMANDS, sub)
            self.assertNotIn("Bash(%s %s:*)" % (self.s9bin, sub), self.tools)

    def test_n1b_the_worker_can_still_do_its_job(self):
        """막기만 하고 일을 못 하게 하면 다음 사람이 목록을 통째로 되돌린다."""
        for sub in ("show", "status", "note", "last", "claim", "log", "new",
                    "set", "link", "search", "ls", "digest", "shot", "commit",
                    "worktree", "blocked", "bind", "now"):
            self.assertIn("Bash(%s %s:*)" % (self.s9bin, sub), self.tools,
                          "작업자가 쓰는 하위명령이 빠졌다: %s" % sub)

    # ---- ③ 목록이 조용히 낡지 않는다 -------------------------------------
    def test_b1_every_subcommand_is_classified(self):
        """새 하위명령은 분류될 때까지 여기서 걸린다 — 기본값이 '허용'이 아니다."""
        registered = set(re.findall(r'sub\.add_parser\(\s*"([^"]+)"', self.src))
        self.assertGreater(len(registered), 60, "하위명령을 못 읽었다")
        allowed = set(self.mod.WORKER_ALLOWED_SUBCOMMANDS)
        denied = set(self.mod.WORKER_DENIED_SUBCOMMANDS)
        self.assertEqual(set(), allowed & denied, "양쪽에 있는 이름")
        self.assertEqual(set(), registered - (allowed | denied),
                         "분류되지 않은 하위명령 — 허용/거부 중 하나로 적어라")
        self.assertEqual(set(), (allowed | denied) - registered,
                         "없는 하위명령이 목록에 있다")

    # ---- ④ 목적지가 자유로운 복사 ---------------------------------------
    def test_f1_no_free_destination_copy(self):
        """출처만 묶은 복사는 저장소 밖으로 나가는 길이었다."""
        seg = self.src[self.src.index('perm = ["--allowedTools"'):]
        seg = seg[:seg.index("if wt_name:")]
        # 주석은 뺀다 — 걷어 낸 이유를 그 자리에 적어 두는 것이 규율이고,
        # 그 설명 안의 이름까지 세면 설명을 못 적게 된다(글은 명령이 아니다).
        code = "\n".join(ln for ln in seg.splitlines()
                         if not ln.strip().startswith("#"))
        self.assertNotIn("Bash(cp ", code,
                         "목적지가 자유로운 복사가 권한 목록에 남아 있다")

    # ---- ⑤ 옛 계약 ------------------------------------------------------
    def test_r4_the_old_contract_holds(self):
        """고치면서 지키던 것을 떨어뜨리지 않는다."""
        seg = self.src[self.src.index('perm = ["--allowedTools"'):]
        seg = seg[:seg.index("# 충돌 규율은")]
        for t in ('"Read"', '"Glob"', '"Grep"', "worker_s9_tools(s9bin)",
                  '"acceptEdits"', 'cfg.get("auto_resume_apply")',
                  'cfg.get("auto_resume_gh")', "WORKTREE_GIT_TOOLS"):
            self.assertIn(t, seg, "권한 목록의 옛 계약이 빠졌다: %s" % t)
        head = seg[:seg.index("if cfg.get(")]
        self.assertNotIn("gh", head, "기본 권한 목록에 gh 가 들어 있다")


if __name__ == "__main__":
    unittest.main()
