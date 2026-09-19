"""worktree 작업자에게도 문서를 고칠 손이 있어야 한다 (REQ-20260919-006-62x6).

실제 사고 2026-09-19: 「9/18 이후 문서를 존댓말로 고쳐라」(REQ-20260919-004-62x6)가
전용 worktree 의 백그라운드 작업자에게 갔는데 한 글자도 못 고쳤다. 적용 모드가
주는 Write·Edit(acceptEdits)는 **작업 디렉터리 안에서만** 묻지 않는데, worktree
작업자의 작업 디렉터리는 `state/worktrees/<이름>` 이고 문서는 본 저장소의
`vault/` 아래다. 바깥 경로는 사람에게 묻고, 사람이 없는 세션에서는 그대로
거부된다. 리드 한 번과 위임한 에이전트 넷이 전부 같은 자리에서 막혔고, 사람에게는
「왜 안 끝났나」로만 보였다.

이 파일이 지키는 성질:
  ① worktree + 적용 모드면 데이터 경로(vault·users·projects)가 `--add-dir` 로 열린다.
  ② 그 인자는 `--allowedTools` **앞**에 선다 — 뒤에 붙으면 도구 이름으로 새어 든다.
  ③ 적용 모드가 아니거나 본 저장소에서 도는 작업자면 아무것도 열지 않는다.
  ④ 여는 것은 데이터 경로뿐이다 — bin·tests·harness 는 열리지 않는다.
  ⑤ worktree 프롬프트가 「사본 말고 본 저장소의 문서를 고쳐라」를 말한다.

실행: python3 tests/ worker_data_dirs
"""
import importlib.util
import os
import tempfile
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
        cls.tmp = tempfile.mkdtemp(prefix="s9-data-dirs-")
        for d in ("vault", "users", "projects", "bin", "tests", "harness"):
            os.makedirs(os.path.join(cls.tmp, d), exist_ok=True)

    def args(self, cfg, wt_name):
        return self.mod.worker_add_dir_args(cfg, wt_name, root=self.tmp)

    # ---- ① 문서를 고칠 손 -------------------------------------------------
    def test_n1_worktree_apply_opens_the_data_paths(self):
        """적용 모드의 worktree 작업자는 본 저장소의 문서를 고칠 수 있다."""
        got = self.args({"auto_resume_apply": True}, "w-919-004-62x6")
        for d in ("vault", "users", "projects"):
            self.assertIn(os.path.join(self.tmp, d), got,
                          "데이터 경로가 안 열렸다: %s" % d)

    def test_n2_every_opened_path_is_paired_with_the_flag(self):
        """`--add-dir <경로>` 짝이 맞아야 인자가 인자로 읽힌다."""
        got = self.args({"auto_resume_apply": True}, "w-919-004-62x6")
        self.assertEqual(0, len(got) % 2, "짝이 안 맞는다: %r" % (got,))
        self.assertEqual(["--add-dir"] * (len(got) // 2), got[0::2])

    # ---- ② 자리 -----------------------------------------------------------
    def test_b1_it_stands_before_allowed_tools(self):
        """`--allowedTools` 는 값을 여럿 받는다 — 뒤에 붙으면 도구 이름이 된다."""
        seg = self.src[self.src.index("perm = worker_add_dir_args("):]
        seg = seg[:seg.index("\n")]
        self.assertIn("worker_add_dir_args(cfg, wt_name) + perm", seg,
                      "데이터 경로 인자가 권한 목록 앞에 서지 않는다: %s" % seg)

    # ---- ③ 열지 않는 자리 --------------------------------------------------
    def test_b2_no_worktree_opens_nothing(self):
        """본 저장소에서 도는 작업자는 이미 그 셋이 작업 디렉터리 안이다."""
        self.assertEqual([], self.args({"auto_resume_apply": True}, ""))

    def test_b3_without_apply_mode_opens_nothing(self):
        """기본 봉투에는 Write·Edit 자체가 없어 열어도 여는 것이 없다."""
        self.assertEqual([], self.args({}, "w-919-004-62x6"))
        self.assertEqual([], self.args({"auto_resume_apply": False},
                                       "w-919-004-62x6"))
        self.assertEqual([], self.args(None, "w-919-004-62x6"))

    def test_b4_missing_paths_are_skipped(self):
        """없는 자리를 열라고 하면 그 인자 하나로 작업자가 안 뜬다."""
        empty = tempfile.mkdtemp(prefix="s9-data-dirs-empty-")
        self.assertEqual([], self.mod.worker_add_dir_args(
            {"auto_resume_apply": True}, "w-1", root=empty))

    # ---- ④ 데이터만 --------------------------------------------------------
    def test_f1_code_paths_stay_outside(self):
        """여는 것은 데이터 한 벌이지 코드가 아니다 — 코드는 worktree 사본이다."""
        got = self.args({"auto_resume_apply": True}, "w-919-004-62x6")
        for d in ("bin", "tests", "harness", "web"):
            self.assertNotIn(os.path.join(self.tmp, d), got,
                             "코드 경로가 열렸다: %s" % d)

    def test_f2_the_list_is_the_one_sync_uses(self):
        """데이터가 무엇인지는 한 곳에서만 정한다 — 두 벌이면 언젠가 갈린다."""
        got = self.args({"auto_resume_apply": True}, "w-919-004-62x6")
        for p in got[1::2]:
            self.assertIn(os.path.basename(p), self.mod.SYNC_DATA_PATHS)

    # ---- ⑤ 사본을 고치지 않게 ---------------------------------------------
    def test_r1_the_prompt_points_at_the_live_vault(self):
        """사본은 가지를 딸 때의 옛 판이다 — 고치면 두 벌이 갈린다."""
        seg = self.src[self.src.index("[작업 자리] 너는 이 요청 전용 worktree"):]
        seg = seg[:seg.index("[이 세션에는 나중이 없다]")]
        self.assertIn("본 저장소의", seg)
        self.assertIn("옛 판", seg)


if __name__ == "__main__":
    unittest.main()
