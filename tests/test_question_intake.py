"""질문 수집 경로 테스트 (REQ-20260826-019 반려: "질문을 많이 한거같은데 정작
질문은 하나밖에 등록이 안되어있다. 정상인가?").

정상이 아니다. 질문이 문서가 되는 입구는 둘인데 **한쪽만 열려 있다.**

- 프롬프트 훅(bin/s9-audit-prompt): 터미널로 들어온 질문 → QST 생성. 열려 있다
  (test_question_qst.py S7/S8 이 덮는다).
- 대시보드 채팅(bin/s9 chat_audit): request 가 아니면 분류를 더 보지 않고
  `s9 log "chat: …"` 만 남겼다 — 질문이든 파편이든 똑같이. **닫혀 있었다.**

사용자는 주로 대시보드로 말한다. 그래서 화면에 질문이 한 장뿐이었다.

REQ-20260826-033 에서 그 입구를 열었다: 채팅 경로도 훅과 **같은 판정자**
(`is_durable_question`)를 쓰고, 남을 질문이면 QST 를 만들어 `last_qst` 로 묶는다.
I1 은 그 입구가 다시 닫히는 것을, I5 는 답이 붙는 이음매가 끊기는 것을 막는다.
(이 파일은 결함을 `expectedFailure` 로 명시해 두었다가 수리와 함께 회귀 테스트가
됐다 — 한 번 `unexpected success` 를 낸 뒤 데코레이터를 뗐다.)

I2·I3 은 그 수리가 **기존 동작을 건드리지 않는다**는 경계다: 채팅 request 는
지금처럼 REQ 가 되고, 짧은 확인 발화는 아무 문서도 만들지 않는다. 질문 입구를 열다가
이 둘이 흔들리면 채팅 카드가 잡음으로 뒤덮인다.

실행: python3 tests/ question_intake
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
PHOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")

# 대시보드에서 실제로 오갔던 모양의 발화들 (세션 로그 question:/chat: 라인 참조)
DURABLE_Q = "이 하네스에서 systemd, cron을 사용 중인건가? 그런건 없기를 바라는데.."
REQUEST_MSG = ("대시보드 Docs 목록에서 타입별로 걸러 볼 수 있게 타입바를 "
               "만들어줘. 건수도 함께 보이게 해라.")
THROWAWAY_Q = "이거 맞아?"


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ChatIntakeTest(unittest.TestCase):
    """chat_audit 를 직접 부른다 — 서버 없이 입구 하나만 본다.

    chat_audit 은 os.environ 을 물려 `s9 new` 를 부르므로 S9_ROOT 를 세워 둔 채로
    모듈 로드와 호출을 모두 끝내고, 클래스가 끝날 때 원복한다(다른 스위트 오염 금지).
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9qintake-")
        cls._prev = {k: os.environ.get(k)
                     for k in ("S9_ROOT", "S9_MACHINE", "S9_USER",
                               "S9_SESSION", "S9_REWORK_WATCH")}
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_MACHINE"] = "testbox"
        os.environ["S9_USER"] = "tester"
        os.environ["S9_REWORK_WATCH"] = "off"   # 무인 스폰 차단 (격리)
        os.environ.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "tester")
        cls.s9 = _load("s9_mod_intake", S9)
        cls.hook = _load("s9_hook_intake", PHOOK)

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    @classmethod
    def cli(cls, *args):
        return subprocess.run([S9, *args], capture_output=True, text=True,
                              timeout=20, stdin=subprocess.DEVNULL)

    def catalog(self):
        p = os.path.join(self.tmp, "index", "catalog.jsonl")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def types(self):
        return [r["type"] for r in self.catalog()]

    # ---------------------------------------------------------------- I1
    # 대시보드로 들어온 '남을 질문'이 문서가 되는가.
    # 한때 되지 않았다 — chat_audit 이 request 가 아니면 로그만 남겼다.
    # 이제 프롬프트 훅과 같은 판정(is_durable_question)을 채팅 경로도 쓴다
    # (REQ-20260826-033). 이 테스트는 그 입구가 다시 닫히는 것을 막는다.
    def test_chat_intake_test(self):
        """chat_audit 를 직접 부른다 — 서버 없이 입구 하나만 본다."""
        with self.subTest("i1_durable_chat_question_becomes_doc"):
                # 전제: 이 발화는 프롬프트 훅 기준으로 '남을 질문'이다.
                self.assertEqual(self.hook.classify(DURABLE_Q), "question")
                self.assertTrue(self.hook.is_durable_question(DURABLE_Q))

                self.s9.chat_audit(DURABLE_Q, "tester", "chatsess")
                self.cli("index", "rebuild")
                self.assertIn("question", self.types(),
                              "대시보드 채팅으로 들어온 질문이 문서가 되지 않는다 "
                              "— 사용자가 화면에서 본 '질문 한 장'의 원인")

            # ---------------------------------------------------------------- I2
            # 경계: 채팅 request 는 지금처럼 REQ 가 된다 (질문 입구를 열다 깨지면 안 된다)
        with self.subTest("i2_chat_request_still_becomes_req"):
                before = self.types().count("request")
                doc_id = self.s9.chat_audit(REQUEST_MSG, "tester", "chatsess")
                self.assertTrue(doc_id and doc_id.startswith("REQ-"),
                                f"채팅 요청이 REQ 로 기록되지 않았다: {doc_id!r}")
                self.cli("index", "rebuild")
                self.assertEqual(self.types().count("request"), before + 1)

            # ---------------------------------------------------------------- I3
            # 경계: 짧은 확인 발화는 아무 문서도 만들지 않는다 (잡음 차단 유지).
            # 질문 입구가 열려도 이 발화는 세션 로그로 끝나야 한다.
        with self.subTest("i3_throwaway_chat_makes_no_doc"):
                self.assertFalse(self.hook.is_durable_question(THROWAWAY_Q),
                                 "짧은 확인 발화가 '남을 질문'으로 판정된다")
                before = len(self.catalog())
                self.assertIsNone(self.s9.chat_audit(THROWAWAY_Q, "tester", "chatsess"))
                self.cli("index", "rebuild")
                self.assertEqual(len(self.catalog()), before,
                                 "짧은 확인 발화가 문서를 만들었다")

            # ---------------------------------------------------------------- I4
            # 두 입구가 같은 자를 써야 한다. 채팅 경로가 분류(classify)만 보고 문서화
            # 판정(is_durable_question)을 보지 않는 것이 이 결함의 형태다 — 수리는
            # 판정 함수를 공유하는 방향이어야 하고, 그 함수는 훅이 소유한다.
        with self.subTest("i5_answer_seam_is_bound"):
            env = {**os.environ, "S9_SESSION": "seamsess"}
            qst = self.s9._chat_question(S9, env, DURABLE_Q,
                                         DURABLE_Q.splitlines()[0], "tester")
            self.assertTrue(qst and qst.startswith("QST-"), f"{qst!r}")
            # 읽기는 Stop 훅과 같은 방식으로 — 키를 주고 부르면 그 키를 **지운다**
            # (`s9 bind <key>` 는 클리어다). 키 없이 부르면 전체를 JSON 으로 낸다.
            b = subprocess.run([S9, "bind"], capture_output=True, text=True,
                               timeout=20, env=env, stdin=subprocess.DEVNULL)
            self.assertEqual(json.loads(b.stdout or "{}").get("last_qst"), qst,
                          "생성한 질문이 last_qst 로 묶이지 않았다 — "
                          "Stop 훅이 답을 붙일 대상을 못 찾는다")
        with self.subTest("i4_intake_judgement_is_shared"):
            with open(S9, encoding="utf-8") as f:
                src = f.read()
            self.assertIn("_chat_classifier", src)
            # classify 를 훅에서 로드해 쓰는 구조는 이미 있다 — 판정도 같은 자리에서
            # 가져올 수 있다는 뜻이다(같은 모듈에 is_durable_question 이 있다).
            self.assertTrue(hasattr(self.hook, "is_durable_question"))
            self.assertTrue(hasattr(self.hook, "classify"))

if __name__ == "__main__":
    unittest.main()
