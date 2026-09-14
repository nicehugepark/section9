"""첫 실행이 사용법 안내 요청을 심는다 (REQ-20260914-011-62x6).

주인 2026-09-14 19:52: 「새로 설치하고 general 프로젝트에 사용법에 대한 요청 문서들이
open 상태로 무사히 준비되어 있는 건가?」 글은 harness/common/onboarding/NN-*.md
(document-writer 의 몫)이고, 이 시험은 그 글이 아니라 **심는 기계**를 잰다 — 임시
S9_ROOT 와 임시 디렉토리의 가짜 안내 파일 셋으로. 심는 자리는 기본 프로젝트가 처음
서는 순간(ensure_default_project)이라, 첫 실행의 이름 물음 뒤에 오는 그 호출을 그대로
부른다(소스 글자가 아니라 함수를 불러 잰다). s9 프로세스는 띄우지 않는다.

실행: python3 tests/ onboarding_seed
"""
import importlib.machinery
import importlib.util
import os
import re
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9.py")
ID_RE = re.compile(r"^REQ-\d{8}-\d{3}-[0-9a-z]{4}$")

# (파일 이름, title, size, tags 표기) — tags 는 사람이 손으로 쓰는 세 꼴을 다 섞는다
FAKE = [
    ("01-start.md", "첫 화면 읽기", "S", '["onboarding", "guide"]'),
    ("02-request.md", "요청 만들기", "M", "[onboarding]"),
    ("03-review.md", "확인 대기 판정", "L", "guide, review"),
]


def load(root):
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        name = "s9_onb_%d" % abs(hash(root))
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


def fake_file(title, size="S", tags='["onboarding"]', with_title=True):
    head = f"title: {title}\n" if with_title else ""
    return (f"---\n{head}summary: {title} 요약\ngoal: {title} 를 읽은 사람이 한 가지를 해 본다\n"
            f"size: {size}\ntags: {tags}\n---\n## Original\n\n{title} 본문 첫 줄.\n\n"
            f"    ~/section9/bin/s9 digest\n\n## Notes\n\n여기는 담기지 않는다.\n")


def write_fake(directory, entries=FAKE):
    os.makedirs(directory, exist_ok=True)
    for name, title, size, tags in entries:
        with open(os.path.join(directory, name), "w", encoding="utf-8") as f:
            f.write(fake_file(title, size, tags))
    return directory


class FirstRunPlantsTheGuides(unittest.TestCase):
    """빈 저장소 → 사람 등록 → 기본 프로젝트가 서는 순간(첫 실행의 이름 물음 뒤)."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-onb-")
        self.m = load(self.root)
        self.m.cmd_init(type("A", (), {})())
        self.m.do_user_add("hong", role="admin")
        self.files = write_fake(os.path.join(self.root, "fake-onboarding"))
        self.m.ONBOARDING_DIR = self.files

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _rows(self):
        return [r for r in self.m.load_catalog()
                if r.get("type") == "request" and "onboarding" in (r.get("tags") or [])]

    def test_n1_the_files_stand_as_open_root_requests_in_general_in_file_order(self):
        """정상: 셋이 open · general · onboarding · root · 파일의 size · 등록한 사람 · Original 본문으로,
        보통 요청과 같은 id 꼴로 서고 카탈로그에 바로 실린다."""
        slug = self.m.ensure_default_project()
        self.assertEqual(slug, self.m.DEFAULT_PROJECT_SLUG)
        rows = sorted(self._rows(), key=lambda r: r["id"])
        self.assertEqual([r["title"] for r in rows], [t for _n, t, _s, _g in FAKE])
        for r, (_name, title, size, _tags) in zip(rows, FAKE):
            self.assertRegex(r["id"], ID_RE)
            self.assertEqual(r["status"], "open", title)
            self.assertEqual(r["project"], slug, title)
            self.assertEqual(r["user"], "hong", title)
            self.assertEqual(r["size"], size, title)
            meta, body = self.m.read_doc(self.m.find_path(r["id"]))
            self.assertTrue(self.m.doc_root(meta), f"root 가 아니다: {title}")
            self.assertEqual(meta.get("parent", ""), "")
            self.assertEqual((meta.get("tags") or [])[0], "onboarding")
            self.assertTrue(meta.get("goal"), title)
            self.assertIn(f"{title} 본문 첫 줄.", body)
            self.assertIn("bin/s9 digest", body)
            self.assertNotIn("여기는 담기지 않는다", body, "Original 밖의 글이 담겼다")
            self.assertNotIn("summary:", body, "프론트매터가 본문에 섞였다")
        self.assertIn("guide", rows[0]["tags"])
        self.assertEqual(rows[2]["tags"], ["onboarding", "guide", "review"])
        state = self.m.onboarding_state()
        self.assertEqual(state.get("reason"), "seeded")
        self.assertEqual(state.get("ids"), [r["id"] for r in rows])

    def test_n2_the_board_order_is_the_file_order(self):
        """정상: 카드 정렬(가중치 내림차순, 같으면 나중 것이 위)에서 01→02→03 — 첫 파일이 가장 높고
        마지막이 기본값 50, 전부 보통 등급 안."""
        self.m.ensure_default_project()
        rows = self._rows()
        ordered = self.m.work_order(rows)
        self.assertEqual([r["title"] for r in ordered], [t for _n, t, _s, _g in FAKE])
        self.assertEqual([r["priority"] for r in ordered], [52, 51, 50])
        self.assertTrue(all(self.m.PRIORITY_DEFAULT <= r["priority"] < self.m.PRIORITY_RUSH
                            for r in rows))

    def test_n3_an_explicit_priority_in_the_file_wins(self):
        """정상: 파일이 priority 를 적으면 그 값이다(순서 규칙보다 앞선다)."""
        with open(os.path.join(self.files, "02-request.md"), "w", encoding="utf-8") as f:
            f.write(fake_file("요청 만들기", "M", "[onboarding]").replace(
                "size: M\n", "size: M\npriority: 60\n"))
        self.m.ensure_default_project()
        by_title = {r["title"]: r["priority"] for r in self._rows()}
        self.assertEqual(by_title["요청 만들기"], 60)
        self.assertEqual(by_title["첫 화면 읽기"], 52)

    def test_e1_a_second_run_plants_nothing_more(self):
        """경계(멱등): 프로젝트 세우기를 다시 불러도, 심는 함수를 직접 다시 불러도, 표식을 지운 뒤
        불러도 셋 그대로다 — 표식과 같은 title 검사 둘 다."""
        self.m.ensure_default_project()
        self.m.ensure_default_project()
        self.assertEqual(self.m.seed_onboarding_requests(self.m.DEFAULT_PROJECT_SLUG, "hong"), [])
        self.assertEqual(len(self._rows()), 3)
        os.remove(self.m.onboarding_mark_path())
        self.assertEqual(self.m.seed_onboarding_requests(self.m.DEFAULT_PROJECT_SLUG, "hong"), [])
        self.assertEqual(len(self._rows()), 3)

    def test_f1_a_joined_place_gets_none(self):
        """실패(합류): `s9 code --join` 이 남기는 표식 뒤에는 파일이 있고 사람이 등록돼 프로젝트가
        서도 0건이다 — 팀 vault 에 내 안내를 넣지 않는다."""
        self.assertTrue(self.m.onboarding_mark_joined())
        self.assertFalse(self.m.onboarding_mark_joined())
        self.assertEqual(self.m.ensure_default_project(), self.m.DEFAULT_PROJECT_SLUG)
        self.assertEqual(self._rows(), [])
        self.assertEqual(self.m.onboarding_state().get("reason"), "joined")

    def test_f2_a_vault_that_already_has_requests_is_not_a_fresh_install(self):
        """실패: 안내가 아닌 요청이 이미 있는 vault(clone 으로 받은 팀 저장소 등)에는 심지 않는다."""
        self.m.do_project_add("pay", name="결제", summary="", actor="hong")
        args = type("A", (), {"doc_type": "request", "title": "이미 있는 일", "summary": "",
                              "goal": "", "status": None, "size": "", "priority": None,
                              "user": "hong", "tag_list": [], "parent": None,
                              "derived_from": None, "relates": None, "ref_doc": None,
                              "ref_link": None, "ref_file": None, "project": "pay",
                              "project_tag": None, "body": "x", "body_file": None,
                              "origin": "human"})()
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.cmd_new(args)
        self.assertEqual(self.m.seed_onboarding_requests("pay", "hong"), [])
        self.assertEqual(self._rows(), [])
        self.assertFalse(os.path.exists(self.m.onboarding_mark_path()))

    def test_r1_no_files_is_quiet_and_the_project_still_stands(self):
        """회귀: 안내 파일이 없으면(빈 디렉토리·없는 디렉토리) 0건이고 첫 실행은 실패하지 않는다."""
        empty = os.path.join(self.root, "empty")
        os.makedirs(empty)
        self.m.ONBOARDING_DIR = empty
        self.assertEqual(self.m.ensure_default_project(), self.m.DEFAULT_PROJECT_SLUG)
        self.assertEqual(self._rows(), [])
        self.assertFalse(os.path.exists(self.m.onboarding_mark_path()))
        self.m.ONBOARDING_DIR = os.path.join(self.root, "does-not-exist")
        self.assertEqual(self.m.seed_onboarding_requests(self.m.DEFAULT_PROJECT_SLUG, "hong"), [])

    def test_r2_a_file_without_a_title_is_skipped_and_the_rest_stand(self):
        """회귀: 프론트매터가 깨진 파일(제목 없음) 하나는 건너뛰고 나머지는 선다 — 예외로 멈추지 않는다."""
        with open(os.path.join(self.files, "02-request.md"), "w", encoding="utf-8") as f:
            f.write(fake_file("요청 만들기", "M", with_title=False))
        self.m.ensure_default_project()
        titles = sorted(r["title"] for r in self._rows())
        self.assertEqual(titles, ["첫 화면 읽기", "확인 대기 판정"])


class TheFirstRunPlantsBeforeAnyoneIsRegistered(unittest.TestCase):
    """압축을 푼 자리의 첫 실행 — 등록된 사람도 프로젝트도 vault 디렉토리도 없는 자리에서
    심는다(cmd_code 가 저장소를 세우기 전에 부르는 그 호출). 담당자는 이 컴퓨터의 계정
    이름이고, 뒤에 사람이 등록되면 그 이름으로 이어진다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-onb-f-")
        self.m = load(self.root)
        self.m.ONBOARDING_DIR = write_fake(os.path.join(self.root, "fake-onboarding"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _rows(self):
        return [r for r in self.m.load_catalog()
                if r.get("type") == "request" and "onboarding" in (r.get("tags") or [])]

    def test_n4_the_guides_stand_before_registration_and_follow_the_registered_name(self):
        """정상: 등록 전 첫 실행에서 셋이 general 을 가리키며 open 으로 서고(프로젝트는 아직 없다),
        사람이 등록돼 프로젝트가 서는 순간 담당자가 그 이름으로 옮겨진다 — 셋 그대로, 중복 없음."""
        self.assertEqual(self.m.registered_users(), [])
        ids = self.m.seed_onboarding_requests(self.m.DEFAULT_PROJECT_SLUG, "acct")
        self.assertEqual(len(ids), 3)
        self.assertEqual(self.m.all_projects(), [])
        rows = self._rows()
        self.assertEqual({r["user"] for r in rows}, {"acct"})
        self.assertEqual({r["project"] for r in rows}, {self.m.DEFAULT_PROJECT_SLUG})
        self.assertEqual({r["status"] for r in rows}, {"open"})
        self.m.do_user_add("hong", role="admin")
        self.assertEqual(self.m.ensure_default_project(), self.m.DEFAULT_PROJECT_SLUG)
        rows = self._rows()
        self.assertEqual(sorted(r["id"] for r in rows), sorted(ids))
        self.assertEqual({r["user"] for r in rows}, {"hong"})
        meta, body = self.m.read_doc(self.m.find_path(ids[0]))
        self.assertEqual(meta.get("creator"), "hong")
        self.assertIn("user: acct -> hong", body)
        self.assertEqual(self.m.onboarding_state().get("ids"), ids)

    def test_n5_registering_under_the_same_name_touches_nothing(self):
        """경계: 계정 이름 그대로 등록하면(Enter) 담당자는 이미 그 이름이라 문서가 바뀌지 않는다."""
        ids = self.m.seed_onboarding_requests(self.m.DEFAULT_PROJECT_SLUG, "hong")
        self.m.do_user_add("hong", role="admin")
        self.assertEqual(self.m.onboarding_adopt("hong"), [])
        self.assertEqual(self.m.ensure_default_project(), self.m.DEFAULT_PROJECT_SLUG)
        _meta, body = self.m.read_doc(self.m.find_path(ids[0]))
        self.assertNotIn("user: hong ->", body)
        self.assertEqual(len(self._rows()), 3)

    def test_f3_adopt_does_not_take_a_registered_persons_documents(self):
        """실패: 담당자가 이미 등록된 다른 사람이면 잇지 않는다 — 남의 것을 가져오지 않는다."""
        self.m.seed_onboarding_requests(self.m.DEFAULT_PROJECT_SLUG, "kim")
        self.m.do_user_add("kim", role="admin")
        self.m.do_user_add("hong", role="member")
        self.assertEqual(self.m.onboarding_adopt("hong"), [])
        self.assertEqual({r["user"] for r in self._rows()}, {"kim"})
        self.assertEqual(self.m.onboarding_adopt("nobody"), [])


class TheFileIsReadTheWayPeopleWriteIt(unittest.TestCase):
    """파일 읽기 — 프론트매터의 세 꼴과 `## Original` 자르기. 저장소가 필요 없다."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9-onb-p-")
        cls.m = load(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_p1_frontmatter_forms(self):
        meta, body = self.m._onboarding_frontmatter(
            '﻿---\r\ntitle: "따옴표 제목"\r\nsize: m\r\ntags:\r\n  - onboarding\r\n  - "guide"\r\n'
            "priority: 55\r\n---\r\n## Original\r\n\r\n본문\r\n")
        self.assertEqual(meta["title"], "따옴표 제목")
        self.assertEqual(meta["tags"], ["onboarding", "guide"])
        self.assertEqual(meta["priority"], "55")
        self.assertEqual(self.m._onboarding_body(body), "본문")
        self.assertEqual(self.m._onboarding_tags("[a, b]"), ["onboarding", "a", "b"])
        self.assertEqual(self.m._onboarding_tags("a, onboarding b"), ["onboarding", "a", "b"])
        self.assertEqual(self.m._onboarding_tags(None), ["onboarding"])

    def test_p2_the_original_section_ends_at_the_next_heading_or_is_the_whole_body(self):
        self.assertEqual(self.m._onboarding_body("## Original\n\n하나\n\n둘\n\n## Notes\n셋\n"),
                         "하나\n\n둘")
        self.assertEqual(self.m._onboarding_body("\n제목 없는 글\n\n### 소제목\n그대로\n"),
                         "제목 없는 글\n\n### 소제목\n그대로")

    def test_p3_parse_normalizes_size_and_priority(self):
        p = os.path.join(self.root, "x.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("---\ntitle: 제목\nsize: xl\npriority: 999\n---\n## Original\n글\n")
        g = self.m.onboarding_parse(p)
        self.assertEqual((g["size"], g["priority"], g["body"], g["tags"]),
                         ("S", None, "글", ["onboarding"]))
        with open(p, "w", encoding="utf-8") as f:
            f.write("---\nsummary: 제목 없음\n---\n글\n")
        self.assertIsNone(self.m.onboarding_parse(p))
        self.assertEqual([self.m.onboarding_priority(i, 7) for i in range(7)],
                         [56, 55, 54, 53, 52, 51, 50])
        self.assertEqual(self.m.onboarding_priority(0, 40), self.m.PRIORITY_RUSH - 1)


if __name__ == "__main__":
    unittest.main()
