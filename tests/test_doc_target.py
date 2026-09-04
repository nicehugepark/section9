"""문서에 이어 말하기 (REQ-20260827-064-62x6).

서버는 이미 `/api/chat` 의 `doc` 를 받으면 새 요청을 만들지 않고 그 문서 노트로
넣는다(커밋 6af957c). `doc` 는 본문 앞머리 표기(`>064 …`)보다 **우선**이다 —
눌러 고른 것이 타이핑보다 확실하기 때문이다. 화면이 할 일은 "집는 손"이다.

계약은 여섯이다.

  ① 카드를 눌러 대상을 집는다. 문서를 읽는 자리(뷰어)에서도 집을 수 있다.
  ② 집혔다는 것이 **입력창에서** 분명히 보인다.
  ③ 푸는 것은 **한 동작**이다.
  ④ 대상이 없을 때의 화면은 지금과 **완전히 같다** — 줄 자체가 없다.
  ⑤ 에이전트 지목과 양립하지 않는다 — 하나를 집으면 다른 쪽이 풀린다.
     (메시지는 에이전트에게 가거나 문서 노트로 들어간다. 둘 다일 수 없다.)
  ⑥ 이미 끝난 요청이면 한 줄로 말한다 — **보내기 전에** 말한다. 보내고 나서
     알려 주면 되돌릴 수 없다.

실행: python3 tests/ doc_target
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class DocTarget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # ---------- ① 집는 손 ----------

    def test_doc_target(self):
        """DocTarget 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("a_card_can_be_picked"):
            self.assertIn('class="pickdoc" data-pick=', self.src, "카드에 손잡이가 없다")
            self.assertRegex(self.src, r'closest\("\[data-pick\]"\)[\s\S]{0,120}docPick',
                             "손잡이를 눌러도 집히지 않는다")
            # 카드 자체가 문서를 여는 버튼이라, 손잡이 클릭이 카드로 흘러가면 안 된다
            self.assertRegex(self.src, r"if \(pk\)\{ e\.stopPropagation\(\); docPick",
                             "손잡이를 눌러도 문서가 열려 버린다")
            # 늘 떠 있는 버튼은 제목보다 먼저 읽힌다 — 얹었을 때만
            css = self._css_card()
            self.assertIn("display:none", css, "손잡이가 카드마다 상시로 붙어 있다")
            self.assertIn(".card:hover .pickdoc", css)
            self.assertIn(":focus-visible", css, "키보드로는 손잡이를 볼 수 없다")
        with self.subTest("the_viewer_can_pick_too"):
                self.assertIn('data-pick="${esc(m.id)}"', self.src,
                              "문서 뷰어에서 집을 수 없다")

            # ---------- ② 입력창에서 보인다 ----------
        with self.subTest("the_input_says_where_it_goes"):
                fn = self._fn("termTargetRender")
                self.assertIn("docTarget", fn, "문서 지목을 그리지 않는다")
                self.assertIn("에 남깁니다", fn, "어디로 가는지 말하지 않는다")
                self.assertIn("shortId(docTarget.id)", fn, "어느 문서인지 말하지 않는다")
                self.assertIn("docTarget.title", fn, "제목 없이 번호만 보여 준다")
                # 목록에서도 어디를 집었는지 잃지 않는다
                self.assertIn("function markPicked", self.src, "집힌 카드를 표시하지 않는다")
                self.assertIn("markPicked();", self._fn("renderBoard"),
                              "보드를 다시 그리면 표시가 사라진다")

            # ---------- ③ 푸는 것은 한 동작 ----------
        with self.subTest("release_is_one_gesture"):
                self.assertIn("termTargetClear", self._fn("termTargetRender"))
                self.assertIn("function docClear", self.src, "푸는 자리가 없다")
                m = re.search(r'if \(TERM !== T \|\| !evEl\(ev\.target\)\?\.closest\("#termTargetClear"\)\) return;'
                              r'[\s\S]{0,300}?\}\);', self.src)
                self.assertIsNotNone(m, "해제 버튼을 잡는 자리를 찾지 못했다")
                self.assertIn("docClear()", m.group(0), "문서 지목은 이 버튼으로 안 풀린다")

            # ---------- ④ 없을 때는 지금과 같다 ----------
        with self.subTest("nothing_changes_when_nothing_is_picked"):
                fn = self._fn("termTargetRender")
                self.assertIn("box.hidden = !t && !docTarget && !asArticle;", fn,
                              "대상이 없어도 빈 줄이 자리를 먹는다")
                # 아티클 모드(REQ-073)가 아니면 그 자리는 여전히 빈 문자열이다
                self.assertRegex(fn, r'box\.innerHTML = asArticle[\s\S]{0,260}?: "";',
                                 "대상이 없는데 내용이 남는다")
                # 보낼 때도 마찬가지 — 없으면 doc 를 붙이지 않는다
                send = self._fn("sendChat")
                self.assertIn("...(dt ? {doc: dt.id} : {})", send,
                              "집지 않았는데도 doc 를 보낸다")

            # ---------- ⑤ 양립하지 않는다 ----------
        with self.subTest("agent_and_doc_are_exclusive"):
                # 아티클 쓰기(REQ-20260827-073)가 더해져 갈래가 셋이 됐다 — 여전히 배타다
                self.assertIn("if (T) T.target = null;", self._fn("docPick"),
                              "문서를 집어도 에이전트 지목이 남는다")
                self.assertIn("if (T.target && docTarget){ docTarget = null; markPicked(); }",
                              self._fn("termTargetSet"),
                              "에이전트를 집어도 문서 지목이 남는다")
                send = self._fn("sendChat")
                self.assertIn("const dt = tgt ? null : docTarget;", send,
                              "둘을 함께 보낸다")

            # ---------- ⑥ 끝난 요청 ----------
        with self.subTest("a_finished_request_says_so_before_sending"):
            fn = self._fn("termTargetRender")
            self.assertRegex(fn, r'docTarget\.status === "done" \|\| docTarget\.status === "cancelled"',
                             "끝난 요청인지 보지 않는다")
            self.assertIn("다시 열리지는 않는다", fn, "무슨 뜻인지 말하지 않는다")
            # 보낸 뒤에도 한 줄 — "새 요청이 생겼다"로 읽히지 않게 말을 가른다
            send = self._fn("sendChat")
            self.assertIn("에 노트로 남았다", send, "어디에 붙었는지 말하지 않는다")
            self.assertIn('"로 기록됨"', send, "새 요청일 때의 말이 사라졌다")
        with self.subTest("it_can_be_opened_without_hands"):
                self.assertIn("[?&]pick=", self.src, "진단 파라미터가 없다")
                self.assertIn("docPick(m[1], pjump)", self.src,
                              "진단이 화면을 옮길지 말지를 고를 수 없다")
                m = re.search(r"const pjump = (.+);", self.src)
                self.assertIsNotNone(m, "건너뜀 스위치를 찾지 못했다")
                self.assertIn("[?&]jump", m.group(1),
                              "기본이 꺼짐이어야 한다 — 그냥 ?pick= 이 화면을 옮기면 "
                              "집힌 카드를 볼 수 없다")

            # ---------- helpers ----------

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _css_card(self):
        m = re.search(r"/\* -+ 문서 집기[\s\S]*?\*/([\s\S]*?)\n\.card \.id\{", self.src)
        self.assertIsNotNone(m, "문서 집기 CSS 블록을 찾지 못했다")
        return m.group(1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
