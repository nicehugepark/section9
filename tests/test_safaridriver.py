"""남겨진 safaridriver 를 가려서 거둔다 (REQ-20260916-019-2n7g).

맥의 Safari 는 한 번에 한 WebDriver 세션만 받는다. 2026-09-16 밤 두 번(04:25 ·
05:13), 끝난 에이전트가 남기고 간 safaridriver 가 짝을 쥐고 있어 다음 사람이
세션을 못 열었다. 푼 길은 pid 를 죽이는 것뿐이었는데 **남의 것인지 남겨진
것인지 가릴 값이 없어** 리드는 20분을 기다린 뒤에야 끊었다.

여기서 못박는 계약은 넷이다: 띄운 주인을 적는다 · 주인 세션의 생사로 판정한다 ·
모르는 것은 모른다고 적는다 · 쓰는 중인 것은 --force 없이 거두지 않는다.

실행: python3 tests/ safaridriver
"""
import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
SKILL = os.path.join(HERE, "..", "harness", "claude", "skills",
                     "s9-skl-browser-verify", "SKILL.md")
ROSTER = os.path.join(HERE, "..", "harness", "claude", "gen_roster.py")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_sd", importlib.machinery.SourceFileLoader("s9_sd", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _args(action="ls", **kw):
    ns = argparse.Namespace(action=action, port=0, session="", req="",
                            mine=False, stale=False, all=False, force=False,
                            older_than=600)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


class SafariDriver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def setUp(self):
        m = self.m
        self.tmp = tempfile.mkdtemp(prefix="s9-sd-")
        self._root, m.ROOT = m.ROOT, self.tmp
        self._plat, m.os_platform = m.os_platform, lambda: "macOS"
        self._age, m._sd_age = m._sd_age, lambda pid: self.ages.get(int(pid), 9999)
        self._tbl, m.proc_table = m.proc_table, lambda *a, **k: dict(self.procs)
        self._bind, m._sd_binding_of = m._sd_binding_of, \
            lambda sid: self.bindings.get((sid or "")[:8])
        self._alive, m.chat_alive = m.chat_alive, lambda b, win=300: bool(b.get("up"))
        self._kill, m._sd_kill = m._sd_kill, self._record_kill
        self.procs, self.ages, self.bindings, self.killed = {}, {}, {}, []

    def tearDown(self):
        m = self.m
        m.ROOT, m.os_platform, m._sd_age = self._root, self._plat, self._age
        m.proc_table, m._sd_binding_of = self._tbl, self._bind
        m.chat_alive, m._sd_kill = self._alive, self._kill
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _record_kill(self, pid, grace=3.0):
        self.killed.append(int(pid))
        return True

    # -- 자리 만들기 ------------------------------------------------------
    def _driver(self, pid, port, owner=None, up=None, age=9999):
        """도는 safaridriver 하나. owner 를 주면 주인 기록까지 함께 세운다."""
        self.procs[pid] = f"/usr/bin/safaridriver -p {port}"
        self.ages[pid] = age
        if owner is not None:
            self.m._sd_write_reg({"port": port, "pid": pid, "session": owner,
                                  "machine": "테스트맥", "req": "REQ-테스트",
                                  "started": "2026-09-16T04:00:00+09:00"})
            if up is not None:
                self.bindings[owner[:8]] = {"session": owner, "up": up}

    def _run(self, ns):
        out = io.StringIO()
        err = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                self.m.cmd_safaridriver(ns)
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    # -- 정상 ------------------------------------------------------------
    def test_z01_ls_lists_running(self):
        """정상 — 떠 있는 드라이버마다 포트·pid·나이·주인·판정 한 줄."""
        self._driver(111, 4445, owner="aaaaaaaa", up=True, age=600)
        code, out, _ = self._run(_args("ls", session="bbbbbbbb"))
        self.assertEqual(code, 0)
        self.assertIn("포트 4445", out)
        self.assertIn("pid 111", out)
        self.assertIn("aaaaaaaa", out)
        self.assertIn(self.m.SD_IN_USE, out)

    def test_z02_verdict_in_use(self):
        """정상 — 주인 세션이 떠 있으면 「쓰는 중」."""
        self._driver(111, 4445, owner="aaaaaaaa", up=True)
        rows = self.m._sd_rows("bbbbbbbb")
        self.assertEqual(rows[0]["verdict"], self.m.SD_IN_USE)

    def test_z03_verdict_left_over(self):
        """정상 — 주인 세션이 끝났으면 「남겨진 것」."""
        self._driver(111, 4445, owner="aaaaaaaa", up=False)
        rows = self.m._sd_rows("bbbbbbbb")
        self.assertEqual(rows[0]["verdict"], self.m.SD_LEFT)

    def test_z04_verdict_unknown_is_not_guessed(self):
        """정상 — 주인 기록이 없으면 「모름」이다. 추측해 「남겨진 것」이라 적지 않는다."""
        self._driver(111, 4445)
        rows = self.m._sd_rows("bbbbbbbb")
        self.assertEqual(rows[0]["verdict"], self.m.SD_UNKNOWN)
        self.assertNotEqual(rows[0]["verdict"], self.m.SD_LEFT)

    def test_z05_verdict_mine(self):
        """정상 — 이 세션이 띄운 것은 「내 것」."""
        self._driver(111, 4445, owner="bbbbbbbb", up=True)
        rows = self.m._sd_rows("bbbbbbbb")
        self.assertEqual(rows[0]["verdict"], self.m.SD_MINE)

    def test_z06_quit_mine_spares_others(self):
        """정상 — quit --mine 은 이 세션 것만 거두고 남의 것은 두고 간다."""
        self._driver(111, 4445, owner="bbbbbbbb", up=True)
        self._driver(222, 4446, owner="aaaaaaaa", up=False)
        code, out, _ = self._run(_args("quit", session="bbbbbbbb", mine=True))
        self.assertEqual(code, 0)
        self.assertEqual(self.killed, [111])
        self.assertIn("포트 4445", out)

    def test_z07_quit_stale_takes_left_and_unknown(self):
        """정상 — quit --stale 은 「쓰는 중」이 아닌 것만 거둔다."""
        self._driver(111, 4445, owner="aaaaaaaa", up=True, age=9999)   # 쓰는 중
        self._driver(222, 4446, owner="cccccccc", up=False, age=9999)  # 남겨진 것
        self._driver(333, 4447, age=9999)                              # 모름
        code, _, _ = self._run(_args("quit", session="bbbbbbbb", stale=True))
        self.assertEqual(code, 0)
        self.assertEqual(sorted(self.killed), [222, 333])

    # -- 경계 ------------------------------------------------------------
    def test_z08_quit_refuses_in_use(self):
        """경계 — 「쓰는 중」인 포트는 거부하고 --force 를 일러 준다."""
        self._driver(111, 4445, owner="aaaaaaaa", up=True)
        code, _, err = self._run(_args("quit", session="bbbbbbbb", port=4445))
        self.assertEqual(code, 1)
        self.assertEqual(self.killed, [])
        self.assertIn("--force", err)

    def test_z09_quit_force_takes_in_use(self):
        """경계 — --force 를 붙이면 「쓰는 중」이어도 거둔다."""
        self._driver(111, 4445, owner="aaaaaaaa", up=True)
        code, _, _ = self._run(_args("quit", session="bbbbbbbb", port=4445,
                                     force=True))
        self.assertEqual(code, 0)
        self.assertEqual(self.killed, [111])

    def test_z10_quit_stale_spares_young(self):
        """경계 — 방금 뜬 것은 --stale 이 남긴다 (옆 세션이 지금 짝을 맺는 중일 수 있다)."""
        self._driver(111, 4445, age=5)
        code, out, _ = self._run(_args("quit", session="bbbbbbbb", stale=True))
        self.assertEqual(code, 0)
        self.assertEqual(self.killed, [])
        self.assertIn("거둘 것 없음", out)

    def test_z11_ls_empty(self):
        """경계 — 떠 있는 것이 없으면 그 사실을 내고 0 으로 끝난다."""
        code, out, _ = self._run(_args("ls", session="bbbbbbbb"))
        self.assertEqual(code, 0)
        self.assertIn("떠 있는 safaridriver 없음", out)

    def test_z12_quit_clears_registry(self):
        """경계 — 거둔 뒤 주인 기록도 함께 지운다. 남은 기록이 다음 판정을 속인다."""
        self._driver(111, 4445, owner="bbbbbbbb", up=True)
        self.assertTrue(os.path.exists(self.m._sd_reg_path(4445)))
        self._run(_args("quit", session="bbbbbbbb", mine=True))
        self.assertFalse(os.path.exists(self.m._sd_reg_path(4445)))

    def test_z13_registry_reused_port_is_not_owned(self):
        """경계 — 같은 포트에 다른 pid 가 섰으면 옛 기록은 그 프로세스의 것이 아니다."""
        self.m._sd_write_reg({"port": 4445, "pid": 111, "session": "aaaaaaaa",
                              "machine": "테스트맥", "req": "", "started": ""})
        self._driver(999, 4445)          # 기록의 pid 와 다르다
        rows = self.m._sd_rows("bbbbbbbb")
        self.assertEqual(rows[0]["verdict"], self.m.SD_UNKNOWN)

    # -- 실패 ------------------------------------------------------------
    def test_z14_not_mac_is_not_an_empty_list(self):
        """실패 — 맥이 아니면 그 사실을 내고 비-0. 빈 목록으로 속이지 않는다."""
        self.m.os_platform = lambda: "Linux"
        code, out, err = self._run(_args("ls"))
        self.assertEqual(code, 2)
        self.assertIn("맥", err)
        self.assertNotIn("떠 있는 safaridriver 없음", out)

    def test_z15_registry_without_process_is_dropped(self):
        """실패 — pid 가 이미 없는 기록은 거두고 나머지를 낸다."""
        self.m._sd_write_reg({"port": 4499, "pid": 777, "session": "aaaaaaaa",
                              "machine": "테스트맥", "req": "", "started": ""})
        self._driver(111, 4445, owner="bbbbbbbb", up=True)
        rows = self.m._sd_rows("bbbbbbbb")
        self.assertEqual([r["port"] for r in rows], [4445])
        self.assertFalse(os.path.exists(self.m._sd_reg_path(4499)))

    def test_z16_quit_no_such_port(self):
        """실패 — 지목한 포트에 드라이버가 없으면 사실을 내고 비-0."""
        code, _, err = self._run(_args("quit", session="bbbbbbbb", port=4600))
        self.assertEqual(code, 1)
        self.assertIn("4600", err)

    def test_z17_broken_registry_row(self):
        """실패 — 기록 파일이 깨졌어도 판정은 「모름」으로 이어진다."""
        os.makedirs(self.m._sd_dir(), exist_ok=True)
        with open(self.m._sd_reg_path(4445), "w", encoding="utf-8") as f:
            f.write("{깨진 것")
        self._driver(111, 4445)
        rows = self.m._sd_rows("bbbbbbbb")
        self.assertEqual(rows[0]["verdict"], self.m.SD_UNKNOWN)

    def test_z18_self_is_not_a_driver(self):
        """실패 — `s9 safaridriver ls` 를 도는 제 자신을 목록에 싣지 않는다."""
        self.procs[555] = "/usr/bin/python3 /Users/x/section9/bin/s9 safaridriver ls"
        rows = self.m._sd_rows("bbbbbbbb")
        self.assertEqual(rows, [])

    # -- 회귀 ------------------------------------------------------------
    def test_z19_start_registers_owner(self):
        """회귀 — start 는 주인(세션·요청·pid·포트)을 적는다. 적지 않으면 다음 사람이 또 20분을 기다린다."""
        m = self.m
        asked = {}
        real_spawn, real_ready = m._sd_spawn, m._sd_ready

        def fake_spawn(port):
            asked["port"] = port
            return 4242

        m._sd_spawn = fake_spawn
        m._sd_ready = lambda port, timeout=8.0: True
        try:
            code, out, _ = self._run(_args("start", session="bbbbbbbb",
                                           port=4445, req="REQ-써봄"))
        finally:
            m._sd_spawn, m._sd_ready = real_spawn, real_ready
        self.assertEqual(code, 0)
        self.assertEqual(asked["port"], 4445)
        with open(m._sd_reg_path(4445), encoding="utf-8") as f:
            rec = json.load(f)
        self.assertEqual(rec["pid"], 4242)
        self.assertEqual(rec["session"], "bbbbbbbb")
        self.assertEqual(rec["req"], "REQ-써봄")
        self.assertIn("quit --mine", out)

    def test_z20_cli_is_wired(self):
        """회귀 — `s9 safaridriver ls` 가 실제 CLI 로 끝까지 돈다.

        판정 논리를 모듈에서 부르는 시험은 argparse 배선을 하나도 재지 않는다 —
        서브명령을 붙이는 것을 잊어도 전부 통과한다."""
        import subprocess
        import s9cli                                    # noqa: F401  (윈도우 진입점)
        out = subprocess.run([os.path.abspath(S9), "safaridriver", "ls"],
                             capture_output=True, text=True, timeout=60)
        both = out.stdout + out.stderr
        self.assertNotIn("Traceback", both)
        self.assertNotIn("invalid choice", both)
        if sys.platform == "darwin":
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertTrue(out.stdout.strip(), "아무 말도 하지 않았다")
        else:
            self.assertEqual(out.returncode, 2, out.stderr)
            self.assertIn("맥", out.stderr)

    def test_z21_skill_has_pairing_section(self):
        """회귀 — browser-verify 스킬에 「짝이 물렸을 때」와 푸는 한 줄이 있다."""
        for path in (SKILL, ROSTER):
            src = open(path, encoding="utf-8").read()
            self.assertIn("already paired", src, path)
            self.assertIn("s9 safaridriver quit --stale", src, path)
            self.assertIn("s9 safaridriver start", src, path)
            self.assertIn("한 번에 한 WebDriver 세션", src, path)

    def test_z23_session_end_reaps_this_sessions_drivers(self):
        """회귀 — SessionEnd 훅이 이 세션이 띄운 드라이버를 거둔다.

        「끝낼 때 quit --mine」은 스킬의 규율인데, 규율은 잊힌다 — 2026-09-16 의
        사고가 정확히 그 잊음이었다. 그래서 훅이 대신 부른다. `--mine` 이어야
        한다: 더 넓게 거두면 끝나는 세션이 남의 검증을 끊는다."""
        hook = open(os.path.join(HERE, "..", "bin", "s9-audit-session"),
                    encoding="utf-8").read()
        i = hook.index('if event == "end":')
        j = hook.index("\n    dual_warn", i)
        end_branch = hook[i:j]
        self.assertIn('"safaridriver", "quit", "--mine"', end_branch,
                      "SessionEnd 가 제 드라이버를 거두지 않는다")
        for wider in ('"--stale"', '"--all"', '"--force"'):
            self.assertNotIn(wider, end_branch,
                             f"끝나는 세션이 {wider} 로 남의 것까지 거둔다")

    def test_z22_section_is_the_same_in_source_and_output(self):
        """회귀 — 이 절이 원천(gen_roster.py)과 생성물(SKILL.md)에 글자 그대로 같이 있다.

        스킬은 생성물이라 직접 고치면 다음 생성에 사라지고, 원천만 고치면 생성을
        돌릴 때까지 아무에게도 안 보인다. 둘 중 한쪽만 고친 것을 생성기를 돌리지
        않고 여기서 잡는다. 파일 전체를 견주지 않는 것은 본문의 다른 절에
        역슬래시(`C:\\Temp\\…`)가 있어 소스 글자와 출력 글자가 원래 다르기
        때문이다 — 이 절에는 없다."""
        head = "## 맥 Safari 의 짝은 하나다"
        cuts = []
        for path in (ROSTER, SKILL):
            src = open(path, encoding="utf-8").read()
            i = src.find(head)
            self.assertGreater(i, -1, f"{path} 에 이 절이 없다")
            j = src.find("\n## ", i + len(head))
            cuts.append(src[i:j if j > -1 else len(src)])
        self.assertEqual(cuts[0], cuts[1],
                         "원천과 생성물의 이 절이 갈라졌다 — 한쪽만 고쳤다")
        self.assertIn("s9 safaridriver quit --stale", cuts[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
