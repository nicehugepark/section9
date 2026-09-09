"""감시 기록이 대시보드 안에서 보이는가 (REQ-20260826-018-62x6).

감시자(REQ-20260825-096)는 죽은 서버를 되살릴 때마다 사유·직전 출력·연속 실패
횟수·백오프를 `state/serve-guard.log` 에 남긴다. 그런데 그걸 보려면 파일을
열어야 했다. "대시보드가 왜 죽었나"는 **대시보드 안에서** 답해야 하는 질문이다.

이 화면이 지켜야 할 것은 "예쁘게 떴는가"가 아니라 **믿을 수 있는가**다. 아래
계약은 전부 코드를 조금만 손대면 조용히 무너지고, 무너져도 화면은 멀쩡해 보인다.

  ① 평소엔 흔적이 없다. 아무 일도 없었는데 자리표시자를 두면 곧 아무도 안 읽고,
     그러면 진짜 사고가 났을 때도 안 읽힌다. → 마크업은 hidden 으로 시작하고
     "사건 없음" 경로는 반드시 감추는 것으로 끝난다.
  ② 서버 무응답을 "사건 없음"으로 오독하지 않는다. 이 알림이 존재하는 이유가
     바로 서버가 죽었다 살아나는 그 순간이다 — 그때 폴은 실패한다. 실패를
     "아무 일 없음"으로 읽으면 알림은 정확히 필요한 순간에 침묵한다.
     → 응답이 없으면 직전 판정을 그대로 두고 다음 폴을 기다린다.
  ③ 신선도는 **서버 시각**으로 잰다. 브라우저 시계가 틀어진 기기에서 6시간 전
     사고가 "방금"이 되면 안 된다. 로그의 ts 는 전부 서버 시각이므로 기준도
     서버가 준 now 여야 한다. → Date.now() 를 쓰지 않는다.
  ④ 화면이 자체 추측하지 않는다. 판단 근거는 읽기 전용 API 하나다.
  ⑤ "되살아났다"와 "이제 안 되살아난다"는 다른 사실이다. 같은 말로 뭉뚱그리면
     둘 다 못 믿게 된다 — 후자만이 사람의 행동을 요구한다.
  ⑥ 명령은 대신 실행하지 않는다. 감시자를 다시 세우는 일은 사람의 판단이다.
     → 붙여넣을 문자열을 주고 복사까지가 화면의 몫이다.
  ⑦ 어휘가 이웃 알림과 충돌하지 않는다. 같은 헤더 줄에 사는 코드 낡음 알림은
     **사람이 하는 재기동**을 말하고, 여기는 **감시자가 하는 자동 복구**를
     말한다. 그리고 터미널 뷰의 "stale"(세션 무응답)은 또 다른 사실이다.

픽셀은 단위 테스트가 볼 수 없다. 여기서는 "믿을 수 없게 만들던 방식으로
되돌아갔는가"만 검사한다 — 실제 가시성은 사람의 캡처 검증이 맡는다
(test_oldcode_banner.py 와 같은 계보).

실행: python3 tests/ guard_ui
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest


def _find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node",
                "/mnt/c/Temp/s9-webkit/node-*/node.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

# 화면에 절대 새면 안 되는 내부 이름 (로그 필드명·이벤트값·파일 경로)
JARGON = ("JSONL", "serve-guard.log", "gave-up", "clean-exit", "spawn-error",
          "retry_in", "ran_sec", "last_death", "rc=", "tail", "backoff",
          "폴링", "렌더", "파싱")


class ServeGuardUI(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.src = f.read()

    # ---------- ① 평소엔 흔적이 없다 ----------

    def test_markup_starts_hidden(self):
        """알림 자리도 기록 자리도 기본이 hidden."""
        m = re.search(r'<div class="hrow3" id="guard"[^>]*>', self.src)
        self.assertIsNotNone(m, "헤더에 자동 복구 알림 자리(#guard)가 없다")
        self.assertIn("hidden", m.group(0),
                      "기본 hidden 이 아니면 빈 경고 줄이 상시 남는다")
        self.assertIn('role="status"', m.group(0),
                      "동적으로 나타나는 알림은 상태 변화를 알려야 한다")
        m2 = re.search(r'<div class="gwlog" id="guard-log"[^>]*>', self.src)
        self.assertIsNotNone(m2, "기록 패널 자리(#guard-log)가 없다")
        self.assertIn("hidden", m2.group(0))

    def test_quiet_path_hides_everything(self):
        """말할 것이 없으면 알림도 기록 패널도 감춘다."""
        body = self._fn("renderGuard")
        head = body[:body.index("const sig")] if "const sig" in body else body
        self.assertIn("hidden = true", head,
                      "사건이 없을 때 감추는 경로가 사라졌다")

    def test_old_incidents_go_quiet_by_themselves(self):
        """잠잠해지면 스스로 걷힌다 — 한 번 난 사고가 영원히 붙어 있으면
        그 줄은 곧 배경이 되고 아무도 안 읽는다."""
        blk = self._fn("gwState")
        self.assertRegex(blk, r"GW_FRESH_\w+",
                         "신선도 창이 없으면 옛 사고가 영구 경고가 된다")
        self.assertRegex(self.src, r"const GW_FRESH_OK\s*=",
                         "복구된 사건의 유효기간이 정의돼 있지 않다")
        self.assertRegex(self.src, r"const GW_FRESH_BAD\s*=",
                         "자동 복구가 멈춘 사실의 유효기간이 정의돼 있지 않다")

    # ---------- ② 무응답 ≠ 사건 없음 ----------

    def test_no_response_keeps_the_last_verdict(self):
        """서버가 죽어 있는 동안 폴은 실패한다. 그 실패를 '아무 일 없음'으로
        읽으면 이 알림은 정확히 필요한 순간에 침묵한다."""
        body = self._fn("checkGuard")
        self.assertRegex(body, r"if\s*\(!d[^)]*\)\s*return;",
                         "무응답일 때 직전 판정을 두고 물러나는 경로가 없다")
        self.assertNotRegex(body, r"gwInfo\s*=\s*null",
                            "무응답을 사건 없음으로 덮어쓰면 안 된다")

    # ---------- ③ 시각은 서버 것으로 ----------

    def test_freshness_uses_server_clock(self):
        """브라우저 시계가 틀어져도 판정이 흔들리지 않아야 한다."""
        blk = self._fn("gwState")
        self.assertNotIn("Date.now()", blk,
                         "신선도를 브라우저 시계로 재면 시계가 틀어진 기기에서 무너진다")
        self.assertIn("d.now", blk, "서버가 준 응답 시각(now)을 기준으로 재야 한다")

    # ---------- ④ 근거는 API 하나 ----------

    def test_reads_one_readonly_api(self):
        """판정 근거는 읽기 전용 API 하나 — 화면이 자체 추측하지 않는다."""
        body = self._fn("checkGuard")
        self.assertIn("/api/serveguard", body)
        self.assertNotIn("POST", body, "읽기 전용이어야 한다")

    def test_polls_only_when_visible(self):
        """보이지 않는 탭에서 계속 두드리지 않는다.

        한때는 `setInterval` 안에 `document.hidden` 이 적혀 있는지를 봤다. 그 검사를
        주기 폴마다 손으로 적다 보니 빠뜨린 자리가 생겼고(카탈로그 벨트가 그랬다,
        REQ-20260909-086), 이제 멈춤 판정은 공통 벨트 `s9Every`(web/app/net.js)
        한 곳에 있다. 그래서 여기서 재는 것도 둘이다 — ① 감시자 폴이 그 벨트를
        타는가 ② 그 벨트가 안 보이는 화면에서 정말 멈추는가(node 로 실행해 센다)."""
        m = re.search(r"checkGuard\(\);[\s\S]{0,300}?s9Every\([^;]+;", self.src)
        self.assertIsNotNone(m, "주기 확인이 공통 벨트(s9Every)를 타지 않는다")
        self.assertIn("checkGuard", m.group(0))
        node = _find_node()
        if not node:
            self.skipTest("node 가 없다 — 벨트의 동작은 재지 못한다")
        net = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "web", "app", "net.js"),
            encoding="utf-8").read()
        js = """
const H = {};
globalThis.document = {hidden: true, addEventListener(n, f){ H[n] = f; }};
%s
let n = 0;
s9Every("guard", 10, () => { n++; });
setTimeout(() => {
  const hidden = n;
  document.hidden = false;
  H["visibilitychange"]();
  console.log(JSON.stringify({hidden, resumed: n}));
  process.exit(0);
}, 80);
""" % net
        out = subprocess.run([node, "-e", js], capture_output=True, text=True,
                             timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(got["hidden"], 0,
                         "안 보이는 화면에서 %d번 두드렸다" % got["hidden"])
        self.assertEqual(got["resumed"], 1,
                         "돌아온 순간 %d번 몰아 두드렸다" % got["resumed"])

    # ---------- ⑤ 복구됨 ≠ 복구가 멈춤 ----------

    def test_recovered_and_stalled_are_different_states(self):
        """되살아난 사실과 이제 안 되살아난다는 사실은 다른 말이어야 한다.
        후자만이 사람의 행동을 요구한다."""
        blk = self._fn("gwState")
        self.assertIn('"recovered"', blk)
        self.assertIn('"attention"', blk)
        self.assertIn("watching", blk,
                      "감시자가 지금 도는지를 봐야 두 상태가 갈린다")
        copy = self._copy()
        self.assertTrue(any("자동 복구" in c for c in copy),
                        "자동 복구라는 말로 사실을 말해야 한다")

    def test_stalled_state_says_what_happens_next(self):
        """'이제 안 되살아난다'는 결과까지 말해야 행동으로 이어진다."""
        copy = " ".join(self._copy())
        self.assertIn("다시 시작되지 않", copy,
                      "자동 복구가 멈추면 다음에 무슨 일이 생기는지 말해야 한다")

    # ---------- ⑥ 명령은 대신 실행하지 않는다 ----------

    def test_offers_the_command_not_the_action(self):
        """감시자를 다시 세우는 것은 사람의 판단이다 — 문자열까지가 화면의 몫."""
        self.assertIn("s9 serve --supervise", self.src,
                      "감시자를 다시 세우는 실제 명령을 줘야 한다")
        body = self._fn("renderGuard")
        self.assertNotIn("fetch(", body, "알림 경로에서 서버를 부르지 않는다")

    # ---------- ⑦ 어휘 ----------

    def test_copy_has_no_internal_names(self):
        """사용자 문장에 로그 필드명·이벤트값·파일 경로가 새지 않는다."""
        for raw in self._copy():
            line = re.sub(r"<[^>]*>", "", re.sub(r"\$\{[^}]*\}", "", raw))
            for j in JARGON:
                self.assertNotIn(j, line, "내부 용어 %r 이 문구에 있다: %s" % (j, line))

    def test_does_not_borrow_the_neighbours_words(self):
        """같은 헤더 줄의 코드 낡음 알림은 **사람이 하는 재기동**을 말한다.
        여기는 **감시자가 하는 자동 복구**다. 그리고 터미널 뷰의 'stale' 은
        세션 무응답이라는 또 다른 사실이다 — 셋이 같은 말을 쓰면 다 못 믿는다."""
        copy = " ".join(self._copy())
        self.assertNotIn("stale", copy, "세션 무응답을 뜻하는 말을 빌려 쓰지 않는다")
        self.assertNotIn("옛 코드", copy, "코드 낡음 알림의 문장을 빌려 쓰지 않는다")

    # ---------- 기록 패널 ----------

    def test_history_is_bounded_with_more(self):
        """무한 목록 금지 — 몇 건까지 보이고 나머지는 '더 보기'로."""
        self.assertRegex(self.src, r"const GW_ROWS\s*=\s*\d+",
                         "기록 표시 제한이 없다")
        self.assertRegex(self.src, r"더 보기", "'더 보기' 경로가 없다")

    def test_history_translates_event_names(self):
        """기록의 종류는 사용자 말로 옮긴다 — died/gave-up 을 그대로 보여주면
        기록이 아니라 암호다."""
        m = re.search(r"const GW_EV\s*=\s*\{[\s\S]*?\};", self.src)
        self.assertIsNotNone(m, "이벤트 이름 대응표가 없다")
        tbl = m.group(0)
        for ev in ("died", "gave-up", "start", "spawn-error"):
            self.assertIn(ev, tbl, "%s 를 옮길 말이 없다" % ev)

    def test_death_output_is_reachable(self):
        """직전 출력이 없으면 '왜 죽었나'에 답할 수 없다 — 죽은 사유의 본문이다."""
        self.assertIn("직전 출력", self.src,
                      "죽기 직전 출력을 볼 경로가 없다")

    def test_empty_history_says_so(self):
        """기록이 비어 있을 때도 화면은 말을 한다 (빈 상태)."""
        self.assertRegex(self.src, r"아직 (기록|남은)",
                         "기록이 없을 때의 문장이 없다")

    # ---------- 시각 언어 ----------

    def test_no_color_fill_and_no_side_bar(self):
        """색면 하이라이트·좌측 세로 띠 금지 — 색은 글자와 마크로."""
        css = self._css()
        for bg in re.findall(r"background\s*:\s*([^;}]+)", css):
            self.assertIn(bg.strip(), ("none", "transparent", "var(--text)",
                                       "var(--bg)", "var(--panel)"),
                          "알림에 색면을 깔지 않는다: %s" % bg)
        self.assertNotIn("border-left", css, "좌측 세로 띠 금지")

    def test_styles_are_token_only(self):
        """tone 6종 전부에서 성립하려면 색은 토큰으로만."""
        css = self._css()
        websrc.no_hex(self, css)
        self.assertNotRegex(css, r"\[data-(?:skin|theme)=",
                            "특정 스킨/톤 전용 스타일이 아니다")

    def test_state_is_readable_without_colour(self):
        """색만으로 상태를 구분하지 않는다 — 마크와 문구가 같이 말한다.
        복구 성공(↻)은 REQ-20260827-017 이후 헤더 줄이 아니라 툴바의 상태
        칩에서 말한다 — 그래서 renderGuard 하나가 아니라 블록 전체를 본다."""
        body = self._block()
        self.assertRegex(body, r"[↻⟳]", "복구를 뜻하는 마크가 없다")
        self.assertIn("▲", body, "주의를 뜻하는 마크가 없다")

    # ---------- 진단 훅 ----------

    def test_capture_hook_exists(self):
        """실사고는 헤드리스 캡처로 재현할 수 없다 — 상태 고정 훅을 둔다
        (?nosse·?mpanel·?conn 선례)."""
        self.assertRegex(self.src, r"\[?\?&\]?guard=",
                         "상태 고정 훅이 없으면 각 상태를 캡처로 검증할 수 없다")

    # ---------- helpers ----------

    def _fn(self, name):
        return websrc.fn(self, self.src, name)

    def _copy(self):
        """화면에 나가는 문장 후보 — 자동 복구 블록 안의 한글 문자열."""
        blk = self._block()
        # 화면 문구는 한 줄이다. 줄바꿈을 허용하면 따옴표가 엇갈려 짝지어지면서
        # 코드 덩어리째 문구로 잡힌다 (그러면 검사가 거짓 경보만 낸다).
        out = re.findall(r"[`\"']([^`\"'\n]*[가-힣][^`\"'\n]*)[`\"']", blk)
        self.assertTrue(out, "사용자 문구를 찾지 못했다")
        return out

    def _block(self):
        m = re.search(r"/\* ── 서버 자동 복구 \(REQ[\s\S]*?\n// ── 자동 복구 끝",
                      self.src)
        self.assertIsNotNone(m, "자동 복구 스크립트 블록을 찾지 못했다")
        return m.group(0)

    def _css(self):
        m = re.search(r"/\* ── 서버 자동 복구 기록[\s\S]*?\*/([\s\S]*?)\n\n",
                      self.src)
        self.assertIsNotNone(m, "자동 복구 CSS 블록을 찾지 못했다")
        return m.group(1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
