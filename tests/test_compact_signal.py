"""압축 중이라는 것이 대시보드에도 보인다 (REQ-20260827-065-62x6).

사용자: "로컬 터미널에서 컨텍스트가 컴팩션 되는 중을 대시보드 터미널에서도
인지하고 똑같이 보여줄 수 없나?"

압축 중에는 응답이 한동안 멎는다. 대시보드만 보는 사람에게 그 침묵은 **고장과
구분되지 않는다** — 침묵의 이유를 말해 주지 않으면 고장으로 읽힌다.

끝 훅 없이 세션이 죽으면 표시가 영영 붙어 있게 된다. 늘 켜져 있는 표시는 곧
아무도 안 읽는다 — 그래서 시작 시각을 함께 두고 오래되면 스스로 거둔다.
(같은 규율: STALLED_WIN · chat_live 의 win.)

실행: python3 tests/ compact_signal
"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-session")
HOOKS_JSON = os.path.join(HERE, "..", "harness", "claude", "hooks.json")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ago(secs):
    return (datetime.datetime.now().astimezone()
            - datetime.timedelta(seconds=secs)).isoformat(timespec="seconds")


class CompactSignal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load("s9_compact", S9)

    # N1. 방금 시작했으면 압축 중이다
    def test_compact_signal(self):
        """CompactSignal 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_fresh_is_compacting"):
                self.assertTrue(self.m.chat_compacting({"compacting": _ago(5)}))

            # N2. 끝 훅이 비우면 아니다
        with self.subTest("n2_cleared"):
                self.assertFalse(self.m.chat_compacting({"compacting": ""}))
                self.assertFalse(self.m.chat_compacting({}))

            # B1. 너무 오래된 표시는 스스로 거둔다 — 끝 훅 없이 죽은 세션
        with self.subTest("b1_stale_self_clears"):
                self.assertFalse(self.m.chat_compacting({"compacting": _ago(4000)}))

            # B2. 읽을 수 없는 값에 단정하지 않는다
        with self.subTest("b2_garbage_is_not_compacting"):
                self.assertFalse(self.m.chat_compacting({"compacting": "어제쯤"}))

            # N3. 훅이 시작/끝을 바인딩에 쓴다
        with self.subTest("n3_hook_writes_binding"):
                root = tempfile.mkdtemp(prefix="s9cmp-")
                # S9_PORT=1 — 세션 훅을 돌리는 테스트의 공통 격리(REQ-20260828-001).
                # 지금 도는 이벤트(compact-*)는 서버를 띄우지 않지만, 훅에 이벤트가
                # 하나 늘어나는 날 사용자 대시보드 포트를 뺏는 자리가 여기다.
                env = {**os.environ, "S9_ROOT": root, "S9_MACHINE": "testbox",
                       "S9_USER": "alice", "S9_SESSION": "abcd1234", "S9_PORT": "1"}
                subprocess.run([S9, "init"], capture_output=True, env=env, timeout=30)
                subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                               env=env, timeout=30)
                payload = json.dumps({"session_id": "abcd1234", "cwd": "",
                                      "trigger": "auto"})

                def hook(ev):
                    subprocess.run([HOOK, ev], input=payload, capture_output=True,
                                   text=True, env=env, timeout=30)

                def binding():
                    r = subprocess.run([S9, "bind"], capture_output=True, text=True,
                                       env=env, timeout=30)
                    return json.loads(r.stdout or "{}")

                hook("compact-start")
                self.assertTrue(self.m.chat_compacting(binding()),
                                "시작 훅 뒤에도 압축 중으로 안 보인다")
                hook("compact-end")
                self.assertFalse(self.m.chat_compacting(binding()),
                                 "끝 훅 뒤에도 표시가 남아 있다")

            # N4. 화면이 물어보는 자리에 실려 나간다 — 판정을 두 벌 만들지 않는다
        with self.subTest("n4_served_on_chat_target"):
                src = open(S9, encoding="utf-8").read()
                i = src.index('parsed.path == "/api/chat/target"')
                self.assertIn("chat_compacting", src[i:i + 1500],
                              "터미널 상태 응답에 압축 여부가 없다")

            # N5. 훅이 정본에 등록돼 있다 — 설치본에만 있으면 다른 머신에서 안 돈다
        with self.subTest("n5_registered"):
            with open(HOOKS_JSON, encoding="utf-8") as f:
                hooks = json.load(f)["hooks"]
            for ev, arg in (("PreCompact", "compact-start"),
                            ("PostCompact", "compact-end")):
                self.assertIn(ev, hooks)
                self.assertIn(arg, json.dumps(hooks[ev]))

if __name__ == "__main__":
    unittest.main()
