"""멈춘 것이 화면에 보인다 (REQ-20260828-036-62x6).

사용자가 하루에 세 번 물었다: "몇개 요청들이 몇십분째 진행중으로 뜨는데 진짜
진행중인건가?" 화면은 못 보고 있던 게 아니라 **반대로 말하고 있었다** — 초록 점
3개 중 2개가 거짓이었다.

점이 재던 것은 "이 요청의 진전"이 아니라 **"이 요청을 잡고 있는 세션의 맥박"**
이다. 리드 세션은 늘 살아 있고 요청을 여럿 한꺼번에 잡으므로, 리드가 다른 일을
하는 동안에도 잡아 둔 요청이 전부 초록으로 뛰었다. CLI(`s9 stalled`)는 이미
2026-08-27 에 고쳐졌고(REQ-20260827-074) 화면만 옛 판정에 남아 있었다.

그래서 계약은 넷이다.

  ① **판정은 한 벌.** `catalog_with_live()` 가 행마다 `stalled_mins` 를 싣고,
     `stalled_requests()` 는 그것을 읽어 거르기만 한다. 두 벌이면 한 벌만
     고쳐진다 — 이번 사고가 정확히 그것이었다.
  ② **말이 어긋나지 않는다.** 멈춘 요청은 초록 점멸을 켜지 않는다. 같은 카드가
     점으로는 "돈다", 글자로는 "멈췄다"고 말하면 둘 다 못 믿게 된다.
  ③ **꺼진 점이 읽힌다.** `.livedot.off` 는 속 빈 링이다. 채운 `--faint` 점은
     라이트·다크 양쪽에서 2.98:1 로 기준(3:1) 미달이었고, 라이트에서는 초록보다
     오히려 밝아 흑백으로 보면 "일하는 중"이 "버려짐"보다 어두웠다.
  ④ **새 층을 만들지 않는다.** 멈춤은 기존 `.rvpt` 한 줄 + 열 머리 숫자로
     말한다 — 새 배지·색면·경고 띠·깜빡임 없이. (선행 대기 줄이 이기던 규칙은
     REQ-20260828-041 2차 반려에서 뒤집혔다 — 그 관문이 지운 것은 문장이 아니라
     **행동**이었고, 카드에만 있어서 문서 화면과 갈라졌다. C4 참조.)

격리: S9_ROOT=mktemp. 실행: python3 tests/ stall_visible
"""
import json
import os
import re
import subprocess
import tempfile
import time
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
INDEX = index_path()


def _grab(src, name):
    m = re.search(r"function %s\([^)]*\)\{[\s\S]*?\n\}" % name, src)
    assert m, name
    return m.group(0)


# --------------------------------------------------------------- 서버: 한 벌

class StallJudgmentServer(unittest.TestCase):
    """catalog_with_live 가 멈춤을 재고, stalled 는 그것을 읽는다."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9stallv-")
        cls.claude = os.path.join(cls.root, "cc")
        os.makedirs(os.path.join(cls.claude, "proj"), exist_ok=True)
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox",
                   "S9_CLAUDE_PROJECTS": cls.claude}
        cls.env.pop("S9_SESSION", None)
        cls.cli(None, "init")
        cls.cli(None, "user", "add", "alice")

        def mk(sess, title):
            rid = cls.cli(sess, "new", "request", "--title", title,
                          "--summary", "s", "--goal", "g", "--size", "S",
                          "--user", "alice", "--body", "x").split()[0]
            cls.cli(sess, "status", rid, "in-progress", "--note", "t")
            return rid

        cls.STALE = mk("aaaa1111", "손 뗀 것")
        cls.FRESH = mk("bbbb2222", "방금 움직인 것")
        cls.DONE = mk("cccc3333", "끝난 것")
        cls.cli("cccc3333", "status", cls.DONE, "done", "--note", "t")

        # 두 세션 모두 **지금** 살아 있다 — 세션 맥박은 둘 다 초록이던 그 상황.
        streams = os.path.join(cls.root, "streams")
        os.makedirs(streams, exist_ok=True)
        for sid in ("aaaa1111", "bbbb2222"):
            p = os.path.join(streams, sid + ".jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"role": "assistant", "text": "x"}) + "\n")
            os.utime(p, (time.time(), time.time()))
        cls._backdate(cls.STALE, 3600)
        # 클레임도 한 시간 전으로 (REQ-20260831-005). 문서만 되감고 클레임을
        # 방금 것으로 두면 "지금 활동 중인 세션이 방금 잡은 것"이 되는데, 그
        # 조합은 이제 멈춤이 아니라 attached 다(긴 턴 진행 중 — 일하는 세션
        # 위에 두 번째 손을 얹지 않는다). 이 시험이 겨냥한 손 뗀 것(REQ-074)은
        # "한 시간 전에 잡고 그 뒤 문서에 아무 일도 없던 것"이고, 그 클레임은
        # claim_dead(30분 유예)가 풀어 준다 — 실제로 한 시간 방치된 요청이
        # 겪는 바로 그 경로다.
        cls._backdate_claim("aaaa1111", cls.STALE, 3500)

    @classmethod
    def _backdate_claim(cls, sid, rid, secs):
        import datetime
        p = os.path.join(cls.root, "state", "sessions", f"testbox__{sid}.json")
        with open(p, encoding="utf-8") as f:
            b = json.load(f)
        ts = (datetime.datetime.now().astimezone()
              - datetime.timedelta(seconds=secs)).isoformat(timespec="seconds")
        cat = dict(b.get("claim_at") or {})
        cat[rid] = ts
        b["claim_at"] = cat
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f)

    @classmethod
    def _backdate(cls, rid, secs):
        import datetime
        ts = (datetime.datetime.now().astimezone()
              - datetime.timedelta(seconds=secs)).isoformat(timespec="seconds")
        for dp, _dn, fns in os.walk(os.path.join(cls.root, "vault")):
            for fn in fns:
                if fn.startswith(rid) and fn.endswith(".md"):
                    q = os.path.join(dp, fn)
                    t = open(q, encoding="utf-8").read()
                    t = "\n".join(
                        (f"status_since: {ts}" if ln.startswith("status_since:")
                         else f"updated: {ts}" if ln.startswith("updated:")
                         else ln) for ln in t.splitlines()) + "\n"
                    open(q, "w", encoding="utf-8").write(t)
                    # 손길도 같이 되감는다 (REQ-20260830-019) — 문서만 되감으면
                    # 방금 만든 하트비트가 '1시간 조용한데 손길은 방금'이라는,
                    # 현실에 없는 조합을 만든다. 실제로 1시간 손 뗀 요청은
                    # 손길도 1시간 낡아 있다.
                    hb = os.path.join(cls.root, "state", "heartbeat", rid)
                    if os.path.exists(hb):
                        t0 = time.time() - secs
                        os.utime(hb, (t0, t0))
                    cls.cli(None, "index", "rebuild")
                    return
        raise AssertionError(f"문서 없음: {rid}")

    @classmethod
    def cli(cls, sess, *argv, expect=0):
        env = dict(cls.env)
        if sess:
            env["S9_SESSION"] = sess
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env, timeout=30)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    @classmethod
    def catalog(cls):
        code = (
            "import importlib.machinery as m, importlib.util as u, json, sys\n"
            "s=u.spec_from_loader('s9m', m.SourceFileLoader('s9m', sys.argv[1]))\n"
            "mod=u.module_from_spec(s); s.loader.exec_module(mod)\n"
            "print(json.dumps(mod.catalog_with_live()))\n")
        r = subprocess.run(["python3", "-c", code, os.path.abspath(S9)],
                           capture_output=True, text=True, env=cls.env,
                           timeout=60)
        if r.returncode:
            raise AssertionError(r.stdout + r.stderr)
        return {x["id"]: x for x in json.loads(r.stdout)}

    # S1. 멈춘 행은 분(minutes)을 달고 온다 — 화면이 다시 재지 않아도 되게
    def test_stall_judgment_server(self):
        """catalog_with_live 가 멈춤을 재고, stalled 는 그것을 읽는다."""
        with self.subTest("s1_stalled_row_carries_minutes"):
                row = self.catalog()[self.STALE]
                self.assertIsNotNone(row.get("stalled_mins"),
                                     "멈춘 in-progress 행에 stalled_mins 가 없다")
                self.assertGreaterEqual(row["stalled_mins"], 15)

            # S2. 세션이 살아 있다고 진전이 아니다 — 그게 이번 사고의 거짓말이었다
            #
            # 개정 (REQ-20260831-005): 원래는 live=True(직접)인 채로 멈춤이 함께 서는
            # 것을 계약으로 삼았다. 이제 그 조합은 정의상 없다 — 클레임 + 2분 내 활동은
            # attached(긴 턴 진행 중)지 멈춤이 아니다(일하는 세션 위에 두 번째 손을
            # 얹지 않는다). 이 시험의 과녁("세션 맥박 ≠ 진전")은 그대로 남는다: 손 뗀
            # 것의 클레임은 유예가 풀고, 그 뒤에도 세션 맥박(간접, live_kind=session)이
            # 뛰는 동안 멈춤은 멈춤이라 말해야 한다.
        with self.subTest("s2_live_session_still_stalled"):
                row = self.catalog()[self.STALE]
                self.assertEqual(row.get("live_kind"), "session",
                                 "이 상황(세션은 활동 중, 클레임은 풀림)이 아니다")
                self.assertIsNotNone(row.get("stalled_mins"),
                                     "세션 맥박을 요청의 진전으로 치고 있다")

            # S3. 방금 움직인 것과 끝난 것에는 안 붙는다
        with self.subTest("s3_fresh_and_done_have_none"):
                cat = self.catalog()
                self.assertIsNone(cat[self.FRESH].get("stalled_mins"))
                self.assertIsNone(cat[self.DONE].get("stalled_mins"))

            # S4. CLI 와 화면이 같은 수를 말한다
        with self.subTest("s4_cli_matches_catalog"):
                out = self.cli(None, "stalled")
                self.assertIn(self.STALE, out)
                self.assertNotIn(self.FRESH, out)
                mins = self.catalog()[self.STALE]["stalled_mins"]
                self.assertIn(f"{mins}분째", out,
                              f"CLI 와 화면의 분이 다르다 (화면 {mins})")

            # S5. 판정을 두 벌 만들지 않는다 — stalled 는 읽기만 한다
        with self.subTest("s5_single_judgment"):
                src = open(S9_SRC, encoding="utf-8").read()
                i = src.index("def stalled_requests(")
                seg = src[i:src.index("\ndef ", i + 10)]
                self.assertIn("stalled_mins", seg,
                              "stalled 가 catalog 의 판정을 읽지 않는다")
                self.assertNotIn("fromisoformat", seg,
                                 "stalled 가 나이를 다시 재고 있다 — 판정이 두 벌이다")

            # S6. 화면으로 나가는 통로에 실린다
        with self.subTest("s6_reaches_the_screen"):
            src = open(S9_SRC, encoding="utf-8").read()
            i = src.index('elif parsed.path == "/api/catalog"')
            j = src.index('elif parsed.path ==', i + 10)   # 다음 갈래 직전까지
            self.assertIn("catalog_with_live()", src[i:j],
                          "/api/catalog 가 live 판정을 거치지 않는다")

# ------------------------------------------------------------------- 화면

class StallOnScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.card = _grab(cls.src, "cardHTML")
        cls.col = _grab(cls.src, "colHTML")
        cls.board = _grab(cls.src, "renderBoard")
        # 멈춤 줄의 글자는 stallHTML 로 옮겨 갔다 (REQ-20260828-041): 보드 카드와
        # 문서 화면이 **한 함수**로 그 줄을 짓게 하려는 것이고, 계약은 그대로다.
        # 그래서 검사는 "카드가 그리는 것" 이 아니라 "카드가 부르는 자리까지"
        # 본다.
        cls.stall = _grab(cls.src, "stallHTML")

    # C1. 꺼진 점은 속 빈 링이다 (대비 2.98:1 → 기준 통과)
    def test_stall_on_screen(self):
        """StallOnScreen 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("c1_off_dot_is_a_ring"):
                m = re.search(r"\.livedot\.off\{([^}]*)\}", self.src)
                self.assertTrue(m, ".livedot.off 규칙이 없다")
                rule = m.group(1)
                self.assertIn("transparent", rule, "꺼진 점이 아직 색으로 채워져 있다")
                self.assertIn("border", rule, "속 빈 링이 아니다")
                self.assertNotIn("var(--faint)", rule,
                                 "--faint 는 대비 2.98:1 로 미달이다")

            # C2. 멈춘 카드는 초록 점멸을 켜지 않는다 — 점과 글자가 어긋나면 둘 다 죽는다
        with self.subTest("c2_stalled_never_pulses_green"):
                i = self.card.index("livedot")
                seg = self.card[:i]
                self.assertIn("stalled_mins", seg,
                              "점을 고르기 전에 멈춤 판정을 읽지 않는다")
                on = self.card.index('livedot on')
                stall = self.card.index("stalled", i - 400 if i > 400 else 0)
                self.assertLess(stall, on,
                                "초록 점멸이 멈춤 판정보다 먼저 걸린다 — 멈춘 것이 초록으로 뛴다")

            # C3. 멈춤은 기존 한 줄 문법(.rvpt)으로 말한다 — 새 배지·색면 없음
        with self.subTest("c3_one_line_reuses_rvpt"):
                self.assertIn("stallHTML(r)", self.card, "카드가 멈춤 줄을 짓는 자리를 안 부른다")
                self.assertIn('rvpt stall', self.stall, "멈춤 줄이 .rvpt 형제가 아니다")
                self.assertIn("진전 없음", self.stall)
                self.assertIn("마지막", self.stall)

            # C4. 선행 대기가 있어도 손잡이를 뺏지 않는다 (REQ-20260828-041 2차로 뒤집힘)
        with self.subTest("c4_dep_does_not_eat_the_handle"):
                m = re.search(r"const stall\s*=([\s\S]{0,400}?);\n", self.card)
                self.assertTrue(m, "멈춤 줄을 짓는 자리가 없다")
                self.assertNotIn("bl.length", m.group(1),
                                 "선행 대기가 아직 멈춤 손잡이를 지운다")

            # C5. 열 머리가 몇 개가 멈췄는지 센다 — in-progress 열에서만, 0이면 안 나온다
        with self.subTest("c5_column_head_counts"):
                self.assertIn("멈춤", self.col, "열 머리에 멈춤 수가 없다")
                # 세는 술어는 카드가 쓰는 그 하나다 (REQ-20260828-041 2차)
                self.assertIn("stallState(", self.col)
                m = re.search(r"const stalls?\s*=([\s\S]{0,300}?);\n", self.col)
                self.assertTrue(m, "멈춤 수를 세는 자리가 없다")
                self.assertIn('in-progress', m.group(1) + self.col,
                              "멈춤 수가 in-progress 열에 한정되지 않는다")

            # C6. in-progress 열은 오래 멈춘 순으로 선다 — 급한 것이 위에
        with self.subTest("c6_stalled_first"):
                self.assertIn("stallState(", self.board,
                              "보드가 멈춤으로 정렬하지 않는다")
                seg = self.board[self.board.index("stallState(") - 300:]
                self.assertIn("in-progress", seg[:400] + self.board,
                              "정렬이 in-progress 열에 한정되지 않는다")

            # C7. 하지 않기로 한 것: 깜빡임·색면·좌측 바·새 경고 띠
        with self.subTest("c7_no_new_layer"):
            m = re.search(r"\.rvpt\.stall[^{]*\{([^}]*)\}", self.src)
            self.assertTrue(m, ".rvpt.stall 규칙이 없다")
            rule = m.group(1)
            for banned in ("animation", "background", "border-left"):
                self.assertNotIn(banned, rule,
                                 f"멈춤 줄이 {banned} 로 새 층을 만들고 있다")
            self.assertNotIn("stallbanner", self.src)
            # 카드 자체에 멈춤 배경을 칠하지 않는다
            self.assertFalse(re.search(r"\.card\[data-stall[^{]*\{[^}]*background",
                                       self.src),
                             "멈춘 카드에 배경을 칠하고 있다")

if __name__ == "__main__":
    unittest.main()
