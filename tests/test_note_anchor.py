"""문서의 어느 구간에 대고 한 말인지 남는다 (REQ-20260827-072-62x6).

사용자: "문서에 특정 라인에 메모를 추가할 수 있는 기능이 있으면 좋겠고, 특정 단어,
문장, 구간을 드래그 하면 미니 프롬프트 팝업창이 떠서 애드혹 하게 프롬프팅 하고,
그 결과나 응답이 문단에 추가 되었으면 좋겠다."

**줄 번호로 매지 않는다.** 문서가 한 줄만 바뀌어도 전부 어긋나고, 그때 메모는
엉뚱한 곳을 가리키면서도 가리키는 척한다 — 조용히 틀린 기록이 아무 기록보다 나쁘다.

**선택한 글 자체를 인용으로** 남긴다. 문서가 바뀌어도 사람은 어디였는지 읽을 수
있고, 화면은 그 글을 찾아 짚으면 된다. 못 찾으면 못 찾았다고 말하면 된다.

한 벌만 둔다 — 프론트매터에 따로 적지 않는다. 두 곳에 적으면 한 곳만 고쳐진다.

실행: python3 tests/ note_anchor
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class NoteAnchor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9anch-")
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "boxA"
        os.environ["S9_USER"] = "alice"
        cls.env = {**os.environ}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "alice")
        cls.A = cls.cli("new", "request", "--title", "무엇인가", "--summary", "s",
                        "--goal", "g", "--size", "S", "--user", "alice",
                        "--body", "본문 한 줄과 또 한 줄").split()[0]
        spec = importlib.util.spec_from_loader(
            "s9_anchor", importlib.machinery.SourceFileLoader("s9_anchor", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def cli(cls, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=30)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def body(self):
        return self.cli("show", self.A)

    # N1. 앵커를 주면 인용이 노트 첫 줄에 남는다
    def test_note_anchor(self):
        """NoteAnchor 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_anchor_quoted"):
                self.cli("note", self.A, "이 문장이 무슨 뜻인가", "--anchor",
                         "본문 한 줄과")
                t = self.body()
                self.assertIn(self.m.ANCHOR_MARK, t)
                self.assertIn("본문 한 줄과", t)
                self.assertIn("이 문장이 무슨 뜻인가", t)

            # N2. 다시 읽어낼 수 있다 — 화면이 그 글을 찾아 짚으려면 필요하다
        with self.subTest("n2_parseable"):
                entry = f"> {self.m.ANCHOR_MARK} 고른 글\n\n무슨 뜻인가"
                self.assertEqual(self.m.note_anchor(entry), "고른 글")

            # N3. 앵커가 없으면 지금과 완전히 같다
        with self.subTest("n3_without_anchor_unchanged"):
                self.cli("note", self.A, "앵커 없는 평범한 노트")
                self.assertEqual(self.m.note_anchor("앵커 없는 평범한 노트"), "")

            # B1. 여러 줄 선택은 한 줄로 눕힌다 — 인용이 문단이 되면 인용이 아니다
        with self.subTest("b1_multiline_flattened"):
                self.cli("note", self.A, "여러 줄 선택", "--anchor",
                         "첫 줄\n  둘째 줄\t셋째")
                self.assertIn("첫 줄 둘째 줄 셋째", self.body())

            # B2. 너무 긴 선택은 자른다 — 문단을 통째로 옮기면 인용이 아니다
        with self.subTest("b2_truncated"):
                long = "가" * (self.m.ANCHOR_MAX + 200)
                self.cli("note", self.A, "긴 선택", "--anchor", long)
                for ln in self.body().splitlines():
                    if ln.startswith(f"> {self.m.ANCHOR_MARK}"):
                        self.assertLessEqual(len(ln), self.m.ANCHOR_MAX + 8)
                        return
                raise AssertionError("앵커 줄이 없다")

            # B3. 프론트매터에 따로 적지 않는다 — 두 곳에 적으면 한 곳만 고쳐진다
        with self.subTest("b3_single_copy"):
                meta = self.cli("show", self.A, "--meta")
                self.assertNotIn("anchor", meta.lower())

            # N4. 채팅 경로가 앵커를 문서까지 나른다
        with self.subTest("n4_chat_path_carries"):
                src = open(S9, encoding="utf-8").read()
                i = src.index("def chat_append_doc(")
                self.assertIn("--anchor", src[i:i + 900])
                j = src.index('parsed.path == "/api/chat"')
                self.assertIn('req.get("anchor")', src[j:j + 3000],
                              "/api/chat 이 앵커를 받지 않는다")

            # N6. 메모는 살아 있는 세션 없이도 남는다 (REQ-20260828-006).
            #     **메모는 기록이지 메시지가 아니다.** 문서에 한 줄 남기는 데 클로드
            #     세션이 있어야 할 이유가 없는데, 구간 메모가 /api/chat 을 타는 바람에
            #     세션이 없으면 통째로 실패했다 — 사용자가 캡처로 지적했다:
            #     "메모를 보내지 못했습니다 — 지금 붙어 있는 세션이 없습니다".
        with self.subTest("n6_note_path_needs_no_session"):
                src = open(S9, encoding="utf-8").read()
                i = src.index('parsed.path == "/api/note"')
                seg = src[i:i + 1800]
                self.assertIn("chat_append_doc", seg)
                self.assertNotIn("chat_target", seg,
                                 "메모가 살아 있는 세션을 요구한다")
                self.assertNotIn("chat_send", seg)

            # N5. 수신함 줄에도 실린다 — 무엇을 대고 한 말인지 없으면 답할 수 없다
        with self.subTest("n5_inbox_carries"):
            src = open(S9, encoding="utf-8").read()
            i = src.index("def chat_send(")
            self.assertIn('line["anchor"]', src[i:i + 2500])

if __name__ == "__main__":
    unittest.main()
