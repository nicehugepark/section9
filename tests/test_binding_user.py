"""빈 칸이 판정의 근거가 되면 기능이 조용히 꺼진다 (REQ-20260902-049-62x6).

바인딩의 `user` 는 오래 빈 칸이었다. 아무도 안 읽었으니 비어도 표가 안 났다.
그러다 REQ-20260902-016 이 착수 통지를 「담당자의 라이브 세션에만」으로 좁히며
그 칸을 판정의 근거로 세웠고, 전수가 빈 채여서 **통지가 아무에게도 가지
않았다** — 실측: 이 저장소의 최근 바인딩 12개 전부 `user=""`.

시험(C20)은 그때부터 빨간불이었는데 「시험 전제가 어긋났나」로 읽혔다. 아니었다.
시험이 맞았고 제품이 틀렸다.

고침은 두 겹이고, 두 겹인 것이 요점이다:
  ① **쓰는 자리 하나** — 제 세션의 바인딩을 쓸 때 제 이름을 적는다. 읽는 쪽마다
     빈 칸을 메우면 그 추측이 자리마다 갈린다.
  ② **읽는 자리의 뜻** — 빈 칸은 「남」이 아니라 「모름」이다. 이름이 적혀 있고
     다를 때만 남의 자리로 치고, 모르는 자리는 후보로 두되 이름이 맞는 자리에
     진다. 016 이 막으려던 오귀속은 ①이 채운 이름으로 막힌다.

실행: python3 tests/ binding_user
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class BindingUser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9binduser-")
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_MACHINE"] = "testbox"
        os.environ["S9_USER"] = "tester"
        spec = importlib.util.spec_from_loader(
            "s9binduser", importlib.machinery.SourceFileLoader("s9binduser", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def setUp(self):
        """바인딩 자리를 비우고 시작한다 — 앞 시나리오가 남긴 자리가 다음
        판정의 후보로 끼면 무엇을 재는지가 흐려진다."""
        import glob
        for p in glob.glob(os.path.join(self.tmp, "state", "sessions",
                                        "*.json")):
            os.remove(p)

    def _live(self, session, user=""):
        """살아 있어 보이는 바인딩 하나 — attach_pid=1 은 언제나 생존이다."""
        b = {"machine": "testbox", "session": session, "user": user,
             "attach_pid": "1"}
        os.makedirs(os.path.join(self.tmp, "streams"), exist_ok=True)
        p = os.path.join(self.tmp, "streams", f"{session}-full.jsonl")
        with open(p, "w") as f:
            f.write("{}\n")
        return b

    def test_u1_own_session_writes_its_own_name(self):
        """U1. 제 세션의 바인딩에는 제 이름이 적힌다 — 이것이 없어 통지가 꺼졌다."""
        os.environ["S9_SESSION"] = "mysess"
        try:
            self.m.write_binding(self._live("mysess"))
        finally:
            os.environ.pop("S9_SESSION", None)
        self.assertEqual(
            self.m.read_binding("testbox", "mysess").get("user"), "tester")

    def test_u2_someone_elses_binding_is_not_labelled_by_us(self):
        """U2. 남의 세션 파일에는 이 프로세스의 이름을 적지 않는다.

        여기서 적으면 016 이 막으려던 그 오귀속을 고침이 스스로 만든다.
        """
        os.environ["S9_SESSION"] = "mysess"
        try:
            self.m.write_binding(self._live("othersess"))
        finally:
            os.environ.pop("S9_SESSION", None)
        self.assertEqual(
            self.m.read_binding("testbox", "othersess").get("user"), "")

    def test_u3_unknown_is_not_someone_else(self):
        """U3. 이름이 빈 자리는 후보로 남는다 — 「모름」은 「남」이 아니다."""
        self.m.write_binding(self._live("unknown1"))
        b = self.m.chat_target(None, user="tester")
        self.assertIsNotNone(b, "빈 이름의 자리가 통째로 걸러졌다")
        self.assertEqual(b.get("session"), "unknown1")

    def test_u4_a_named_seat_beats_an_unknown_one(self):
        """U4. 이름이 맞는 자리가 모르는 자리를 이긴다."""
        self.m.write_binding(self._live("unknown2"))
        self.m.write_binding(self._live("named", user="tester"))
        b = self.m.chat_target(None, user="tester")
        self.assertEqual(b.get("session"), "named")

    def test_u5_a_different_name_is_still_someone_else(self):
        """U5. 이름이 적혀 있고 다르면 여전히 남의 자리다 (016 의 계약)."""
        self.m.write_binding(self._live("theirs", user="somebody"))
        self.assertIsNone(self.m.chat_target(None, user="tester"))


if __name__ == "__main__":
    unittest.main()
