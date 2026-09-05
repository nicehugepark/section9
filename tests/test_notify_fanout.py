"""전이 통지가 유실되지 않는다 (REQ-20260826-015).

2026-08-26 13:47, 사용자가 REQ-20260826-009 를 반려했다. 그 통지는 리드가
아니라 **이미 물러난 무인 워커 세션**의 수신함으로 갔고, 38분간 아무도 몰랐다.
사용자가 "009는 왜 in-progress에 있는거지?"라고 물어서야 드러났다.

원인은 한 줄이었다 — 통지 루프가 후보를 순회하다 **첫 번째에서 return** 했다.
후보 순서는 glob 이 정하므로 누가 받을지는 사실상 임의였다. 그날은 워커가
먼저 걸렸다.

여기서 고정하는 두 가지:
1. 클레임한 살아 있는 세션이 여럿이면 **모두** 받는다. 중복 수신은 싸고
   유실은 비싸다 — 받은 쪽이 둘이면 하나가 놓쳐도 다른 하나가 처리한다.
2. 아무도 못 받으면 **그 사실이 남는다**. 통지를 못 보내는 것 자체는 정상일
   수 있지만(아무 세션도 안 켜져 있으면), 흔적 없이 사라지는 것은 아니다.

실행: python3 tests/ notify_fanout
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)

TMP = tempfile.mkdtemp(prefix="s9-fanout-")
os.environ["S9_ROOT"] = TMP
spec = importlib.util.spec_from_loader(
    "s9_mod_fan", importlib.machinery.SourceFileLoader("s9_mod_fan", S9))
s9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s9)


class Unacked(unittest.TestCase):
    def setUp(self):
        try:
            os.remove(s9.UNACKED)
        except OSError:
            pass

    def tearDown(self):
        try:
            os.remove(s9.UNACKED)
        except OSError:
            pass

    def test_records_what_nobody_received(self):
        s9._unacked_record("REQ-X", "반려", "돌아가서 다시 하라")
        rows = s9.unacked_transitions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "REQ-X")
        self.assertEqual(rows[0]["kind"], "반려")
        self.assertIn("다시", rows[0]["text"])

    def test_consume_empties_it(self):
        """읽고 비운다 — 안 비우면 다음 digest 마다 같은 줄이 쌓여
        곧 아무도 안 읽는 목록이 된다."""
        s9._unacked_record("REQ-A", "반려", "a")
        s9._unacked_record("REQ-B", "승인", "b")
        self.assertEqual(len(s9.unacked_transitions(consume=True)), 2)
        self.assertEqual(s9.unacked_transitions(), [])

    def test_missing_file_is_empty_not_error(self):
        self.assertEqual(s9.unacked_transitions(), [])

    def test_broken_line_does_not_kill_the_rest(self):
        """기록이 깨졌다고 나머지까지 잃으면, 사고 기록이 사고에 취약해진다."""
        s9._unacked_record("REQ-OK", "반려", "정상")
        with open(s9.UNACKED, "a", encoding="utf-8") as f:
            f.write("{망가진 줄\n")
        rows = s9.unacked_transitions()
        self.assertEqual([r["id"] for r in rows], ["REQ-OK"])


class FanOutContract(unittest.TestCase):
    """구현 계약 — 첫 후보에서 멈추지 않는다."""

    def test_loop_does_not_return_on_first_candidate(self):
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        i = src.index("def chat_notify_transition")
        seg = src[i:i + 4200]
        self.assertIn("sent.append", seg,
                      "후보를 모아 보내지 않고 하나만 보낸다")
        self.assertIn("_unacked_record", seg,
                      "아무도 못 받은 경우를 기록하지 않는다")
        self.assertNotIn("return chat_send(msg, sid8=b.get(\"session\")", seg,
                         "첫 후보에서 반환하는 옛 경로가 남아 있다")


class DigestSurfaces(unittest.TestCase):
    def test_digest_has_a_section_for_it(self):
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("받지 못한 전이 통지", src,
                      "digest 가 미수신 통지를 보여주지 않는다")
        i = src.index("sections = [")
        head = src[i:i + 400]
        self.assertIn("받지 못한 전이 통지", head,
                      "미수신 통지가 digest 첫 절에 있지 않다 — "
                      "아무도 모르는 지시가 아래로 밀리면 또 유실된다")


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
