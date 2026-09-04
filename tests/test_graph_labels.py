"""DAG 글자가 안개가 된다 (REQ-20260828-035-62x6).

사용자: "그래프 dag 화면인데 글자가 너무 겹쳐 포그가 되어 사실상 볼 수 없다."

세 관점(designer·architect·frontend-developer)이 재 온 숫자가 이 계약의 근거다.

  · 라벨 사각형 476개의 글자 총면적이 판 넓이의 **1.58배**다. 어떤 배치를 쓰든
    다 놓을 자리가 물리적으로 없다 — **거르는 것은 선택이 아니라 필수다.**
  · `showLabel` 의 `|| graphLayout === "dag"` 한 조각이 줌·깊이 게이트를 통째로
    무효화해 프레임당 fillText 477회(= 노드 수)를 그렸다. 그것이 안개다.
  · `gap = min(170, (W-120)/층 인원)` 에 하한이 없어 depth 0 의 352개가 2.84px
    간격으로 놓였다 — 라벨을 다 꺼도 **점 자체가 3.5겹**이다.
  · force 도 대칭으로 실패했다: 전체 보기(k=0.362)를 누르면 `near > 0.45` 에
    전부 걸려 이름이 **한 개도** 안 남았다.
  · 성능은 원인이 아니다 — 겹침 그리디 0.07~0.12ms(프레임 예산 16.7ms 중).
    매 프레임 돌린다. 캐시는 "언제 무효화하나"라는 결함 표면만 새로 만든다.

계약은 여섯이다.

  ① dag 라고 라벨 게이트를 건너뛰지 않는다 — 그 한 조각이 안개의 원인이다.
  ② 이름은 **겹치지 않는 것만** 예산까지 놓는다(자리로 정한다). 줌이 저절로
     LOD 가 되므로 `k > 0.75` 라는 절벽은 없앤다.
  ③ 우선순위는 "지금 손이 가야 할 것" 순이다 — 병목(미완료 파생) → 진행 중·
     막힘·검토 → 허브(연결 수) → 미완료. 문서 id 해시가 절반인 `n.near` 가
     아니다.
  ④ 관성(히스테리시스) — 직전 프레임에 있던 이름을 정렬 맨 앞에. 없으면 팬 중
     프레임당 3.19개가 갈려 읽히지 않고 고장으로 보인다.
  ⑤ dag 층은 판보다 넓으면 **접는다**(간격 하한 + 누적 세로 오프셋). 판이
     세로로 길어지므로 첫 화면은 전체 보기로 시작한다.
  ⑥ 고치기 전과 후를 같은 자에 놓고 잴 수 있다 — `?glab`(표시 수·겹침쌍·교체)
     와 대조군 손잡이 `?glabraw`·`?gdagraw`·`?glabnohys`.

실행: python3 tests/ graph_labels
"""
import os
import re
import unittest
from webasset import index_path, part   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)
GRAPH = part("app/graph.js")   # 이 시험이 묻는 것은 그래프 조각의 draw 다

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


class GraphLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    # ---------- ① dag 라고 게이트를 건너뛰지 않는다 ----------

    def test_graph_labels(self):
        """GraphLabels 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("dag_no_longer_bypasses_the_label_gate"):
            self.assertNotRegex(
                self.src, r'showLabel[\s\S]{0,200}graphLayout === "dag"',
                '라벨 규칙이 dag 를 예외로 둔다 — 476개를 매 프레임 전부 그린다')
            self.assertNotIn("const showLabel", self.src,
                             "노드마다 자기 이름을 그리던 옛 규칙이 남아 있다")
        with self.subTest("labels_are_drawn_after_every_node"):
                d = self._fn("draw")
                i_node = d.index("for (const n of drawOrder)")
                i_lab = d.index("pickLabels(hov, nb)")
                self.assertLess(i_node, i_lab, "이름을 점보다 먼저 그린다 — 점에 잘린다")
                self.assertLess(d.index("picked.acc"), d.index("picked.hot"),
                                "hover 이름이 채택 집합보다 먼저 그려진다 (맨 위여야 한다)")

            # ---------- ② 겹치지 않는 것만, 예산까지 ----------
        with self.subTest("overlap_is_actually_measured"):
            self.assertIn("ctx.measureText", self._fn("labWidth"),
                          "라벨 폭을 재지 않는다 — 겹침을 판정할 수 없다")
            self.assertRegex(self.src, r"const labHits = \(a, b\) =>[\s\S]{0,160}a\.x0 < b\.x1",
                             "겹침 판정(사각형 교차)이 없다")
            pick = self._fn("pickLabels")
            self.assertIn("labHits(a, c)", pick, "채택 전에 겹침을 보지 않는다")
            self.assertIn("acc.length >= LAB_BUDGET", pick, "예산 상한이 없다")
            self.assertRegex(self.src, r"const LAB_BUDGET = \d+;", "예산 값이 없다")
        with self.subTest("no_zoom_cliff"):
            self.assertNotIn("st.tf.k > 0.75 && n.near > 0.45", self.src,
                             "줌·깊이 절벽이 남아 있다 — 전체 보기에서 이름이 사라진다")
        with self.subTest("off_screen_labels_are_culled"):
            self.assertRegex(self._fn("pickLabels"),
                             r"b\.x1 < 0 \|\| b\.x0 > W \|\| b\.y1 < 0 \|\| b\.y0 > H",
                             "화면 밖 컬링이 없다")
        with self.subTest("measure_text_is_cached_per_title"):
            fn = self._fn("labWidth")
            self.assertIn("labWCache", fn, "제목별 폭 기억이 없다")
            self.assertIn("labWCache.set", fn)
        with self.subTest("pick_runs_every_frame"):
                self.assertIn("pickLabels(hov, nb)", self._fn("draw"),
                              "그리는 자리에서 매번 고르지 않는다")

            # ---------- ③ 우선순위는 "지금 손이 가야 할 것" ----------
        with self.subTest("priority_is_what_needs_a_hand_now"):
                self.assertRegex(self.src, r"const labPri = n => \(n\.waiting \|\| 0\) \* 10",
                                 "병목(미완료 파생)이 첫 자리가 아니다")
                self.assertIn("LAB_ST[n.status]", self._src_of("labPri"),
                              "진행 중·막힘·검토를 앞세우지 않는다")
                self.assertIn("Math.sqrt(deg[n.id] || 0)", self._src_of("labPri"),
                              "허브(연결 수)를 보지 않는다")
                # n.near(문서 id 해시가 절반)로 이름을 고르던 옛 규칙이 돌아오지 않게
                self.assertNotIn("n.near > 0.45", self.src,
                                 "임의값(해시 섞인 깊이)이 다시 이름을 고른다")

            # ---------- ④ 관성 ----------
        with self.subTest("hysteresis_keeps_names_from_flickering"):
            pick = self._fn("pickLabels")
            self.assertRegex(pick, r"labPrev\.has\(n\.id\) \? 1e6 : 0",
                             "관성이 없다 — 팬 중 이름이 깜빡인다")
            self.assertIn("labPrev = ids", pick, "이번 프레임 채택을 기억하지 않는다")
        with self.subTest("hover_names_dodge_each_other"):
                pick = self._fn("pickLabels")
                self.assertRegex(pick, r"for \(const dy of \[0, -\(2 \* rr \+ 21\)",
                                 "hover 이름이 자리를 옮겨 보지 않는다 — 서로 포갠다")
                self.assertIn("n.id === hov.id || !hot.some", pick,
                              "얹은 노드 자신의 이름이 밀려날 수 있다")

            # ---------- ⑤ 층 접기 ----------
        with self.subTest("layers_wrap_instead_of_crushing_into_one_row"):
            self.assertNotIn("const gap = Math.min(170, (W - 120) / Math.max(layer.length, 1));",
                             self.src, "한 층을 반드시 한 줄에 우겨넣는 옛 계산이 남아 있다")
            self.assertRegex(self.src, r"const DAG_GAP_MIN = (1[89]|2[0-6]);",
                             "가로 간격 하한이 없거나 18~26px 밖이다")
            self.assertIn("Math.floor(avail / DAG_GAP_MIN)", self.src, "줄바꿈 폭을 하한으로 정하지 않는다")
            self.assertIn("yCur + r * DAG_ROW_H", self.src, "접힌 줄이 세로로 벌어지지 않는다")
            self.assertNotIn("n.y = 70 + d * 105;", self.src,
                             "층 세로 위치가 고정이다 — 접은 줄만큼 밀리지 않아 층이 포갠다")
            self.assertRegex(self.src, r"yCur \+= \(rows - 1\) \* DAG_ROW_H \+ DAG_LAYER_H",
                             "층 사이가 누적 오프셋이 아니다")
        with self.subTest("dag_starts_at_fit"):
            self.assertRegex(self.src,
                             r'if \(graphLayout === "dag" && !graphTf\)\{[\s\S]{0,120}gFitTf\(\)',
                             "dag 첫 화면이 전체 보기가 아니다")
        with self.subTest("dag_layout_reads_as_layers"):
                self.assertRegex(self.src,
                                 r'const pfOf = n => graphLayout === "dag" \? 1 :',
                                 "dag 에서도 깊이 시차가 곧은 줄을 휘게 한다")

            # ---------- ⑥ 전후를 같은 자로 잰다 ----------
        with self.subTest("diagnostic_handles"):
                for h, why in (("glab", "잰 값을 판 위에 적는 손잡이"),
                               ("glabraw", "거르기 전 대조군"),
                               ("gdagraw", "접기 전 대조군"),
                               ("glabnohys", "관성 없는 대조군"),
                               ("gpan", "끄는 동안 갈리는지 재는 손잡이")):
                    self.assertIn("[?&]%s" % h, self.src, "%s (?%s) 가 없다" % (why, h))
                stat = self._fn("drawLabStat")
                self.assertIn("겹침쌍", stat, "겹침쌍을 적지 않는다 — 0 임을 그림으로 못 보인다")
                self.assertIn("교체/프레임", stat, "깜빡임을 적지 않는다")

            # ---------- 도구 ----------

    def _fn(self, name):
        """그래프 조각 **안에서만** 찾는다 (REQ-20260829-027 이후).

        이어 붙인 한 장에서 찾으면 먼저 오는 조각의 같은 이름이 잡힌다 —
        진단 조각(`app/oops.js`, 맨 앞)이 자기 `draw()` 를 두자 실제로 그것을
        집었다. 제품은 멀쩡한데 시험만 빨개지는 실패라, 묻는 자리를 좁힌다.
        """
        m = re.search(r"function %s\([^)]*\)\{[\s\S]*?\n  \}" % name, GRAPH)
        self.assertIsNotNone(m, "%s() 를 찾지 못했다" % name)
        return m.group(0)

    def _src_of(self, name):
        m = re.search(r"const %s = [\s\S]*?;\n" % name, self.src)
        self.assertIsNotNone(m, "%s 를 찾지 못했다" % name)
        return m.group(0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
