"""전수 점검: 한 필드 두 뜻의 나머지 구멍 (REQ-20260827-011-62x6 반려 재작업).

앞선 고침은 `agent_transcript_path` 를 읽고 쓰는 경계(`_norm_binding`)에 방어를
뒀고, 상해 있던 바인딩 둘을 실제로 복구했다. 반려 사유는 "한번 더 전수
점검해줘" 였고, 훑어 보니 **같은 함정이 세 갈래로 더 남아 있다.**

  H1. 존재 확인이 `exists` 라 **디렉토리도 통과한다.** 그래서 `"/"` 는 여전히
      살아남는다 — `s9 bind agent_transcript_path /` 한 줄이면 되고, 쪼개진
      리스트의 join 결과가 디렉토리여도 마찬가지다(`list("/tmp")`). transcript
      는 언제나 파일이므로 `isfile` 이어야 한다. 이 결함의 진짜 해가 "루트가
      활동 경로로 살아남는 것"이었는데, 그 문이 아직 닫히지 않았다.

  H2. 활동 경로 계산이 **두 벌**이다. `_binding_activity_paths()` 와 카탈로그
      live 판정(`s9 serve` 안)이 같은 코드를 각자 손으로 들고 있고, 둘 다
      `isinstance(atp, list)` 로 **읽는 쪽에 흩어진 방어**를 한다 — 쪼개진
      리스트는 그 방어를 그냥 통과한다. 이 문서의 요점이 "방어는 읽는 쪽이
      아니라 경계"였는데 정작 활동 경로의 경계가 비어 있다.

  H3. 형제 필드 `active_reqs` 가 **무방비**다. `s9 bind active_reqs REQ-X` 는
      값을 문자열로 넣고, 그다음 `_claim_req`/`update_active_reqs` 의
      `list(...)` 가 그것을 글자로 쪼갠 뒤 `write_binding` 이 **그대로
      저장한다** — `_norm_binding` 은 `agent_transcript_path` 만 보기 때문이다.
      결과는 원본 결함보다 나쁘다: `binding_req_ids` 가 오염되어 클레임 판정이
      깨지고, 워처가 같은 REQ에 워커를 중복 스폰한다(REQ-20260825-086 이 이미
      한 번 밟은 자리).

고침은 전부 `bin/s9` 안이라 이 계약들을 쓴 무인 워커의 봉투(web·vault·tests)
밖이었다. 그래서 워커는 **고치지 못하는 자리의 구멍을 `expectedFailure` 로 못
박아 두었다** — 말로 넘기면 다음 사람이 읽고도 지나친다. 리드가 셋을 닫자
이 테스트들이 `unexpected success` 로 스위트를 붉게 만들었고, 그때 마커를 뗐다.
지금은 회귀 테스트다.

닫은 방식은 세 갈래가 아니라 **한 자리**였다: 경계(`_norm_binding`)가
`agent_transcript_path` 와 `active_reqs` 를 함께 보고, 존재가 아니라 **파일인가**로
거르며(`"/"` 는 실재하는 디렉토리다), 활동 경로 계산을 한 벌로 모아 그 한 벌이
경계를 태운다. 방어가 읽는 쪽에 흩어져 있던 것이 이 결함의 형태였으므로,
고침도 흩어진 자리를 늘리는 쪽이 아니라 경계로 모으는 쪽이어야 한다.

실행: python3 tests/ binding_sweep
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")


def _load(prefix):
    tmp = tempfile.mkdtemp(prefix=prefix)
    os.environ["S9_ROOT"] = tmp
    spec = importlib.util.spec_from_loader(
        prefix, importlib.machinery.SourceFileLoader(prefix, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m, tmp


class NormIsSound(unittest.TestCase):
    """이미 서 있는 계약 — 회귀하면 안 되는 것들."""

    @classmethod
    def setUpClass(cls):
        cls.m, cls.tmp = _load("s9sweepA")
        cls.real = os.path.join(cls.tmp, "agent-out.jsonl")
        with open(cls.real, "w") as f:
            f.write("{}\n")

    def test_norm_is_sound(self):
        """이미 서 있는 계약 — 회귀하면 안 되는 것들."""
        with self.subTest("a1_idempotent"):
            b = {"agent_transcript_path": list(self.real)}
            once = self.m._norm_binding(dict(b))
            twice = self.m._norm_binding(dict(once))
            self.assertEqual(once, twice)
        with self.subTest("a2_absent_key_is_not_invented"):
            self.assertNotIn("agent_transcript_path",
                             self.m._norm_binding({"session": "x"}))
        with self.subTest("a3_non_string_junk_is_dropped"):
            b = self.m._norm_binding(
                {"agent_transcript_path": [None, 7, self.real, {"a": 1}]})
            self.assertEqual(b["agent_transcript_path"], [self.real])
        with self.subTest("a4_mixed_list_keeps_the_real_path"):
            b = self.m._norm_binding(
                {"agent_transcript_path": [self.real] + list("/tmp/x")})
            self.assertEqual(b["agent_transcript_path"], [self.real])
        with self.subTest("a5_write_boundary_is_the_only_writer"):
            with open(S9, encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(src.count("binding_path(binding[\"machine\"]"), 1)

class DirectoriesAreNotTranscripts(unittest.TestCase):
    """H1. 존재 확인은 `isfile` 이어야 한다 — 디렉토리는 transcript 가 아니다."""

    @classmethod
    def setUpClass(cls):
        cls.m, cls.tmp = _load("s9sweepB")

    def test_h1a_root_as_a_plain_string_does_not_survive(self):
        """`s9 bind agent_transcript_path /` 한 줄이면 루트가 활동 경로가 된다.

        문자열 갈래는 존재 확인 자체를 하지 않는다 — 그대로 리스트에 담긴다.
        """
        b = self.m._norm_binding({"agent_transcript_path": "/"})
        self.assertEqual(b["agent_transcript_path"], [])

    def test_h1b_split_list_that_rejoins_to_a_directory(self):
        """쪼개진 글자를 붙였더니 디렉토리면 그것도 버려야 한다.

        `exists` 는 디렉토리에 참이다. 이 결함의 진짜 해가 "실재하는 디렉토리의
        mtime 이 세션 활동으로 읽히는 것"이었으므로, 걸러야 할 것은 '없는
        경로'가 아니라 '파일이 아닌 것'이다.
        """
        b = self.m._norm_binding({"agent_transcript_path": list("/tmp")})
        self.assertEqual(b["agent_transcript_path"], [])


class ActivityPathsHaveOneBoundary(unittest.TestCase):
    """H2. 활동 경로 계산은 한 벌이어야 하고, 그 한 벌이 정규화를 태워야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.m, cls.tmp = _load("s9sweepC")

    def test_activity_paths_have_one_boundary(self):
        """H2. 활동 경로 계산은 한 벌이어야 하고, 그 한 벌이 정규화를 태워야 한다."""
        with self.subTest("h2a_split_binding_never_yields_root"):
            paths = self.m._binding_activity_paths(
                {"session": "junk", "agent_transcript_path": list("/tmp/없는것")})
            self.assertNotIn("/", paths)
        with self.subTest("h2b_no_scattered_isinstance_defense_remains"):
            with open(S9, encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(src.count("isinstance(atp, list)"), 0)
        with self.subTest("h2c_no_string_default_for_a_list_field"):
            with open(S9, encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(src.count('b.get("agent_transcript_path", "")'), 0)

class ActiveReqsHasTheSameTrap(unittest.TestCase):
    """H3. 형제 필드 `active_reqs` — 같은 함정, 더 큰 해."""

    @classmethod
    def setUpClass(cls):
        cls.m, cls.tmp = _load("s9sweepD")

    def test_active_reqs_has_the_same_trap(self):
        """H3. 형제 필드 `active_reqs` — 같은 함정, 더 큰 해."""
        with self.subTest("h3a_string_becomes_a_list"):
            b = self.m._norm_binding({"active_reqs": "REQ-20260827-011-62x6"})
            self.assertEqual(b["active_reqs"], ["REQ-20260827-011-62x6"])
        with self.subTest("h3b_split_ids_are_rejoined"):
            b = self.m._norm_binding(
                {"active_reqs": list("REQ-20260827-011-62x6")})
            self.assertEqual(b["active_reqs"], ["REQ-20260827-011-62x6"])
        with self.subTest("h3c_claim_does_not_shatter_a_string"):
            m = self.m
            os.makedirs(m.STATE, exist_ok=True)
            with open(m.binding_path("testbox", "shatter"), "w",
                      encoding="utf-8") as f:
                json.dump({"machine": "testbox", "session": "shatter",
                           "active_reqs": "REQ-20260827-011-62x6"}, f)
            m._claim_req("testbox", "shatter", "REQ-20260827-012-62x6")
            got = m.read_binding("testbox", "shatter")["active_reqs"]
            self.assertTrue(all(len(x) > 1 for x in got), got)
        with self.subTest("h3d_healthy_active_reqs_is_untouched"):
            good = ["REQ-20260827-011-62x6", "REQ-20260827-012-62x6"]
            b = self.m._norm_binding({"active_reqs": list(good)})
            self.assertEqual(b["active_reqs"], good)

class StoredBindingsAreClean(unittest.TestCase):
    """이 워크스페이스에 실제로 남아 있는 데이터의 전수 확인.

    반려 사유가 "전수 점검"이었다. 코드만 보고 끝내면 상한 파일이 남아 있어도
    모른다 — 그래서 저장된 바인딩 전부를 훑는다.
    """

    @classmethod
    def setUpClass(cls):
        cls.files = sorted(glob.glob(
            os.path.join(REPO, "state", "sessions", "*.json")))

    @unittest.skipUnless(
        os.path.isdir(os.path.join(REPO, "state", "sessions")),
        "이 워크스페이스에 바인딩이 없다 (다른 S9_ROOT)")
    def test_d1_no_binding_holds_a_shattered_list(self):
        """어떤 바인딩에도 글자로 쪼개진 목록이 남아 있지 않다."""
        bad = []
        for fp in self.files:
            try:
                with open(fp, encoding="utf-8") as f:
                    b = json.load(f)
            except (OSError, ValueError):
                continue
            if not isinstance(b, dict):
                continue
            for k, v in b.items():
                if isinstance(v, list) and v and all(
                        isinstance(x, str) and len(x) <= 1 for x in v):
                    bad.append(f"{os.path.basename(fp)}:{k}")
        self.assertEqual(bad, [], f"쪼개진 필드가 남아 있다: {bad}")

    @unittest.skipUnless(
        os.path.isdir(os.path.join(REPO, "state", "sessions")),
        "이 워크스페이스에 바인딩이 없다 (다른 S9_ROOT)")
    def test_d2_list_fields_are_never_strings(self):
        """리스트로 쓰는 필드가 문자열로 저장돼 있지 않다 — 쪼개짐의 씨앗."""
        bad = []
        for fp in self.files:
            try:
                with open(fp, encoding="utf-8") as f:
                    b = json.load(f)
            except (OSError, ValueError):
                continue
            if not isinstance(b, dict):
                continue
            for k in ("agent_transcript_path", "active_reqs", "history"):
                if isinstance(b.get(k), str):
                    bad.append(f"{os.path.basename(fp)}:{k}")
        self.assertEqual(bad, [], f"문자열로 저장된 리스트 필드: {bad}")


if __name__ == "__main__":
    unittest.main()
