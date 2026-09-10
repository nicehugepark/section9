"""세션 훅은 대화 기록 파일이 **생기기 전에도** 그 경로를 바인딩에 적는다
(REQ-20260910-009-2n7g, 실제 사고 2026-09-10 22:41).

새 세션의 대화 기록(`<cfg>/projects/<cwd>/<sid>.jsonl`)은 첫 프롬프트가 지나야
생기는데, 시작 훅은 그보다 2초 앞서 돈다. 두 훅이 「파일이 있을 때만」 경로를
적어서 그 사이 바인딩에는 transcript_path 가 없었고, 사람이 그때 계정을 바꾸려
하자 「이 세션의 대화 기록을 찾지 못해 계정을 바꾸지 않았습니다」로 거부됐다 —
파일은 그때 이미 있었다. 경로는 Claude Code 가 준 사실이라 존재와 무관하게
참이고, 읽는 쪽(_binding_activity_paths·transcript_read)은 없는 파일을 견딘다.

실행: python3 tests/ bind_transcript_early
"""
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
SESSION_HOOK = os.path.join(HERE, "..", "bin", "s9-audit-session")
PROMPT_HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")


class BindTranscriptEarly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9early-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester", "S9_PORT": "1"}
        for k in ("S9_SESSION", "CLAUDE_CONFIG_DIR"):
            cls.env.pop(k, None)
        for argv in (("init",), ("user", "add", "tester")):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=cls.env, timeout=30, stdin=subprocess.DEVNULL)
            if r.returncode != 0:
                raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")

    def _bound(self, sid8):
        # 바인딩 파일을 직접 읽는다 — `s9 bind <키>` 는 값 없이 부르면 지운다
        p = os.path.join(self.tmp, "state", "sessions", f"testbox__{sid8}.json")
        try:
            with open(p, encoding="utf-8") as f:
                return str(json.load(f).get("transcript_path") or "")
        except (OSError, ValueError):
            return ""

    def _hook(self, script, arg, payload):
        r = subprocess.run([script, *arg], input=json.dumps(payload),
                           capture_output=True, text=True, env=self.env, timeout=40)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])

    def test_e1_session_start_binds_a_path_that_does_not_exist_yet(self):
        """핵심 — 시작 훅: 파일이 없어도 경로가 바인딩에 선다."""
        full = "earlyone-full-session-id"
        tp = os.path.join(self.tmp, "nowhere", full + ".jsonl")
        self.assertFalse(os.path.exists(tp))
        self._hook(SESSION_HOOK, ["start"],
                   {"session_id": full, "source": "startup",
                    "transcript_path": tp, "cwd": self.tmp})
        self.assertEqual(self._bound(full[:8]), tp,
                         "파일이 생기기 전이라 경로를 안 적었다 — 그 사이의 계정 전환이 거부된다")

    def test_e2_first_prompt_binds_it_too(self):
        """회귀 — 프롬프트 훅의 자가 치유도 파일 존재를 조건으로 걸지 않는다."""
        full = "earlytwo-full-session-id"
        tp = os.path.join(self.tmp, "nowhere", full + ".jsonl")
        self._hook(PROMPT_HOOK, [],
                   {"session_id": full, "prompt": "question: 시각",
                    "transcript_path": tp, "cwd": self.tmp})
        self.assertEqual(self._bound(full[:8]), tp)

    def test_e3_no_path_binds_nothing(self):
        """경계 — 경로를 안 주면 아무것도 지어내지 않는다."""
        full = "earlythree-full-session-id"
        self._hook(SESSION_HOOK, ["start"],
                   {"session_id": full, "source": "startup", "cwd": self.tmp})
        self.assertEqual(self._bound(full[:8]), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
