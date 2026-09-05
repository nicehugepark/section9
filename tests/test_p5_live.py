"""P5 실측의 얼굴 — 다섯 장면을 **진짜 두 컴퓨터**로 밟는다
(REQ-20260902-037-62x6. 몸통은 tests/p5_live.py).

    python3 tests/ p5_live

**사람이 `p5_live` 라고 지목한 실행에서만 깨어난다.** 이유는 하나다: 이 시험은
두 번째 컴퓨터(외부 비밀로 닿는 리눅스)가 켜져 있어야만 돌고, 그 컴퓨터가 꺼진
날 전체 스위트가 붉어지면 게이트가 사람을 속인다. **환경이 답을 바꾸는 것은
게이트로 세우지 않는다** — 매번 도는 회귀는 tests/test_p5_field.py(한 컴퓨터
안에서 머신 이름 둘로 위장, 17건)가 맡고, 이 파일은 그 마지막 한 칸
「정말 두 대에서도 그런가」를 사람이 부를 때 잰다.

지목을 알아보는 법: 러너가 스스로 고른 자리는 argv 에 **파일 이름**을 넘기고
(전체 스위트의 샤드 자식은 `test_p5_live.py`, `--changed` 도 파일 이름이다),
전체는 아예 빈 argv 다. 사람이 손으로 부를 때만 `p5_live` 라는 낱말이 선다.
따로 만든 깃발(`--p5-live` 같은)을 쓰지 않는 이유는 러너가 모르는 `--낱말` 을
패턴으로 세어 「고르지 못한 패턴」으로 실행 전체를 붉히기 때문이다(실측).
"""
import sys
import unittest

import p5_live

LIVE = "p5_live" in sys.argv[1:]
WHY = ("두 번째 컴퓨터가 필요한 실측이다 — `python3 tests/ p5_live` 로 지목해서 부른다")


@unittest.skipUnless(LIVE, WHY)
class TestP5Live(unittest.TestCase):
    """다섯 장면을 순서대로 — 뒤 장면이 앞 장면의 문서를 이어 쓴다."""

    @classmethod
    def setUpClass(cls):
        key = None                      # 없으면 기억된 원격(state/test-remote)
        if "--key" in sys.argv:
            key = sys.argv[sys.argv.index("--key") + 1]
        cls.fx = p5_live.Live(key=key, keep="--keep" in sys.argv)
        cls.fx.build()
        cls.fx.cast()
        cls.X = None

    @classmethod
    def tearDownClass(cls):
        p5_live.REPORT.summary()
        cls.fx.close()

    def _scene(self, fn, *a):
        """장면 하나 — 그 안의 판정이 하나라도 어긋나면 그 장면이 붉다."""
        n = p5_live.REPORT.mark()
        out = fn(self.fx, *a)
        bad = p5_live.REPORT.failed_since(n)
        self.assertFalse(bad, "\n".join(f"[{s}] {l}: {d}" for s, l, _o, d in bad))
        return out

    def test_s1_assign(self):
        """장면 1 · 할당 — A 가 만든 일이 B 컴퓨터의 사람에게 간다."""
        type(self).X = self._scene(p5_live.scene1_assign)

    def test_s2_two_machines(self):
        """장면 2 · 두 대 — 리스가 문서에 실려 건너가고 --takeover 가 이어받는다."""
        self._scene(p5_live.scene2_two_machines)

    def test_s3_derived(self):
        """장면 3 · 파생 — 곁가지 요청의 기원이 남고 B 는 집지 않는다."""
        self._scene(p5_live.scene3_derived)

    def test_s4_viewer(self):
        """장면 4 · 관찰자 — 읽기만 하는 계정이 B 컴퓨터에서도 그대로 막힌다."""
        self._scene(p5_live.scene4_viewer, self.X)

    def test_s5_sync_failure(self):
        """장면 5 · 동기화 실패 — 끊겨도 잃지 않고, 겹쳐도 사라지지 않는다."""
        self._scene(p5_live.scene5_sync_failure, self.X)


if __name__ == "__main__":
    unittest.main()
