"""「본 저장소」라고 판정했으면 정말로 본 저장소에 앉아야 한다
(REQ-20260919-004-62x6, 실제 사고 2026-09-19 11:08).

`worker_workspace` 로 들어오는 cwd 는 담당 세션의 바인딩이 적어 둔 자리다. 그
세션이 앞 회차에 worktree 에서 돌았으면 바인딩의 cwd 는 그 worktree 이고, 판정이
`main` 이어도 이 자리는 그것을 **그대로 돌려줬다.**

그날 「9/18 이후 문서를 존댓말로 고쳐라」가 두 번 그 어긋남에 걸렸다. 자리 판정은
`worktree-exists` 로 본 저장소를 가리켰고 프롬프트도 본 저장소 갈래(동시 작업
규율·네 차례)로 나갔는데, 작업자가 실제로 선 곳은 worktree 였다. 문서는 본 저장소
`vault/` 아래에 있고 그 자리에서는 작업 디렉터리 밖이라, 작업자는 Edit 거부만
받고 한 글자도 못 고친 채 멈췄다. 사람에게는 「왜 또 안 끝났나」로만 보였다.

지키는 성질:
  ① 판정이 main 인데 cwd 가 이 저장소의 worktree 면 본 저장소로 되돌린다.
  ② 저장소 밖의 다른 자리는 건드리지 않는다 — 되돌리는 것은 worktree 일 때뿐이다.
  ③ 판정이 worktree 면 종전대로 자리를 만든다(이 길은 손대지 않았다).

실행: python3 tests/ workspace_leaves_worktree
"""
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9_SRC = os.path.join(ROOT, "bin", "s9.py")


def load_s9():
    spec = importlib.util.spec_from_file_location("s9mod_wsleave", S9_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class WorkspaceLeavesWorktree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_s9()

    def go(self, cwd, reason="worktree-exists"):
        dec = {"kind": "main", "reason": reason, "scope": None,
               "blocking": [], "wt": ""}
        return self.mod.worker_workspace("REQ-20260919-004-62x6", {}, cwd,
                                         dec=dec)

    # ---- ① 판정대로 앉는다 -------------------------------------------------
    def test_n1_a_worktree_cwd_goes_back_to_the_repo(self):
        """판정이 본 저장소면 앞 회차의 worktree 자리를 물려받지 않는다."""
        wt = os.path.join(self.mod.WORKTREE_HOME, "w-919-004-62x6")
        cwd, env, name = self.go(wt)
        self.assertEqual(self.mod.ROOT, cwd,
                         "판정은 본 저장소인데 자리는 worktree 그대로다")
        self.assertEqual("", name)
        self.assertEqual({}, env)

    def test_n2_a_subdirectory_of_a_worktree_too(self):
        """자리는 worktree 안쪽 어디여도 같은 사본이다."""
        deep = os.path.join(self.mod.WORKTREE_HOME, "w-1", "web", "app")
        self.assertEqual(self.mod.ROOT, self.go(deep)[0])

    def test_n3_every_main_reason_leaves(self):
        """되돌리는 까닭은 하나가 아니다 — main 이라고 한 모든 판정이 그렇다."""
        wt = os.path.join(self.mod.WORKTREE_HOME, "w-1")
        for why in ("off", "worktree-pile", "worktree-exists", "live-verify",
                    "self-edit", "dirty-overlap", "doc-work"):
            self.assertEqual(self.mod.ROOT, self.go(wt, why)[0], why)

    # ---- ② 남의 자리는 건드리지 않는다 -------------------------------------
    def test_b1_the_repo_itself_is_left_alone(self):
        """이미 본 저장소면 바꿀 것이 없다."""
        self.assertEqual(self.mod.ROOT, self.go(self.mod.ROOT)[0])

    def test_b2_an_outside_directory_is_left_alone(self):
        """다른 프로젝트의 자리를 우리 저장소로 끌어오지 않는다."""
        out = tempfile.mkdtemp(prefix="s9-elsewhere-")
        self.assertEqual(out, self.go(out)[0])

    def test_b3_a_lookalike_name_is_not_a_worktree(self):
        """이름이 비슷한 이웃 디렉터리는 그 안이 아니다."""
        near = self.mod.WORKTREE_HOME + "-backup"
        self.assertEqual(near, self.go(near)[0])

    def test_b4_an_empty_cwd_does_not_crash(self):
        """자리를 모를 때 되돌리기가 터지면 작업자가 아예 안 뜬다."""
        self.assertEqual("", self.go("")[0])

    # ---- ③ worktree 길은 그대로 -------------------------------------------
    def test_r1_the_worktree_branch_is_untouched(self):
        """고치면서 반대쪽 길을 떨어뜨리지 않는다 — 거기는 자리를 만든다."""
        src = open(S9_SRC, encoding="utf-8").read()
        seg = src[src.index("def worker_workspace("):]
        seg = seg[:seg.index("\ndef ", 10)]
        self.assertIn("worker_worktree_name(doc_id)", seg)
        self.assertIn('{"S9_ROOT": ROOT}', seg)


if __name__ == "__main__":
    unittest.main()
