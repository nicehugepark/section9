"""한 필드가 두 뜻으로 쓰이면 데이터가 상한다 (REQ-20260827-011-62x6).

`agent_transcript_path` 가 한때 **문자열**과 **리스트** 두 뜻으로 쓰였다. 읽는
자리 셋 중 둘은 `isinstance` 로 방어했지만 쓰는 자리 하나가 안 했고, 그 하나로
`list("/tmp/claude-…")` 이 새어 경로가 글자 하나씩 쪼개진 채 저장됐다:

    ["/", "t", "m", "p", "/", "c", "l", "a", "u", "d", "e", …]

**해가 없지 않다.** 그중 `"/"` 는 실제로 존재하는 디렉토리라 활동 경로 판정에서
살아남아 **루트 디렉토리의 mtime 이 세션 활동 신선도로 계산된다.** 그리고
바인딩마다 가짜 경로 100여 개를 매번 `os.path.exists` 로 두드리는데, 그건 채팅
대상 고르기가 메시지마다 도는 경로다(실측 107개 → 정상 1개).

고침의 요점은 되돌리기가 아니라 **자리**다. 방어를 읽는 쪽에 흩어 두면 쓰는 쪽
하나만 새어도 데이터가 상하고, 그 데이터를 읽는 새 코드가 또 당한다. 그래서
바인딩을 읽고 쓰는 **경계 한 곳**에서 모양을 바로잡는다.

이 결함은 이 저장소가 같은 날 세 번 밟은 것과 같은 계열이다 — `data-goto` 가 탭
이름과 상태 전이 두 뜻을 가졌고(REQ-20260826-025), 질문 판정자가 두 입구에 갈려
있었고(REQ-20260826-033), 마크다운 렌더러가 두 벌이었다(REQ-20260827-008).

실행: python3 tests/ binding_shape
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


class BindingShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9bshape-")
        os.environ["S9_ROOT"] = cls.tmp
        spec = importlib.util.spec_from_loader(
            "s9bshape", importlib.machinery.SourceFileLoader("s9bshape", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        cls.real = os.path.join(cls.tmp, "agent-out.jsonl")
        with open(cls.real, "w") as f:
            f.write("{}\n")

    def test_binding_shape(self):
        """BindingShape 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("s1_split_path_is_rejoined"):
            b = self.m._norm_binding(
                {"agent_transcript_path": list(self.real)})
            self.assertEqual(b["agent_transcript_path"], [self.real])
        with self.subTest("s2_split_path_that_no_longer_exists_is_dropped"):
            b = self.m._norm_binding(
                {"agent_transcript_path": list("/tmp/사라진/파일.output")})
            self.assertEqual(b["agent_transcript_path"], [])
        with self.subTest("s3_root_slash_never_survives"):
            b = self.m._norm_binding({"agent_transcript_path": list("/tmp/x")})
            self.assertNotIn("/", b["agent_transcript_path"])
        with self.subTest("s4_plain_string_becomes_a_list"):
            b = self.m._norm_binding({"agent_transcript_path": self.real})
            self.assertEqual(b["agent_transcript_path"], [self.real])
        with self.subTest("s5_healthy_list_is_untouched"):
            second = os.path.join(self.tmp, "agent-out2.jsonl")
            with open(second, "w") as f:
                f.write("{}\n")
            good = [self.real, second]
            b = self.m._norm_binding({"agent_transcript_path": list(good)})
            self.assertEqual(b["agent_transcript_path"], good)
        with self.subTest("s6_the_boundary_is_read_and_write"):
            with open(S9_SRC, encoding="utf-8") as f:
                src = f.read()
            self.assertIn("return _norm_binding(json.load(f))", src,
                          "읽기 경계에 정규화가 없다")
            self.assertIn("binding = _norm_binding(binding)", src,
                          "쓰기 경계에 정규화가 없다")
        with self.subTest("s7_round_trip_repairs_the_stored_file"):
            m = self.m
            os.makedirs(m.STATE, exist_ok=True)
            b = {"machine": "testbox", "session": "shapetst",
                 "agent_transcript_path": list(self.real)}
            m.write_binding(b)
            again = m.read_binding("testbox", "shapetst")
            self.assertEqual(again["agent_transcript_path"], [self.real])
            with open(m.binding_path("testbox", "shapetst"), encoding="utf-8") as f:
                self.assertEqual(
                    json.load(f)["agent_transcript_path"], [self.real])

class LiveAgents(unittest.TestCase):
    """이 정규화가 무엇을 떠받치는가 (REQ-20260827-002).

    커밋 게이트가 "지금 누가 붙어 있나"를 이 목록의 mtime 으로 판정한다.
    쪼개진 데이터가 남아 있었다면 `"/"` 가 섞여 **루트 디렉토리의 mtime 이
    '에이전트가 살아 있다'로 읽혔을 것**이다 — 게이트가 언제나 걸리고, 언제나
    걸리는 게이트는 우회가 습관이 되어 없는 것과 같아진다.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9live-")
        os.environ["S9_ROOT"] = cls.tmp
        spec = importlib.util.spec_from_loader(
            "s9live", importlib.machinery.SourceFileLoader("s9live", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        cls.m.current_machine = lambda: "testbox"   # 바인딩은 이 머신 것만 (REQ-20260902-017)
        os.makedirs(cls.m.STATE, exist_ok=True)

    def _bind(self, sid, atp, **kw):
        b = {"machine": "testbox", "session": sid,
             "agent_transcript_path": atp}
        b.update(kw)
        with open(os.path.join(self.m.STATE, f"testbox__{sid}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(b, f)

    def setUp(self):
        for fn in os.listdir(self.m.STATE):
            os.remove(os.path.join(self.m.STATE, fn))

    def test_l1_fresh_transcript_is_a_live_agent(self):
        """L1. 기록이 방금 갱신됐으면 그 에이전트는 일하는 중이다."""
        p = os.path.join(self.tmp, "a.output")
        open(p, "w").write("x")
        self._bind("livesess", [p])
        self.assertEqual([a["session"] for a in self.m.live_agents()],
                         ["livesess"])

    def test_l2_old_transcript_is_not(self):
        """L2. 오래된 기록은 아니다 — 끝난 에이전트가 영원히 게이트를 잡으면
        아무도 커밋을 못 한다."""
        p = os.path.join(self.tmp, "b.output")
        open(p, "w").write("x")
        old = __import__("time").time() - 9999
        os.utime(p, (old, old))
        self._bind("oldsess", [p])
        self.assertEqual(self.m.live_agents(), [])

    def test_l3_split_garbage_does_not_fake_liveness(self):
        """L3. 쪼개진 옛 데이터가 '살아 있음'을 지어내지 않는다.

        `"/"` 는 실제로 존재하고 mtime 도 있다. 읽기 경계가 정규화하지 않으면
        모든 세션이 영원히 '에이전트가 붙어 있음'으로 읽힌다.
        """
        self._bind("junksess", list("/tmp/사라진/것.output"))
        self.assertEqual(self.m.live_agents(), [])

    def test_l4_ended_session_is_skipped(self):
        """L4. 끝난 세션은 세지 않는다."""
        p = os.path.join(self.tmp, "c.output")
        open(p, "w").write("x")
        self._bind("endsess", [p], ended="1")
        self.assertEqual(self.m.live_agents(), [])


class ShapeAudit(unittest.TestCase):
    """전수 검사를 명령으로 남긴다 (REQ-20260827-011 반려: "한번 더 전수 점검").

    한 번 더 훑는 것으로는 부족하다. **사람이 물어볼 때만 도는 검사는 물어보지
    않으면 안 돈다.** 되돌리기보다 다시 생기는지 계속 보는 것이 본체다.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9shapes-")
        os.environ["S9_ROOT"] = cls.tmp
        spec = importlib.util.spec_from_loader(
            "s9shapes", importlib.machinery.SourceFileLoader("s9shapes", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        os.makedirs(cls.m.STATE, exist_ok=True)

    def setUp(self):
        for fn in os.listdir(self.m.STATE):
            os.remove(os.path.join(self.m.STATE, fn))

    def _write(self, name, obj):
        with open(os.path.join(self.m.STATE, name), "w",
                  encoding="utf-8") as f:
            json.dump(obj, f)

    def test_a1_clean_state_has_no_issue(self):
        """A1. 멀쩡하면 조용하다 — 늘 시끄러운 검사는 곧 무시된다."""
        self._write("testbox__ok.json",
                    {"machine": "testbox", "session": "ok",
                     "agent_transcript_path": ["/a/b.output"]})
        issues, stat = self.m.shape_audit()
        self.assertEqual(issues, [], issues)
        self.assertEqual(stat["bindings"], 1)

    def test_a2_split_chars_are_found(self):
        """A2. 글자로 쪼개진 값을 찾아낸다 (실제로 상해 있던 모양)."""
        self._write("testbox__bad.json",
                    {"machine": "testbox", "session": "bad",
                     "agent_transcript_path": list("/tmp/x.output")})
        issues, _ = self.m.shape_audit()
        self.assertTrue(any("쪼개짐" in why for _, why in issues), issues)

    def test_a3_one_field_two_shapes_is_found(self):
        """A3. 한 필드가 두 모양으로 나타나면 잡는다.

        이게 이 검사의 본체다 — 상한 결과가 아니라 **상하게 될 자리**를 본다.
        """
        self._write("testbox__s1.json",
                    {"machine": "testbox", "session": "s1", "last_req": "R-1"})
        self._write("testbox__s2.json",
                    {"machine": "testbox", "session": "s2",
                     "last_req": ["R-1"]})
        issues, _ = self.m.shape_audit()
        self.assertTrue(any("여러 모양" in why for _, why in issues), issues)

    def test_a4_empty_list_is_not_a_second_shape(self):
        """A4. 빈 리스트는 다른 뜻이 아니다.

        원소 타입을 모를 뿐인데 그걸 불일치로 세면 검사가 늘 시끄러워지고,
        시끄러운 검사는 아무도 안 본다.
        """
        self._write("testbox__e1.json",
                    {"machine": "testbox", "session": "e1", "tags": []})
        self._write("testbox__e2.json",
                    {"machine": "testbox", "session": "e2", "tags": ["x"]})
        issues, _ = self.m.shape_audit()
        self.assertEqual([i for i in issues if "tags" in i[1]], [], issues)

    def test_a4b_short_single_char_list_is_not_split(self):
        """A4b. 한 글자짜리 원소가 몇 개 있다고 쪼개진 것은 아니다.

        처음 판정이 `["x"]` 를 쪼개짐으로 읽었고 A4 가 그걸 잡았다. 쪼개진
        경로는 언제나 길다 — 길이로 가른다.
        """
        self.assertFalse(self.m._split_chars(["x"]))
        self.assertFalse(self.m._split_chars(list("abc")))
        self.assertTrue(self.m._split_chars(list("/tmp/x.output")))

    def test_a5_non_binding_files_are_skipped(self):
        """A5. 바인딩 폴더의 **바인딩 아닌 파일**은 건너뛴다.

        `approvals_seen.json` 이 그 폴더에 산다 — REQ id 를 키로 쓰는 별개
        파일이다. 바인딩으로 읽으면 그 키들이 전부 "이상한 필드"가 된다.
        """
        self._write("approvals_seen.json",
                    {"REQ-20260823-034": "2026-08-23T16:19:40+09:00"})
        issues, stat = self.m.shape_audit()
        self.assertEqual(stat["bindings"], 0)
        self.assertEqual(issues, [], issues)

    def test_a6_broken_json_is_reported_not_raised(self):
        """A6. 깨진 파일은 보고하되 검사를 세우지 않는다 — 하나 때문에 나머지를
        못 보면 전수 검사가 아니다."""
        with open(os.path.join(self.m.STATE, "testbox__broken.json"),
                  "w", encoding="utf-8") as f:
            f.write('{"machine": "testbox", "sess')
        issues, _ = self.m.shape_audit()
        self.assertTrue(any("파싱 실패" in why for _, why in issues), issues)


if __name__ == "__main__":
    unittest.main()
