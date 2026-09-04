"""뜨는 순간 끊기는 요청들 — 부트가 받는 값은 한 문을 지난다 (REQ-20260828-039-62x6).

화면이 뜨는 순간 부트는 여덟 개 남짓한 API 를 부른다. 이 환경(WSL 로컬 중계)에서
그 여덟을 **동시에** 던지면 120 요청 중 25~30건이 `Connection reset by peer` 다
(실측). 하나씩이면 2%. 그런데 예전 부트는 자리마다 `catch(e){}` 로 제각각 물러났고,
**물러난 사실이 화면 어디에도 안 남았다.**

실제로 잡힌 판이 이것이다: `/api/users` 가 끊기면 저장해 둔 화면 설정(skin·tone)이
안 실려 **기본 스킨으로 떴다.** 사용자에게는 "가끔 내 화면 설정이 초기화된다" 로
보인다. 목록이 끊긴 판은 열 다섯이 "…없음" 으로 서서 "할 일이 없다" 로 읽혔다 —
없는 것과 안 온 것이 화면에서 같아 보이던 REQ-20260828-027 과 같은 결함이다.

계약은 다섯이다.

  ① **한꺼번에 안 던진다.** 동시에 도는 수를 묶고(SUPPLY_LANES), 첫 화면에 필요한
     것과 나중 것을 가른다 — usage·serveinfo·serveguard 는 판이 그려진 뒤다.
  ② **첫 그림을 붙잡지 않는다.** 늦는 값은 FIRST_PAINT_GRACE 까지만 봐 주고,
     늦게 온 값은 도착한 자리에서 스스로 화면을 고친다.
  ③ **물러섰다 다시 받는다.** 재시도는 자리마다가 아니라 공통 문(loadSupply)에 있다.
  ④ **조용히 기본값으로 안 떨어진다.** 화면 설정은 신원과 목록이 둘 다 손에 있을
     때만 적용한다 — 못 받은 채로 기본값을 덮으면 "설정이 초기화됐다" 가 된다.
  ⑤ **물러난 사실이 화면에 남고, 다시 받는 길이 있다.** 새 띠는 세우지 않는다 —
     헤더의 서버 상태 칩 · 판 · 신원 자리, 이미 있는 자리에 적는다.

`?apifail=users` / `?apifail=users:once` / `?apifail=users:3` 으로 이 상황을 손 없이
만들 수 있다(?transfail 과 같은 어휘).

실행: python3 tests/ boot_supply
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

# 부트가 첫 화면을 위해 받는 값 → 그 값을 받는 유일한 fetch 주소
BOOT_ENDPOINTS = ["/api/whoami", "/api/users", "/api/catalog", "/api/projects",
                  "/api/transitions"]
# 첫 화면 뒤로 미룬 값 (헤더 칩 · 알림 줄 — 판을 그리는 데 필요 없다)
LATER_ENDPOINTS = ["/api/claude/usage", "/api/serveinfo", "/api/serveguard"]


def grab(src, name):
    m = re.search(r"(?:async )?function %s\([^)]*\)\{[\s\S]*?\n\}" % name, src)
    assert m, name
    return m.group(0)


class BootSupply(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.boot = grab(cls.src, "boot")
        cls.door = grab(cls.src, "loadSupply")
        cls.pump = grab(cls.src, "supplyPump")
        cls.render = grab(cls.src, "render")
        cls.apply = grab(cls.src, "applyMyUI")

    # ── ① 한꺼번에 안 던진다 ────────────────────────────────────────────────
    def test_boot_supply(self):
        """BootSupply 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("b1_one_door"):
            self.assertNotIn("fetch(", self.boot, "부트가 API 를 직접 받는다")
            for url in BOOT_ENDPOINTS + LATER_ENDPOINTS:
                self.assertEqual(self.src.count('fetch("%s' % url), 1,
                                 "%s 를 받는 자리가 하나가 아니다" % url)
                m = re.search(r'loadSupply\([\s\S]{0,400}?fetch\("%s' % re.escape(url),
                              self.src)
                self.assertTrue(m, "%s 가 공통 문을 안 지난다" % url)
        with self.subTest("b2_concurrency_is_capped"):
            m = re.search(r"const SUPPLY_LANES = (\d+)", self.src)
            self.assertTrue(m, "동시 요청 상한이 없다")
            self.assertLessEqual(int(m.group(1)), 4,
                                 "상한이 느슨하다 — 이 환경에서 폭주는 25%가 끊긴다")
            self.assertIn("supplyBusy < SUPPLY_LANES", self.pump,
                          "펌프가 상한을 안 본다")
        with self.subTest("b3_later_waits_for_the_first_paint"):
                for url in LATER_ENDPOINTS:
                    seg = self.src[self.src.index('fetch("%s' % url):][:400]
                    self.assertIn("prio: 1", seg, "%s 가 첫 묶음에 섞여 있다" % url)
                self.assertIn("supplyRelease", self.boot)
                self.assertLess(self.boot.index("render()"), self.boot.index("supplyRelease()"),
                                "나중 것이 첫 그림보다 먼저 풀린다")
                self.assertIn("supplyOpen", self.pump,
                              "펌프가 '아직 안 풀렸다'를 안 본다")

            # ── ② 첫 그림을 붙잡지 않는다 ──────────────────────────────────────────
        with self.subTest("b4_first_paint_is_not_held"):
            m = re.search(r"const FIRST_PAINT_GRACE = (\d+)", self.src)
            self.assertTrue(m, "첫 그림이 값을 무한정 기다린다")
            self.assertLessEqual(int(m.group(1)), 1000,
                                 "봐 주는 시간이 길다 — 사람이 그만큼 흰 화면을 본다")
            self.assertIn("Promise.race", self.boot, "부트가 늦는 값을 안 놓아 준다")
        with self.subTest("b5_late_value_fixes_the_screen"):
                self.assertIn("paintedWith", self.boot,
                              "그릴 때의 상태를 안 들고 있다 — 다시 그릴 근거가 없다")
                i = self.boot.index("paintedWith")
                self.assertIn("render()", self.boot[i:i + 300],
                              "늦게 온 목록이 판을 안 고친다")

            # ── ③ 물러섰다 다시 받는다 ────────────────────────────────────────────
        with self.subTest("b6_backs_off_and_retries"):
            self.assertTrue(re.search(r"for\s*\(", self.door), "한 번만 받고 만다")
            self.assertIn("setTimeout", self.door, "물러섰다 다시 받지 않는다")
            self.assertIn("SUPPLY_BACKOFF", self.door)
            self.assertIn('s.state = "lost"', self.door,
                          "끝내 못 받은 사실을 안 남긴다")
        with self.subTest("b7_unusable_answer_is_not_success"):
                self.assertIn("d != null", self.door)
                for name, guard in (("loadWhoami", "j.user"),
                                    ("loadUsers", "Array.isArray(j.users)"),
                                    ("refreshProjects", "Array.isArray(j.projects)"),
                                    ("refreshCatalog", "Array.isArray(j)")):
                    self.assertIn(guard, grab(self.src, name),
                                  "%s 가 쓸 수 없는 답을 성공으로 친다" % name)

            # ── ④ 조용히 기본값으로 안 떨어진다 ───────────────────────────────────
        with self.subTest("b8_ui_settings_never_fall_back_silently"):
                self.assertIn("window.__users", self.apply)
                self.assertIn("window.__whoami", self.apply)
                self.assertTrue(re.search(r"if \(!window\.__users \|\| !window\.__whoami\) return",
                                          self.apply),
                                "신원·설정을 못 받은 채로 화면 설정을 적용한다")
                # 설정을 적용하는 자리는 initTheme(첫 칠)과 applyMyUI(내 설정) 둘뿐이다
                self.assertEqual(self.src.count("applyUISettings("), 3,
                                 "화면 설정을 적용하는 자리가 흩어져 있다")

            # ── ⑤ 물러난 사실이 화면에 남는다 ─────────────────────────────────────
        with self.subTest("b9_lost_is_said_in_places_that_already_exist"):
            chip = grab(self.src, "renderSvChip")
            self.assertIn("supplyLost", chip, "헤더가 못 받은 값을 말하지 않는다")
            # 새 띠를 세우지 않았다 — 알림 줄은 여전히 둘(oldcode · guard)뿐이다
            self.assertEqual(self.src.count('class="hrow3"'), 2,
                             "알림 띠를 새로 만들었다")
        with self.subTest("b10_empty_board_is_not_a_lost_board"):
            self.assertIn('supplyState("catalog") !== "ok"', self.render,
                          "판이 목록 길이만 보고 '없다'고 말한다")
            self.assertIn("supplyLine(", self.render)
            line = grab(self.src, "supplyLine")
            self.assertIn("받지 못했습니다", line)
            self.assertIn("불러오는 중", line, "받는 중과 못 받음을 안 가른다")
            self.assertIn("data-resupply", line, "다시 받는 길이 없다")
        with self.subTest("b11_unregistered_is_not_unreachable"):
            who = grab(self.src, "renderWhoami")
            self.assertIn('supplyLost("whoami")', who)
            mine = grab(self.src, "syncMineToggle")
            self.assertIn('supplyLost("whoami")', mine,
                          "못 받았을 때 '등록하세요' 라고 잘못 안내한다")
        with self.subTest("b12_retry_handler_exists"):
                self.assertIn("data-resupply", self.src, "다시 받기 버튼이 없다")
                self.assertIn("dataset.resupply", self.src, "다시 받기에 핸들러가 없다")
                again = grab(self.src, "supplyAgain")
                self.assertIn("SUPPLY_JOBS", again, "무엇을 다시 부를지 모른다")
                self.assertIn("s.tries = 0", again, "손으로 눌러도 횟수가 안 되돌아간다")

            # ── 손 없이 이 상황을 만든다 (진단·헤드리스 캡처용) ────────────────────
        with self.subTest("b13_diagnostic_switch"):
            self.assertIn("apifail", self.src, "재현 스위치가 없다")
            self.assertIn("API_FAIL", self.door, "스위치가 실제 경로를 안 탄다")
            self.assertIn("s.hits", self.door,
                          "진단 셈이 재시도 셈과 섞여 있다 — 손으로 눌러도 안 낫는다")
            self.assertIn("transfail", self.src,
                          "027 의 재현 절차(문서에 적힌 주소)가 깨졌다")

if __name__ == "__main__":
    unittest.main()
