"""문서를 못 고치는 자리는 **봉투가 아니라 자리**로 푼다 (REQ-20260919-006-62x6).

실제 사고 2026-09-19: 「9/18 이후 문서를 존댓말로 고쳐라」(REQ-20260919-004-62x6)가
전용 worktree 의 백그라운드 작업자에게 갔는데 한 글자도 못 고쳤다. 적용 모드가
주는 Write·Edit(acceptEdits)는 **작업 디렉터리 안에서만** 묻지 않는데, worktree
작업자의 작업 디렉터리는 `state/worktrees/<이름>` 이고 문서는 본 저장소의
`vault/` 아래다. 바깥 경로는 사람에게 묻고, 사람이 없는 세션에서는 거부된다.

갈래는 둘이었다.
  ① **자리를 바꾼다** — 산출물이 문서인 요청은 worktree 로 보내지 않는다.
  ② **손을 준다** — worktree 작업자에게 `--add-dir` 로 데이터 경로를 열어 준다.

006 이 ①을 골랐고 ②를 반려했다: ②는 사람이 없는 자리의 작업자가 감사 없이 어떤
문서든 고칠 수 있게 하는 **보안 경계 변경**이고, 그런 스위치는 주인이 알고 켜야
한다. ①은 봉투를 하나도 넓히지 않은 채 같은 일을 되게 한다.

이 파일은 그 판정을 붙든다. 같은 벽에 다시 부딪힌 작업자가 손이 닿는 쪽(봉투)을
먼저 넓히기 쉽기 때문이다 — 실제로 2026-09-19 에 그 시도가 한 번 있었고 여기서
되돌렸다. 넓혀야 한다면 그때는 이 시험이 먼저 실패해, 주인의 판정을 거치게 된다.

지키는 성질:
  ① 작업자 봉투에 `--add-dir` 가 없다 — 데이터 경로를 열지 않는다.
  ② 봉투를 만드는 자리에 데이터 경로 이름이 섞여 있지 않다.
여는 길(자리 판정 — 문서가 산출물인 요청은 본 저장소로 간다)은 여기서 세지 않는다.
그 자리는 `tests/test_spawn_workspace.py` 의 W13·W13a 가 지킨다 — 판정이 사는 곳과
시험이 사는 곳을 맞춘다.

실행: python3 tests/ worker_data_dirs
"""
import importlib.util
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9_SRC = os.path.join(ROOT, "bin", "s9.py")


def load_s9():
    spec = importlib.util.spec_from_file_location("s9mod_data_dirs", S9_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class WorkerDataDirs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_s9()
        with open(S9_SRC, encoding="utf-8") as f:
            cls.src = f.read()
        # 봉투를 세우는 구간 — 권한 목록이 시작하는 줄부터 프롬프트가 시작하기 전까지.
        seg = cls.src[cls.src.index('perm = ["--allowedTools"'):]
        cls.envelope = seg[:seg.index("# 충돌 규율은")]

    # ---- ① 봉투는 넓히지 않는다 -------------------------------------------
    def test_n1_the_envelope_opens_no_extra_directory(self):
        """`--add-dir` 는 작업 디렉터리 밖을 여는 손이다 — 봉투에 두지 않는다."""
        self.assertNotIn("--add-dir", self.envelope,
                         "작업자 봉투가 작업 디렉터리 밖을 연다 — 006 이 반려한 갈래다")

    def test_n2_no_helper_builds_that_argument(self):
        """도우미 함수로 숨겨 두어도 같은 것이다."""
        self.assertNotIn("add_dir", self.src.replace("--add-dir", ""),
                         "`--add-dir` 를 짓는 자리가 소스에 남아 있다")

    # ---- ② 데이터 경로는 봉투의 말이 아니다 -------------------------------
    def test_b1_data_paths_are_not_named_in_the_envelope(self):
        """주석은 뺀다 — 까닭을 적는 것은 규율이고, 글은 명령이 아니다."""
        code = "\n".join(ln for ln in self.envelope.splitlines()
                         if not ln.strip().startswith("#"))
        self.assertNotIn("SYNC_DATA_PATHS", code)
        for name in ("vault", "users", "projects"):
            self.assertIsNone(
                re.search(r'["\']%s["\']' % name, code),
                "봉투가 데이터 경로를 이름으로 댄다: %s" % name)

    # ---- ③ 옛 계약은 그대로다 ---------------------------------------------
    def test_r1_the_old_envelope_contract_holds(self):
        """봉투에서 무엇을 빼면서 지키던 것을 함께 떨어뜨리지 않는다."""
        for t in ('"Read"', '"Glob"', '"Grep"', "worker_s9_tools(s9bin)",
                  '"acceptEdits"', 'cfg.get("auto_resume_apply")',
                  "WORKTREE_GIT_TOOLS"):
            self.assertIn(t, self.envelope, "봉투의 옛 계약이 빠졌다: %s" % t)


if __name__ == "__main__":
    unittest.main()
