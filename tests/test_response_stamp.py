"""응답 시각 헤딩 규약 (REQ-20260826-024-62x6).

모든 에이전트의 모든 응답은 `# [yyyy-MM-dd HH:mm:ss KST]` 한 줄로 시작한다.

이 규약이 조용히 죽는 방식은 둘이다.
  ① 규칙만 있고 재료가 없다 — 모델은 지금이 몇 시인지 모른다. 규칙만 적어두면
     그럴듯한 시각을 지어내고, 지어낸 시각은 없느니만 못하다. 그래서 훅이 매 턴
     실제 값을 함께 준다.
  ② 예외가 생긴다 — "명령 턴은 빼고", "시스템 통지는 빼고" 로 한 번 뚫리면
     규칙이 곧 죽는다. audit 대상이 아닌 턴도 **응답은 하므로** 지시는 나간다.

실행: python3 tests/ response_stamp
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PHOOK = os.path.join(ROOT, "bin", "s9-audit-prompt")
PROTOCOL = os.path.join(ROOT, "harness", "common", "PROTOCOL.md")
AGENTS = os.path.join(ROOT, "harness", "claude", "agents")

# 백틱까지 계약이다 — "해시 강조" 는 커밋 해시가 받는 그 강조(인라인 코드)를
# 뜻한다. 마크다운 제목(#)이 아니다: 한 번 그렇게 읽어 `#` 이 화면에 새어나왔다.
# 시간대 이름은 고정이 아니다 (REQ-20260828-024) — 개인 설정 timezone 을
# 따르므로 KST·EDT·+09 등 무엇이든 올 수 있다. 계약은 "시각 뒤에 시간대
# 이름이 붙는다" 이지 "KST 다" 가 아니다.
STAMP_RE = (r"(?<!#\s)`\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([A-Za-z]{2,5}|[+-]\d{2}(?::?\d{2})?) - ([\w-]+)\]`")


# 훅은 세션 로그를 남긴다 — 실 vault 를 더럽히지 않게 임시 루트로 격리한다.
TMP = tempfile.mkdtemp(prefix="s9stamp-")


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def hook(prompt, session="stampses"):
    r = subprocess.run([PHOOK], input=json.dumps(
        {"prompt": prompt, "session_id": session + "-full", "cwd": TMP}),
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "S9_ROOT": TMP, "S9_MACHINE": "testbox"})
    try:
        return json.loads(r.stdout or "{}").get(
            "hookSpecificOutput", {}).get("additionalContext", "")
    except ValueError:
        return ""
    finally:
        if not (r.stdout or "").strip():
            with open("/tmp/claude-1000/-home-sjpark1-section9/d15c553b-8362-411a-a4f7-ed7f1d8e2b4b/scratchpad/why.log", "a") as _f:
                _f.write(f"rc={r.returncode}\nOUT={r.stdout!r}\nERR={r.stderr[-3000:]!r}\n---\n")


class ResponseStamp(unittest.TestCase):
    def test_response_stamp(self):
        """규칙과 재료가 같은 자리에 있다 — 지시문과 실제 시각을 함께 준다."""
        with self.subTest("hook_injects_instruction_and_material"):
            ctx = hook("지금 상태 알려줘")
            # 라벨은 이 값이 **무엇인지** 말한다 (REQ-20260903-013):
            # 「현재 시각」이라 부르면 몇 분 뒤 답을 쓰며 그대로 베낀다.
            self.assertIn("이 턴이 도착한 시각", ctx)
            self.assertIn("답을 쓰기 직전에 재라", ctx)
            self.assertRegex(ctx, STAMP_RE)
        with self.subTest("heading_names_the_speaker"):
            m = re.search(STAMP_RE, hook("아무 말"))
            self.assertIsNotNone(m)
            self.assertEqual(m.group(3), "lead")
        with self.subTest("injected_time_is_real_and_kst"):
            ctx = hook("아무 말")
            m = re.search(STAMP_RE, ctx)
            self.assertIsNotNone(m)
            got = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            # 이 테스트 환경에는 사용자 설정이 없어 시스템 로컬로 물러선다.
            now = datetime.datetime.now().astimezone().replace(tzinfo=None)
            # 창을 10분으로 둔다 (REQ-20260904-003). 이 검사가 잡으려는 것은
            # **고정값**과 **다른 시간대**인데, 시간대가 어긋나면 최소 30분이고
            # 고정값은 며칠씩 벌어진다 — 10분으로도 둘 다 잡힌다. 반대로 창이
            # 좁으면 부하가 걸린 병렬 실행에서 멀쩡한 값이 붉어진다.
            self.assertLess(abs((now - got).total_seconds()), 600,
                            "주입 시각이 지금과 다르다 — 고정값이나 다른 시간대다")
        with self.subTest("no_heading_marker"):
            ctx = hook("아무 말")
            self.assertNotIn("# `[", ctx)
            self.assertIn("`#` 은 붙이지 마라", ctx)
        with self.subTest("no_exception_for_command_turns"):
            self.assertRegex(hook("/help"), STAMP_RE)
        with self.subTest("no_exception_for_system_notification_turns"):
            self.assertRegex(hook("<task-notification>done</task-notification>"),
                             STAMP_RE)
        with self.subTest("protocol_carries_the_rule"):
            with open(PROTOCOL, encoding="utf-8") as f:
                src = f.read()
            self.assertIn("KST", src)
            self.assertIn("지어내지 마라", src)
            self.assertIn("date '+%Y-%m-%d %H:%M:%S %Z'", src,
                          "주입이 없는 환경에서 시각을 얻을 방법을 알려줘야 한다 — "
                          "시간대는 %Z 로 따라가야 한다 (REQ-20260828-024)")
            self.assertIn("lead", src, "응답 주체 이름 규칙이 공통 규약에 없다")
            self.assertIn("KST - lead]`", src, "표기 형태가 규약과 어긋난다")
            self.assertNotIn("# `[2026", src, "제목 기호(#)가 규약에 남아 있다")
        with self.subTest("every_role_agent_carries_the_rule"):
            names = [n for n in os.listdir(AGENTS) if n.endswith(".md")
                     and n != "README.md"]
            self.assertGreater(len(names), 20, "역할 에이전트를 찾지 못했다")
            missing, unnamed = [], []
            for n in names:
                with open(os.path.join(AGENTS, n), encoding="utf-8") as f:
                    txt = f.read()
                if "KST" not in txt:
                    missing.append(n)
                # 각자 자기 이름을 쓰도록 박혀 있어야 한다 — 일반 안내로는 안 지켜진다
                elif f"KST - {n[:-3]}]`" not in txt:
                    unnamed.append(n)
            self.assertEqual(missing, [], f"시각 규칙이 빠진 에이전트: {missing}")
            self.assertEqual(unnamed, [], f"자기 이름이 박히지 않은 에이전트: {unnamed}")

if __name__ == "__main__":
    unittest.main(verbosity=2)
