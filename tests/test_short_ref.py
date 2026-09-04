"""짧게 쓴 문서 번호도 링크가 동작해야 한다 (REQ-20260828-021-62x6).

사용자: "REQ-028 은 당연히 문서 번호가 아니지. 그런데 우리가 대화할 때는 그걸로
식별 중이잖아. 가장 최근 날짜의 28번째 문서를 암묵적으로 사용하고 있었잖아.
그럼 링크를 걸 수 있는거 아냐."

맞는 말인데, **"가장 최근"의 기준시각이 어디냐가 전부다.**

architect 실측: 이 저장소에 굳어 있는 축약 언급에 "렌더하는 지금 기준 최신"을
대면 셋 중 둘이 다른 문서로 풀린다. 하루 발번이 29~91건이라 **스크롤백이
하루도 못 버틴다.** 예 —

    SES-20260823-006 본문 "REQ-078"   당시 뜻 REQ-20260823-078
                                       렌더시각 규칙 → REQ-20260827-078-62x6

그래서 기준시각을 **그 줄이 쓰인 때**로 옮긴다. 계약은 넷이다.

  ① **시간에 대해 고정된다.** 내일 새 문서가 생겨도 오늘 쓴 줄의 해석이 바뀌지
     않는다 — 기록이 나중에 다른 것을 가리키는 일이 없다. (종류, 날짜, 번호)
     중복이 카탈로그에 0건이라 임의 시각 t 에 대해 답은 언제나 유일하다.
  ② **그때 없던 문서는 짐작하지 않는다.** 없으면 링크를 걸지 않는다 — 지어낸
     링크는 없느니만 못하다.
  ③ **판정은 한 규칙이다.** 화면에도 같은 규칙이 있어야 하는데(카탈로그가 이미
     화면에 있고 링크는 인라인 렌더라 왕복할 수 없다) 두 벌이 갈리면 화면과
     서버가 다른 문서를 가리킨다. 그래서 **계약표를 두 엔진이 함께 읽는다** —
     이 테스트가 서버를, `?shortref` 손잡이가 화면을 같은 표로 검사한다.
  ④ 짐작 해석은 **읽기 전용**이다. `이어 말하기` 는 그 문서에 영구 기록을
     남기고, 화면이 축약을 미리 접어 보내면 `/api/note` 의 모호성 가드 앞에서
     애매함이 이미 사라진 채 도착한다.

그리고 별개의 계약 하나 — **없는 문서에는 링크를 걸지 않는다.** id 모양이기만
하면 밑줄을 긋던 탓에 없는 문서도 있는 것처럼 보였고, 누르면 빈 미리보기가 떴다.

실행: python3 tests/ short_ref
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
INDEX = index_path()


def load_s9():
    """이 검사는 **진짜 저장소의 카탈로그**를 본다 — 코퍼스가 곧 반증 조건이다.
    앞선 테스트가 남긴 임시 S9_ROOT 를 물려받으면 빈 카탈로그를 재게 되므로
    여기서 못 박고, 남의 테스트에 흘리지 않도록 되돌려 놓는다."""
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = os.path.abspath(os.path.join(HERE, ".."))
    try:
        spec = importlib.util.spec_from_loader(
            "s9short", importlib.machinery.SourceFileLoader("s9short", S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


class ShortRefRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_s9()
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def rows(self, *ids_and_dates):
        """(id, created) 목록 → 카탈로그 모양"""
        return [{"id": i, "created": c} for i, c in ids_and_dates]

    # ---------- ① 시간에 대해 고정된다 ----------

    def test_short_ref_rule(self):
        """ShortRefRule 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("the_answer_is_the_newest_one_that_existed_when_the_line_was_written"):
            rows = self.rows(
                ("REQ-20260823-078", "2026-08-23T10:00:00+09:00"),
                ("REQ-20260825-078-62x6", "2026-08-25T10:00:00+09:00"),
                ("REQ-20260827-078-62x6", "2026-08-27T10:00:00+09:00"))
            got = self.m.resolve_short("REQ", "078", "2026-08-24T09:00:00+09:00", rows)
            self.assertEqual(got["id"], "REQ-20260823-078",
                             "그 줄을 쓴 뒤에 생긴 문서를 집었다")
        with self.subTest("a_newer_document_does_not_change_what_an_old_line_meant"):
            at = "2026-08-24T09:00:00+09:00"
            before = self.rows(("REQ-20260823-078", "2026-08-23T10:00:00+09:00"))
            after = before + self.rows(
                ("REQ-20260829-078-62x6", "2026-08-29T10:00:00+09:00"))
            self.assertEqual(self.m.resolve_short("REQ", "078", at, before)["id"],
                             self.m.resolve_short("REQ", "078", at, after)["id"])
        with self.subTest("the_number_is_compared_as_a_number_not_as_text"):
            rows = self.rows(("REQ-20260823-028", "2026-08-23T10:00:00+09:00"))
            at = "2026-08-24T09:00:00+09:00"
            for said in ("28", "028"):
                self.assertEqual(self.m.resolve_short("REQ", said, at, rows)["id"],
                                 "REQ-20260823-028")
        with self.subTest("a_different_kind_is_a_different_number"):
                rows = self.rows(("REQ-20260823-012", "2026-08-23T10:00:00+09:00"))
                self.assertIsNone(self.m.resolve_short(
                    "DOC", "012", "2026-08-24T09:00:00+09:00", rows))

            # ---------- ② 그때 없던 것은 짐작하지 않는다 ----------
        with self.subTest("a_number_that_did_not_exist_yet_is_not_guessed"):
            rows = self.rows(("REQ-20260827-041-62x6", "2026-08-27T10:00:00+09:00"))
            self.assertIsNone(self.m.resolve_short(
                "REQ", "041", "2026-08-21T18:02:06+09:00", rows))
        with self.subTest("without_a_write_time_nothing_is_resolved"):
                rows = self.rows(("REQ-20260823-078", "2026-08-23T10:00:00+09:00"))
                for at in (None, "", "언제였더라"):
                    self.assertIsNone(self.m.resolve_short("REQ", "078", at, rows))

            # ---------- 무엇을 축약으로 볼 것인가 ----------
        with self.subTest("only_a_kind_prefix_and_a_hyphen_makes_a_short_reference"):
                hit = lambda s: [m.group(0) for m in self.m.SHORT_REF_RE.finditer(s)]
                self.assertEqual(hit("REQ-028 을 봐"), ["REQ-028"])
                self.assertEqual(hit("DOC-12 · QST-3"), ["DOC-12", "QST-3"])
                for miss in ("#028 번", "v1.2-028", "버전 028", "x-REQ-028",
                             "REQ-20260828-021", "REQ-20260828-021-62x6"):
                    self.assertEqual(hit(miss), [], "%s 에 번졌다" % miss)

            # ---------- ③ 두 엔진이 같은 답을 낸다 ----------
        with self.subTest("the_screen_and_the_server_share_one_contract_table"):
            block = re.search(r"const CC_SHORT_VECTORS = \[([\s\S]*?)\n\];", self.src)
            self.assertIsNotNone(block, "화면에 계약표가 없다")
            vectors = re.findall(
                r'\["([A-Z]{3}-\d{1,3})",\s*"([^"]+)",\s*(?:"([^"]+)"|null)\]',
                block.group(1))
            self.assertGreaterEqual(len(vectors), 5, "계약표가 너무 얇다")
            self.assertTrue([v for v in vectors if not v[2]],
                            "'안 푼다' 는 줄이 표에 없다 — 가장 중요한 경우가 빠졌다")
            rows = self.m.load_catalog()
            for ref, at, want in vectors:
                kind, num = ref.split("-")
                got = self.m.resolve_short(kind, num, at, rows)
                self.assertEqual(got["id"] if got else None, want or None,
                                 "%s @%s — 화면 표와 서버 판정이 다르다" % (ref, at))
        with self.subTest("the_screen_resolves_by_write_time_too"):
                code = re.sub(r"/\*[\s\S]*?\*/", "", self.src)
                fn = re.search(r"function resolveShortRef\([\s\S]*?\n\}", code)
                self.assertIsNotNone(fn, "화면에 해석기가 없다")
                fn = fn.group(0)
                self.assertIn("t > atMs) continue", fn,
                              "화면이 그 줄을 쓴 뒤에 생긴 문서까지 후보로 센다")
                self.assertIn("atMs > 0", fn, "쓰인 때를 모르는데도 짐작한다")
                # 쓰인 때는 표시용 문자열이 아니라 원본 시각이어야 한다
                self.assertIn('Date.parse(at || "") || Date.now()', code,
                              "글이 쓰인 때를 받지 않는다")
                self.assertIn('"at": at,', open(S9, encoding="utf-8").read(),
                              "서버가 원본 시각을 함께 내주지 않는다")

            # ---------- ④ 짐작은 읽기 전용 ----------
        with self.subTest("a_guess_cannot_be_written_into_a_document"):
            code = re.sub(r"/\*[\s\S]*?\*/", "", self.src)
            peek = re.search(r"async function ccPeek\(a\)\{[\s\S]*?\n\}", code).group(0)
            self.assertIn('a.dataset.guess === "1"', peek, "짐작인지 보지 않는다")
            self.assertRegex(peek, r'guess \? "" : `<button class="pri" data-ppick',
                             "짐작에도 이어 말하기를 준다")
            self.assertIn("data-popen", peek, "문서 열기까지 막으면 확인할 길이 없다")
            # 무엇으로 읽었는지 카드가 말한다
            self.assertIn("을 이 문서로 읽었습니다", peek, "짐작을 실토하지 않는다")
        with self.subTest("a_guess_link_does_not_look_like_a_certain_one"):
                m = re.search(r"\.ccterm a\.doclink\.guess\{([^}]*)\}", self.src)
                self.assertIsNotNone(m, "짐작 링크에 다른 옷이 없다")
                self.assertIn("text-decoration-style:wavy", m.group(1))
                # 귀띔에 풀린 전체 id 를 적는다 — 짐작이 틀렸을 때 그 자리에서 알아챈다
                code = re.sub(r"/\*[\s\S]*?\*/", "", self.src)
                gl = re.search(r"const ccGuessLink = [\s\S]*?;\n", code).group(0)
                self.assertIn("title=", gl)
                self.assertIn("${esc(r.id)}", gl, "귀띔에 풀린 전체 번호가 없다")
                # 터미널 글자는 고치지 않는다 — 통째로 긁어 복사하는 자리다
                self.assertIn("${esc(raw)}</a>", gl, "원문 글자에 덧글을 붙였다")

            # ---------- 없는 문서에는 링크를 걸지 않는다 ----------
        with self.subTest("a_document_that_does_not_exist_stays_plain_text"):
            code = re.sub(r"/\*[\s\S]*?\*/", "", self.src)
            code = re.sub(r"(?m)^\s*//.*$", "", code)
            cc = re.search(r"const ccDocLink = id => \{[\s\S]*?\n\};", code).group(0)
            self.assertIn("const r = catFind(id);", cc, "존재를 묻지 않는다")
            self.assertIn("if (!r) return esc(id);", cc, "없는 문서에도 링크를 건다")
            li = re.search(r"const linkifyIds = [\s\S]*?\n", code).group(0) \
                + code.split("const linkifyIds =")[1][:300]
            self.assertIn("catFind(id)", li, "문서 본문 쪽 판정이 갈린다")
            self.assertIn("esc(shortId(id))", li)
        with self.subTest("both_places_ask_the_same_function"):
            code = re.sub(r"/\*[\s\S]*?\*/", "", self.src)
            for fn in ("const ccDocLink", "const linkifyIds"):
                blk = code[code.index(fn):code.index(fn) + 400]
                self.assertIn("catFind", blk, "%s 가 카탈로그에 묻지 않는다" % fn)

class ShortRefCorpus(unittest.TestCase):
    """저장소에 굳어 있는 축약을 실제로 대 본다 — 반증 조건(REQ-20260828-021).

    "당시 뜻" 을 독립적으로 아는 신탁은 없다. 우리가 세운 가정이 **"그 줄을 쓴
    때의 최신이 곧 작성자의 뜻"** 이고, 이 코퍼스는 그 가정 위에서 두 가지를
    잰다: ① 얼마나 풀리는가(미해결율) ② "최근 우선" 과 얼마나 갈리는가.
    ②가 작으면 이 작업 전체가 헛수고였다는 뜻이고, ①이 낮으면 사용자는 다시
    "왜 안 눌리냐" 고 할 것이다.
    """

    @classmethod
    def setUpClass(cls):
        cls.m = load_s9()
        cls.rows = cls.m.load_catalog()
        cls.refs = cls.collect(cls.m, cls.rows)

    @staticmethod
    def collect(m, rows):
        """vault 본문의 축약 언급 + 그 줄이 쓰인 때(노트 머리 ISO, 없으면 created)"""
        note = re.compile(r"^### (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+\d:]*)")
        out = []
        for r in rows:
            p = os.path.join(m.ROOT, r.get("path") or "")
            if not os.path.exists(p):
                continue
            meta, body = m.read_doc(p)
            at = meta.get("created") or ""
            for line in body.split("\n"):
                nm = note.match(line)
                if nm:
                    at = nm.group(1)
                    continue
                for mm in m.SHORT_REF_RE.finditer(line):
                    out.append((mm.group(1), mm.group(2), at))
        return out

    def test_short_ref_corpus(self):
        """저장소에 굳어 있는 축약을 실제로 대 본다 — 반증 조건(REQ-20260828-021)."""
        with self.subTest("the_corpus_is_big_enough_to_judge_by"):
            self.assertGreaterEqual(len(self.refs), 150,
                                    "축약이 이만큼 안 굳어 있으면 이 작업의 전제가 다르다")
        with self.subTest("almost_everything_resolves"):
            got = [self.m.resolve_short(k, n, at, self.rows) for k, n, at in self.refs]
            rate = sum(1 for g in got if g) / len(got)
            self.assertGreater(rate, 0.9,
                              "축약의 10%% 넘게 못 푼다 (%.0f%%)" % (rate * 100))
        with self.subTest("the_render_time_rule_would_have_been_wrong_most_of_the_time"):
            latest = {}
            for r in self.rows:
                g = re.match(r"^([A-Z]{3})-(\d{8})-(\d+)", r.get("id") or "")
                if not g:
                    continue
                key, t = (g.group(1), int(g.group(3))), self.m._epoch(r.get("created"))
                if t is not None and (key not in latest or t > latest[key][1]):
                    latest[key] = (r, t)
            diff = 0
            for kind, num, at in self.refs:
                a = self.m.resolve_short(kind, num, at, self.rows)
                b = latest.get((kind, int(num)), (None,))[0]
                if a and (not b or b["id"] != a["id"]):
                    diff += 1
            self.assertGreater(diff / len(self.refs), 0.5,
                               "'최근 우선' 과 답이 갈리는 줄이 절반도 안 된다 — "
                               "그렇다면 기준시각을 옮길 이유가 약하다 (%d/%d)"
                               % (diff, len(self.refs)))

