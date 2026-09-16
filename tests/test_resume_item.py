"""항목 재개·워크플로 추적 테스트 (REQ-20260825-090-62x6).

설계 근거: DOC-20260825-003-62x6 4·5단계.
지금은 끊긴 작업을 이어받을 때 문서 전체를 다시 읽혀 재작업시키므로 중복이
생긴다. resume-item 은 "무엇이 끝났고 무엇이 끊겼는가"만 뽑아 넘긴다.

격리: S9_ROOT=mktemp. 스폰은 하지 않는다 (기본이 출력 전용, 포트 규율).
실행: python3 tests/ resume_item
"""
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class ResumeItemTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9resume")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_SESSION": "deadbeef", "S9_AUDIT": "off"}
        self.env.pop("S9_PORT", None)
        self.s9run("init")
        self.doc = self.s9run("new", "request", "--title", "재개 대상",
                              "--summary", "s", "--body",
                              "b").stdout.split()[0].strip()
        self.s9run("status", self.doc, "in-progress", "--note", "착수")

    def s9run(self, *argv, rc=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=60)
        self.assertEqual(r.returncode, rc, r.stderr)
        return r

    def seed(self):
        self.s9run("contrib", self.doc, "--actor", "sub:backend:aaaa1111",
                   "--item", "N1 파서", "--result", "done")
        self.s9run("contrib", self.doc, "--actor", "sub:qa:bbbb2222",
                   "--item", "N2 테스트", "--result", "running",
                   "--transcript", "/tmp/agent-b.output")

    def test_r1_only_unfinished_items(self):
        self.seed()
        out = json.loads(self.s9run("resume-item", self.doc, "--json").stdout)
        pend = [p["item"] for p in out["pending"]]
        self.assertIn("N2 테스트", pend)
        self.assertNotIn("N1 파서", pend, "완료 항목을 다시 시키면 중복 작업이다")
        self.assertIn("N1 파서", [d["item"] for d in out["done"]])

    def test_r2_prompt_has_four_elements(self):
        self.seed()
        out = json.loads(self.s9run("resume-item", self.doc, "--json").stdout)
        p = out["prompt"]
        self.assertIn(self.doc, p)
        self.assertIn("N1 파서", p, "완료된 항목이 프롬프트에 없다")
        self.assertIn("N2 테스트", p, "끊긴 항목이 프롬프트에 없다")
        self.assertIn("/tmp/agent-b.output", p, "transcript 경로가 없다")

    def test_r3_no_pending_is_not_an_error(self):
        self.s9run("contrib", self.doc, "--actor", "sub:backend:aaaa1111",
                   "--item", "N1", "--result", "done")
        r = self.s9run("resume-item", self.doc)
        self.assertIn("재개할 항목", r.stdout)

    def test_r4_json_contract(self):
        self.seed()
        out = json.loads(self.s9run("resume-item", self.doc, "--json").stdout)
        for k in ("id", "done", "pending", "prompt"):
            self.assertIn(k, out)
        for k in ("actor", "item", "result", "transcript"):
            self.assertIn(k, out["pending"][0])

    # 로그의 살림살이 파일은 스폰의 자취가 아니다 (REQ-20260916-006-62x6):
    # `_auto_log` 가 같은 사유의 되풀이를 접으려고 이 파일에 몇 번째인지를
    # 적는다. 재는 것은 「프로세스를 띄웠나」이므로 요청별 스폰 기록만 센다.
    AUTO_BOOKKEEPING = {"_global.json", "spawn-repeat.json"}

    def test_r5_no_spawn_without_flag(self):
        """기본은 출력만 — 조회 한 번이 프로세스를 띄우면 사고가 난다."""
        self.seed()
        r = self.s9run("resume-item", self.doc)
        self.assertNotIn("spawn", r.stdout.lower())
        auto = os.path.join(self.root, "state", "auto_resume")
        left = ([f for f in os.listdir(auto)
                 if f.endswith(".json") and f not in self.AUTO_BOOKKEEPING]
                if os.path.isdir(auto) else [])
        self.assertFalse(left, "조회 한 번이 스폰 기록을 남겼다: %s" % left)

    def test_r7_legacy_doc_without_contributions(self):
        r = self.s9run("resume-item", self.doc)
        self.assertIn("재개할 항목", r.stdout)


class WorkflowContribTest(unittest.TestCase):
    """R6: 워크플로는 transcript 파일이 없다 — 저널 경로를 기여로 등록한다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9wf")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_SESSION": "deadbeef", "S9_AUDIT": "off"}
        self.env.pop("S9_PORT", None)
        self.journal = os.path.join(self.root, "wf-run.jsonl")
        subprocess.run([S9, "init"], env=self.env, capture_output=True,
                       text=True, timeout=60)
        self.doc = subprocess.run(
            [S9, "new", "request", "--title", "워크플로 추적", "--summary", "s",
             "--body", "b"], env=self.env, capture_output=True, text=True,
            timeout=60).stdout.split()[0].strip()
        subprocess.run([S9, "status", self.doc, "in-progress", "--note", "착수"],
                       env=self.env, capture_output=True, timeout=60)
        with open(self.journal, "w") as f:
            f.write("{}\n")

    def test_r6_workflow_actor_and_journal(self):
        r = subprocess.run(
            [S9, "contrib", self.doc, "--actor", "wf:review:9c0f1122",
             "--item", "리뷰 라운드 1", "--result", "running",
             "--transcript", self.journal],
            env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        h = json.loads(subprocess.run(
            [S9, "agents", "health", "--json"], env=self.env,
            capture_output=True, text=True, timeout=60).stdout)
        row = next(a for a in h["agents"] if a["actor"] == "wf:review:9c0f1122")
        self.assertEqual(row["transcript"], self.journal)
        self.assertEqual(row["state"], "alive",
                         "방금 쓴 저널은 진전 신호여야 한다")


if __name__ == "__main__":
    unittest.main()
