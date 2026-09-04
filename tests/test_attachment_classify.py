"""첨부가 질문을 가리는가 (REQ-20260826-034-62x6).

분류는 질문 표지(물음표·종결어미)를 **마지막 줄**에서 찾는다. 그런데 화면을
캡처해 붙이면 원문의 마지막 줄이 `[Image: /경로]` 가 되어 물음표가 밀려난다.
그래서 명백한 질문이 request 카드가 됐다. 실사고 둘, 같은 날:

  - "이 요청은 붉은색 점은 무슨 의미야? 녹색점멸도 아니고" → REQ-20260826-032
  - "idle인 이유가 뭐라고?"                              → REQ-20260826-031

이게 특히 나쁜 이유는 **가장 물어보고 싶을 때 정확히 이 경로를 밟기 때문**이다.
사람은 화면이 이상할 때 캡처해서 묻는다. 질문 타입을 만들어 놓고 캡처가 붙은
질문만 골라 놓치면, 그 타입이 가장 필요한 자리에서 비어 있게 된다.

고침은 분류 전에 첨부 참조 줄을 걷어내는 것이다 — 첨부는 분류의 재료가 아니다.
첨부뿐인 메시지는 원문 그대로 두어 기존 동작을 보존한다.

**반려 이후 (2026-08-27 00:19)**: 고친 뒤에도 같은 일이 또 났다 —
"이거 시킨대로 하는건데 이렇게 하는거 맞아?" + 캡처 → REQ-20260827-006-62x6.
디스크 코드는 이미 옳았다. 그 메시지를 받은 것은 **22:43 에 뜬 서버**였고, 고침은
23:53 에 들어갔다. 서버는 기동 시점 코드를 메모리에 들고 돈다(REQ-20260826-011).
그래서 여기 두 층을 나눠 못 박는다:

  - E 계열: 순수 판정 함수 — 그날 반려를 부른 발화까지 포함해 회귀로 고정한다.
  - C 계열: **채팅 입구 전체**(`chat_audit`) — 함수만 옳고 입구가 옛날이면
    사용자에게는 아무것도 고쳐지지 않은 것과 같다. 입구를 직접 통과시켜 본다.
  - X: `[File: …]`(이미지가 아닌 첨부)도 걷힌다 — 워커가 구멍을 테스트로
    남기고 리드가 닫았다.
    대시보드는 확장자로 `[Image:]` 와 `[File:]` 을 가른다(web/index.html sendChat).
    로그·PDF 를 붙여 물으면 같은 함정을 그대로 밟는다. 고침 자리는 bin/ 이라
    이 세션의 수정 범위 밖 — `expectedFailure` 로 명시해 두었다가 수리와 함께
    회귀 테스트가 된다(test_question_intake.py 가 쓴 방식과 같다).

실행: python3 tests/ attachment_classify
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PHOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")
S9 = os.path.join(HERE, "..", "bin", "s9")

# 반려를 부른 그 메시지 — 대시보드 수신함(inbox-8e60e4af.jsonl, 00:18:23)의 원문
REJECTED_MSG = (
    "이거 시킨대로 하는건데 이렇게 하는거 맞아?\n"
    "[Image: /home/sjpark1/section9/state/terminal/uploads/sjpark1/"
    "20260827T001811-image.png]")


def _load(name=None, path=None):
    name = name or "s9att"
    path = path or PHOOK
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class AttachmentClassify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = _load()

    def test_attachment_classify(self):
        """AttachmentClassify 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("t1_the_two_real_incidents"):
            for text in (
                "이 요청은 붉은색 점은 무슨 의미야? 녹색점멸도 아니고\n"
                "[Image: /home/u/state/terminal/uploads/x/a.png]",
                "idle인 이유가 뭐라고?\n[Image: assets/REQ-x/b.png]",
            ):
                self.assertEqual(self.h.classify(text), "question",
                                 f"질문이 request 로 분류됐다: {text.splitlines()[0]}")
        with self.subTest("t2_same_text_without_attachment_is_unchanged"):
            bare = "이 요청은 붉은색 점은 무슨 의미야? 녹색점멸도 아니고"
            self.assertEqual(self.h.classify(bare),
                             self.h.classify(bare + "\n[Image: /x/a.png]"))
        with self.subTest("t3_paste_form_is_also_stripped"):
            self.assertEqual(
                self.h.classify("이 화면이 왜 이렇게 나오나?\n[Image #1]"),
                "question")
        with self.subTest("t4_request_with_attachment_stays_request"):
            self.assertEqual(
                self.h.classify("보드 카드 글자가 너무 작다. 한 단계 키워 달라.\n"
                                "[Image: /x/c.png]"),
                "request")
        with self.subTest("t5_attachment_only_keeps_old_behavior"):
            only = "[Image: /x/d.png]"
            self.assertEqual(self.h.strip_attachment_refs(only), only)
        with self.subTest("t6_length_is_measured_without_attachments"):
                self.assertFalse(self.h.is_durable_question(
                    "이거 맞아?\n[Image: /home/user/section9/state/terminal/uploads/"
                    "sjpark1/20260826T224537-image.png]"))

            # ---------------------------------------------------------------- E7
        with self.subTest("e7_the_utterance_that_caused_the_rejection"):
                self.assertEqual(self.h.classify(REJECTED_MSG), "question")
                self.assertTrue(self.h.is_durable_question(REJECTED_MSG),
                                "남을 질문인데 문서가 되지 않는다")

            # ---------------------------------------------------------------- X
        with self.subTest("x_non_image_attachment_is_stripped_too"):
            self.assertEqual(
                self.h.classify("이 로그 보고 판단한 게 맞나?\n"
                                "[File: /home/u/section9/state/serve.log]"),
                "question")

class ChatEntranceWithAttachment(unittest.TestCase):
    """C 계열 — 함수가 아니라 **입구**를 통과시킨다.

    반려의 형태가 그랬다. 판정 함수는 옳았는데 사용자는 여전히 요청 카드를 봤다.
    사용자가 만나는 것은 함수가 아니라 입구다(대시보드 채팅 → `chat_audit`).
    그래서 여기서는 chat_audit 을 격리된 S9_ROOT 에서 직접 부르고, 카탈로그에
    무엇이 생겼는지로 판정한다 (test_question_intake.py 와 같은 방식).
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9attchat-")
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
        cls.s9 = _load("s9_mod_att", S9)

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmp, ignore_errors=True)

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

    # ---------------------------------------------------------------- C1
    def test_chat_entrance_with_attachment(self):
        """C 계열 — 함수가 아니라 **입구**를 통과시킨다."""
        with self.subTest("c1_captured_question_makes_no_request_card"):
                before = self.types().count("request")
                self.assertIsNone(
                    self.s9.chat_audit(REJECTED_MSG, "tester", "attsess"),
                    "캡처 붙은 질문이 여전히 요청 카드가 된다 — 반려 사유 그대로다")
                self.cli("index", "rebuild")
                self.assertEqual(self.types().count("request"), before,
                                 "요청 카드가 늘었다")

            # ---------------------------------------------------------------- C2
        with self.subTest("c2_captured_question_is_kept_as_a_question"):
                self.assertIn("question", self.types(),
                              "캡처 붙은 질문이 문서로 남지 않았다")

            # ---------------------------------------------------------------- C3
        with self.subTest("c3_captured_request_still_makes_a_card"):
            doc_id = self.s9.chat_audit(
                "보드 카드 글자가 너무 작다. 한 단계 키워 달라.\n"
                "[Image: /home/u/section9/state/terminal/uploads/t/x.png]",
                "tester", "attsess")
            self.assertTrue(doc_id and doc_id.startswith("REQ-"),
                            f"캡처 붙은 요청이 기록되지 않았다: {doc_id!r}")

if __name__ == "__main__":
    unittest.main()
