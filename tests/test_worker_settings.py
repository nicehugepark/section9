"""설정을 화면에서 바꾼다 — 「백그라운드 작업」 판의 계약 (REQ-20260901-022-62x6).

사용자 질문 QST-20260901-006: "깃헙에 푸시 여부에 대해서 옵션 설정을 바꿨는데
어디서 하는거지?" 답이 없었던 이유는 화면에 자리가 없었기 때문이다 —
`auto_resume_gh` 는 「내 계정」 맨 끝의 `기타: {…}` **읽기 전용 JSON 한 줄**
62번째 글자로 서 있었고, 바꾸는 길은 `s9 user config` 뿐이었다.

이 시험이 지키는 계약:

  ① **자리** — Settings 좌측 목록에 「백그라운드 작업」이 「내 계정」 다음, 「사용자
     관리」 앞에 선다(나 → 나 → 남 → 전체).
  ② **행 목록은 config 가 아니라 화면이 정한다** — 아는 키 열넷이 표에 있고,
     모르는 `auto_resume_*`/`worker_*` 는 접두사로 제 자리에 간다.
  ③ **두 번 서지 않는다** — `extraCfg` 제외가 손으로 적은 목록이 아니라
     `WCFG_KEYS`·`wcfgMine` 에서 온다(판에 행이 늘면 제외도 저절로 는다).
     그리고 `기타: {…}` JSON 한 줄 자체가 화면에서 사라졌다.
  ④ **낱말** — 리드 판정이 확정한 것만 선다. 화면에서 내려진 낱말
     (깃헙·워크트리·작업 자리·사본·에이전트·워커)은 한 자도 없다.
     「푸시」도 없다: 023 이 같은 판에 세울 「올리기」와 한 개념 두 이름이 된다.
  ⑤ **무게는 색면이 아니다** — 사실 줄은 글자색뿐이고, 켤 때만 `s9dlg` 확인
     창이 선다(네이티브 confirm/alert 금지). 끌 때는 창이 없다.
  ⑥ **즉시 저장** — 이 판에 일괄 저장 단추가 없다(낡은 값이 방금 고른 값을
     덮는 사고를 이 폼이 이미 겪었다). 실패하면 손잡이를 되돌린다.
  ⑦ **윗스위치가 꺼져도 gh 사실 줄은 안 흐려진다** — "권한을 준 적 있다"가
     화면에서 사라지면 안 된다.
  ⑧ **서버가 화면과 같은 낱말로 말한다** — 스폰 차단문에서 세 번째 이름
     (「자동 이어가기」)과 원시 키 노출이 사라지고, 권한 거절문이 문장이 됐다.

실행: python3 tests/ worker_settings
"""
import os
import re
import unittest

import websrc
from webasset import index_path

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9")

# 이 판이 세우는 행 — 화면이 정한 목록이라, 여기 적힌 것이 곧 계약이다.
SWITCHES = ["auto_resume", "auto_resume_apply", "auto_resume_gh",
            "worker_worktree"]
TEXTS = ["auto_resume_model", "s9code_args"]
CAPS = ["auto_resume_grace_sec", "auto_resume_cooldown_sec",
        "auto_resume_max_inflight", "auto_resume_wake_per_hour",
        "auto_resume_wake_per_day", "auto_resume_global_per_hour",
        "auto_resume_global_per_day", "auto_resume_rush_reserve"]

# 화면에서 내려진 낱말 — 하나라도 서면 이미 내린 판정을 되돌리는 것이다.
BANNED = ["깃헙", "워크트리", "작업 자리", "에이전트", "워커", "다이제스트"]


def slice_between(src, start, end_after):
    i = src.index(start)
    j = src.index(end_after, i)
    j = src.index("\n}\n", j) + 3
    return src[i:j]


def strip_comments(js):
    """주석을 뺀 코드 — **화면에 서는 글자**만 남긴다.

    낱말 계약(내려진 낱말이 화면에 없다)은 화면 문자열의 계약이지 주석의
    계약이 아니다. 이 파일의 주석은 내려진 낱말을 **왜 안 쓰는지** 적기
    위해 일부러 그 낱말을 부른다 — 그것까지 금지하면 근거를 못 적는다.
    """
    js = re.sub(r"/\*[\s\S]*?\*/", " ", js)
    return "\n".join(ln for ln in js.splitlines()
                     if not ln.lstrip().startswith("//"))


class WorkerSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(index_path(), encoding="utf-8") as f:
            cls.src = f.read()
        with open(S9, encoding="utf-8") as f:
            cls.s9 = f.read()
        # 판을 짓는 코드 전부 — 마지막 함수(showWorkerCfg)까지.
        cls.wc = slice_between(cls.src, "/* workercfg.js", "function showWorkerCfg")
        # 낱말 계약은 주석이 아니라 **화면에 서는 글자**를 본다.
        cls.words = strip_comments(cls.wc)

    # ---- ① 자리 ---------------------------------------------------------
    def test_worker_settings(self):
        """WorkerSettings 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("left_list_places_worker_between_account_and_users"):
            m = re.search(r"const SECTIONS = \[[\s\S]*?\n  \];", self.src)
            self.assertIsNotNone(m, "좌측 목록(SECTIONS)을 찾지 못했다")
            order = re.findall(r'\["(display|account|worker|users|about)"',
                               m.group(0))
            self.assertIn("worker", order, "좌측 목록에 「백그라운드 작업」 구역이 없다")
            i = order.index
            self.assertLess(i("account"), i("worker"),
                            "「백그라운드 작업」은 「내 계정」 다음이다")
            self.assertLess(i("worker"), i("users"),
                            "「백그라운드 작업」은 「사용자 관리」 앞이다 (나 → 나 → 남)")
            self.assertRegex(self.src, r'\["worker", "백그라운드 작업"',
                             "구역 이름은 「백그라운드 작업」이다 (REQ-20260902-005)")
        with self.subTest("route_and_render_reach_the_panel"):
            # 주소(#settings/worker)로 바로 열리고, 그 갈래가 판을 그린다.
            self.assertIn('settingsSection === "worker"', self.src,
                          "worker 갈래가 renderSettingsSection 에 없다")
            self.assertIn("showWorkerCfg(", self.src, "판을 그리는 손이 없다")
        with self.subTest("nav_subtitle_doubles_as_state"):
                # 목록만 봐도 열려 있는 문이 보인다.
                self.assertIn("GitHub 권한 켬", self.words,
                              "gh 가 켜져 있으면 좌측 목록 부제가 그렇게 말해야 한다")
                self.assertIn("workerNavSub(", self.src)

            # ---- ② 행 목록은 화면이 정한다 --------------------------------------
        with self.subTest("every_known_key_gets_a_row"):
            for k in SWITCHES + TEXTS + CAPS:
                self.assertIn('key: "%s"' % k, self.wc, "%s 행이 없다" % k)
        with self.subTest("unknown_keys_are_routed_by_prefix_not_dropped"):
            self.assertIn("wcfgMine", self.wc, "모르는 키를 가르는 자가 없다")
            self.assertIn("아직 이름 없는 값", self.words)
            self.assertIn("그 밖의 값", self.src,
                          "「내 계정」 쪽 자리(그 밖의 값)가 없다")
        with self.subTest("row_list_is_not_driven_by_config"):
                # 아는 키는 config 에 없어도 행이 선다 — 목록을 순회하는 것은 상수다.
                for name in ("WCFG_SWITCHES.map", "WCFG_TEXTS.map", "WCFG_CAPS.map"):
                    self.assertIn(name, self.wc,
                                  "행을 %s 로 세우지 않으면 안 켠 스위치는 영영 안 보인다"
                                  % name)

            # ---- ③ 두 번 서지 않는다 --------------------------------------------
        with self.subTest("extra_cfg_excludes_every_key_that_got_a_row"):
            uf = websrc.fn(self, self.src, "showUserForm")
            self.assertIn("WCFG_KEYS.includes(k)", uf,
                          "자리를 얻은 키를 extraCfg 에서 빼지 않으면 두 번 선다")
            self.assertIn("wcfgMine(k)", uf,
                          "접두사로 데려간 키도 extraCfg 에서 빠져야 한다")
        with self.subTest("the_raw_json_line_is_gone"):
                self.assertNotIn("기타: ${esc(JSON.stringify", self.src,
                                 "읽기 전용 JSON 한 줄이 아직 남아 있다")

            # ---- ④ 낱말 ---------------------------------------------------------
        with self.subTest("labels_are_the_lead_verdict"):
            # 「worktree 쓰게 하기」 — 한때 「따로 떼어 놓고 일하기」였다.
            # 사용자가 반려했다(REQ-20260902-002): 남의 도구가 지은 이름은
            # 우리가 별명을 지어 주지 않는다. 별명은 두 사람 다 잃게 한다 —
            # git 을 모르는 사람은 여전히 못 읽고, 아는 사람은 잇지 못한다.
            # 행 이름은 **술어만** 진다 (REQ-20260902-005) — 개체 이름은 판 제목이
            # 한 번만 지고, 행이 그것을 되풀이하면 한 판에 이름이 열 번 선다.
            for label in ("맡기기", "파일 직접 고치기",
                          "내 GitHub 계정 쓰게 하기", "worktree 쓰게 하기"):
                self.assertIn(label, self.words, "확정 낱말이 아니다: " + label)
            self.assertNotIn("자동 이어받기", self.words,
                             "계정 스위치는 카드의 요청별 정책과 다른 이름을 쓴다")
        with self.subTest("no_word_that_was_taken_off_the_screen"):
            for w in BANNED:
                self.assertNotIn(w, self.words, "화면에서 내려진 낱말: " + w)
            # 「사본」은 worktree 의 기각된 **별명** — 낱말로 서면 안 된다.
            # (worktree 자체는 이제 원어로 선다. 내려간 것은 우리가 지은
            #  별명이지 git 이 지은 이름이 아니었다 — REQ-20260902-002.)
            self.assertNotRegex(self.words, r"저장소 사본|따로 떼어 둔 사본")
        with self.subTest("push_is_called_by_the_screen_name"):
            # 023 이 같은 판에 `push` 단추를 세운다 — 한 개념에 두 이름 금지.
            # 음차(「푸시」)도 옮김(「올리는 것」)도 아니고 **원어**다
            # (REQ-20260902-002): 화면을 닫고 그 일을 하려면 사람이 치는 글자가
            # `git push` 라, 그 글자가 곧 화면의 낱말이다.
            self.assertNotIn("푸시", self.words, "음차는 원어로 — `push`")
            self.assertNotIn("저장소에 올리는 것도", self.words,
                             "옮김도 반려됐다 — 남의 도구 이름은 그대로 세운다")
            self.assertIn("저장소에 push 하는 것도 그중 하나입니다", self.words)
        with self.subTest("on_off_words_carry_the_state"):
                # 색 없이 상태가 읽힌다 — 옵션 글자가 무슨 일이 일어나는지 말한다.
                for opt in ("켬 — ", "끔 — "):
                    self.assertIn(opt, self.words)
                self.assertNotRegex(self.words, r'>ON<|>OFF<|활성|비활성')

            # ---- ⑤ 무게 ---------------------------------------------------------
        with self.subTest("only_turning_gh_on_raises_a_dialog"):
            # `ask` 는 gh 항목 하나에만 있고, 켤 때(val === "on")만 지난다.
            self.assertEqual(self.wc.count("   ask: n => ({"), 1,
                             "확인 창은 gh 하나에만 붙는다")
            self.assertIn('if (r.ask && val === "on"', self.wc,
                          "끌 때는 창을 세우지 않는다")
            self.assertIn('cap: "권한"', self.wc)
        with self.subTest("no_native_dialogs"):
            self.assertNotRegex(self.words, r"\b(window\.)?(confirm|alert)\s*\(",
                                "네이티브 창 금지 — s9dlg 를 쓴다")
            self.assertIn("s9dlg(", self.wc)
        with self.subTest("fact_line_stands_only_while_it_is_on"):
            self.assertIn("r.fact && wcfgOn(cfg[r.key])", self.wc,
                          "사실 줄은 켜져 있는 동안에만 선다")
            self.assertIn("지금 켜져 있습니다", self.words)
        with self.subTest("weight_is_ink_not_a_colour_field"):
                css = websrc.css_section(self, self.src, r"/\* -+ 백그라운드 작업 설정")
                self.assertIn(".wfact", css, "사실 줄 규칙을 찾지 못했다")
                websrc.no_hex(self, css)
                # 색은 글자색 하나뿐 — 색면(배경 칠)도 좌측 세로 띠도 없다.
                self.assertNotRegex(css, r"background(-color)?\s*:\s*(?!none)",
                                    "색면 하이라이트 금지")
                self.assertNotRegex(css, r"border-left\s*:\s*[^;]*var\(--c-",
                                    "좌측 세로 띠 금지")
                self.assertRegex(css, r"\.wfact\{[^}]*color:var\(--c-blocked\)")

            # ---- ⑥ 즉시 저장 ----------------------------------------------------
        with self.subTest("saves_at_once_with_no_batch_button"):
            self.assertNotRegex(self.words, r'id="w-save"|설정 저장|값 저장',
                                "이 판에는 일괄 저장 단추를 두지 않는다")
            self.assertIn('addEventListener("change"', self.wc)
            self.assertIn('postJSONRaw("/api/user/config"', self.wc,
                          "쓰는 길은 이미 있는 그 하나다 — 새 API 금지")
        with self.subTest("failure_puts_the_handle_back"):
            # 화면이 켜졌다고 보여 주는데 서버는 껐다면 그 화면은 거짓말이다.
            self.assertIn("if (el && prev !== undefined) el.value = prev;", self.wc)
            self.assertIn('say(key, "✕ " + res.error, "bad")', self.wc,
                          "서버가 준 문장을 그대로 인라인으로 — 팝업 금지")
        with self.subTest("message_shares_one_grid_cell_with_the_meaning"):
                # 따로 줄을 내면 열 행이 저장할 때마다 아래가 밀린다.
                css = websrc.css_section(self, self.src, r"/\* -+ 백그라운드 작업 설정")
                self.assertRegex(css, r"\.wsay\{[^}]*display:grid")
                self.assertRegex(css, r"\.wsay>\*\{[^}]*grid-area:1/1")

            # ---- ⑦ 꺼진 줄과 그 예외 --------------------------------------------
        with self.subTest("off_rows_dim_but_the_fact_line_does_not"):
                css = websrc.css_section(self, self.src, r"/\* -+ 백그라운드 작업 설정")
                m = re.search(r"tr\.woff [^{]*\{[^}]*opacity:\.45\}", css)
                self.assertIsNotNone(m, "꺼진 줄을 물리는 규칙이 없다")
                self.assertNotIn(".wfact", m.group(0),
                                 "gh 사실 줄은 흐려지지 않는다 — 권한을 준 적 있다는 "
                                 "사실이 화면에서 사라지면 안 된다")
                self.assertIn("값은 지우지 않는다", self.wc)

            # ---- ⑧ 서버 문장 ----------------------------------------------------
        with self.subTest("spawn_block_speaks_the_screen_word"):
            self.assertNotIn("자동 이어가기가 꺼져", self.s9,
                             "화면에 없는 세 번째 이름")
            self.assertNotIn("auto_resume \"\n", self.s9)
            # 폐기된 행 이름이 서버 문장에 되살아나지 않는다 (REQ-20260902-005).
            # 주석·docstring 은 이 잣대 밖이다 — 실사고를 적은 글은 반려어를
            # 인용해야 쓸 수 있고, 그 근거를 지우면 다음 사람이 다시 짓는다
            # (test_screen_lexicon 이 세운 규율). 화면 문장만 잰다.
            self.assertNotIn("무인 작업 맡기기", self.s9,
                             "폐기된 행 이름이 서버 문장에 남았다 (REQ-20260902-005)")
            self.assertIn("「백그라운드 작업」에서 「맡기기」가 꺼져", self.s9)
            i = self.s9.index("「백그라운드 작업」에서 「맡기기」가 꺼져")
            near = self.s9[i:i + 200]
            self.assertNotIn("auto_resume", near,
                             "사용자에게 원시 키를 외우게 하지 않는다")
        with self.subTest("config_refusal_is_a_sentence"):
            self.assertNotIn("본인 또는 admin만 설정 변경 가능", self.s9)
            self.assertIn("본인이나 admin 만 이 설정을 바꿀 수 ", self.s9)

if __name__ == "__main__":
    unittest.main()
