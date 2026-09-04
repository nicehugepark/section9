"""우선순위가 곧 순서다 — 화면의 손잡이와 그 값이 닿는 끝 (REQ-20260829-029-62x6).

원문: "우선순위 기능을 화면에서 조절할 수 있게 하고, 우선순위가 바뀌면 제일
최우선으로 실행될 수 있게 설계를 제대로 하고, 구현해줘."

두 겹이고 둘 다 여기서 잠근다.

  ① **손잡이** — 여태 이 축은 읽을 수만 있었다. 값을 바꾸는 길은 hovercard 가
     가르치는 `s9 set … --priority high` 하나였고, 그건 화면을 보는 사람에게
     "여기서는 못 한다"는 말이다. 순서를 정하는 판은 보드인데 정하는 자리가
     터미널에 있었다.
  ② **그 값이 실제 순서를 바꾼다** — ②가 없으면 ①은 숫자놀음이다. 화면이 바꾼
     값이 색인을 거쳐 `work_order()` 에 닿고, 그 함수가 `s9 next`(이어받을 것
     고르기)와 무인 작업자 스폰 순서를 정한다.

여기서 고정하는 결정:

  · 표기가 곧 손잡이다. 두 번째 자리를 만들면 보이는 것과 누르는 것이 갈린다.
  · 문(門)은 하나다 — CLI 든 화면이든 `apply_priority()` 를 지난다. 두 벌이면
    화면으로 바꾼 것만 History 에 안 남는 날이 온다.
  · **`updated` 는 안 건드린다.** 그 시각이 멈춤 판정의 시계(`quiet_mins`)라,
    카드를 끌어 올리는 것만으로 멈춤 경보가 꺼지면 안 된다 (REQ-20260829-034
    가 클레임에 대해 막은 그 병의 대칭).

실행: python3 tests/ priority_handle
"""
import contextlib
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request

from portpool import free_port, wait_server
from webasset import index_path, part

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
INDEX = index_path()


@contextlib.contextmanager
def borrowed_env(overrides):
    """이 프로세스의 환경을 잠깐 갈아입고 **반드시 되돌린다**.

    `bin/s9` 를 모듈로 읽으려면 `S9_ROOT` 가 import 시점에 서 있어야 해서
    전역 환경을 건드릴 수밖에 없다. 그런데 갈아입고 안 벗으면 그 값은 이
    프로세스가 끝날 때까지 남고, 스위트가 나란히 도는 판에서는 **옆 스위트가
    띄우는 자식 프로세스**가 그것을 물려받는다.

    실측: 이 파일을 배치에 넣자 `test_delegation_target` 다섯이 함께 넘어졌다
    (따로 돌리면 통과). 새어 나간 것은 `S9_USER=tester` 였다 — 그쪽 문서의
    주인은 alice 다. 모듈을 읽는 동안만 빌려 입고 곧바로 돌려준다.

    값이 `None` 이면 **벗긴다** — 옆 스위트가 켜 놓고 안 벗은 스위치(예:
    `S9_AUTO_RESUME`)가 이 시험의 답을 바꾸지 못하게 하려는 것이다."""
    saved = {k: os.environ.get(k) for k in overrides}
    for k, v in overrides.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _fn_body(src, name):
    """`function <name>(` 부터 다음 최상위 `function ` 선언 직전까지."""
    m = re.search(r"\n(?:async\s+)?function\s+" + re.escape(name) + r"\s*\(",
                  src)
    if not m:
        return ""
    rest = src[m.end():]
    nxt = re.search(r"\n(?:async\s+)?function\s+\w+\s*\(", rest)
    return rest[:nxt.start()] if nxt else rest


# ------------------------------------------------------------------ ① 손잡이
class HandleIsTheLabel(unittest.TestCase):
    """보이는 그 글자가 손잡이다 — 세 화면이 한 함수를 쓰므로 셋 다 눌린다."""

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.html = f.read()
        cls.prio = _fn_body(cls.html, "prioHTML")

    def test_label_carries_the_handle(self):
        """표기 함수가 대상 문서를 실어 낸다 — 이것이 없으면 눌러도 무엇을
        바꾸는지 모른다."""
        self.assertIn("data-prioset=", self.prio,
                      "우선순위 표기에 손잡이가 없다 — 화면에서 못 바꾼다")
        self.assertIn("r.id", self.prio,
                      "손잡이가 어느 문서인지 말하지 않는다")

    def test_handle_is_a_button(self):
        """button 이라야 키보드·보조기술이 저절로 닿는다. span 에 클릭만
        얹으면 마우스 있는 사람만 쓸 수 있는 기능이 된다."""
        self.assertRegex(self.prio, r'<button type="button" class="prio',
                         "손잡이가 버튼이 아니다")

    def test_one_renderer_still(self):
        """카드·Docs 행·문서 뷰어가 여전히 한 함수를 쓴다 — 손잡이가 한 화면에만
        생기면 '어디서는 되고 어디서는 안 되는' 기능이 된다."""
        self.assertGreaterEqual(len(re.findall(r"prioHTML\(", self.html)), 4)
        self.assertEqual(len(re.findall(r"\nfunction\s+prioHTML\s*\(",
                                        self.html)), 1,
                         "표기 함수가 둘 이상이다")

    def test_tooltip_says_it_can_be_pressed(self):
        """누를 수 있다는 사실은 글자가 말해야 한다 — 밑줄만으로는 손을
        얹기 전까지 아무 말도 하지 않는다."""
        self.assertRegex(self.prio, r"눌러서 바꾸기",
                         "툴팁이 누를 수 있다고 말하지 않는다")


class HandleBeatsTheCard(unittest.TestCase):
    """손잡이는 카드가 아니다 — 문서를 여는 길보다 먼저 잡힌다."""

    @classmethod
    def setUpClass(cls):
        cls.events = part("app/events.js")

    def test_delegated_and_stops(self):
        m = re.search(r'closest\("\[data-prioset\]"\);\s*\n\s*if\s*\(\w+\)\{([^}]*)\}',
                      self.events)
        self.assertIsNotNone(m, "[data-prioset] 위임 손잡이가 없다")
        self.assertIn("stopPropagation", m.group(1),
                      "누르면 문서까지 열린다 — 전파를 끊지 않았다")
        self.assertIn("prioSet(", m.group(1), "창을 열지 않는다")

    def test_caught_before_the_document(self):
        """세 화면 다 이 글자가 [data-doc] 행 안에 있다. 뒤에 서면 누르는
        순간 문서가 열리고 창이 그 뒤에서 뜬다."""
        self.assertLess(self.events.index("[data-prioset]"),
                        self.events.index('closest("[data-doc]")'),
                        "손잡이가 문서 열기보다 뒤에 선다")


class ChooserReusesTheDialog(unittest.TestCase):
    """새 컴포넌트를 만들지 않는다 — 이 화면에 이미 있는 고르기 창이다."""

    @classmethod
    def setUpClass(cls):
        cls.dialog = part("app/dialog.js")
        cls.body = _fn_body(cls.dialog, "prioSet")

    def test_uses_the_existing_choose_dialog(self):
        self.assertTrue(self.body, "prioSet() 이 없다")
        self.assertRegex(self.body, r'kind:\s*"choose"',
                         "고르기 창을 새로 지었다 — s9dlg 의 변형을 써라")

    def test_offers_the_four_tiers(self):
        """숫자 1~99 를 그대로 묻지 않는다 — 이 화면이 이미 내린 판단이다
        (사람이 읽는 글자는 등급 낱말)."""
        for v in ("90", "75", "50", "25"):
            self.assertIn(v, self.body, "등급 대표값 %s 가 없다" % v)
        self.assertIn("PRIO_TIERS[", self.body,
                      "등급 이름을 표에서 가져오지 않는다 — 낱말이 갈린다")

    def test_no_change_no_request(self):
        """같은 등급을 다시 눌러도 서버를 두드리지 않는다."""
        self.assertRegex(self.body, r"===?\s*cur\b|cur\s*===?",
                         "지금 값과 같은지 보지 않는다")

    def test_one_endpoint(self):
        """화면이 값을 보내는 자리는 하나다."""
        self.assertEqual(len(re.findall(r'"/api/priority"', self.dialog)), 1)
        self.assertIn("refreshCatalog", _fn_body(self.dialog, "postPriority"),
                      "바꾼 뒤 목록을 다시 받지 않는다")

    def test_failure_does_not_fake_success(self):
        post = _fn_body(self.dialog, "postPriority")
        self.assertIn("d.ok", post, "서버의 거절을 읽지 않는다")
        self.assertIn("alert", post, "실패를 말하지 않는다")

    def test_cli_hint_is_replaced_by_the_handle(self):
        """hovercard 마지막 줄이 더 이상 '터미널에서 하라'고 말하지 않는다."""
        hov = _fn_body(self.dialog, "showPrioHover")
        self.assertNotIn("--priority", hov,
                         "척도 카드가 여전히 CLI 로 가라고 가르친다")
        self.assertIn("눌러서", hov, "바꾸는 법을 말하지 않는다")


class HandleLooksLikeTheLabel(unittest.TestCase):
    """버튼이 됐다고 화면이 부풀지 않는다 — 브라우저 기본 옷을 벗긴다."""

    @classmethod
    def setUpClass(cls):
        cls.css = part("css/board.css")

    def test_button_chrome_is_stripped(self):
        m = re.search(r"\n\.prio\{([^}]*)\}", self.css)
        self.assertIsNotNone(m, ".prio 규칙을 찾지 못했다")
        for decl in ("background:none", "border:0", "padding:0"):
            self.assertIn(decl, m.group(1).replace(" ", ""),
                          ".prio 가 버튼 기본 옷(%s)을 벗기지 않는다" % decl)
        self.assertIn("cursor:pointer", m.group(1).replace(" ", ""),
                      "누를 수 있는 것으로 보이지 않는다")

    def test_affordance_is_on_hover_not_always(self):
        """306장이 늘 밑줄을 달면 판이 밑줄밭이 된다."""
        self.assertRegex(self.css, r"\.prio:hover \.pname\{[^}]*border-bottom",
                         "얹었을 때의 표시가 없다")

    def test_keyboard_focus_is_visible(self):
        self.assertRegex(self.css, r"\.prio:focus-visible\{[^}]*outline",
                         "키보드 초점이 보이지 않는다")


# -------------------------------------------------------------------- ② 문
class OneDoor(unittest.TestCase):
    """CLI 든 화면이든 같은 문을 지난다."""

    @classmethod
    def setUpClass(cls):
        with open(S9, encoding="utf-8") as f:
            cls.src = f.read()

    def test_server_route_exists(self):
        self.assertIn('parsed.path == "/api/priority"', self.src,
                      "화면이 두드릴 자리가 서버에 없다")

    def test_route_goes_through_the_door(self):
        m = re.search(r'parsed\.path == "/api/priority":(.*?)\n                elif',
                      self.src, re.S)
        self.assertIsNotNone(m)
        self.assertIn("set_doc_priority(", m.group(1),
                      "라우트가 제 손으로 문서를 쓴다 — 문을 지나야 한다")
        self.assertIn("user=actor", m.group(1),
                      "누가 바꿨는지를 클라이언트 말로 적는다")

    def test_cli_shares_the_door(self):
        body = re.search(r"\ndef cmd_set\(args\):(.*?)\n\ndef ", self.src, re.S)
        self.assertIsNotNone(body)
        self.assertIn("apply_priority(", body.group(1),
                      "CLI 가 제 규칙을 따로 들고 있다 — 두 벌이면 갈라진다")


class DoorBehaviour(unittest.TestCase):
    """문의 계약 — 근거는 남기고, 시계는 되감지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9prioh-")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_MACHINE": "testbox", "S9_USER": "tester",
                    "S9_SYNC": "off", "S9_AUDIT": "off"}
        for k in ("S9_SESSION", "S9_PORT"):
            self.env.pop(k, None)
        self.ok("init")
        self.a = self.new("첫 요청")
        self.b = self.new("둘째 요청")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # ------------------------------------------------------------ 도우미
    def cli(self, *argv):
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env=self.env, timeout=90,
                              stdin=subprocess.DEVNULL)

    def ok(self, *argv):
        r = self.cli(*argv)
        self.assertEqual(r.returncode, 0, "%s 실패: %s" % (argv, r.stderr))
        return r.stdout

    def new(self, title):
        return self.ok("new", "request", "--title", title, "--summary", "s",
                       "--body", "b").split()[0].strip()

    def mod(self):
        name = "s9prioh_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        with borrowed_env(self.env):
            spec.loader.exec_module(m)
        return m

    def doc_text(self, m, doc_id):
        with open(m.locate(doc_id), encoding="utf-8") as f:
            return f.read()

    def catalog(self):
        # 파일이 아니라 문 (REQ-20260902-035) — 갓 쓴 행은 델타에 있다.
        return [json.loads(l) for l in self.ok("index", "cat").splitlines()
                if l.strip()]

    # ------------------------------------------------------------ 계약
    def test_change_is_recorded(self):
        """왜 이게 위에 있나 — 나중에 반드시 묻는 질문이고, 답은 현재값
        하나로는 못 낸다."""
        m = self.mod()
        res = m.set_doc_priority(self.a, "high", user="tester",
                                 via="dashboard")
        self.assertEqual((res["old"], res["new"], res["changed"]),
                         (50, 75, True))
        self.assertRegex(self.doc_text(m, self.a),
                         r"- \S+ priority: 50 -> 75 \(by tester\) \[via dashboard\]")

    def test_same_value_is_a_noop(self):
        """같은 등급을 다시 눌러도 같은 줄이 쌓이지 않는다."""
        m = self.mod()
        m.set_doc_priority(self.a, 75, user="tester", via="dashboard")
        res = m.set_doc_priority(self.a, "high", user="tester", via="dashboard")
        self.assertTrue(res["ok"])
        self.assertFalse(res["changed"])
        self.assertEqual(
            len(re.findall(r"- \S+ priority: ", self.doc_text(m, self.a))), 1,
            "값이 그대로인데 History 가 늘었다")

    def test_updated_is_not_touched(self):
        """순서를 바꾼 것은 진전이 아니다 — 여기서 시계를 되감으면 카드를
        끌어 올리는 것만으로 멈춤 경보가 꺼진다 (REQ-20260829-034 의 대칭)."""
        m = self.mod()
        before = m.read_doc(m.locate(self.a))[0].get("updated")
        m.set_doc_priority(self.a, "urgent", user="tester", via="dashboard")
        after = m.read_doc(m.locate(self.a))[0].get("updated")
        self.assertEqual(before, after,
                         "우선순위를 바꾸는 것이 갱신 시각을 되감는다")

    def test_cli_records_too(self):
        """같은 문을 지나므로 CLI 로 바꾼 것도 근거가 남는다."""
        self.ok("set", self.a, "--priority", "urgent")
        m = self.mod()
        self.assertRegex(self.doc_text(m, self.a),
                         r"- \S+ priority: 50 -> 90 \(by ")

    def test_bad_value_preserves_the_old_one(self):
        """조용히 기본값으로 되돌리지 않는다 — 사람이 매긴 값이 사라지면
        사라졌다는 사실조차 안 남는다."""
        m = self.mod()
        m.set_doc_priority(self.a, 77, user="tester")
        for bad in ("0", "100", "abc", ""):
            with self.assertRaises(ValueError, msg=bad):
                m.set_doc_priority(self.a, bad, user="tester")
        self.assertEqual(m.doc_priority(m.read_doc(m.locate(self.a))[0]), 77)

    def test_only_requests_have_this_axis(self):
        """knowledge/session 에 붙이면 정렬에 쓰이지도 않는 값이 남는다."""
        kid = self.ok("new", "knowledge", "--title", "지식",
                      "--summary", "s", "--body", "b").split()[0].strip()
        m = self.mod()
        with self.assertRaises(ValueError):
            m.set_doc_priority(kid, "high", user="tester")

    def test_missing_document_is_refused(self):
        m = self.mod()
        with self.assertRaises(ValueError):
            m.set_doc_priority("REQ-19700101-999-zzzz", "high")


# ------------------------------------------- ③ 값이 **지연**과 **예산**에 닿는다
class RushStart(unittest.TestCase):
    """긴급·높음은 워처를 기다리지 않는다 (REQ-20260829-029 4차 반려).

    사용자: "승인이나, 반려를 하려면 화면에 보이는 글자만 바뀌는 것이 아니라,
    실제로 에이전트가 해당 요청에 대해서 작업을 캐치해야하고, 특히 긴급이나
    높음의 경우 바로 시작되어야 하는데 …"

    ②(순서)까지는 이미 서 있었다. 그런데 순서만으로는 '긴급'이 이름뿐이다 —
    유예 30초도 워처 주기 30초도 상수라 **긴급이든 보통이든 똑같이 최대 1분**을
    기다렸고, 예산이 바닥나면 순서가 첫째여도 뜰 자리가 없었다. 이 시험이
    잡는 것은 그 둘이다: **지연**과 **예산**.

    스폰은 가짜로 바꿔 놓고 잰다 — 진짜 워커를 띄우는 시험은 시험이 아니라 사고다.

    실행: python3 tests/ priority_handle
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9priorush-")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_MACHINE": "testbox", "S9_USER": "tester",
                    "S9_SYNC": "off", "S9_AUDIT": "off"}
        for k in ("S9_SESSION", "S9_PORT", "S9_AUTO_RESUME",
                  "S9_AUTO_RESUME_DISABLE"):
            self.env.pop(k, None)
        self.ok("init")
        self.doc = self.new("급한 요청")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # ------------------------------------------------------------ 도우미
    def cli(self, *argv):
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env=self.env, timeout=90,
                              stdin=subprocess.DEVNULL)

    def ok(self, *argv):
        r = self.cli(*argv)
        self.assertEqual(r.returncode, 0, "%s 실패: %s" % (argv, r.stderr))
        return r.stdout

    def new(self, title):
        return self.ok("new", "request", "--title", title, "--summary", "s",
                       "--body", "b").split()[0].strip()

    def mod(self):
        name = "s9priorush_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        with borrowed_env(self.env):
            spec.loader.exec_module(m)
        return m

    def rejected(self, prio=None):
        """반려된 문서 하나를 만든다 — 실제 전이 경로를 지난다."""
        if prio is not None:
            self.ok("set", self.doc, "--priority", str(prio))
        self.ok("set", self.doc, "--goal", "확인 가능한 목표")
        self.ok("status", self.doc, "in-progress", "--note", "착수")
        self.ok("status", self.doc, "review", "--note", "무엇이 달라졌나 · "
                                                       "어디를 눌러 보나")
        self.ok("status", self.doc, "in-progress", "--note", "반려: 다시")
        return self.doc

    def stub(self, m):
        """스폰을 가짜로 — 부른 사실만 남긴다."""
        seen = []
        m._spawn_rework = lambda doc_id, meta, note: (seen.append(doc_id)
                                                      or True)
        return seen

    def clean(self):
        """스폰 스위치를 **벗은 채로** 잰다 — 옆 스위트가 켜 놓고 안 벗은
        값이 이 시험의 답을 바꾸면, 통과도 실패도 아무 뜻이 없다."""
        return borrowed_env({"S9_AUTO_RESUME": None,
                             "S9_AUTO_RESUME_DISABLE": None})

    def meta_of(self, m, prio):
        return {"id": self.doc, "user": "tester", "priority": prio}

    # ---------------------------------------------------------- 지연
    def test_rush_has_no_grace(self):
        """유예는 살아 있는 세션이 먼저 집을 기회다 — 급한 것만 그것을 포기한다."""
        m = self.mod()
        for p in (90, 75):
            self.assertEqual(m.rework_grace(self.meta_of(m, p)), 0,
                             f"우선순위 {p} 가 아직 기다린다")
        for p in (74, 50, 25):
            self.assertGreater(m.rework_grace(self.meta_of(m, p)), 0,
                               f"우선순위 {p} 의 유예가 사라졌다 — 일하는 "
                               f"파일 위에 두 번째 손이 붙는다")

    def test_the_threshold_matches_the_screen(self):
        """사람이 '높음'으로 올렸는데 시스템이 안 서두르면 손잡이가 거짓말이다."""
        m = self.mod()
        self.assertEqual(m.PRIORITY_RUSH, m.PRIORITY_ALIASES["high"])
        self.assertIn("p >= 75 ? \"high\"", part("app/const.js"),
                      "화면의 등급 경계가 서버의 문턱과 갈라졌다")

    def test_rush_starts_at_the_transition(self):
        """워처의 다음 틱(최대 30초)을 기다리지 않는다."""
        m = self.mod()
        self.rejected(prio="urgent")
        seen = self.stub(m)
        with self.clean():
            self.assertTrue(m.maybe_auto_resume(
                self.doc, "review", "in-progress", "반려: 다시"))
        self.assertEqual(seen, [self.doc], "긴급인데 전이 자리에서 안 떴다")

    def test_normal_still_waits_for_the_watcher(self):
        """보통 이하는 종전 그대로 — 그 30초는 낭비가 아니라 선점 기회다."""
        m = self.mod()
        self.rejected()
        seen = self.stub(m)
        with self.clean():
            self.assertFalse(m.maybe_auto_resume(
                self.doc, "review", "in-progress", "반려: 다시"))
            self.assertEqual(seen, [], "보통 요청이 유예 없이 떴다")
            # 그래도 버려지지 않는다 — 유예를 0 으로 주면 워처가 집는다.
            self.assertEqual(m.rework_watch_tick(grace=0), [self.doc])

    def test_claimed_is_never_kicked(self):
        """이미 집힌 것 위에는 뜨지 않는다 — 워처와 같은 규율이다."""
        m = self.mod()
        self.rejected(prio="urgent")
        seen = self.stub(m)
        m.rework_claimed = lambda *a, **k: True
        with self.clean():
            self.assertFalse(m.rework_kick(self.doc))
        self.assertEqual(seen, [])

    def test_only_the_watchers_candidates_are_kicked(self):
        """루프 방어는 후보 판정 하나다 — 워커가 스스로 만든 전이(착수·상신)에
        다시 워커가 뜨면 그 요청은 영원히 돈다.

        환경변수를 이 프로세스에서 켜고 끄지 않는다: 스위트가 나란히 도는
        판이라 그 창(窓) 동안 옆 스위트의 자식 프로세스가 그 값을 물려받는다
        (실측: 이 시험을 넣자 test_delegation_target 다섯이 함께 넘어졌다)."""
        m = self.mod()
        self.rejected(prio="urgent")
        seen = self.stub(m)
        for lt in ((None, "in-progress", "review", "상신"),
                   (None, "review", "done", "승인"),
                   (None, "open", "in-progress", "CLI 착수"),
                   None):
            self.assertFalse(m.rework_candidate(lt), lt)
        # 워처가 안 집는 전이는 즉시 경로도 안 집는다 — 문이 하나다.
        self.assertTrue(m.rework_candidate(
            (None, "review", "in-progress", "반려")))
        self.assertTrue(m.rework_candidate(
            (None, "open", "in-progress", "끌어다 놓음 [via dashboard]")))
        self.assertEqual(seen, [])

    # ---------------------------------------------------------- 예산
    def test_the_budget_keeps_seats_for_rush(self):
        """순위가 있는데 자리가 없으면 순위는 아무 말도 하지 않는다.

        보통 요청들이 시간당 예산을 바닥까지 긁으면, 그다음에 올린 긴급은
        순서가 첫째여도 뜰 자리가 없었다. 뚫지 않고 **남긴다** — 상한 자체는
        그대로라 캡을 세운 이유(겹친 워커)는 유지된다."""
        m = self.mod()
        cfg = {"auto_resume_global_per_hour": 6,
               "auto_resume_global_per_day": 20,
               "auto_resume_rush_reserve": 2,
               "auto_resume_cooldown_sec": 0}
        m._auto_cap_counts = lambda nowt: {"hour_count": 4, "day_count": 4,
                                           "wake_hour_count": 0,
                                           "wake_day_count": 0}
        normal = m._auto_cap_block(self.doc, cfg, prio=50)
        self.assertTrue(normal, "보통이 예비 자리까지 먹었다")
        self.assertIn("긴급", normal, "왜 막혔는지가 사유에 없다 — 사람은 "
                                      "한도를 올리러 간다")
        self.assertFalse(m._auto_cap_block(self.doc, cfg, prio=90),
                         "긴급이 남겨 둔 자리를 못 쓴다")
        # 상한 자체는 그대로다 — 예비를 다 쓰면 긴급도 막힌다.
        m._auto_cap_counts = lambda nowt: {"hour_count": 6, "day_count": 6,
                                           "wake_hour_count": 0,
                                           "wake_day_count": 0}
        self.assertTrue(m._auto_cap_block(self.doc, cfg, prio=90),
                        "긴급이 상한을 뚫었다 — 캡을 세운 이유가 사라진다")

    def test_reserve_never_eats_the_whole_budget(self):
        """예비가 상한을 삼켜 아무도 못 뜨는 것이 더 나쁜 고장이다."""
        m = self.mod()
        cfg = {"auto_resume_rush_reserve": 99}
        self.assertEqual(m._rush_limits(cfg, 50, 3, 2), (1, 1))
        self.assertEqual(m._rush_limits(cfg, 90, 3, 2), (3, 2))


# ------------------------------------------------------- ② 값이 순서에 닿는다
class ChangedValueMovesTheQueue(unittest.TestCase):
    """①이 숫자놀음이 아닌 이유 — 바꾼 값이 색인을 거쳐 순서 함수에 닿는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9prioq-")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_MACHINE": "testbox", "S9_USER": "tester",
                    "S9_SYNC": "off", "S9_AUDIT": "off"}
        for k in ("S9_SESSION", "S9_PORT"):
            self.env.pop(k, None)
        subprocess.run([S9, "init"], capture_output=True, text=True,
                       env=self.env, timeout=90, stdin=subprocess.DEVNULL)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def new(self, title):
        r = subprocess.run(
            [S9, "new", "request", "--title", title, "--summary", "s",
             "--body", "b"], capture_output=True, text=True, env=self.env,
            timeout=90, stdin=subprocess.DEVNULL)
        # rc·stderr 를 삼키면 병렬 부하의 간헐 실패가 IndexError 로 둔갑해
        # 원인이 안 잡힌다 (REQ-20260830-029 계측이 실제로 겪은 것).
        if r.returncode != 0 or not r.stdout.split():
            raise AssertionError(
                f"s9 new rc={r.returncode}\nstdout={r.stdout!r}\n"
                f"stderr={r.stderr!r}")
        return r.stdout.split()[0].strip()

    def mod(self):
        name = "s9prioq_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        with borrowed_env(self.env):
            spec.loader.exec_module(m)
        return m

    def test_raised_document_leads_the_order(self):
        """뒤에 만든 것을 올리면 대기열 맨 앞으로 온다 — 화면이 바꾼 값이
        색인(catalog)까지 반영되지 않으면 순서는 그대로다."""
        first = self.new("먼저 만든 것")
        last = self.new("나중 만든 것")
        m = self.mod()
        rows = [r for r in m.load_catalog() if r["type"] == "request"]
        self.assertEqual(m.work_order(rows)[0]["id"], first,
                         "전제 확인 실패: 같은 값이면 오래 기다린 것이 먼저다")
        m.set_doc_priority(last, "urgent", user="tester", via="dashboard")
        # 색인을 **다시 읽는다** — 문이 rebuild_index 를 부르지 않으면 문서만
        # 바뀌고 순서를 정하는 쪽은 옛 값을 계속 본다.
        rows = [r for r in m.load_catalog() if r["type"] == "request"]
        self.assertEqual(m.work_order(rows)[0]["id"], last,
                         "올린 것이 대기열 앞으로 오지 않는다")

    def test_pickup_and_spawn_read_the_same_order(self):
        """`s9 next`(이어받기)와 무인 스폰이 그 순서를 본다 — 둘 중 하나라도
        제 기준을 들면 화면에서 올린 것이 실제로는 안 집힌다."""
        with open(S9, encoding="utf-8") as f:
            src = f.read()
        pick = re.search(r"\ndef next_pickup\(.*?\n\ndef ", src, re.S)
        self.assertIsNotNone(pick)
        self.assertIn("work_order(", pick.group(0),
                      "이어받을 것을 고르는 자리가 우선순위를 안 본다")
        tick = re.search(r"\ndef rework_watch_tick\(.*?\n\ndef ", src, re.S)
        self.assertIsNotNone(tick)
        self.assertIn("work_order(", tick.group(0),
                      "무인 스폰이 우선순위를 안 본다")


class RouteEndToEnd(unittest.TestCase):
    """진짜 서버를 세워 화면이 두드리는 그 자리를 두드린다.

    소스를 훑는 계약만으로는 라우트가 **돌아가는지**를 못 본다 — 이름 하나
    틀려도 grep 은 통과하고 사람은 창에서 실패를 본다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9prioe2e-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester", "S9_SYNC": "off", "S9_AUDIT": "off"}
        for k in ("S9_SESSION", "S9_PORT"):
            cls.env.pop(k, None)
        cls.cli("init")
        cls.cli("user", "add", "tester")
        cls.doc = cls.cli("new", "request", "--title", "끝단 확인",
                          "--summary", "s", "--body", "b").split()[0].strip()
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**cls.env, "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        try:
            cls.srv.wait(timeout=5)
        except Exception:
            cls.srv.kill()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def cli(cls, *argv):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=90, stdin=subprocess.DEVNULL)
        if r.returncode:
            raise AssertionError("s9 %s: %s%s" % (" ".join(argv), r.stdout,
                                                  r.stderr))
        return r.stdout

    def api(self, payload):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/priority" % self.port,
            data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_press_changes_the_value(self):
        code, res = self.api({"id": self.doc, "priority": 90})
        self.assertEqual(code, 200, res)
        self.assertEqual((res["ok"], res["old"], res["new"]), (True, 50, 90))
        # 색인까지 갔나 — 순서를 정하는 쪽이 읽는 곳은 문서가 아니라 이 줄이다.
        # 파일이 아니라 문으로 묻는다 (REQ-20260902-035).
        row = [r for r in
               (json.loads(x) for x in self.cli("index", "cat").splitlines()
                if x.strip())
               if r.get("id") == self.doc][0]
        self.assertEqual(row["priority"], 90)

    def test_bad_value_is_refused_with_a_reason(self):
        """창이 사람에게 보여 줄 문장이 있어야 한다 — 빈 실패는 못 고친다."""
        code, res = self.api({"id": self.doc, "priority": "abc"})
        self.assertEqual(code, 400)
        self.assertFalse(res["ok"])
        self.assertTrue(res.get("error"), "이유 없는 거절")

    def test_missing_document_is_refused(self):
        code, res = self.api({"id": "REQ-19700101-999-zzzz", "priority": 75})
        self.assertEqual(code, 400)
        self.assertFalse(res["ok"])


if __name__ == "__main__":
    unittest.main()
