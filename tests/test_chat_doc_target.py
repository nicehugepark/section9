"""문서를 지목하면 새 요청이 아니라 그 문서에 붙는다 (REQ-20260827-064-62x6).

사용자: "생성된 요청 문서에 추가요청을 좀 더 편하게 더할 수 있는 방법이 없을까"

지금은 채팅으로 무엇을 말하든 새 REQ 가 생긴다. 그래서 "아까 그 요청에 이것도"가
늘 별개 문서가 되고, 나중에 사람이 손으로 잇게 된다.

**못 찾거나 모호하면 지목하지 않는다.** 잘못 집어 남의 문서에 붙이는 것이 못
찾는 것보다 나쁘다 — `locate` 가 모호한 id 를 거부하는 것과 같은 규율. 대신
왜 안 붙었는지 세션 로그에 남긴다: 조용히 새 요청이 생기면 사용자는 알 길이 없다.

실행: python3 tests/ chat_doc_target
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ChatDocTarget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9chat-")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "boxA",
                   "S9_USER": "alice"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "alice")
        cls.A = cls.mk("살아 있는 요청")
        cls.cli("status", cls.A, "in-progress", "--note", "t")
        cls.DONE = cls.mk("끝난 요청")
        cls.cli("status", cls.DONE, "in-progress", "--note", "t")
        cls.cli("status", cls.DONE, "done", "--note", "t")
        # 모듈 내부를 손대지 않고 환경으로 격리한다 — ROOT 는 import 시점에
        # 갈라져 나가는 값이라 나중에 덮으면 일부만 바뀐다.
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "boxA"
        os.environ["S9_USER"] = "alice"
        cls.m = _load("s9_chatdoc", S9)

    @classmethod
    def cli(cls, *argv):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=30)
        if r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    @classmethod
    def mk(cls, title):
        return cls.cli("new", "request", "--title", title, "--summary", "s",
                       "--goal", "g", "--size", "S", "--user", "alice",
                       "--body", "x").split()[0]

    def num(self, rid):
        return rid.split("-")[2]

    # N1. 전체 id 로 지목하면 그 문서다
    def test_chat_doc_target(self):
        """ChatDocTarget 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_full_id"):
                tgt, rest, err = self.m.chat_doc_target(f">{self.A} 이것도 같이")
                self.assertEqual(tgt, self.A)
                self.assertEqual(rest.strip(), "이것도 같이")
                self.assertFalse(err)

            # N2. 세 자리 번호만 써도 진행 중 요청에서 찾는다 — 이게 '편하게' 다
        with self.subTest("n2_short_number"):
                tgt, rest, _ = self.m.chat_doc_target(f"#{self.num(self.A)} 이것도")
                self.assertEqual(tgt, self.A)
                self.assertEqual(rest.strip(), "이것도")

            # N3. 지목이 없으면 지금과 완전히 같다
        with self.subTest("n3_plain_untouched"):
                tgt, rest, err = self.m.chat_doc_target("그냥 새 요청이다")
                self.assertEqual((tgt, err), ("", ""))
                self.assertEqual(rest, "그냥 새 요청이다")

            # B1. 없는 문서는 지목하지 않고 이유를 말한다
        with self.subTest("b1_missing_refused"):
                tgt, rest, err = self.m.chat_doc_target(">REQ-19990101-001 어쩌구")
                self.assertEqual(tgt, "")
                self.assertIn("없다", err)
                self.assertEqual(rest, ">REQ-19990101-001 어쩌구", "본문을 잃었다")

            # B2. 끝난 요청은 번호로 안 잡힌다 — 완료 목록까지 뒤지면 번호가 겹친다
        with self.subTest("b2_done_not_matched_by_number"):
                tgt, _r, err = self.m.chat_doc_target(f"#{self.num(self.DONE)} 이것도")
                self.assertEqual(tgt, "")
                self.assertTrue(err)

            # B3. 지목만 있고 할 말이 없으면 평소대로 둔다
        with self.subTest("b3_prefix_only"):
                tgt, rest, _ = self.m.chat_doc_target(f">{self.A}")
                self.assertEqual(tgt, "")
                self.assertEqual(rest, f">{self.A}")

            # N4. 붙이면 문서에 남고, 새 문서는 생기지 않는다
        with self.subTest("n4_appends_to_doc"):
                before = len(self.m.load_catalog())
                self.m.chat_append_doc(self.A, "이것도 같이 해줘", "alice", "abcd1234")
                self.assertIn("이것도 같이 해줘", self.cli("show", self.A))
                self.assertEqual(len(self.m.load_catalog()), before,
                                 "지목했는데 새 문서가 생겼다")

            # B4. 끝난 문서에 붙이면 그 사실을 알린다 — 조용히 묻히면 안 된다
        with self.subTest("b4_done_warns"):
                warn = self.m.chat_append_doc(self.DONE, "이것도", "alice", "abcd1234")
                self.assertIn("done", warn)

            # N5. 화면이 집어 준 것이 앞머리 표기보다 우선한다
        with self.subTest("n5_explicit_doc_wins"):
                src = open(S9, encoding="utf-8").read()
                i = src.index("def chat_audit(text, sender, sid8, doc=")
                seg = src[i:i + 1600]
                self.assertIn("if doc:", seg)
                self.assertIn("chat_doc_target", seg)

            # R1. 커맨드·경로로 시작하는 줄은 예전 그대로 audit 를 건너뛴다
        with self.subTest("r1_command_untouched"):
            tgt, _r, err = self.m.chat_doc_target("/permissions")
            self.assertEqual((tgt, err), ("", ""))

if __name__ == "__main__":
    unittest.main()
