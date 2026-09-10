"""맡기기가 켜진 컴퓨터인지가 저장소를 타고 보인다 (REQ-20260910-003-t8rc).

맡기기 스위치(`auto_resume`)는 그 컴퓨터의 `config/local.json` 에만 살고 그 파일은
저장소가 추적하지 않는다 — 무인 실행을 켜는 스위치라 그래야 한다(추적 파일에
살면 저장소에 push 할 수 있는 누구나 남의 컴퓨터에서 무인 실행을 켤 수 있다,
REQ-20260902-031). 그 자리가 맞는지를 이 요청이 다시 물었고, 답은 **그대로 두되
드러낸다** 였다.

실측 2026-09-10: 한 컴퓨터에는 그 값이 아예 없어 꺼짐이었고, 그 컴퓨터에 배정된
요청이 하나도 빠짐없이 조용히 걸러졌다. 배정하는 쪽에서는 그 사실을 볼 길이
없었다 — 담당 컴퓨터를 박는 것은 이쪽에서 하는데 그 컴퓨터가 일을 받을 수 있는지는
저쪽의 추적되지 않는 파일에만 있었기 때문이다.

그래서 **사실만** 내보낸다: 각 컴퓨터가 제 맡기기 켜짐/꺼짐을 등록부
(profile.md 의 `machine_accounts` 줄 · 추적됨)에 적고, 담당 컴퓨터를 고르는 창이
그것을 읽는다. 읽는 방향은 바뀌지 않는다 — 등록부의 값으로는 아무것도 켜지지
않는다.

화면 쪽 계약(고르는 창의 낱말·켬/끔을 묻는 자리가 하나뿐인지)은 그 화면의
시험이 진다 — test_assign_screen(고르는 창) · test_worker_settings(스위치 판).
여기서는 **불러서 값을 확인**한다.

실행: python3 tests/ machine_takes
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")


class MachineTakes(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9takes-")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_MACHINE": "boxA", "S9_USER": "alice"}
        self.env.pop("S9_SESSION", None)
        self._env0 = {k: os.environ.get(k)
                      for k in ("S9_ROOT", "S9_MACHINE", "S9_USER")}
        self.cli("init")
        self.cli("user", "add", "alice")

    def tearDown(self):
        for k, v in self._env0.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def cli(self, *argv, env=None, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env or self.env, timeout=30)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def profile_path(self, name="alice"):
        return os.path.join(self.root, "users", name, "profile.md")

    def rows(self, name="alice"):
        for ln in open(self.profile_path(name), encoding="utf-8"):
            if ln.startswith("machine_accounts:"):
                return json.loads(ln.split(":", 1)[1].strip())
        return []

    def row_of(self, machine, name="alice"):
        for r in self.rows(name):
            if r.get("machine") == machine:
                return r
        self.fail(f"등록부에 {machine} 줄이 없다")

    def write_rows(self, rows, name="alice"):
        """등록부를 손으로 고쳐 둔다 — 옛 줄(맡기기가 적히기 전)과 남이 밀어
        넣은 줄을 만드는 유일한 길이다."""
        p = self.profile_path(name)
        out = []
        for ln in open(p, encoding="utf-8"):
            out.append(f"machine_accounts: {json.dumps(rows, ensure_ascii=False)}\n"
                       if ln.startswith("machine_accounts:") else ln)
        open(p, "w", encoding="utf-8").writelines(out)

    def s9mod(self, machine="boxA"):
        """본체를 모듈로 읽어 함수를 직접 부른다 — 화면이 읽는 그 함수다.

        환경은 **부른 뒤에도 그대로 둔다**(tearDown 이 되돌린다) — 저장소 자리는
        읽을 때 굳지만 「여기가 어느 컴퓨터인가」는 부를 때마다 환경을 다시
        보기 때문이다. 먼저 되돌려 놓고 부르면 이 컴퓨터가 시험이 세운
        컴퓨터가 아니게 된다."""
        os.environ.update({"S9_ROOT": self.root, "S9_MACHINE": machine,
                           "S9_USER": "alice"})
        name = "s9takes" + re.sub(r"\W", "", self.root)[-16:] + machine
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    # N1. 켠 컴퓨터는 켜짐으로 실린다
    def test_n1_on_recorded(self):
        self.cli("user", "config", "alice", "auto_resume", "on")
        self.cli("user", "seen")
        self.assertIs(self.row_of("boxA").get("takes"), True)

    # N2. 켜지 않은 컴퓨터는 꺼짐으로 실린다 — 값이 아예 없는 것도 꺼짐이다
    def test_n2_off_recorded(self):
        self.cli("user", "seen")
        self.assertIs(self.row_of("boxA").get("takes"), False)

    # N3. 담당 컴퓨터를 고르는 목록(machine_table)이 그 값을 그대로 싣는다.
    #     여기서 boxA 는 **다른 컴퓨터**다 — 등록부로만 알 수 있는 자리.
    def test_n3_table_carries(self):
        self.cli("user", "config", "alice", "auto_resume", "on")
        self.cli("user", "seen")
        t = self.s9mod(machine="boxB").machine_table("alice")
        self.assertIs(t["boxA"]["takes"], True)

    # N4. 이 컴퓨터 줄은 등록부보다 **지금 설정**이 이긴다 — 방금 끈 것이
    #     곧바로 꺼짐으로 보여야 배정하는 사람이 헛짚지 않는다
    def test_n4_here_live_wins(self):
        self.cli("user", "config", "alice", "auto_resume", "on")
        self.cli("user", "seen")
        self.cli("user", "config", "alice", "auto_resume", "off")
        t = self.s9mod(machine="boxA").machine_table("alice")
        self.assertIs(t["boxA"]["takes"], False)

    # B1. 스위치를 바꾸면 줄이 늘지 않고 그 줄이 갱신된다
    def test_b1_switch_updates_same_row(self):
        self.cli("user", "seen")
        self.cli("user", "config", "alice", "auto_resume", "on")
        self.cli("user", "seen")
        rows = [r for r in self.rows() if r.get("machine") == "boxA"]
        self.assertEqual(len(rows), 1, "같은 컴퓨터가 두 줄이 됐다")
        self.assertIs(rows[0].get("takes"), True)

    # B2. 한 번도 적히지 않은 컴퓨터는 **모름**이다 — 없는 것을 꺼짐으로
    #     단정하면 화면이 거짓을 말한다
    def test_b2_unwritten_stays_unknown(self):
        self.cli("user", "seen")
        rows = self.rows()
        rows.append({"machine": "boxC", "os": "Linux", "account": "x",
                     "first": "2026-01-01T00:00:00+09:00",
                     "last": "2026-01-01T00:00:00+09:00"})
        self.write_rows(rows)
        t = self.s9mod(machine="boxA").machine_table("alice")
        self.assertIsNone(t["boxC"]["takes"])

    # F1. 추적 파일에 실려 온 스위치는 읽지 않는다 (회귀, REQ-20260902-031)
    def test_f1_tracked_switch_ignored(self):
        p = os.path.join(self.root, "users", "alice", "config", "settings.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump({"auto_resume": "on"}, open(p, "w", encoding="utf-8"))
        m = self.s9mod()
        self.assertFalse(m.auto_resume_on(m.user_config("alice")),
                         "추적 파일의 값으로 맡기기가 켜졌다")

    # F2. 등록부의 takes 는 **표시값**이다 — 손으로 켜도 아무것도 안 켜진다
    def test_f2_registry_is_display_only(self):
        self.cli("user", "seen")
        rows = self.rows()
        for r in rows:
            r["takes"] = True
        self.write_rows(rows)
        m = self.s9mod()
        self.assertFalse(m.auto_resume_on(m.user_config("alice")),
                         "등록부의 값으로 맡기기가 켜졌다")

    # B3. 켜짐으로 읽는 모양은 서버와 화면이 같은 목록이다 — 손으로 적은
    #     참값(`true`)을 한쪽만 켜짐으로 읽으면 화면과 실제가 갈린다
    def test_b3_same_shapes_both_sides(self):
        m = self.s9mod()
        for v in (True, "on", "ON", " true ", "1", "yes"):
            self.assertTrue(m.auto_resume_on({"auto_resume": v}), repr(v))
        for v in (None, "", "off", "false", "0", "no"):
            self.assertFalse(m.auto_resume_on({"auto_resume": v}), repr(v))

    # R3. 터미널에서 컴퓨터를 잘못 부르면 함께 뜨는 「아는 컴퓨터」 목록도
    #     같은 사실을 적는다 — 화면과 터미널이 다른 말을 하지 않는다
    def test_r3_cli_list_says_it(self):
        self.cli("user", "seen")                       # boxA — 맡기기 꺼짐
        m = self.s9mod(machine="boxB")
        with self.assertRaises(ValueError) as e:
            m.resolve_machine_name("없는컴퓨터", "alice")
        self.assertIn("맡기기 꺼짐", str(e.exception))


if __name__ == "__main__":
    unittest.main()
