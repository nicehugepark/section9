"""위임 지명 경고 — 지명 없는 위임은 그 자리에서 들린다 (REQ-20260830-020).

실사고 2026-08-29 20:09: 지명이 안 풀린 위임이 추측 귀속으로 REQ-029 에 붙어
사고 둘(030 거짓 멈춤 + 겹침 스폰, 029 가려진 진짜 멈춤)을 낳았다. 다각 검토
(REQ-20260830-017) 합의는 **경고 먼저**: 차단·새 명령·레지스트리 없이, 훅이
스폰 시점에 리드에게 알린다. hooks.json 봉투가 stderr 를 버리고 exit 를 물기
때문에(`2>/dev/null || true`) stdout JSON(decision=block)이 유일한 통로다 —
PostToolUse 의 block 은 도구를 되돌리지 않는다(이미 떠 있다). 모델에게 reason
을 보일 뿐이다.

실행: python3 tests/ delegate_warn
"""
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-agent")


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9dw-")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_MACHINE": "testbox"}
        self.env.pop("S9_SESSION", None)
        self.env.pop("S9_AUDIT", None)
        self.cli("init")
        self.cli("user", "add", "alice")
        rid = self.cli("new", "request", "--title", "지명 대상", "--summary",
                       "s", "--size", "S", "--user", "alice", "--goal", "g",
                       "--body", "x").split()[0]
        self.rid = rid
        self.num = rid.split("-")[2]           # 세 자리 문서 번호
        self.out = os.path.join(self.root, "agent.out")
        with open(self.out, "w") as f:
            f.write("x")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def cli(self, *argv):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, stdin=subprocess.DEVNULL, timeout=30)
        if r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r.stdout.strip()

    def hook(self, description, env_extra=None):
        payload = {
            "tool_name": "Agent", "session_id": "cafe1234", "cwd": self.root,
            "tool_input": {"description": description, "prompt": "일해라",
                           "subagent_type": "designer"},
            "tool_response": {"agentId": "a123456789abcdef0",
                              "output_file": self.out}}
        env = dict(self.env)
        env.update(env_extra or {})
        r = subprocess.run([HOOK], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, timeout=60)
        return r

    def block_reason(self, r):
        for ln in (r.stdout or "").splitlines():
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("decision") == "block":
                return d.get("reason") or ""
        return None


class TheWarning(Base):
    def test_the_warning(self):
        """TheWarning 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("d1_declared_delegation_is_silent"):
            r = self.hook(f"{self.num} 화면 몫")
            self.assertEqual(r.returncode, 0)
            self.assertIsNone(self.block_reason(r),
                              "지명이 풀렸는데 경고가 났다 — 늑대 소년이 된다")
            # 종전 등록 경로 회귀(D5): 지명된 문서에 기여가 남았다
            body = self.cli("show", self.rid)
            self.assertIn("designer", body, "위임 등록(contrib)이 사라졌다")
        with self.subTest("d2_undeclared_delegation_warns"):
            r = self.hook("화면을 다듬는 잡일")     # 번호도 id 도 없다
            self.assertEqual(r.returncode, 0, "경고가 훅을 실패로 만들면 안 된다")
            reason = self.block_reason(r)
            self.assertIsNotNone(reason, "지명 없는 위임에 경고가 없다")
            self.assertIn("지명", reason)
        with self.subTest("d3_the_warning_says_what_to_do"):
            reason = self.block_reason(self.hook("잡일")) or ""
            self.assertIn("s9 claim", reason, "바로잡는 명령이 없다")
            self.assertIn("description", reason, "다음부터 어떻게 하는지가 없다")
        with self.subTest("d4_audit_off_is_silent"):
            r = self.hook("잡일", env_extra={"S9_AUDIT": "off"})
            self.assertEqual(r.returncode, 0)
            self.assertEqual((r.stdout or "").strip(), "",
                             "S9_AUDIT=off 인데 출력이 있다")

if __name__ == "__main__":
    unittest.main(verbosity=2)
