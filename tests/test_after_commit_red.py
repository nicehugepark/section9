"""실패 기록의 파일을 담은 commit 은 넓지 않아도 전체를 띄운다 (REQ-20260915-008-62x6).

실제 사고 2026-09-15 11:38. 전체 테스트가 test_github_ui.py·test_hook_code_stamp.py 로
실패해 state/tests-last-red.json 이 섰다. 리드가 그 둘만 고쳐 담은 commit(3a332c6bf)은
tests/ 만 닿아 head_touches_wide 가 비었고 post-commit 은 전체를 띄우지 않았다 — 표식은
통과 기록(10:34)보다 새로운 채 남았고, 다음 code 커밋(실패한 파일을 담지 않은 것)은
red_ratchet 에 막혔다. 원격 러너는 미커밋 변경이 있는 동안 통과 기록을 남기지 않으니
손으로 전체를 돌려도 안 지워지고, 남는 길이 `S9_FIX_RED` 뿐이었다.

계약 둘: ① after_commit 은 실패 기록의 파일을 담은 commit 에 전체를 띄운다(head_fixes_red).
② red_ratchet 은 표식의 파일이 전부 그 실패 뒤에 commit 됐으면 막지 않는다(red_fixed_since)
— 그 commit 이 띄운 전체가 다시 실패하면 더 새로운 표식이 서므로 저절로 닫힌다.
실행: python3 tests/ after_commit_red
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

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")


class FixCommitLaunchesTheFullRun(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9acr-")
        self.git("init", "-q", "-b", "main")
        for p, body in (("bin/s9.py", "x = 1\n"), ("tests/test_x.py", "a\n"), ("tests/test_y.py", "b\n")):
            os.makedirs(os.path.join(self.root, os.path.dirname(p)), exist_ok=True)
            open(os.path.join(self.root, p), "w").write(body)
        self.commit("base")
        self.base_at = time.time()
        time.sleep(1.1)                      # git 의 초 단위 시각과 --since 가 갈리지 않게
        open(os.path.join(self.root, "tests", "test_x.py"), "a").write("fixed\n")
        self.commit("test_x 를 고친다")
        self.fix_sha = self.git("rev-parse", "HEAD")
        old = os.environ.get("S9_ROOT")
        os.environ["S9_ROOT"] = self.root
        try:
            name = "s9guard_acr_" + os.path.basename(self.root)
            spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, GUARD))
            self.m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.m)
            self.m.ROOT = self.root          # s9-guard 의 ROOT 는 제 파일 위치다 — 임시 저장소로 돌린다
            self.m.LAST_RED = os.path.join(self.root, "state", "tests-last-red.json")
        finally:
            if old is None:
                os.environ.pop("S9_ROOT", None)
            else:
                os.environ["S9_ROOT"] = old

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def git(self, *a):
        r = subprocess.run(["git", "-C", self.root, *a], capture_output=True, encoding="utf-8")
        return r.stdout.strip()

    def commit(self, msg):
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)

    def red(self, files, at):
        d = {"at": at, "fingerprint": "f", "files": files}
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        with open(self.m.LAST_RED, "w", encoding="utf-8") as f:
            json.dump(d, f)
        return d

    # 정상 — 실패한 파일을 담은 commit 은 넓지 않아도 전체 실행의 계기다
    def test_fix_commit_is_found(self):
        self.red(["test_x.py"], self.base_at)
        self.assertEqual(self.m.head_touches_wide(self.fix_sha), [], "시험 파일만 닿았는데 넓다고 한다")
        self.assertEqual(self.m.head_fixes_red(self.fix_sha), ["tests/test_x.py"],
                         "실패한 파일을 담은 commit 을 못 알아본다 — 그날 그 자리")

    # 경계 — 표식이 없거나 이름이 없으면 종전대로 넓은 파일만 본다
    def test_no_red_or_unnamed_red_is_silent(self):
        self.assertEqual(self.m.head_fixes_red(self.fix_sha), [])
        self.red(["(원격 머신)"], self.base_at)
        self.assertEqual(self.m.head_fixes_red(self.fix_sha), [])

    # 경계 — 표식의 파일을 담지 않은 tests/ 만의 commit 은 종전대로 띄우지 않는다
    def test_other_test_commit_is_not_a_fix(self):
        self.red(["test_y.py"], self.base_at)
        self.assertEqual(self.m.head_fixes_red(self.fix_sha), [])
        self.assertFalse(self.m.red_fixed_since(self.m._read_json(self.m.LAST_RED)))

    # 계약 ② — 실패한 파일이 전부 그 실패 뒤에 commit 됐으면 다음 commit 을 막지 않는다
    def test_ratchet_passes_once_the_red_files_were_committed(self):
        red = self.red(["test_x.py"], self.base_at)
        self.assertTrue(self.m.red_fixed_since(red))
        blocked, files = self.m.red_ratchet(["bin/s9.py"], red=red, green_age=None, fix_env="")
        self.assertFalse(blocked, "고치러 온 commit 이 이력에 있는데 다음 code 커밋을 막았다")
        self.assertEqual(files, ["test_x.py"])

    # 회귀 — 실패가 그 commit 보다 새로우면(다시 실패) 종전대로 막는다 · 일부만 고쳐졌어도 막는다
    def test_ratchet_still_blocks_when_the_red_is_newer_or_partial(self):
        red = self.red(["test_x.py"], time.time() + 60)
        self.assertFalse(self.m.red_fixed_since(red))
        blocked, _ = self.m.red_ratchet(["bin/s9.py"], red=red, green_age=None, fix_env="")
        self.assertTrue(blocked, "더 새로운 실패인데 지나갔다")
        red = self.red(["test_x.py", "test_y.py"], self.base_at)
        self.assertFalse(self.m.red_fixed_since(red), "둘 중 하나만 고쳐졌는데 전부 고쳐졌다고 한다")
        blocked, _ = self.m.red_ratchet(["bin/s9.py"], red=red, green_age=None, fix_env="")
        self.assertTrue(blocked)

    # 소스 계약 — after_commit 은 넓은 파일과 실패한 파일 둘 다 물은 뒤에 --is-green 을 본다
    def test_after_commit_consults_both(self):
        src = open(GUARD, encoding="utf-8").read()
        i = src.index("def after_commit(")
        seg = src[i:src.index("def ", i + 10)]
        self.assertIn("head_fixes_red(sha)", seg, "after_commit 이 실패한 파일을 담은 commit 을 묻지 않는다")
        self.assertLess(seg.index("head_fixes_red(sha)"), seg.index("--is-green"))


if __name__ == "__main__":
    unittest.main()
