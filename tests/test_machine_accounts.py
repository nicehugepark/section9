"""어느 머신에서 어느 계정으로 일했는지 (REQ-20260827-066-62x6).

사용자: "개인설정에서 접속하는 혹은 사용하는 머신의 이력, 사용하는 머신별
리눅스나 macOS의 계정 정보를 같이 기록하게 해줘."

`os_accounts` 와 `machines` 는 각각 납작한 목록이라 **둘을 짝지을 수 없다** —
머신이 셋이고 계정이 둘이면 어느 쌍이 실제였는지 알 수 없다. 계정 이름을 바꿔
보고 나서야 이 짝이 신원 판정의 실제 근거임이 드러났다(REQ-20260827-060:
짝을 못 이어서 자기 문서가 하나도 안 보였다).

처음 본 때와 마지막으로 본 때를 함께 둔다 — 목록만 있으면 "지금도 쓰는 머신"과
"한 번 스쳐간 머신"이 같아 보인다.

손으로 attach 할 때만 남기면 기록이 늘 뒤처진다. 세션이 시작될 때 스스로 적는다.

실행: python3 tests/ machine_accounts
"""
import getpass
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-session")


class MachineAccounts(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9mach-")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_MACHINE": "boxA", "S9_USER": "alice"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "alice")

    def cli(self, *argv, env=None, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env or self.env, timeout=30)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def rows(self, name="alice"):
        p = os.path.join(self.root, "users", name, "profile.md")
        for ln in open(p, encoding="utf-8"):
            if ln.startswith("machine_accounts:"):
                return json.loads(ln.split(":", 1)[1].strip())
        return []

    # N1. 머신·OS 계정·운영체제가 한 줄로 묶여 남는다
    def test_n1_pair_recorded(self):
        self.cli("user", "seen")
        r = self.rows()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["machine"], "boxA")
        # 계정은 **로그인한 운영체제 계정**이다 (하네스 이름 alice 가 아니다)
        self.assertEqual(r[0]["account"], getpass.getuser())
        self.assertTrue(r[0]["os"], "운영체제가 비어 있다")
        self.assertTrue(r[0]["first"] and r[0]["last"])

    # N2. 머신이 늘면 줄이 는다 — 머신마다 한 줄이다
    def test_n2_second_machine(self):
        self.cli("user", "seen")
        self.cli("user", "seen", "alice",
                 env={**self.env, "S9_MACHINE": "boxB"})
        me = getpass.getuser()
        pairs = {(x["machine"], x["account"]) for x in self.rows()}
        self.assertEqual(pairs, {("boxA", me), ("boxB", me)})

    # B1. 같은 짝을 또 보면 줄이 늘지 않고 마지막 시각만 바뀐다
    def test_b1_same_pair_updates(self):
        self.cli("user", "seen")
        first = self.rows()[0]["first"]
        self.cli("user", "seen")
        r = self.rows()
        self.assertEqual(len(r), 1, "같은 짝이 두 줄이 됐다")
        self.assertEqual(r[0]["first"], first, "처음 본 때가 덮였다")

    # B3. S9_USER 는 하네스 신원을 갈아 끼우는 스위치지 로그인한 계정이 아니다
    #     (REQ-20260827-066 반려). 이 표의 뜻이 "어느 머신에 어느 **OS 계정**으로
    #     로그인해 일했나" 이므로 여기서 하네스 이름이 섞이면 표가 통째로 거짓이
    #     된다 — 실제로 리드가 커밋할 때 쓰던 S9_USER 가 없는 계정 한 줄을 만들었다.
    def test_b3_s9_user_does_not_leak_into_account(self):
        self.cli("user", "seen", "alice",
                 env={**self.env, "S9_USER": "가짜하네스이름"})
        accts = {x["account"] for x in self.rows()}
        self.assertIn(getpass.getuser(), accts)
        self.assertNotIn("가짜하네스이름", accts,
                         "하네스 이름이 OS 계정 자리에 들어갔다")

    # B2. 미등록 이름은 거부한다
    def test_b2_unknown_refused(self):
        self.cli("user", "seen", "ghost", expect=1)

    # N3. 세션 시작이 스스로 적는다 — 손으로 할 때만 남기면 늘 뒤처진다
    def test_n3_session_start_records(self):
        src = open(HOOK, encoding="utf-8").read()
        i = src.index("ensure_serve()  #")
        self.assertIn('"seen"', src[i:i + 700],
                      "세션 시작이 머신·계정을 적지 않는다")

    # N4. 화면이 읽을 수 있게 실려 나간다
    def test_n4_served(self):
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index('parsed.path == "/api/users"')
        self.assertIn("machine_accounts", src[i:i + 2000],
                      "사용자 API 에 머신 이력이 없다")

    # R1. 기존 os_accounts 는 그대로 — 신원 판정이 그것을 쓴다
    def test_r1_os_accounts_kept(self):
        self.cli("user", "seen")
        p = os.path.join(self.root, "users", "alice", "profile.md")
        self.assertIn("os_accounts:", open(p, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
