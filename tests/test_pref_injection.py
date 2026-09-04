"""개인 설정은 모든 턴에 실린다 (REQ-20260827-069-62x6).

사용자: "개인 설정의 개인 선호 저장을 했는데 왜 적용이안되지"

값은 제대로 저장돼 있었다. **주입이 빠진 경로가 있었다.**

    request / question 턴   pref 있음
    nothing / fragment 턴   pref 없음      ← 짧은 대화 턴
    시스템 통지 턴          pref 없음      ← 대시보드 채팅이 도착하는 자리

하필 그 셋이 짧은 대화 턴이라 **말투 설정이 가장 필요한 자리**였다. 그리고 이
사용자는 주로 대시보드로 말한다 — 그 말은 시스템 통지로 도착하므로, 평소 경로가
통째로 빠져 있었던 셈이다. (이 저장소가 겪은 "입구는 둘인데 한쪽만 열려 있었다"
와 같은 모양이다 — REQ-20260826-033.)

그래서 분기마다 문자열을 조립하지 않고 **모든 경로가 지나는 emit 한 자리**로
옮겼다. 시각 주입과 같은 성격이다: 규칙이 아니라 재료이고, 매 턴 함께 줘야
지켜진다.

실행: python3 tests/ pref_injection
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")


class PrefInjection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9pref-")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "boxA",
                   "S9_USER": "alice"}
        cls.env.pop("S9_SESSION", None)
        cls.env.pop("S9_AUTO_RESUME", None)
        for argv in (["init"], ["user", "add", "alice"],
                     ["user", "config", "alice", "pref_말투", "존댓말 쓰기"]):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=cls.env, timeout=30)
            assert r.returncode == 0, r.stdout + r.stderr

    def ctx(self, prompt):
        """훅을 한 번 돌리고 주입 컨텍스트를 준다."""
        data = json.dumps({"prompt": prompt, "session_id": "abcd1234",
                           "cwd": self.root})
        r = subprocess.run([HOOK], input=data, capture_output=True, text=True,
                           env=self.env, timeout=60)
        try:
            return json.loads(r.stdout or "{}").get(
                "hookSpecificOutput", {}).get("additionalContext", "")
        except ValueError:
            return ""

    # N1. 시스템 통지 턴 — 대시보드 채팅이 도착하는 자리
    def test_pref_injection(self):
        """PrefInjection 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_system_notification_turn"):
                c = self.ctx("<system-reminder>\n어떤 통지\n</system-reminder>")
                self.assertIn("존댓말", c, "대시보드로 온 말에는 개인 설정이 안 실린다")

            # N2. 짧은 파편 턴
        with self.subTest("n2_fragment_turn"):
                self.assertIn("존댓말", self.ctx("ㅇㅇ"))

            # N3. 감탄·잡담 턴
        with self.subTest("n3_nothing_turn"):
                self.assertIn("존댓말", self.ctx("좋다"))

            # N4. 원래 실리던 곳은 그대로 실린다
        with self.subTest("n4_request_turn_kept"):
                self.assertIn("존댓말",
                              self.ctx("대시보드 카드 정렬을 바꿔 줘. 지금은 뒤죽박죽이다."))

            # B1. 두 번 실리지 않는다 — 같은 지시가 두 번 오면 어느 쪽이 최신인지 흐려진다
        with self.subTest("b1_not_duplicated"):
                self.assertEqual(self.ctx("좋다").count("이 사용자의 개인 설정"), 1)

            # B2. 명령(`/x`)·빈 프롬프트 턴에도 실린다 — 예외를 만들면 규칙이 곧 죽는다
        with self.subTest("b2_command_turn"):
                self.assertIn("존댓말", self.ctx("/permissions"))

            # R1. 시각 주입은 그대로 — 한 자리에 모으면서 잃지 않았다
        with self.subTest("r1_stamp_kept"):
                # 문구가 "현재 시각" 에서 바뀌었다 — 훅이 넣는 값은 프롬프트가 **도착한**
                # 때이지 지금이 아니고, 그 둘을 같은 말로 부르면 모델이 지어낸 시각을
                # 적게 된다(REQ-20260903-013). 계약은 「시각 도장이 실린다」이므로
                # 지금 그 도장이 쓰는 말로 본다.
                self.assertIn("도착한 시각", self.ctx("좋다"))

            # R2. 한 프로세스에서 두 번 물으면 그때그때 다시 읽는다 — 캐시하면 먼저 읽은
            #     값이 굳어 방금 바꾼 설정이 안 먹는다. 이 요청이 고치려던 바로 그 증상이다.
        with self.subTest("r2_not_cached"):
                import importlib.machinery
                import importlib.util
                spec = importlib.util.spec_from_loader(
                    "s9_hook_cache",
                    importlib.machinery.SourceFileLoader("s9_hook_cache", HOOK))
                h = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(h)
                seen = []

                def fake_run(env, *argv, inp=None):
                    if argv[:2] == ("user", "current"):
                        out = "alice [source: test]"
                    elif argv[:2] == ("user", "config"):
                        out = json.dumps({"pref_말투": seen.pop(0)})
                    else:
                        out = ""
                    return mock.Mock(returncode=0, stdout=out)

                with mock.patch.object(h, "run", fake_run):
                    seen[:] = ["첫 값"]
                    self.assertIn("첫 값", h.turn_prefs())
                    seen[:] = ["바뀐 값"]
                    self.assertIn("바뀐 값", h.turn_prefs())


            # F1. 설정이 없으면 기본 복귀를 지시한다 (REQ-20260824-016 유지)
        with self.subTest("f1_absent_says_default"):
            root2 = tempfile.mkdtemp(prefix="s9pref2-")
            env2 = {**self.env, "S9_ROOT": root2, "S9_USER": "bob"}
            for argv in (["init"], ["user", "add", "bob"]):
                subprocess.run([S9, *argv], capture_output=True, env=env2,
                               timeout=30)
            data = json.dumps({"prompt": "좋다", "session_id": "efgh5678",
                               "cwd": root2})
            r = subprocess.run([HOOK], input=data, capture_output=True, text=True,
                               env=env2, timeout=60)
            c = json.loads(r.stdout or "{}").get("hookSpecificOutput", {}).get(
                "additionalContext", "")
            self.assertIn("개인 설정: 없음", c)

if __name__ == "__main__":
    unittest.main()
