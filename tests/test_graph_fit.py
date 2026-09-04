"""줌아웃이 구석으로 쏠린다 (REQ-20260827-083-62x6).

사용자: "줌아웃을 하면 항상 대각선 방향으로 고정이되고 쏠리게 되는데 마음에
들지 않는다. 옵시디언도 이런식인가?"

1차에는 **커서 기준 줌 자체는 옳다**고 보고 되돌릴 길만 더했다. 2차 반려에서
그 판단이 틀렸음이 드러났다(아래 참조) — 지금은 줌 기준점 자체를 손질한다.

진짜 문제는 **되돌릴 방법이 없다**는 것이었다. 화면 가장자리에서 줌아웃하면
내용이 그 구석에 남고, 손으로 끌어 되찾아야 하니 "고정된다"로 느껴진다.
옵시디언과 다른 점은 둘이다: 전체 보기 동작이 없었고, 줌아웃이 화면을 비웠다.

1차 반려: "비어있는곳을 더블클릭 하면 원복이 안된다. 직접 눈으로 보고 직접
행동해봐." 실제로 눌러 보니 세 군데가 틀려 있었다.

  ㉠ 옮기는 일을 프레임 루프에만 맡겼다. 프레임은 늘 도는 것이 아니다 —
     헤드리스 캡처에서 재 보니 3.3초에 세 장이었다(배경 탭·전원 절약도 같다).
     그러면 gFit() 은 불렸는데 화면은 그대로다 = "눌러도 아무 일이 없다".
  ㉡ 두 번 누른 것을 브라우저의 dblclick 하나로만 알았다. 이 캔버스는 끌기를
     놓치지 않으려 pointerdown 에서 포인터를 잡아 둔다(setPointerCapture).
     그 하나에만 기대면 안 된다 — 이제 우리가 직접 센다.
  ㉢ 맞출 자리를 월드 좌표로 쟀다. 화면 좌표는 깊이 가중(pfOf 0.72~1.24)을 한 번
     더 지나므로, 그 자로 "맞췄다"고 해도 화면에서는 어긋난다.

2차 반려: "줌 아웃만 생각한걸까, 줌 인은 달라진게 하나도 없는데... 그리고
줌아웃도 사실 뭐가 달라진건지 모르겠다." 둘 다 맞는 지적이었다. 재 보니:

  ㉣ 확대(줌인)에는 손이 전혀 닿지 않았다. 구석에 커서를 두고 여덟 번 확대하면
     무리가 반대쪽으로 894px 밀려나고 화면에 남는 노드가 10% 였다.
  ㉤ 축소도 늦게 일했다. 가운데로 물리는 손질에 `fill >= 1` 이라는 문턱이 있어서,
     그래프 **전체가 화면보다 작아진 뒤**에야(여덟 번쯤 굴린 뒤) 작동했다.
     그 전까지는 날것과 똑같이 구석으로 쏠렸다 — 그래서 "뭐가 달라진 건지
     모르겠다"가 맞다.

계약은 열이다.

  ① 줌 기준점은 **커서와 화면 가운데의 중간**이다. 커서 기준 그대로면 굴릴
     때마다 화면이 대각선으로 밀린다 — 확대·축소 양쪽에서 같은 규칙을 쓴다.
     커서가 가운데에 가까울수록 손질은 0으로 수렴한다.
  ② 전체 보기 — 경계 상자를 재서 여백을 두고 화면에 꽉 채운다. 빈 곳
     더블클릭과 손잡이 버튼, 두 길 모두로 닿는다.
  ③ 순간이동하지 않는다 — 짧은 감속 이동. 움직임을 줄여 달라고 한 사람에게는
     옮기지 않고 바로 놓는다.
  ④ 굴린 결과가 화면을 비우면 되당긴다(목줄). 축마다 따로 본다. 화면보다 작으면
     여유에 비례해 가운데로, 아직 넘치면 가장자리의 빈 띠만큼만. 문턱은 없다.
  ⑤ 손잡이는 **거의 나갔을 때만** 나온다. 늘 떠 있는 안내는 곧 안 읽힌다.
     물리가 도는 동안 깜빡이지 않게 뜸을 들이고, 돌아오면 즉시 사라진다.
  ⑥ 프레임이 돌지 않아도 도착한다. 약속한 것은 부드러움이 아니라 전체 보기다.
  ⑦ 빈 곳 두 번 누르기를 직접 센다 — dblclick 하나에 목숨을 걸지 않는다.
  ⑧ 재는 자와 그리는 자가 같다 — 화면 좌표(깊이 가중 포함)로 잰다.
  ⑨ 확대와 축소가 같은 손질을 받는다 — 한쪽만 고치면 다른 쪽이 그대로 남는다.
  ⑩ 고치기 전과 후를 같은 자에 놓고 잴 수 있다(`?graw`) — "뭐가 달라졌는지
     모르겠다"에 그림 두 장으로 답할 수 있어야 한다.

실행: python3 tests/ graph_fit
"""
import os
import re
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class GraphFit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # ---------- ① 줌 기준점은 커서와 화면 가운데의 중간 ----------

    def test_graph_fit(self):
        """GraphFit 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("zoom_anchor_sits_between_cursor_and_centre"):
            w = self._wheel()
            # 표준 공식의 뼈대(기준점 a 를 고정하는 그 식)는 그대로다 — 기준점만 옮긴다
            self.assertIn("st.tf.x = ax - (ax - st.tf.x) * k2 / st.tf.k", w,
                          "줌 공식의 뼈대가 사라졌다")
            self.assertIn("st.tf.y = ay - (ay - st.tf.y) * k2 / st.tf.k", w)
            self.assertIn("mx + (W / 2 - mx) * GZ_BLEND", w, "기준점을 가운데로 당기지 않는다")
            self.assertIn("my + (H / 2 - my) * GZ_BLEND", w)
            # 절반 — 0이면 손질이 없는 것이고 1이면 커서를 아예 무시하는 것이다
            self.assertRegex(self.src, r"const GZ_BLEND = 0\.5;",
                             "당기는 비율이 절반이 아니다")
        with self.subTest("zoom_in_and_out_get_the_same_treatment"):
                w = self._wheel()
                # 방향은 배율에서만 갈린다 — 기준점·목줄은 갈리지 않는다
                self.assertIn('e.deltaY < 0 ? 1.12 : 0.89', w, "확대/축소 배율이 없다")
                self.assertNotRegex(w, r"deltaY[^\n]*\?[^\n]*gLeash",
                                    "목줄이 한쪽 방향에서만 걸린다")
                body = w[w.index("st.tf.k = k2;"):]
                self.assertIn("if (!raw) gLeash();", body,
                              "굴린 뒤 화면을 비웠는지 보지 않는다")
                self.assertNotIn("if (fill >= 1) return;", w,
                                 "문턱 때문에 그래프가 화면보다 작아진 뒤에야 일한다 (2차 반려 ㉤)")

            # ---------- ② 전체 보기 ----------
        with self.subTest("fit_measures_the_graph_and_leaves_a_margin"):
            self.assertIn("function gBBox", self.src, "경계 상자를 재지 않는다")
            fit = self._fn("gFitTf")
            self.assertIn("GFIT_PAD", fit, "여백 없이 가장자리에 붙인다")
            self.assertIn("W / 2 - b.cx * k", self._fn("gCenterAt"), "가운데로 맞추지 않는다")
            # 줌 한계 안에 머문다 — 노드가 하나뿐일 때 무한대로 확대되지 않는다
            self.assertRegex(self.src, r"gClampK = k => Math\.min\(4, Math\.max\(0\.25",
                             "줌 한계를 벗어난다")
            self.assertIn("gClampK", fit, "전체 보기가 줌 한계를 무시한다")
        with self.subTest("two_ways_to_reach_it"):
            self.assertRegex(self.src, r'addEventListener\("dblclick"[\s\S]{0,240}gFit\(\)',
                             "빈 곳 더블클릭으로 전체 보기가 안 된다")
            self.assertRegex(self.src, r'if \(hit\(mx, my\)\) return;',
                             "노드 위 더블클릭이 문서 열기와 겹친다")
            self.assertIn('class="gfit" id="gfit"', self.src, "손잡이가 없다")
            self.assertRegex(self.src, r'gfit\.addEventListener\("click"[^)]*\) => \{[^}]*gFit\(\)',
                             "손잡이를 눌러도 안 된다")
            # 조작법은 이미 있는 안내 줄에 한 항목으로 붙인다 — 새 안내를 만들지 않는다
            self.assertIn("빈 곳 더블클릭 = 전체 보기", self.src, "어떻게 하는지 어디에도 없다")
        with self.subTest("it_moves_instead_of_teleporting"):
                fn = self._fn("gFit")
                self.assertIn("REDUCE_MOTION", fn, "움직임을 줄여 달라는 설정을 무시한다")
                self.assertRegex(fn, r"ms: 2[0-4]0", "지속시간이 모션 규약(120~240ms) 밖이다")
                step = self._fn("gFitStep")
                self.assertIn("1 - Math.pow(1 - t, 3)", step, "감속(ease-out)이 아니다")
                # 손이 개입하면 옮기던 것은 멈춘다
                self.assertRegex(self.src, r"st\.fit = null;\s*//[^\n]*손이 개입",
                                 "휠을 굴려도 이동이 계속된다")

            # ---------- ④ 굴린 결과가 화면을 비우면 되당긴다 ----------
        with self.subTest("the_leash_keeps_the_screen_from_emptying"):
                one = self._fn("gLeash1")
                # ㉠ 화면보다 작다 — 여유에 비례해 가운데로. 한 번에 끌지 않는다.
                self.assertRegex(one, r"return \(span / 2 - c\) \* \(0\.15 \+ 0\.5 \* "
                                      r"\(1 - len / avail\)\)", "가운데로 물리지 않는다")
                # ㉡ 아직 넘친다 — 빈 띠가 생길 때만, 그 띠만큼만
                self.assertIn("if (a0 > m) return m - a0;", one, "시작 쪽 빈 띠를 두고 본다")
                self.assertIn("if (a1 < span - m) return (span - m) - a1;", one,
                              "끝 쪽 빈 띠를 두고 본다")
                self.assertIn("return 0;", one, "화면이 차 있는데도 건드린다")
                # 축마다 따로 — 가로로 넘치고 세로로 남는 배치가 흔하다
                leash = self._fn("gLeash")
                self.assertIn("st.tf.x += gLeash1(s.x0, s.x1, s.cx, s.w, W, m)", leash)
                self.assertIn("st.tf.y += gLeash1(s.y0, s.y1, s.cy, s.h, H, m)", leash,
                              "세로축은 목줄 없이 놔둔다")
                self.assertIn("gScreenBox(st.tf.k, st.tf.x, st.tf.y, c.set)", leash,
                              "그려지는 자리가 아니라 월드 좌표로 잰다")
                # 튄 몇 개를 끼우면 상자가 늘 화면보다 커서 목줄이 통째로 잠든다 (4차 반려)
                self.assertIn("const c = gCore();", leash, "목줄이 이상치까지 끼워 잰다")
                self.assertRegex(self.src, r"const GZ_BAND = 0\.1[0-9];",
                                 "허용하는 빈 띠의 크기가 없다")

            # ---------- ⑤ 손잡이는 갇혔을 때만 ----------
        with self.subTest("handle_shows_only_when_the_graph_is_nearly_gone"):
            fn = self._fn("gAwaySync")
            self.assertRegex(fn, r"if \(seen >= 0\.25\)\{ st\.awayT = 0; btn\.hidden = true;",
                             "조금만 벗어나도 손잡이가 뜬다")
            self.assertRegex(fn, r"performance\.now\(\) - st\.awayT < 400",
                             "물리가 도는 동안 손잡이가 깜빡인다")
            self.assertIn("st.fit", fn, "옮기는 중에도 손잡이가 떠 있다")
            self.assertIn("hidden", self.src[self.src.index('class="gfit"'):
                                             self.src.index('class="gfit"') + 120],
                          "처음부터 떠 있다")
        with self.subTest("handle_measures_what_is_left_on_screen_not_box_area"):
            fn = self._fn("gSeenAt")
            self.assertIn("pfOf(n)", fn, "그리는 좌표가 아닌 것으로 잰다")
            self.assertIn("prj(n.x, k, tx, st.dx, W / 2, pf)", fn,
                          "카메라 드리프트를 빼고 잰다")
            self.assertRegex(fn, r"return of \? on / of : 1;",
                             "남아 있는 노드의 비율이 아니라 넓이로 잰다")
            # 지금 상태를 재는 gSeen 은 같은 자를 빌려 쓴다 — 자가 둘이면 또 어긋난다
            self.assertIn("function gSeen(){ return gSeenAt(st.tf.k, st.tf.x, st.tf.y); }",
                          self.src, "지금 상태와 후보를 다른 자로 잰다")
        with self.subTest("handle_wears_ink_not_a_colour_field"):
                css = self._css()
                websrc.no_hex(self, css)
                self.assertNotRegex(css, r"\bborder-left\b", "좌측 세로 띠 금지")
                for v in re.findall(r"(?:background|color|border(?:-color)?)\s*:\s*([^;}\n]+)", css):
                    v = v.strip()
                    if v.startswith("1px solid "):
                        v = v[len("1px solid "):]
                    self.assertIn(v, ("none", "transparent", "var(--panel)", "var(--text)",
                                      "var(--bg)", "var(--border)", "var(--hairline)"),
                                  "잉크·지면 밖의 색: %s" % v)

            # ---------- ⑥ 프레임이 안 돌아도 도착한다 (반려 ㉠) ----------
        with self.subTest("it_arrives_even_when_no_frame_runs"):
                fn = self._fn("gFit")
                self.assertIn("st.fitLand = setTimeout(", fn,
                              "옮기는 일을 프레임 루프에만 맡긴다 — 프레임이 없으면 안 움직인다")
                self.assertRegex(fn, r"if \(st\.fit && st\.fit\.to === to\)\{ st\.tf = \{\.\.\.to\}",
                                 "시간이 지나도 목표 자리에 놓지 않는다")
                # 휠이 취소한 이동을 되살리면 안 된다 — 같은 이동인지 확인하고 놓는다
                self.assertIn("st.fit.to === to", fn, "취소된 이동을 되살린다")
                self.assertIn("clearTimeout(st.fitLand)", fn, "이동을 겹쳐 걸면 늦게 온 것이 덮는다")
                # 320ms = 이동(240ms)이 끝났어야 할 시각 조금 뒤
                self.assertRegex(fn, r"\}, 3[0-9]0\);", "구제 시각이 이동 시간과 어긋난다")

            # ---------- ⑦ 두 번 누르기를 직접 센다 (반려 ㉡) ----------
        with self.subTest("two_taps_are_counted_by_us_not_only_by_the_browser"):
                up = self.src[self.src.index('canvas.addEventListener("pointerup"'):]
                up = up[:up.index('canvas.addEventListener("dblclick"')]
                self.assertIn("st.tap", up, "두 번 누른 것을 직접 세지 않는다")
                self.assertRegex(up, r"t - st\.tap\.t < 4[0-9]0", "두 번으로 묶는 시간 기준이 없다")
                self.assertRegex(up, r"Math\.abs\(ux - st\.tap\.x\) < [0-9]+", "손떨림 허용이 없다")
                self.assertIn("gFit()", up, "두 번 눌러도 전체 보기가 불리지 않는다")
                self.assertIn("if (!panned || st.moved >= 4 || e.button !== 0)", up,
                              "노드를 끌거나 판을 옮긴 것·왼쪽이 아닌 버튼까지 두 번 누르기로 센다")
                # 브라우저가 dblclick 을 주는 환경에서 두 번 불리지 않는다
                dbl = self.src[self.src.index('canvas.addEventListener("dblclick"'):]
                self.assertIn("if (st.fit) return;", dbl[:400], "같은 손짓으로 두 번 부른다")

            # ---------- ⑧ 재는 자와 그리는 자가 같다 (반려 ㉢) ----------
        with self.subTest("it_measures_where_nodes_are_actually_drawn"):
                box = self._fn("gScreenBox")
                self.assertIn("pfOf(n)", box, "깊이 가중을 빼고 잰다")
                self.assertIn("prj(n.x, k, tx, st.dx, W / 2, pf)", box,
                              "카메라 드리프트를 빼고 잰다")
                self.assertIn("n.r * k * (0.62 + 0.55 * n.near)", box, "노드 반지름을 빼고 잰다")
                # 전체 보기·손잡이·목줄 세 곳이 모두 같은 자를 쓴다
                self.assertIn("gScreenBox(k, x, y, only)", self._fn("gCenterAt"), "전체 보기가 다른 자로 잰다")
                self.assertIn("gScreenBox(t.k, t.x, t.y, core)", self._fn("gFitTf"), "후보를 다른 자로 잰다")
                self.assertIn("gScreenBox", self._fn("gLeash"), "목줄이 다른 자로 잰다")
                self.assertIn("pfOf(n)", self._fn("gSeenAt"), "손잡이 판정이 다른 자로 잰다")

            # ---------- ⑪ 판 바닥이 화면 안에 있다 (3차 반려) ----------
        with self.subTest("panel_height_is_measured_not_assumed"):
                self.assertNotIn("Math.max(340, innerHeight - 210)", self.src,
                                 "판 높이를 아직 상수로 뺀다")
                head = self.src[self.src.index('const canvas = $("#gcanvas");'):]
                head = head[:head.index("const ctx = canvas.getContext")]
                self.assertIn("canvas.getBoundingClientRect().top", head,
                              "판이 화면 어디서 시작하는지 재지 않는다")
                self.assertIn("Math.max(340,", head, "최소 높이를 잃었다")

            # ---------- ⑫ 전체 보기가 자기 결과를 재 보고 쓴다 (3차 반려) ----------
        with self.subTest("fit_verifies_its_own_iteration_before_moving"):
                fn = self._fn("gFitTf")
                # 푼 값을 믿지 않는다 — 후보를 훑어 **재 본** 값 중에서 고른다
                self.assertIn("for (let i = -7; i <= 7; i++)", fn, "배율 후보를 훑지 않는다")
                self.assertIn("gCenterAt(gClampK(k0 * Math.pow(1.2, i)), b, core)", fn,
                              "후보마다 가운데에 놓아 보지 않는다")
                self.assertIn("gSeenAt(t.k, t.x, t.y, core) * 100", fn,
                              "화면에 남는 노드 수를 기준으로 고르지 않는다")
                self.assertIn("(fill <= 1 ? fill : 1 / fill)", fn,
                              "넘치게 키운 답이 꽉 찬 답을 이긴다")
                # 배율을 바꾸는 되풀이는 gCenterAt 안에 없어야 한다 — 되먹임이 거기서 났다
                self.assertNotIn("k = gClampK(k *", self._fn("gCenterAt"),
                                 "자리를 맞추면서 배율까지 건드려 되먹임이 되살아났다")

            # ---------- ⑬ 헤드리스도 자리 잡힌 그래프를 본다 (3차 반려) ----------
        with self.subTest("physics_can_be_settled_by_hand"):
                self.assertRegex(self.src, r"settle: n => \{ for \(let i = 0; i < \(n \|\| 0\); i\+\+\)",
                                 "물리를 손으로 돌리는 이음새가 없다")
                # **루프와 같은 관문을 지나야 같은 것을 잰다.** 관문 없이 계속 돌리면 다 식은
                # 뒤에도 밀어내는 힘만 남아 노드가 끝없이 흩어진다(실측: 월드 상자 28,330px).
                # 그건 사용자가 보는 그래프가 아니라 진단이 만들어 낸 그래프다.
                seam = self.src[self.src.index("settle: n =>"):]
                self.assertIn("if (st.alpha > 0.006) step();", seam[:160],
                              "진단이 물리를 루프보다 오래 돌려 없는 그래프를 만든다")
                self.assertIn("if (st.alpha > 0.006) step();", self._fn("loop"),
                              "루프의 관문이 달라졌다 — 진단과 어긋난다")
                self.assertIn("[?&]gsettle=", self.src, "진단 파라미터 ?gsettle 이 없다")
                # 다른 진단(타이머)보다 먼저 돌아야 자리 잡힌 판을 잰다
                self.assertLess(self.src.index("[?&]gsettle="), self.src.index("[?&]goff"),
                                "자리를 잡기 전에 다른 진단이 먼저 돈다")

            # ---------- ⑩ 고치기 전과 후를 같은 자에 놓고 잰다 ----------
        with self.subTest("before_and_after_can_be_put_on_the_same_ruler"):
            w = self._wheel()
            # ?graw — 기준점 손질과 목줄을 **둘 다** 끈 날것
            self.assertIn('const raw = /[?&]graw/.test(location.search)', w,
                          "고치기 전 거동을 재현할 스위치가 없다")
            self.assertIn("const ax = raw ? mx :", w, "?graw 가 기준점 손질을 끄지 않는다")
            self.assertIn("if (!raw) gLeash();", w, "?graw 가 목줄을 끄지 않는다")
            # 진단은 확대 쪽도 태울 수 있어야 한다 — 부호로 방향을 준다
            gz = self.src[self.src.index("const gz = /[?&]gzoom="):]
            self.assertIn("gzoom=(-?\\d+)", self.src, "확대(음수) 방향을 태울 수 없다")
            self.assertIn("deltaY: steps > 0 ? 120 : -120", gz, "부호가 방향으로 이어지지 않는다")
            # 잰 값은 화면에 얹는다 — 캡처 한 장이 곧 증거가 되게
            self.assertIn("가운데서 벗어난 거리", gz, "쏠린 거리를 숫자로 내놓지 않는다")
            self.assertIn("고치기 전(?graw)", gz, "어느 쪽을 찍은 것인지 그림에 없다")
        with self.subTest("it_can_be_opened_without_hands"):
                for q in ("goff", "gfit", "gzoom", "gdbl"):
                    self.assertIn("[?&]%s" % q, self.src, "진단 파라미터 ?%s 가 없다" % q)
                # 줌아웃 진단은 **실제 핸들러**를 태워야 증거가 된다
                self.assertIn('new WheelEvent("wheel"', self.src,
                              "줌아웃 진단이 실제 휠 경로를 지나지 않는다")
                # 더블클릭 진단도 마찬가지다 — 그 좌표에서 **실제로 이벤트를 받는 요소**를
                # 찾아 거기서 버블링시킨다. 캔버스에 바로 쏘면 위에 뭔가 덮여 있어도 통과한다.
                gd = self.src[self.src.index("if (/[?&]gdbl/"):]
                self.assertIn("document.elementFromPoint(cx, cy)", gd,
                              "덮인 요소가 있어도 진단이 통과해 버린다")
                self.assertIn('mk("dblclick", MouseEvent)', gd, "더블클릭을 실제로 하지 않는다")
                # 진단이 **죽은 판**을 재고 "잘 된다"고 말하지 않게 세대를 함께 본다
                self.assertIn("gen: myGen", self.src, "그래프 판의 세대를 표시하지 않는다")
                self.assertRegex(gd, r"gen\s+\$\{gen0\} → \$\{L\.gen\}", "세대를 보고하지 않는다")

            # ---------- ⑭ 무리는 구 모양으로 남는다 (4차 반려) ----------
        with self.subTest("depth_does_not_shear_the_cluster_along_the_pan"):
                self.assertIn("half + (w * k + t + d - half) * pf", self.src,
                              "깊이 배율이 화면 가운데를 기준으로 먹지 않는다")
                # 팬 오프셋에 직접 곱하던 옛 식이 어디에도 남아 있으면 안 된다 — ?praw 는 예외
                live = self.src.replace("PRAW ? w * k + (t + d) * pf : ", "")
                self.assertNotIn("(st.tf.x + st.dx) * pfOf", live, "옛 투영이 남아 있다")
                self.assertNotIn("(tx + st.dx) * pf", live, "옛 투영이 남아 있다")
                # 끌기 역변환도 같은 식을 되짚는다 — 아니면 노드가 커서에서 미끄러진다
                self.assertIn("((mx - W / 2) / pf + W / 2 - st.tf.x - st.dx) / st.tf.k",
                              self.src, "끌기가 새 투영을 되짚지 않는다")
                # 눈싸움으로 판정하지 않는다 — 긴 축/짧은 축 비를 재는 자가 있어야 한다
                self.assertIn("aniso: () => {", self.src, "무리 모양을 잴 자가 없다")
                self.assertIn("[?&]gshape", self.src, "그 값을 그림에 얹을 길이 없다")
                self.assertIn("[?&]praw", self.src, "고치기 전과 나란히 놓을 수 없다")

            # ---------- helpers ----------

    def _wheel(self):
        w = self.src[self.src.index('canvas.addEventListener("wheel"'):]
        return w[:w.index("{ passive: false }")]

    def _fn(self, name):
        m = re.search(r"function %s\([^)]*\)\{[\s\S]*?\n  \}" % name, self.src)
        self.assertIsNotNone(m, "%s() 를 찾지 못했다" % name)
        return m.group(0)

    def _css(self):
        m = re.search(r"/\* -+ 전체 보기 손잡이[\s\S]*?\*/([\s\S]*?)\n\.legend\{", self.src)
        self.assertIsNotNone(m, "손잡이 CSS 블록을 찾지 못했다")
        return m.group(1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
