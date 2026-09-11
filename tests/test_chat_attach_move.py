"""채팅에 붙인 그림이 세션에게 빈 자리로 도착하던 결함 (REQ-20260911-010).

사용자 보고: "채팅 첨부 그림이 사라진다". 실제로는 사라진 것이 아니라
**옮겨졌다**. `/api/chat` 은 한 요청 안에서 둘을 순서대로 한다:

  ① `chat_audit` — 원문으로 문서를 만들고 `ingest_assets` 가 붙은 파일을
     `state/terminal/uploads/…` 에서 `vault/…/assets/<문서id>/` 로 옮긴다.
  ② `chat_send` — **원문 그대로** 수신함에 한 줄 적는다.

그래서 줄에 실린 절대경로는 적히는 순간 이미 빈 자리였다. 세션은 그 경로를
Read 해 보고 그림이 없다고 했다(2026-09-11 12:42 실측: `20260911T124243-image.png`
는 `vault/requests/2026/09/assets/REQ-20260911-009-62x6/` 에 있었다).

여기서 보는 것은 **입구 하나**다 — 서버 없이 `chat_audit` → `chat_send` 를 그
순서로 부르고, 수신함에 적힌 줄의 경로가 **실제로 열리는 파일**인지 본다.
경로 문자열이 무엇으로 바뀌었는지는 계약이 아니다(자리는 언제든 옮길 수 있다);
계약은 "그 줄을 받은 세션이 그림을 읽을 수 있다" 하나다.

실행: python3 tests/ chat_attach_move
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

# 1x1 PNG — 내용은 아무래도 좋으나 파일이 실제로 있어야 ingest 가 옮긴다.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000100ffff03000006"
    "000557bfabd40000000049454e44ae426082")

REQUEST_MSG = ("대시보드 Docs 목록에서 타입별로 걸러 볼 수 있게 타입바를 "
               "만들어줘. 건수도 함께 보이게 해라.")
DURABLE_Q = "이 하네스에서 systemd, cron을 사용 중인건가? 그런건 없기를 바라는데.."

MARK = re.compile(r"\[Image: ([^\]\n]+)\]")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ChatAttachMoveTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9attmove-")
        cls._prev = {k: os.environ.get(k)
                     for k in ("S9_ROOT", "S9_MACHINE", "S9_USER",
                               "S9_SESSION", "S9_REWORK_WATCH")}
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_MACHINE"] = "testbox"
        os.environ["S9_USER"] = "tester"
        os.environ["S9_REWORK_WATCH"] = "off"      # 무인 스폰 차단 (격리)
        os.environ.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, text=True,
                       timeout=20, stdin=subprocess.DEVNULL)
        subprocess.run([S9, "user", "add", "tester"], capture_output=True,
                       text=True, timeout=20, stdin=subprocess.DEVNULL)
        cls.s9 = _load("s9_mod_attmove", S9)
        # 수신함은 살아 있는 대상 세션을 전제한다 — 서버 없이 그 자리만 세운다.
        cls.s9.chat_target = lambda sid8=None: {"session": "attsess",
                                                "ended": False}

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def upload(self, name):
        """대시보드 업로드가 놓는 그 자리에 파일 하나를 놓는다."""
        d = os.path.join(self.tmp, "state", "terminal", "uploads", "tester")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(PNG)
        return p

    def inbox_last(self):
        p = os.path.join(self.tmp, "state", "terminal", "inbox-attsess.jsonl")
        with open(p, encoding="utf-8") as f:
            return json.loads([l for l in f if l.strip()][-1])

    def roundtrip(self, text):
        """서버가 하는 그 순서 그대로 — audit 가 먼저, 수신함이 나중."""
        doc_id = self.s9.chat_audit(text, "tester", "attsess")
        self.s9.chat_send(text, sid8="attsess", sender="tester")
        return doc_id, self.inbox_last()

    # ------------------------------------------------------------------ A1
    # 요청 갈래: 그림을 붙인 요청이 REQ 가 되면서 파일이 문서 옆으로 옮겨진다.
    # 그 뒤에 적히는 수신함 줄이 **열리는 경로**를 들고 있어야 한다.
    def test_request_attachment_path_is_readable(self):
        src = self.upload("20260911T124243-image.png")
        _doc, line = self.roundtrip(f"{REQUEST_MSG}\n[Image: {src}]")

        self.assertFalse(os.path.exists(src),
                         "전제가 깨졌다 — ingest_assets 가 업로드를 옮기지 않았다")
        got = MARK.search(line["text"])
        self.assertTrue(got, f"수신함 줄에서 첨부 표기가 사라졌다: {line['text']!r}")
        self.assertTrue(
            os.path.exists(got.group(1)),
            "수신함 줄이 빈 자리를 가리킨다 — 세션이 그림을 읽을 수 없다: "
            f"{got.group(1)}")

    # ------------------------------------------------------------------ A2
    # 질문 갈래(_chat_question)도 같은 자리에서 옮긴다. 입구가 둘인데 한쪽만
    # 고치면 "대시보드로 물으면 그림이 없는" 비대칭이 그대로 남는다.
    def test_question_attachment_path_is_readable(self):
        src = self.upload("20260911T084152-image.png")
        _doc, line = self.roundtrip(f"{DURABLE_Q}\n[Image: {src}]")

        got = MARK.search(line["text"])
        self.assertTrue(got, f"수신함 줄에서 첨부 표기가 사라졌다: {line['text']!r}")
        self.assertTrue(os.path.exists(got.group(1)),
                        f"질문에 붙인 그림이 빈 자리를 가리킨다: {got.group(1)}")

    # ------------------------------------------------------------------ A3
    # 고치지 **않아야** 하는 것들과, 기록이 없을 때의 되찾기.
    def test_rewrite_leaves_everything_else_alone(self):
        rw = self.s9.upload_move_rewrite

        with self.subTest("첨부 없는 말은 그대로"):
            self.assertEqual(rw("그냥 하는 말이다"), "그냥 하는 말이다")

        with self.subTest("제자리에 있는 경로는 그대로"):
            here = self.upload("20260911T130000-image.png")
            self.assertEqual(rw(f"[Image: {here}]"), f"[Image: {here}]")

        with self.subTest("상대경로는 그대로"):
            t = "[Image: assets/REQ-20260911-001-62x6/a.png]"
            self.assertEqual(rw(t), t)

        with self.subTest("어디에도 없는 경로는 그대로 — 추측으로 바꾸지 않는다"):
            t = f"[Image: {os.path.join(self.tmp, 'nope', 'zzz-none.png')}]"
            self.assertEqual(rw(t), t)

        # 이 고침 전에 옮겨진 것은 기록이 없다. 그때도 문서 옆 assets 에서
        # 같은 이름을 찾아 되살려야 낡은 줄이 살아난다.
        with self.subTest("기록이 없어도 이름으로 되찾는다"):
            src = self.upload("20260911T140000-image.png")
            self.s9.chat_audit(f"{REQUEST_MSG}\n[Image: {src}]",
                               "tester", "attsess")
            moves = os.path.join(self.tmp, "state", "terminal",
                                 "upload-moves.jsonl")
            if os.path.exists(moves):
                os.remove(moves)
            got = MARK.search(rw(f"[Image: {src}]"))
            self.assertTrue(got and os.path.exists(got.group(1)),
                            "옮긴 기록이 없으면 되찾지 못한다 — 이 고침 전에 "
                            "적힌 줄이 영영 빈 자리를 가리킨다")


if __name__ == "__main__":
    unittest.main()
