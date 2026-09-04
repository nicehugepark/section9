"""탐지기는 늘 돌아야 탐지기다 (REQ-20260901-009).

REQ-20260901-004 가 유실을 **드러내는** 눈(snapshot --audit)을 세웠지만, 아무도
안 돌리는 탐지기는 없는 탐지기다 — 113건 유실도 사람이 의심하고 나서야 보였다.
그래서 두 자리에 배선한다: 워처 10분 주기(사람의 협조가 필요 없는 본체)와
digest 말미(세션을 시작하는 리드의 눈). 이 파일이 지키는 성질 셋:

  ① 유실이 주입되면 알림이 난다 — 로그와 수신함(send) 양쪽.
  ② 같은 유실을 매 바퀴 다시 떠들지 않는다 — 지문은 복원되면 지워져,
     다음 유실은 새 사건으로 알린다.
  ③ digest 가 유실을 안 채로 조용히 끝나지 않는다.

실행: python3 tests/ audit_wiring
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

DOC = """---
id: REQ-20260901-777-62x6
type: request
title: 탐지기 시험
status: in-progress
user: tester
created: 2026-09-01T09:00:00+09:00
---

## Original

x

## Notes

### 2026-09-01T10:00:00+09:00 response (by tester)

hello

## History
- 2026-09-01T09:00:00+09:00 created by tester (status: open)
- 2026-09-01T10:00:01+09:00 status: open -> in-progress (by tester)
"""
LOST_LINE = "- 2026-09-01T10:00:01+09:00 status: open -> in-progress (by tester)\n"


class AuditWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9audw-")
        subprocess.run(["git", "init", "-q", cls.tmp], check=True)
        os.environ["S9_ROOT"] = cls.tmp
        spec = importlib.util.spec_from_loader(
            "s9audwmod", importlib.machinery.SourceFileLoader("s9audwmod", S9))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        cls.rel = "vault/requests/2026/09/REQ-20260901-777-62x6.md"
        cls.path = os.path.join(cls.tmp, cls.rel)
        os.makedirs(os.path.dirname(cls.path), exist_ok=True)
        with open(cls.path, "w", encoding="utf-8") as f:
            f.write(DOC)
        cls.mod.snapshot_dirty()          # 독립 사본이 떠 있어야 맞댈 수 있다

    def hurt(self):
        with open(self.path, encoding="utf-8") as f:
            t = f.read()
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(t.replace(LOST_LINE, ""))

    def heal(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(DOC)

    def test_audit_wiring(self):
        """AuditWiring 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("w1_injected_loss_raises_one_alert"):
            self.hurt()
            got = []
            n = self.mod.snapshot_audit_alert(send=lambda m, **k: got.append(m))
            self.assertEqual(n, 1, "유실을 주입했는데 알림이 없다")
            self.assertTrue(got, "수신함으로 아무것도 안 갔다")
            self.assertIn(self.rel, got[0])
            self.assertIn("snapshot --audit", got[0])
        with self.subTest("w2_the_same_loss_is_told_once"):
            self.hurt()
            send = lambda m, **k: None
            self.mod.snapshot_audit_alert(send=send)
            self.assertEqual(0, self.mod.snapshot_audit_alert(send=send),
                             "같은 유실을 두 바퀴째 또 떠들었다")
            self.heal()
            self.assertEqual(0, self.mod.snapshot_audit_alert(send=send),
                             "복원됐는데 알림이 났다")
            self.hurt()
            self.assertEqual(1, self.mod.snapshot_audit_alert(send=send),
                             "복원 뒤의 새 유실이 옛 지문에 먹혔다")
            self.heal()
        with self.subTest("w3_a_dead_inbox_does_not_kill_the_alarm"):
            self.hurt()
            def boom(m, **k):
                raise ValueError("라이브 클로드 세션이 없다")
            self.mod._AUDIT_TOLD.clear()
            n = self.mod.snapshot_audit_alert(send=boom)
            self.assertEqual(n, 1, "수신함 실패가 감사 자체를 죽였다")
            self.heal()
        with self.subTest("w4_digest_speaks_of_the_loss"):
            self.hurt()
            r = subprocess.run([S9, "digest"], capture_output=True, text=True,
                               env={**os.environ, "S9_ROOT": self.tmp}, timeout=60)
            self.assertIn("기록 유실 감지", r.stdout,
                          "digest 가 유실을 말하지 않았다:\n" + r.stdout[-800:])
            self.assertIn("snapshot --audit", r.stdout)
            self.heal()
            r2 = subprocess.run([S9, "digest"], capture_output=True, text=True,
                                env={**os.environ, "S9_ROOT": self.tmp}, timeout=60)
            self.assertNotIn("기록 유실 감지", r2.stdout,
                             "유실이 없는데 경보가 났다 — 거짓 경보는 꺼진 탐지기다")
        with self.subTest("w5_the_watcher_loop_carries_the_audit"):
            with open(S9, encoding="utf-8") as f:
                src = f.read()
            i = src.index("def _rework_loop")
            loop = src[i:i + 1500]
            self.assertIn("snapshot_audit_alert()", loop,
                          "워처가 감사를 부르지 않는다")
            self.assertIn("% 20 == 0", loop, "10분(20틱) 주기가 아니다")

if __name__ == "__main__":
    unittest.main()
