"""`s9 release try` — 배포판을 만들어 풀고 첫 실행까지 스스로 시험한다 (REQ-20260913-020).

맥의 백그라운드 작업자는 `bin/s9 …` 만 실행할 수 있어 tar·python3 을 직접 못 부른다.
이 명령이 그 절차 전부를 대신하므로, 여기서는 그 명령이 **이 컴퓨터에서** 끝까지
가는지와(통과 보고), 배포판에 문서가 없는지를 CLI 로 잰다.

실행: python3 tests/ release_try
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")
TRY = os.path.join(REPO, "scratchpad", "release-try")


def reltry():
    spec = importlib.util.spec_from_file_location(
        "s9_reltry", os.path.join(REPO, "bin", "s9_reltry.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ReleaseTry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = {k: v for k, v in os.environ.items() if not k.startswith("S9_")}
        env["S9_SYNC"] = "off"
        cls.r = subprocess.run([sys.executable, S9, "release", "try", "--ref", "HEAD"],
                               capture_output=True, encoding="utf-8", errors="replace",
                               cwd=REPO, env=env, timeout=420, stdin=subprocess.DEVNULL)
        cls.out = (cls.r.stdout or "") + (cls.r.stderr or "")

    def test_t1_the_whole_run_passes(self):
        """정상: 만들기 → 풀기 → 첫 실행 → 확인 전부 통과, exit 0."""
        self.assertEqual(self.r.returncode, 0, self.out[-3000:])
        self.assertIn("전부 통과", self.out)
        self.assertNotIn("✗ ", self.out)

    def test_t2_the_first_run_stood_a_repo_and_answered(self):
        """정상: 보고에 저장소·main·local·훅·대시보드 확인 줄이 다 있다."""
        for line in ("저장소를 새로 세웠다는 줄이 있다", "가지가 main 이다",
                     ".s9-sync 가 local", "Claude 훅이 임시 설정에", "대시보드가 그 자리에서 답한다"):
            self.assertIn("✓ " + line, self.out)

    def test_t3_the_archive_holds_no_data_and_the_try_dir_is_removed(self):
        """경계: 배포판에 문서·사용자·상태가 없고, --keep 없이는 푼 자리가 남지 않는다."""
        self.assertIn("✓ 배포판에 문서·사용자·상태가 없다", self.out)
        self.assertFalse(os.path.exists(TRY), TRY)


class Sums(unittest.TestCase):
    """받은 파일과 SHA256SUMS 대조 (REQ-20260914-009-62x6) — 맥의 백그라운드 작업자는
    shasum 을 부를 수 없어 이 판정이 s9 안에 있다. 망이 필요 없는 단위 시험이다."""

    def setUp(self):
        self.m = reltry()
        self.d = tempfile.mkdtemp(prefix="reltry-sums-")
        self.tar = os.path.join(self.d, "section9-0.9.0-linux-macos.tar.gz")
        with open(self.tar, "wb") as f:
            f.write(b"section9")
        self.sha = self.m.sha256_of(self.tar)
        self.sums = os.path.join(self.d, "SHA256SUMS")

    def write(self, text):
        with open(self.sums, "w", encoding="utf-8") as f:
            f.write(text)

    def test_s1_the_same_hash_passes(self):
        """정상: SHA256SUMS 의 해시가 받은 파일과 같으면 통과."""
        self.write(f"{self.sha}  {os.path.basename(self.tar)}\n")
        same, why = self.m.sums_match(self.sums, self.tar)
        self.assertTrue(same, why)

    def test_s2_a_binary_star_and_a_path_still_match(self):
        """경계: 이름 앞의 `*`(binary 표시)와 경로가 붙어 있어도 같은 파일로 본다."""
        self.write(f"{self.sha} *dist/{os.path.basename(self.tar)}\n")
        self.assertTrue(self.m.sums_match(self.sums, self.tar)[0])

    def test_s3_a_missing_line_is_not_a_pass(self):
        """경계: 그 파일 줄이 없으면 통과가 아니다 — 대조하지 못한 것을 통과로 읽지 않는다."""
        self.write(f"{self.sha}  section9-0.9.0-windows.zip\n")
        same, why = self.m.sums_match(self.sums, self.tar)
        self.assertFalse(same)
        self.assertIn("없다", why)

    def test_s4_a_different_hash_fails(self):
        """실패: 해시가 다르면 실패로 판정하고 근거에 양쪽 앞자리를 적는다."""
        self.write("0" * 64 + f"  {os.path.basename(self.tar)}\n")
        same, why = self.m.sums_match(self.sums, self.tar)
        self.assertFalse(same)
        self.assertIn(self.sha[:16], why)


if __name__ == "__main__":
    unittest.main()
