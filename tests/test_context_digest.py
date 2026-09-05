"""CONTEXT.md 본문이 digest 에 실린다 (REQ-20260905-020, DOC-20260824-001 3단계).

경로 한 줄만 가리키면 읽지 않은 세션은 모른다 — 저장소 정책 같은 규칙을 거기 두는
순간부터 본문이 실려야 한다. 앞 CONTEXT_HEAD 줄만, 절은 한 번만.

실행: python3 tests/ context_digest
"""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class ContextInDigest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9ctxd-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_USER": "tester",
                    "S9_MACHINE": "testbox"}
        self.env.pop("S9_SESSION", None)

    def s9(self, *argv):
        return subprocess.run([S9, *argv], capture_output=True, text=True, env=self.env,
                              timeout=60, stdin=subprocess.DEVNULL)

    def test_c1_the_first_lines_of_context_ride_the_digest_once(self):
        """C1. 내 프로젝트 CONTEXT.md 의 앞줄이 digest 본문에 실리고, 절은 한 번만 선다."""
        self.s9("init"); self.s9("user", "add", "tester")
        r = self.s9("project", "add", "demo", "--name", "데모")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.s9("project", "scaffold", "demo")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.s9("new", "request", "--title", "데모", "--summary", "s", "--size", "S",
                    "--project", "demo", "--goal", "g", "--body", "b")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ctx = os.path.join(self.root, "projects", "demo", "CONTEXT.md")
        self.assertTrue(os.path.exists(ctx), "scaffold 가 CONTEXT.md 를 안 만들었다")
        with open(ctx, "w", encoding="utf-8") as f:
            f.write("# demo\n\n## 저장소 정책\n- push 는 main 으로 직접 한다\n" +
                    "".join(f"- 줄 {i}\n" for i in range(60)))
        out = self.s9("digest").stdout
        self.assertEqual(out.count("## 프로젝트 컨텍스트 본문"), 1, out[:600])
        self.assertIn("push 는 main 으로 직접 한다", out, "본문이 안 실렸다")
        self.assertIn("나머지는 Read", out, "상한을 넘긴 사실을 안 말한다")
        self.assertNotIn("- 줄 59", out, "전체를 주입했다 — 상한이 없다")


if __name__ == "__main__":
    unittest.main()
