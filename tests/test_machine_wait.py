"""「기다린다」는 말이 참이 아니었다 — 기다리는 까닭 셋 (REQ-20260911-004-62x6).

주인 물음 2026-09-11 08:54: 「그래서 저 작업을 맥에서 지금 하고 있는건지
안하는건지는 알 수 없는거지?」

그때 맥미니는 5분 전에도 저장소를 받고 있었고(켜져 있었다) 맡기기만 꺼져 있어
배정된 요청을 영영 집지 않았다. 카드는 8시간 51분째 「담당 컴퓨터 … 을 기다리는
중」이라고만 적었다 — **꺼진 컴퓨터와 똑같은 문장**이었다. 기다림의 까닭이 셋이면
줄도 셋이어야 한다:

  quiet — 오래 못 받고 있다(꺼져 있거나 받는 길이 끊겼다)
  off   — 맡기기가 꺼져 있어 저절로 시작하지 않는다
  soon  — 받고 있고 맡기기도 켜져 있다, 그 컴퓨터가 집는다

갈래를 정하는 자리는 서버 하나(machine_wait_verdict)이고 화면은 그 갈래의 말만
고른다. 화면이 스스로 판정하면 임계가 두 벌이 되고, 한 자리에서 고친 수가 다른
자리에서 어긋난다 — 이 저장소가 멈춤 표시에서 이미 배운 것이다.

실행: python3 tests/ machine_wait
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import unittest

from webasset import index_path

HERE = os.path.dirname(os.path.abspath(__file__))
S9_SRC = os.path.join(HERE, "..", "bin", "s9.py")


def _find_node():
    """시험끼리 import 하지 않는다 (test_stdlib_only) — 그래서 두 도우미는 화면
    시험마다 제 파일에 둔다. 둘 다 짧고, 재는 대상이 아니라 재는 도구다."""
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node", "/root/.vscode-server/bin/*/node"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


NODE = _find_node()


def _grab(src, name):
    """`function 이름(...){ … }` 한 덩어리를 원문 그대로 떠 온다."""
    m = re.search(r"\nfunction %s\([^)]*\)\{[\s\S]*?\n\}" % name, src)
    assert m, name
    return m.group(0)


def _s9():
    spec = importlib.util.spec_from_loader(
        "s9_machine_wait", importlib.machinery.SourceFileLoader(
            "s9_machine_wait", S9_SRC))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


NOW = 1_757_000_000.0


def _row(**kw):
    """등록부 한 줄 — machine_table 이 내는 모양 그대로."""
    r = {"machine": "MAC", "os": "macOS", "names": [], "account": "",
         "last": "", "last_recv": "", "takes": None}
    r.update(kw)
    return r


def _iso(secs_ago):
    import datetime
    return datetime.datetime.fromtimestamp(NOW - secs_ago).astimezone().isoformat(
        timespec="seconds")


class TheServerJudgesOnce(unittest.TestCase):
    """갈래를 정하는 자리는 하나다 — 사실(받은 때 · 맡기기)에서 갈래가 나온다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _s9()

    def verdict(self, **kw):
        row = _row(**kw)
        return self.m.machine_wait_verdict(
            "MAC", now=NOW, table={"MAC": row})

    def test_the_three_kinds_and_the_silence(self):
        # N1 받고 있고 맡기기가 켜졌다 — 그 컴퓨터가 집는다
        v = self.verdict(last_recv=_iso(300), takes=True)
        self.assertEqual(v["kind"], "soon")
        self.assertEqual(v["recv_mins"], 5, "마지막으로 받은 때가 안 실린다")

        # N2 받고 있는데 맡기기가 꺼졌다 — 켜져 있어도 저절로 시작하지 않는다
        #    (2026-09-11 실측의 그 맥미니가 이 갈래다)
        v = self.verdict(last_recv=_iso(300), takes=False)
        self.assertEqual(v["kind"], "off")

        # B1 오래 못 받고 있다 — 맡기기가 켜져 있어도 집을 문서가 안 온다.
        #    못 받는 것이 맡기기보다 앞선다.
        old = self.m.MACHINE_RECV_ALERT_SEC + 600
        self.assertEqual(self.verdict(last_recv=_iso(old),
                                      takes=True)["kind"], "quiet")
        self.assertEqual(self.verdict(last_recv=_iso(old),
                                      takes=False)["kind"], "quiet")

        # F1 적힌 것이 없으면 갈래를 만들지 않는다 — 모르는 것을 지어내지 않는다
        self.assertIsNone(self.verdict())
        self.assertIsNone(self.verdict(last_recv=_iso(300)))
        self.assertIsNone(self.m.machine_wait_verdict("없는컴퓨터", now=NOW,
                                                      table={"MAC": _row()}))
        self.assertIsNone(self.m.machine_wait_verdict("", now=NOW, table={}))

    def test_only_the_waiting_rows_carry_it(self):
        """행에 싣는 조건 — in-progress · 담당 컴퓨터가 있고 · 이 컴퓨터가 아니다."""
        src = open(os.path.join(HERE, "..", "bin", "s9.py"),
                   encoding="utf-8").read()
        i = src.index('r["machine_wait"] = _mw')
        seg = src[src.index("def catalog_with_live("):i]
        self.assertIn('_want == _here', seg, "이 컴퓨터의 일에도 싣는다")
        self.assertIn('r.get("status") != "in-progress"', seg)
        # 표는 사람마다 한 번만 읽는다 — 행마다 읽으면 폴마다 프로필을 n번 연다
        self.assertIn("if _u not in _tables:", seg)


@unittest.skipUnless(NODE, "node 없음 — 실행 검증 생략")
class TheRowSaysWhich(unittest.TestCase):
    """그리고 **그려 본다** — 갈래마다 줄의 꼬리와 점의 문장이 갈리는가."""

    @classmethod
    def setUpClass(cls):
        with open(index_path(), encoding="utf-8") as f:
            cls.src = f.read()

    def draw(self, rows):
        g = lambda n: _grab(self.src, n)
        script = "\n".join([
            'const esc = s => String(s ?? "").replace(/[&<>"]/g,'
            ' c => ({"&":"&amp;","<":"&lt;",">":"&gt;",\'"\':"&quot;"}[c]));',
            'const window = {__whoami: {machine: "THIS-PC"}};',
            "function leaseElsewhere(){ return null; }",
            "function canTakeover(){ return false; }",
            g("fmtStall"),
            g("waitingMachine"), g("waitingWords"),
            g("waitingRowHTML"), g("waitingDotHTML"),
            "const R = %s;" % json.dumps(rows),
            "console.log(JSON.stringify(R.map(r =>"
            " ({id: r.id, row: waitingRowHTML(r), dot: waitingDotHTML(r)}))));",
        ])
        p = subprocess.run([NODE, "-e", script], capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(p.returncode, 0, "node 실행 실패:\n" + p.stderr[-2000:])
        return {o["id"]: o for o in json.loads(p.stdout.strip().splitlines()[-1])}

    ROWS = [
        {"id": "SOON", "type": "request", "status": "in-progress", "user": "u",
         "needs_machine": "MAC", "quiet_mins": 531,
         "machine_wait": {"kind": "soon", "recv_mins": 5, "takes": True}},
        {"id": "OFF", "type": "request", "status": "in-progress", "user": "u",
         "needs_machine": "MAC", "quiet_mins": 531,
         "machine_wait": {"kind": "off", "recv_mins": 5, "takes": False}},
        {"id": "QUIET", "type": "request", "status": "in-progress", "user": "u",
         "needs_machine": "MAC", "quiet_mins": 531,
         "machine_wait": {"kind": "quiet", "recv_mins": 260, "takes": True}},
        # 갈래를 모르는 것 — 지금까지의 문장 그대로 (회귀)
        {"id": "UNKNOWN", "type": "request", "status": "in-progress", "user": "u",
         "needs_machine": "MAC", "quiet_mins": 531},
        # 담당 컴퓨터가 이 컴퓨터인 것 · 없는 것 — 줄 자체가 없다 (회귀)
        {"id": "HERE", "type": "request", "status": "in-progress", "user": "u",
         "needs_machine": "THIS-PC", "quiet_mins": 531},
        {"id": "ANY", "type": "request", "status": "in-progress", "user": "u",
         "quiet_mins": 531},
    ]

    def test_each_kind_gets_its_own_words(self):
        out = self.draw(self.ROWS)
        for rid in ("SOON", "OFF", "QUIET", "UNKNOWN"):
            with self.subTest(rid):
                # 기다리는 사실과 기다린 시간은 네 갈래 모두에 그대로 남는다
                self.assertIn("을 기다리는 중", out[rid]["row"])
                self.assertIn("8시간 51분째", out[rid]["row"])
        self.assertIn("곧 집습니다", out["SOON"]["row"])
        self.assertIn("맡기기가 꺼져 있습니다", out["OFF"]["row"])
        self.assertIn("그 컴퓨터가 조용합니다", out["QUIET"]["row"])
        # 갈래를 모르면 아무 말도 덧붙이지 않는다
        for w in ("곧 집습니다", "맡기기가", "조용합니다"):
            self.assertNotIn(w, out["UNKNOWN"]["row"])
        # 점과 줄은 한 벌 — 같은 갈래의 같은 문장을 쓴다
        self.assertIn("맡기기가 꺼져 있어", out["OFF"]["dot"])
        self.assertIn("곧 시작합니다", out["SOON"]["dot"])
        self.assertIn("받지 못하고 있습니다", out["QUIET"]["dot"])
        # 켜져 있는지 모르는 채로 「켜져 있다」고 단정하지 않는다
        self.assertNotIn("켜져 있지만", out["OFF"]["row"] + out["OFF"]["dot"])

    def test_the_line_does_not_stand_where_there_is_nothing_to_wait_for(self):
        out = self.draw(self.ROWS)
        self.assertEqual(out["HERE"]["row"], "", "이 컴퓨터의 일에 기다리는 줄이 섰다")
        self.assertEqual(out["ANY"]["row"], "")
        self.assertEqual(out["HERE"]["dot"], "")

    def test_the_screen_does_not_keep_its_own_threshold(self):
        """화면은 갈래를 다시 판정하지 않는다 — 임계를 베껴 두면 두 벌이 된다."""
        js = _grab(self.src, "waitingWords") + _grab(self.src, "waitingMachine")
        js = re.sub(r"/\*[\s\S]*?\*/", " ", js)
        for w in ("last_recv", "takes", "RECV", "1800", "7200"):
            self.assertNotIn(w, js, f"화면이 갈래를 스스로 재고 있다 ({w})")
        self.assertIn("r.machine_wait", js, "서버가 실어 준 갈래를 안 읽는다")


if __name__ == "__main__":
    unittest.main()
