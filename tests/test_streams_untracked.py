"""대화 기록은 리포에 다시 실리지 않는다 (REQ-20260827-047-62x6).

이 리포는 공개다. 2026-08-27 20:21 의 커밋 하나(c16d407)가 대화 미러 158MB 를
이력에 실었고, 같은 날 filter-branch 로 걷어냈다. git 은 지운 것도 기억하므로
보관 기간을 아무리 짧게 둬도 **이력은 영구 누적**이었다 — 한 달 0.3GB 규모.
되돌릴 기회는 그 커밋이 원격의 tip 이던 그때뿐이었다.

그래서 막는 것은 "다시 들어오는 길"이다. 길은 둘이다.
  ① .gitignore 에서 streams 줄이 사라진다 (누가 정리하다 지운다)
  ② 미러를 쓰는 코드가 **다른 자리로 옮겨 간다** — 사용자별 보관
     (`users/<u>/streams/`)으로 옮기는 일이 이 요청에 남아 있다. 옮긴 자리가
     ignore 밖이면 .gitignore 는 멀쩡한 채로 158MB 가 다시 실린다.

②를 잡으려면 .gitignore 만 읽어서는 안 된다. **미러 코드가 실제로 만든 파일**을
git 에게 물어야 한다. 그래서 이 테스트는 임시 리포에 이 리포의 .gitignore 를
그대로 깔고, 훅의 미러 함수를 진짜로 돌린 뒤 `git add -A` 로 무엇이 담기는지
본다. 미러가 어디로 가든, 담기면 실패한다.

실행: python3 tests/ streams_untracked
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
STOP_HOOK = os.path.join(ROOT, "bin", "s9-audit-response")
GITIGNORE = os.path.join(ROOT, ".gitignore")


# 훅 아래에서 돌 때 물려받는 GIT_DIR 을 벗긴다 (REQ-20260829-005). `-C <경로>`
# 는 GIT_DIR 을 이기지 못한다 — 벗기지 않으면 임시 리포에 하려던 `git init` 이
# 본 저장소의 공용 config 를 bare 로 뒤집는다.
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_INDEX_VERSION",
                "GIT_QUARANTINE_PATH")


def clean_git_env():
    e = dict(os.environ)
    for k in GIT_ENV_VARS:
        e.pop(k, None)
    return e


def git(*argv, cwd=ROOT):
    return subprocess.run(["git", "-C", cwd, *argv], env=clean_git_env(),
                          capture_output=True, text=True, timeout=30)


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stream_paths(names):
    """`streams` 디렉토리 아래에 있는 경로만 골라낸다 — 자리를 옮겨도 잡힌다."""
    return [n for n in names
            if "streams/" in n.replace("\\", "/") and n.strip()]


def in_repo():
    """저장소인가 — `.git` 이 디렉토리인지로 묻지 않는다 (REQ-20260829-001).

    워크트리의 `.git` 은 파일이라 그 질문은 늘 '아니오'다. 그러면 이 검사가
    통째로 사라지는데, 158MB 미러를 실을 위험이 가장 큰 자리가 바로 무인
    워커가 커밋하는 워크트리다. git 에게 물으면 두 자리 모두에서 산다."""
    r = git("rev-parse", "--is-inside-work-tree")
    return r.returncode == 0 and r.stdout.strip() == "true"


@unittest.skipUnless(in_repo(), "git 리포가 아니면 이력을 물을 수 없다")
class StreamsUntracked(unittest.TestCase):
    """이 리포의 지금 상태 — 인덱스와 HEAD 이력에 미러가 없어야 한다."""

    # N1. 지금 track 되는 파일 중 미러가 없다
    def test_streams_untracked(self):
        """이 리포의 지금 상태 — 인덱스와 HEAD 이력에 미러가 없어야 한다."""
        with self.subTest("n1_index_has_no_mirror"):
                names = git("ls-files").stdout.splitlines()
                self.assertEqual(_stream_paths(names), [],
                                 "미러가 인덱스에 있다 — 다음 커밋에 실린다")

            # N2. HEAD 트리에도 없다
        with self.subTest("n2_head_tree_has_no_mirror"):
                names = git("ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
                self.assertEqual(_stream_paths(names), [])

            # N3. HEAD 에서 거슬러 올라간 **이력 전체**에도 없다.
            #     재작성이 되돌려지거나(backup 브랜치 merge) 새로 실리면 여기서 걸린다.
        with self.subTest("n3_history_has_no_mirror"):
                out = git("log", "--oneline", "--",
                          "streams", "users/*/streams").stdout.strip()
                self.assertEqual(out, "", f"이력에 미러를 담은 커밋이 있다:\n{out}")

            # N4. 지금 자리와 옮겨 갈 자리 둘 다 ignore 다 —
            #     옮기고 나서 막으면 옮긴 경로가 또 한 번 이력에 실린다
        with self.subTest("n4_both_locations_ignored"):
                for rel in ("streams/abc.jsonl",
                            "users/sjpark1/streams/abc.jsonl"):
                    with self.subTest(rel=rel):
                        self.assertEqual(git("check-ignore", "-q", rel).returncode, 0,
                                         f"{rel} 이 ignore 밖이다")

            # B1. vault/users/projects 는 계속 track 한다 — 이 요청이 바꾼 것은
            #     대화 원문 158MB 뿐이고, 하네스 기록 공개 판정(REQ-20260827-036)은 유효하다
        with self.subTest("b1_vault_still_tracked"):
                for rel in ("vault", "users", "projects"):
                    with self.subTest(rel=rel):
                        if not os.path.isdir(os.path.join(ROOT, rel)):
                            continue
                        n = len(git("ls-files", "--", rel).stdout.splitlines())
                        self.assertGreater(n, 0, f"{rel} 이 통째로 ignore 됐다")

            # B2. 비밀값은 여전히 막혀 있다 (REQ-20260827-035) —
            #     users/ 를 track 하므로 이 줄이 사라지면 그대로 올라간다
        with self.subTest("b2_secrets_still_ignored"):
            self.assertEqual(
                git("check-ignore", "-q", "users/sjpark1/secrets/token").returncode,
                0)

class MirrorWriterStaysIgnored(unittest.TestCase):
    """미러 코드가 실제로 만드는 파일이 git 에 담기지 않는가.

    .gitignore 를 읽어 비교하지 않는다 — 그건 규칙을 규칙으로 검사하는 것이라,
    미러가 자리를 옮기는 순간 무력해진다. 여기서는 **써 놓고 git 에게 묻는다.**
    """

    def setUp(self):
        if not shutil.which("git"):
            self.skipTest("git 없음")
        self.root = tempfile.mkdtemp(prefix="s9strm-")
        git("init", "-q", cwd=self.root)
        git("config", "user.email", "t@t", cwd=self.root)
        git("config", "user.name", "t", cwd=self.root)
        shutil.copyfile(GITIGNORE, os.path.join(self.root, ".gitignore"))
        self._old = os.environ.get("S9_ROOT")
        os.environ["S9_ROOT"] = self.root
        self.m = _load("s9_mirror_ign", STOP_HOOK)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = self._old
        shutil.rmtree(self.root, ignore_errors=True)

    def staged(self):
        git("add", "-A", cwd=self.root)
        return git("diff", "--cached", "--name-only", cwd=self.root
                   ).stdout.splitlines()

    def find(self, basename):
        """미러가 실제로 어디에 쓰였는지 찾는다 — 자리를 옮겨도 따라간다."""
        for dirpath, _dirs, files in os.walk(self.root):
            if basename in files and os.path.abspath(dirpath) != os.path.abspath(self.root):
                return os.path.relpath(os.path.join(dirpath, basename),
                                       self.root).replace("\\", "/")
        return None

    # N1. 훅이 실제로 쓴 미러 파일이 — 그 자리가 어디든 — 담기지 않는다
    def test_n1_mirror_never_staged(self):
        src = os.path.join(self.root, "sess-2222.jsonl")
        with open(src, "w", encoding="utf-8") as f:
            f.write('{"a":1}\n')
        r = self.m.mirror_transcript(src)
        if r == "off":
            self.skipTest("이 환경은 미러가 꺼져 있다 (REQ-20260827-042)")
        self.assertEqual(r, "full")
        rel = self.find("sess-2222.jsonl")
        self.assertIsNotNone(rel, "미러가 만들어지지 않았다")
        self.assertNotIn(rel, self.staged(),
                         f"미러가 담겼다: {rel} — 이 자리를 .gitignore 가 막지 않는다")

    # B1. 지금 자리와 옮겨 갈 자리 둘 다, 파일을 놓아도 담기지 않는다
    def test_b1_both_locations_stay_out(self):
        rels = ["streams/x.jsonl", "users/sjpark1/streams/x.jsonl"]
        for rel in rels:
            p = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write("x\n")
        staged = self.staged()
        for rel in rels:
            with self.subTest(rel=rel):
                self.assertNotIn(rel, staged)

    # F1. 감시가 살아 있는지 스스로 증명한다 — ignore 밖 파일은 **담겨야** 한다.
    #     이게 없으면 위 두 개는 "아무것도 안 담긴다"로도 통과한다
    def test_f1_guard_is_alive(self):
        with open(os.path.join(self.root, "plain.txt"), "w",
                  encoding="utf-8") as f:
            f.write("x\n")
        self.assertIn("plain.txt", self.staged(),
                      "감시가 죽었다 — 무엇을 놓아도 통과한다")


if __name__ == "__main__":
    unittest.main()
