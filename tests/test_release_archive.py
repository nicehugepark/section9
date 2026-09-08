"""배포판에는 코드만 담긴다 (REQ-20260908-069).

주인 물음 2026-09-08 21:03: 「section9 을 깃헙에서 깨끗한 상태로 릴리스 태그를 따고
배포판을 만들 수는 없나? 압축파일처럼?」 — `git archive` 와 GitHub 릴리스의
Source code zip 은 `.gitattributes` 의 `export-ignore` 를 지킨다. 이 저장소가
track 하는 자기 문서(vault)·사용자(users)·프로젝트 자료(projects)·상태(state)는
하네스가 아니라 이 설치의 데이터라 배포판에 들어가면 안 된다.

실행: python3 tests/ release_archive
"""
import os
import subprocess
import tarfile
import io
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DATA_DIRS = ("vault", "users", "projects", "state", "scratchpad")
CODE_DIRS = ("bin", "web", "harness", "tests", "docs")


def archive_top_level():
    """HEAD 를 git archive 로 묶어 최상위 이름을 센다 — 파일을 남기지 않는다.
    `--worktree-attributes`: 속성은 지금 working tree 의 .gitattributes 를 읽는다 —
    아니면 commit 전에는 옛 속성으로 재어 고친 것이 보이지 않는다."""
    raw = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", "--worktree-attributes", "HEAD"],
                         capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
        return {m.name.split("/")[0] for m in tf.getmembers()}


class TheArchiveIsCodeOnly(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.top = archive_top_level()

    def test_a1_data_dirs_are_not_in_the_archive(self):
        leaked = sorted(d for d in DATA_DIRS if d in self.top)
        self.assertEqual(leaked, [], "배포판에 이 설치의 데이터가 담겼다 — "
                                     ".gitattributes 의 export-ignore 를 보라")
        self.assertNotIn(".s9-sync", self.top,
                         "동기화 표식이 담기면 받은 사람의 저장소가 인스턴스로 읽힌다")

    def test_a2_code_dirs_are_in_the_archive(self):
        missing = sorted(d for d in CODE_DIRS if d not in self.top)
        self.assertEqual(missing, [], "배포판에 코드가 빠졌다")
        for f in ("README.md", "CLAUDE.md", ".gitignore", ".gitattributes"):
            self.assertIn(f, self.top, f"{f} 가 배포판에 없다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
