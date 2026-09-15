"""사람은 이름으로 보이고, 계정은 id 로 남는다 (REQ-20260915-031-62x6 · -032-62x6).

주인 지시 2026-09-15: 「id, first name, last name, full name을 대시보드 전체에서
구석구석 어떻게 사용할지」. 이 제품은 사람을 **id** 로 다룬다 — `users/<id>/` 가
폴더 이름이고 문서 앞머리의 `user:` 이며 CLI 인자에 같은 글자로 다시 나온다.
그런데 사람이 화면에서 읽고 싶은 것은 id 가 아니라 제 이름이다.

계약은 넷이다.

  ① **이름을 짓는 자리는 하나다.** `personName`(이름, 없으면 id)과
     `personTitle`(id 와 이름이 함께)이 state.js 한 곳에 있고, 호출부는 제 손으로
     `first + " " + last` 를 잇지 않는다 — 자리마다 규칙이 갈리면 같은 사람이
     화면마다 다른 이름으로 보인다(명령 표기에서 겪은 그대로, REQ-20260915-023).
  ② **카드의 주체는 이름으로 선다.** 배지의 얼굴(`badgeFace`)은 `personName` 을
     지난다.
  ③ **올려서 보이는 글에는 id 와 이름이 함께.** 배지의 `title` 은 `personTitle`
     을 지나는 글이다 — 올렸는데 이름만 다시 보이면 올린 값이 0 이다.
  ④ **이름이 없으면 종전 그대로 id.** 서버가 아직 이름을 안 실을 수 있고, 그때
     화면은 `@id` 로 선다 — 빈 자리도, 「이름 없음」 같은 자리 표시자도, 새어
     나온 `undefined` 도 없다. `@` 는 **계정의 표식**이라 이름에는 붙지 않는다.

  그리고 색조는 **id 로 잰다** — 이름으로 키를 삼으면 이름이 바뀌는 날 사람과
  색이 갈린다.

실행: python3 tests/ person_name
"""
import os
import re
import unittest
from webasset import index_path

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")
INDEX = index_path()


def _read(*parts):
    with open(os.path.join(WEB, *parts), encoding="utf-8") as f:
        return f.read()


class PersonName(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.state = _read("app", "state.js")
        cls.card = _read("app", "card.js")
        cls.css = _read("css", "board.css")

    # ① 짓는 자리는 하나
    def test_naming_lives_in_one_place(self):
        for fn in ("function personOf(", "function personId(",
                   "function personFull(", "personName =", "personTitle ="):
            self.assertIn(fn, self.state, "이름을 짓는 함수가 state.js 에 없습니다: " + fn)

    def test_callers_do_not_join_names_by_hand(self):
        """호출부가 성·이름을 제 손으로 잇지 않는다 — 규칙은 한 곳에만."""
        body = self.src.replace(self.state, "")
        hits = re.findall(r"first_name|last_name", body)
        self.assertEqual(hits, [], "state.js 밖에서 성·이름을 직접 읽습니다: %r" % hits)

    # ② 카드의 주체는 이름
    def test_badge_face_reads_the_name(self):
        m = re.search(r"function badgeFace\([\s\S]*?\n\}", self.card)
        self.assertTrue(m, "badgeFace 가 없습니다")
        self.assertIn("personName(", m.group(0),
                      "카드 배지가 이름을 지나지 않습니다")

    # ③ 올려서 보이는 글에는 id 와 이름이 함께
    def test_hover_carries_both(self):
        m = re.search(r"function ownerBadgeHTML\([\s\S]*?\n\}", self.card)
        self.assertTrue(m, "ownerBadgeHTML 이 없습니다")
        self.assertIn("title=", m.group(0))
        tell = re.search(r"function lineageTell\([\s\S]*?\n\}", self.card)
        self.assertTrue(tell, "lineageTell 이 없습니다")
        self.assertIn("personTitle(", tell.group(0),
                      "손 위의 글이 id 와 이름을 함께 말하지 않습니다")

    def test_person_title_says_both(self):
        m = re.search(r"personTitle = [\s\S]*?\n\};", self.state)
        self.assertTrue(m, "personTitle 이 없습니다")
        self.assertIn("full ?", m.group(0))
        self.assertIn("(${id})", m.group(0),
                      "올려서 보이는 글에 id 가 없습니다")

    # ④ 이름이 없으면 종전 그대로 id
    def test_falls_back_to_id(self):
        m = re.search(r"const personName = [^\n]*", self.state)
        self.assertTrue(m)
        self.assertIn("personId(", m.group(0),
                      "이름이 없을 때 id 로 대신하지 않습니다")
        # 사람 자리에 자리 표시자를 두지 않는다 (배지·계보는 card.js 의 몫)
        self.assertNotIn("이름 없음", self.card, "자리 표시자를 두지 않습니다")

    def test_at_sign_marks_the_account_only(self):
        """`@` 는 계정의 표식이다 — 이름에는 붙지 않는다."""
        self.assertIn('.badge::before{content:"@"}', self.css)
        self.assertIn(".badge.named::before{content:none}", self.css)

    def test_name_is_not_monospaced(self):
        """고정폭에는 한글 얼굴이 없다 — 이름은 본문체, 계정 id 는 고정폭."""
        m = re.search(r"\.badge\.named \.bnm\{[^}]*\}", self.css)
        self.assertTrue(m, ".badge.named .bnm 규칙이 없습니다")
        self.assertIn("var(--sans)", m.group(0))
        self.assertNotIn("var(--mono)", m.group(0))

    # ⑤ 사람이 읽는 자리는 모두 같은 한 함수를 지난다 (REQ-20260915-035-62x6)
    def test_people_places_read_the_name(self):
        """사람 칸·작성자·미리보기 머리는 이름으로 선다 — 자리마다 손으로 짓지 않는다."""
        for parts, needle, where in (
                (("app", "docs.js"), "personBadgeHTML(m.user", "아티클의 쓴 사람"),
                (("app", "project.js"), "personName(m.user)", "프로젝트 멤버 표의 사람 칸"),
                (("app", "dialog.js"), "personName(r.user)", "문서 미리보기의 머리줄"),
                (("app", "tidy.js"), "personName(r.user", "휴지통·보관함 줄"),
                (("app", "settings.js"), "personName(u)", "사용자 관리 목록"),
        ):
            self.assertIn(needle, _read(*parts),
                          where + " 가 이름을 지나지 않습니다")

    def test_badge_is_built_in_one_place(self):
        """배지의 속을 손으로 다시 짓지 않는다 — 이니셜 마크는 badgeFace 한 곳."""
        self.assertEqual(self.src.count('<i class="av">'), 1,
                         "배지를 손으로 복제한 자리가 있습니다")
        self.assertIn("const personBadgeHTML =", self.card,
                      "읽기만 하는 자리의 사람 배지가 한 줄로 서 있지 않습니다")

    # 기계가 읽는 값은 id 그대로 — 라벨만 이름이다
    def test_machine_values_stay_the_id(self):
        app = _read("app", "app.js")
        m = re.search(r"const fill = \(sel, vals, label\) => \{[\s\S]*?\n  \};", app)
        self.assertTrue(m, "필터를 채우는 자리가 없습니다")
        self.assertIn("o.value = v;", m.group(0),
                      "필터 값이 id 가 아닙니다 — 카탈로그의 user 와 글자가 갈립니다")
        self.assertIn("o.textContent = face(v)", m.group(0),
                      "필터의 보이는 글자가 이름을 지나지 않습니다")
        self.assertIn('fill("#f-user", catalog.map(r => r.user), personName)', app,
                      "사람 필터가 이름을 라벨로 쓰지 않습니다")
        pick = re.search(r"const pickItem = [\s\S]*?\}\);", self.card)
        self.assertTrue(pick, "담당 고르기의 항목을 짓는 자리가 없습니다")
        self.assertIn("key: name", pick.group(0),
                      "담당 고르기의 값이 id 가 아닙니다 — /api/assign 이 받는 글자가 갈립니다")
        self.assertIn("label: personName(", pick.group(0),
                      "담당 고르기의 라벨이 이름이 아닙니다")
        prj = _read("app", "project.js")
        for attr in ('data-pjmem="${esc(m.user)}"', 'data-pjrm="${esc(m.user)}"'):
            self.assertIn(attr, prj, "DOM 키·API 인자가 id 가 아닙니다: " + attr)

    # 색조는 id 로 잰다
    def test_hue_is_keyed_on_the_id(self):
        m = re.search(r"function badgeAttrs\([\s\S]*?\n\}", self.card)
        self.assertTrue(m, "badgeAttrs 가 없습니다")
        self.assertIn("tagHue(personId(", m.group(0),
                      "색조가 id 가 아닌 것으로 매겨집니다")


if __name__ == "__main__":
    unittest.main()
