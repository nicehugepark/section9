"""훅은 section9 의 세션에서만 움직인다 (REQ-20260906-074).

훅은 ~/.claude 에 전역으로 서므로 이 기계의 모든 Claude 세션에서 돈다. 맥미니 실제 발생
2026-09-06 13:30: section9 밖 디렉토리의 기존 작업 프롬프트가 vault 에 기록·동기화됐고
작성자는 미등록 OS 계정이었다. 세션 cwd 가 루트 밖이면(명시 S9_ROOT 없이) 다섯 훅 모두
아무것도 하지 않고, 등록되지 않은 계정은 프롬프트 훅이 기록 대신 잇는 길만 말한다.

실행: python3 tests/ hook_scope
"""
import glob
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "..", "bin")
HOOKS = ("s9-audit-prompt", "s9-audit-response", "s9-audit-session", "s9-audit-agent", "s9-audit-subagent")


class HookScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 훅이 실린 저장소를 임시로 하나 만든다 — 기본 루트는 훅 파일의 위치에서 나온다
        cls.root = tempfile.mkdtemp(prefix="s9scope-")
        os.makedirs(os.path.join(cls.root, "bin"))
        for name in ("s9", "s9.py", *HOOKS):
            shutil.copy2(os.path.join(BIN, name), os.path.join(cls.root, "bin", name))
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("S9_")}
        cls.env["S9_PORT"] = "1"
        subprocess.run([os.path.join(cls.root, "bin", "s9"), "init"], capture_output=True,
                       env={**cls.env, "S9_ROOT": cls.root}, timeout=60)
        subprocess.run([os.path.join(cls.root, "bin", "s9"), "user", "add", "tester"], capture_output=True,
                       env={**cls.env, "S9_ROOT": cls.root}, stdin=subprocess.DEVNULL, timeout=60)
        cls.outside = tempfile.mkdtemp(prefix="s9scope-outside-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)
        shutil.rmtree(cls.outside, ignore_errors=True)

    def reqs(self):
        return sorted(glob.glob(os.path.join(self.root, "vault", "requests", "**", "*.md"), recursive=True))

    def hook(self, name, payload, **env):
        return subprocess.run([os.path.join(self.root, "bin", name)] + (["start"] if name == "s9-audit-session" else []),
                              input=json.dumps(payload), capture_output=True, text=True,
                              env={**self.env, **env}, timeout=120)

    # H1. 루트 밖 cwd + 명시 S9_ROOT 없음 → 다섯 훅 모두 아무것도 하지 않는다
    def test_h1_a_session_outside_the_root_is_not_ours(self):
        tp = os.path.join(self.outside, "t.jsonl")
        with open(tp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "m",
                                "content": [{"type": "text", "text": "주식 브리핑을 써 줘"}]}}) + "\n")
        before = self.reqs()
        for name in HOOKS:
            r = self.hook(name, {"cwd": self.outside, "session_id": "scopeout-full-id", "source": "startup",
                                 "prompt": "당신은 한국 주식시장 데일리 브리핑 작성자다. 뉴스를 해설해라",
                                 "transcript_path": tp, "stop_hook_active": False,
                                 "tool_name": "Agent", "tool_input": {"description": "x"}, "tool_response": {}},
                          S9_USER="tester")
            self.assertEqual(r.returncode, 0, f"{name}: {r.stderr[-300:]}")
            self.assertEqual(r.stdout.strip(), "", f"{name} 이 남의 세션에 무엇인가 주입했다")
        self.assertEqual(self.reqs(), before, "루트 밖 세션의 프롬프트가 요청으로 기록됐다")
        self.assertFalse(glob.glob(os.path.join(self.root, "state", "sessions", "*scopeout*")),
                         "루트 밖 세션의 바인딩이 생겼다")

    # H2. 루트 안 + 등록 계정 → 평소대로 기록한다 (긍정 대조)
    def test_h2_inside_the_root_with_a_registered_account_records(self):
        before = self.reqs()
        r = self.hook("s9-audit-prompt", {"cwd": self.root, "session_id": "scopein-full-id",
                                          "prompt": "대시보드에 요청 카드마다 담당자 아바타를 보여 주는 위젯을 만들어 줘 — 서버 API 와 화면 둘 다 필요하다"},
                      S9_USER="tester")
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        self.assertIn("additionalContext", r.stdout)
        self.assertEqual(len(self.reqs()), len(before) + 1, "우리 세션의 요청이 기록되지 않았다")

    # H3. 루트 안 + 미등록 계정 → 기록하지 않고 잇는 길만 말한다
    def test_h3_an_unregistered_account_is_told_how_to_attach_and_not_recorded(self):
        before = self.reqs()
        r = self.hook("s9-audit-prompt", {"cwd": self.root, "session_id": "scopeun-full-id",
                                          "prompt": "대시보드에 요청 카드마다 담당자 아바타를 보여 주는 위젯을 만들어 줘 — 서버 API 와 화면 둘 다 필요하다"},
                      S9_USER="stranger-os-account")
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        self.assertIn("등록돼 있지 않아", r.stdout)
        self.assertIn("s9 user attach", r.stdout)
        self.assertEqual(self.reqs(), before, "미등록 계정의 프롬프트가 요청으로 기록됐다")


if __name__ == "__main__":
    unittest.main()
