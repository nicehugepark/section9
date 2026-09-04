"""타임존을 골라서 고른다 (REQ-20260828-029-62x6).

사용자: "개인 설정의 timezone을 선택할 수 있게 해줘. 타자로 칠 수 있지만, 검색과
선택을 같이 할 수 있게."

지금까지 이 칸은 빈 입력칸이었고, **오타는 조용히 물러섰다** — 화면은
`Asia/Seuol` 을 저장했다고 보여 주는데 시각은 시스템 로컬이었다. 그 거짓말을
없애는 것이 이 작업의 본질이다.

계약은 일곱이다.

  ① **목록의 출처는 서버다.** 브라우저 `Intl.supportedValuesOf` 와 서버
     zoneinfo 는 목록이 다르다 — 다르면 "화면에 없는데 저장은 되는 이름"이
     생긴다. 고르는 목록과 저장을 판정하는 목록이 같아야 한다.
  ② **`Etc/*` 와 `UTC` 같은 호환용 이름은 훑는 목록에서 뺀다.** `Etc/GMT+9` 는
     POSIX 규약 탓에 실제로 UTC−9 라, 448개 사이에 섞어 두면 이름만 보고
     고르는 사람을 속인다. 직접 칠 때만 나온다.
  ③ **`Factory`·`localtime` 은 어떤 검색어로도 나오지 않는다** — 시간대가
     아니라 파일 시스템 부산물이다.
  ④ **모르는 이름은 저장이 거절한다.** 조용히 받아 두고 시각만 물러서는 것이
     지금까지의 결함이었다.
  ⑤ **한 줄에 이름과 지금 몇 시인가 둘뿐.** 오프셋은 화면에서 빼고 검색어로만
     받는다. 한국어 도시명은 병기하지 않는다 — 498개 중 번역표가 있는 것이
     30개 남짓이라 절반만 한국어인 목록은 미완성으로 읽힌다. 한국어는
     **보이지 않는 검색어**로 둔다.
  ⑥ **고르면 바로 저장되고, 실패하면 보이는 값이 되돌아온다.** 그리고 낡은
     값을 덮어쓸 다른 저장 경로가 없어야 한다 — `설정 저장` 버튼이 렌더
     시점의 값을 함께 보내면 방금 고른 값이 지워진다.
  ⑦ **Tab 은 고르지 않고 닫힌다.** 콤보박스의 가장 흔한 결함이고, 시간대는
     잘못 저장돼도 즉시 티가 안 나 피해가 오래간다. 확정은 Enter 하나뿐.

실행: python3 tests/ timezone_pick
"""
import importlib.machinery
import importlib.util
import os
import re
import tempfile
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
INDEX = index_path()


class TimezoneList(unittest.TestCase):
    """서버가 내주는 목록 — 고르는 자리와 저장을 판정하는 자리의 단일 출처."""

    @classmethod
    def setUpClass(cls):
        # 임시 루트는 이 모듈을 들일 때만 필요하다 — 남의 테스트에 흘리면
        # 그쪽이 빈 저장소를 보게 된다
        cls._prev_root = os.environ.get("S9_ROOT")
        os.environ["S9_ROOT"] = tempfile.mkdtemp(prefix="s9tz-")
        spec = importlib.util.spec_from_loader(
            "s9tz", importlib.machinery.SourceFileLoader("s9tz", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        cls.d = cls.m.timezone_list()
        cls.names = {z["name"] for z in cls.d["zones"]}
        cls.legacy = {z["name"] for z in cls.d["legacy"]}
        if cls._prev_root is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = cls._prev_root

    # ---------- ① 저장을 판정하는 그 목록 ----------

    def test_timezone_list(self):
        """서버가 내주는 목록 — 고르는 자리와 저장을 판정하는 자리의 단일 출처."""
        with self.subTest("every_offered_name_is_a_name_this_server_can_store"):
            import zoneinfo
            for name in list(self.names)[:40] + list(self.legacy):
                zoneinfo.ZoneInfo(name)   # 못 해석하면 여기서 터진다
        with self.subTest("the_offered_list_is_the_full_tzdata_list"):
                import zoneinfo
                all_names = zoneinfo.available_timezones()
                self.assertEqual(self.names | self.legacy,
                                 all_names - {"Factory", "localtime"},
                                 "서버 목록이 tzdata 와 다르다")

            # ---------- ② 호환용 이름은 훑는 목록 밖 ----------
        with self.subTest("the_gmt_plus_nine_trap_is_not_in_the_browsable_list"):
                self.assertNotIn("Etc/GMT+9", self.names)
                self.assertIn("Etc/GMT+9", self.legacy)
                # 훑는 목록에는 `Etc/` 도 슬래시 없는 호환 이름도 없다
                self.assertFalse([n for n in self.names if n.startswith("Etc/")])
                self.assertFalse([n for n in self.names if "/" not in n])
                for n in ("UTC", "EST", "GMT", "MST7MDT"):
                    self.assertIn(n, self.legacy, "%s 가 훑는 목록에 섞였다" % n)

            # ---------- ③ 파일 시스템 부산물 ----------
        with self.subTest("factory_and_localtime_are_offered_nowhere"):
                for junk in ("Factory", "localtime"):
                    self.assertNotIn(junk, self.names)
                    self.assertNotIn(junk, self.legacy)

            # ---------- ⑤ 한 줄에 적을 것 ----------
        with self.subTest("each_row_carries_only_a_name_and_the_offset_that_draws_its_clock"):
                row = self.d["zones"][0]
                self.assertEqual(set(row), {"name", "off"}, "줄에 군더더기가 붙었다")
                self.assertIsInstance(row["off"], int)
                seoul = [z for z in self.d["zones"] if z["name"] == "Asia/Seoul"][0]
                self.assertEqual(seoul["off"], 540)
                gmt9 = [z for z in self.d["legacy"] if z["name"] == "Etc/GMT+9"][0]
                self.assertEqual(gmt9["off"], -540, "이름이 +9 인데 실제는 −9 — 이게 함정이다")

            # ---------- ④ 모르는 이름은 거절 ----------
        with self.subTest("an_unknown_zone_is_refused_instead_of_silently_falling_back"):
            # 실제 호출은 등록 사용자가 필요하므로 검증 규칙을 그 함수에서 읽는다
            with open(S9, encoding="utf-8") as f:
                src = f.read()
            fn = re.search(r"def do_user_config_set\([\s\S]*?\n\ndef ", src).group(0)
            self.assertIn('key == "timezone"', fn, "시간대를 검증하지 않는다")
            self.assertIn("zoneinfo.ZoneInfo(value)", fn,
                          "목록을 만든 그 판정으로 저장을 막지 않는다")
            self.assertIn("모르는 시간대입니다", fn, "거절 이유를 사람 말로 말하지 않는다")

class TimezoneCombo(unittest.TestCase):
    """화면 — 검색과 선택이 같은 자리에서 일어난다."""

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        # 주석에 적어 둔 설명이 검사에 걸리면 다음 사람은 설명을 지워 통과시킨다
        cls.code = re.sub(r"/\*[\s\S]*?\*/", "", cls.src)
        cls.code = re.sub(r"(?m)^\s*//.*$", "", cls.code)

    def _fn(self, name):
        m = re.search(r"(?:async )?function %s\([\s\S]*?\n\}" % name, self.code)
        self.assertIsNotNone(m, "%s 가 없다" % name)
        return m.group(0)

    def _rule(self, sel):
        m = re.search(sel + r"\{([^}]*)\}", self.src)
        self.assertIsNotNone(m, "%s 규칙이 없다" % sel)
        return m.group(1)

    # ---------- ① 목록 출처 ----------

    def test_timezone_combo(self):
        """화면 — 검색과 선택이 같은 자리에서 일어난다."""
        with self.subTest("the_list_comes_from_the_server_not_from_the_browser"):
                self.assertIn('fetch("/api/timezones")', self.code, "서버에 묻지 않는다")
                self.assertNotIn("supportedValuesOf", self.code,
                                 "브라우저 목록을 쓴다 — 저장 검증과 출처가 갈린다")

            # ---------- ⑤ 한 줄에 적는 것 ----------
        with self.subTest("a_row_says_the_name_and_what_time_it_is_there"):
            row = self._fn("tzRowHTML")
            self.assertIn("tzClock(it.off)", row, "줄에 지금 시각이 없다")
            self.assertIn("지금", row)
            # 오프셋은 **적지 않는다** — 시계를 그리는 값일 뿐이다
            self.assertNotRegex(row, r"UTC[+-]|\+0?9:00", "줄에 오프셋을 적었다")
        with self.subTest("the_clock_says_which_day_it_is_when_the_day_differs"):
            fn = self._fn("tzClock")
            self.assertIn("어제", fn)
            self.assertIn("내일", fn)
        with self.subTest("korean_names_are_search_words_not_labels"):
                self.assertIn('"Asia/Seoul": "서울', self.code, "한국어 검색어가 없다")
                self.assertGreaterEqual(len(re.findall(r'"[A-Za-z_]+/[A-Za-z_/]+": "',
                                                       self.code)), 50,
                                        "별칭표가 너무 얇다 — 한국어로 못 찾는다")
                row = self._fn("tzRowHTML")
                self.assertNotIn("TZ_ALIAS", row, "한국어를 목록에 적었다")

            # ---------- ② 함정은 직접 칠 때만 ----------
        with self.subTest("an_offset_search_never_surfaces_the_gmt_trap"):
            fn = self._fn("tzFilter")
            self.assertIn("offq !== null", fn, "오프셋 질문을 따로 다루지 않는다")
            self.assertIn("!legacy && z.off === offq", fn,
                          "오프셋 검색이 호환용 이름을 끌어온다")
        with self.subTest("an_unsigned_number_is_not_an_offset"):
                fn = self._fn("tzOffQuery")
                self.assertIn("^([+-])", fn, "부호 없는 숫자를 오프셋으로 읽는다")

            # ---------- ⑥ 고르면 바로 저장 ----------
        with self.subTest("picking_saves_at_once"):
            fn = self._fn("tzSave")
            self.assertIn('"/api/user/config"', fn, "저장하지 않는다")
            self.assertIn('key: "timezone"', fn)
            self.assertIn("저장했습니다 — 이제 ${val} 기준입니다.", fn,
                          "알림이 무엇이 바뀌었는지 말하지 않는다")
        with self.subTest("a_failed_save_puts_the_old_value_back_on_screen"):
            fn = self._fn("tzSave")
            self.assertIn("const prev = S.saved", fn)
            self.assertIn("S.saved = prev; S.input.value = prev;", fn,
                          "실패해도 새 값이 화면에 남는다")
        with self.subTest("no_other_save_path_can_overwrite_the_picked_value"):
                self.assertNotIn('#cf-timezone', self.code,
                                 "옛 입력칸이 남아 있다 — 낡은 값이 다시 저장된다")
                m = re.search(r"const sets = \[[\s\S]*?\];", self.code)
                self.assertIsNotNone(m)
                self.assertNotIn("timezone", m.group(0),
                                 "설정 저장 버튼이 아직 timezone 을 함께 보낸다")

            # ---------- ⑦ 키보드 ----------
        with self.subTest("tab_closes_without_picking_and_enter_is_the_only_confirm"):
            fn = self._fn("tzWire")
            self.assertRegex(fn, r'e\.key === "Tab"\)\{\s*\n?\s*if \(S\.open\) tzClose\(true\)',
                             "Tab 이 고르지 않고 닫히지 않는다")
            self.assertIn('e.key === "Enter"', fn)
            self.assertIn("tzPick(S.idx)", fn, "Enter 로 확정하지 않는다")
            # 끝에서 멈춘다 — 순환하면 목록의 끝을 손으로 알 수 없다
            self.assertIn("Math.min(S.idx + 1, S.items.length - 1)", fn)
            self.assertIn("Math.max(S.idx - 1, 0)", fn)
        with self.subTest("escape_closes_without_leaving_typed_text_behind"):
                fn = self._fn("tzClose")
                self.assertIn("if (restore) S.input.value = S.saved;", fn)

            # ---------- 비어 있을 때 ----------
        with self.subTest("an_empty_setting_does_not_pretend_to_be_seoul"):
            self.assertNotIn('placeholder="Asia/Seoul"', self.code,
                             "빈 값에 거짓 예시를 흐리게 적었다 — 설정된 것처럼 읽힌다")
            self.assertIn('placeholder="설정 안 함"', self.code)
            fn = self._fn("tzNowRender")
            self.assertIn("이 컴퓨터의 시간대를 따릅니다", fn,
                          "물러서는 곳을 말하지 않는다")
            # 서버가 실제 해석 값을 주기 전까지 그 이름을 함부로 적지 않는다
            self.assertNotIn("KST", fn)
        with self.subTest("a_name_this_server_does_not_know_says_so"):
                fn = self._fn("tzNowRender")
                self.assertIn("이 이름을 모릅니다", fn)

            # ---------- 시계 ----------
        with self.subTest("the_clock_stops_when_nobody_is_looking_and_when_the_pane_closes"):
                fn = self._fn("tzTick")
                self.assertIn("document.hidden", fn, "안 보이는데도 계속 돈다")
                self.assertIn("tzStop()", fn, "판이 닫혀도 타이머가 남는다")
                self.assertIn("setInterval(tzTick, 30000)", self.code, "갱신 주기가 다르다")
                stop = self._fn("tzStop")
                self.assertIn("clearInterval(tzTimer)", stop)

            # ---------- 시각 언어 ----------
        with self.subTest("the_list_is_drawn_in_this_panel_s_own_vocabulary"):
            on = self._rule(r"\.tzpop \.tzrow\.on")
            self.assertIn("border-left-color:var(--text)", on, "고른 줄에 잉크 바가 없다")
            pop = self._rule(r"\.tzpop")
            self.assertNotIn("box-shadow", pop, "그림자를 썼다 — 이 판의 어휘가 아니다")
            self.assertNotIn("border-radius", pop, "라운드를 썼다")
            self.assertIn("border:1px solid var(--text)", pop)
            # 이름은 식별자다 — 모노
            self.assertIn("font-family:var(--mono)", self._rule(r"\.tzpop \.tzn"))

