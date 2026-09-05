"""계정 목록이 막다른 길이 되지 않는다 (REQ-20260827-079 라운드1 · 서버 몫).

두 번 반려된 자리다. 실측(2026-08-29 16:50)이 확정한 것:

**하나 — 목록이 고를 수 있는 줄을 0개로 만든다.** `account_rows` 의 중복 제거가
같은 메일의 프로필 줄을 통째로 `continue` 로 버렸다. 기본 계정(@home)이 먼저
`seen` 에 들어가므로 살아남는 것은 `current` 한 줄 + `ready:false` 두 줄이고,
화면의 `다시 시작` 은 영원히 비활성이다. 반대 방향(세션이 프로필로 떠 있을 때)은
같은 코드가 @home 줄을 지워 **돌아올 문**을 다시 닫았다.

**둘 — 조회가 자격증명을 지운다.** `account_settle` 의 `shutil.rmtree` 는 같은
메일이 두 자리에 있으면 새 자리를 통째로 지운다. 그 판정이 대시보드의 5초 폴
(`/api/chat/target` → `account_rows`)에서도 돌아, **로그인 중인 프로필이 살아 있는
채로 사라진다.** 지우는 판단이 틀리면 사용자는 로그인을 잃는다 — 되돌릴 수 없다.

**셋 — 로그인 전 자리를 지울 길이 없다.** `POST /api/account/remove` 는 404 고
`s9 account remove` 도 없다. 그리고 붙이는 순간 `safe_name('..') == '..'` 이라
프로필 루트 밖이 사정권에 든다.

실행: python3 tests/ account_merge
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


def _load(name="s9merge"):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _login(d, email):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, ".claude.json"), "w", encoding="utf-8") as f:
        json.dump({"oauthAccount": {"emailAddress": email}}, f)
    with open(os.path.join(d, ".credentials.json"), "w", encoding="utf-8") as f:
        f.write("{}")


def _fingerprint(root):
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out[os.path.relpath(p, root)] = (st.st_mtime_ns, st.st_size)
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.m = _load()
        self.tmp = tempfile.mkdtemp(prefix="s9merge-")
        self.home = os.path.join(self.tmp, "home")
        self.base = os.path.join(self.tmp, "profiles")
        os.makedirs(self.home)
        os.makedirs(self.base)
        _login(self.home, "first@ex.com")
        self.m.profiles_base = lambda: self.base
        self.m.claude_home = lambda: self.home
        # `@home` 의 자리는 이제 `account_home_dir` 이 정한다
        # (REQ-20260901-017 R6): 서버가 물려받은 CLAUDE_CONFIG_DIR 에 흔들리던
        # 뜻을 래퍼와 같게(언제나 ~/.claude) 못 박은 자리라, 무대의 '집'도
        # 그쪽으로 세운다.
        self.m.account_home_dir = lambda: self.home
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def prof(self, name):
        return os.path.join(self.base, name)


class ARowStaysSelectable(Base):
    """A1~A3 — 지우지 말고 합치되, 고를 수 있게."""

    def test_a1_duplicate_account_keeps_one_selectable_row(self):
        """같은 메일이 두 자리에 있어도 고를 수 있는 줄이 남는다.

        실측: @home(claude02, current) + 프로필(claude02) → 종전 코드는 프로필
        줄을 버려 ready && !current 가 0개가 됐다. 그 0이 화면의 영구 비활성
        버튼이다."""
        _login(self.prof("first@ex.com"), "first@ex.com")
        _login(self.prof("second@ex.com"), "second@ex.com")
        rows = self.m.account_rows()
        same = [r for r in rows if r["email"] == "first@ex.com"]
        self.assertEqual(len(same), 1, "한 계정은 한 줄이다")
        self.assertTrue(same[0].get("also"),
                        "합친 줄이 다른 자리를 말하지 않는다 (also 없음)")
        self.assertEqual(self.m.account_switchable(rows), 1,
                         "고를 수 있는 줄이 없다 — 창이 막다른 길이 된다")

    def test_a2_home_row_survives_when_session_is_on_a_profile(self):
        """돌아올 문 — 세션이 프로필로 떠 있어도 @home 줄은 사라지지 않는다.

        @home 은 메일이 아니라 'CLAUDE_CONFIG_DIR 미설정'을 뜻하는 유일한 키라
        다른 디렉토리와 교환 가능하지 않다."""
        p = self.prof("first@ex.com")
        _login(p, "first@ex.com")
        rows = self.m.account_rows(cfg_dir=p)
        self.assertIn(self.m.ACCOUNT_HOME_KEY, [r["key"] for r in rows],
                      "프로필로 떠 있으니 기본 계정이 목록에서 사라졌다")
        self.assertEqual(sum(1 for r in rows if r["current"]), 1)

    def test_a3_switchable_count_is_reported(self):
        """0이면 화면이 그 사실을 말할 수 있어야 한다 — 셈은 서버가 한다."""
        self.assertEqual(self.m.account_switchable(self.m.account_rows()), 0)
        _login(self.prof("second@ex.com"), "second@ex.com")
        self.assertEqual(self.m.account_switchable(self.m.account_rows()), 1)
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.find('elif parsed.path == "/api/accounts"')
        self.assertGreater(i, 0)
        self.assertIn("switchable", src[i:i + 600],
                      "/api/accounts 가 고를 수 있는 줄 수를 싣지 않는다")


class SettleNeverDeletes(Base):
    """A4~A6 — 조회가 로그인을 지우지 않는다."""

    def test_a4_settle_does_not_delete_credentials(self):
        """중복이라고 판단해도 지우지 않는다 — 판단이 틀리면 되돌릴 수 없다."""
        _login(self.prof("dup@ex.com"), "dup@ex.com")
        stale = self.prof("새-계정-2")
        _login(stale, "dup@ex.com")
        final = self.m.account_settle(stale)
        self.assertEqual(os.path.basename(final), "dup@ex.com")
        self.assertFalse(os.path.isdir(stale), "옛 자리 이름이 목록에 남는다")
        parked = os.path.join(self.base, ".dup")
        found = []
        for dp, _d, fs in os.walk(parked):
            found += [os.path.join(dp, f) for f in fs
                      if f == ".credentials.json"]
        self.assertTrue(found, "자격증명이 사라졌다 — settle 이 지웠다")

    def test_a4b_no_rmtree_in_settle(self):
        """경위는 docstring 에 남아도 좋다 — 코드에 남으면 안 된다."""
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.find("def account_settle(")
        j = src.find("\ndef ", i + 10)
        body = src[i:j].split('"""')[-1]
        self.assertTrue(body.strip(), "함수 본문을 못 찾았다")
        self.assertNotIn("rmtree", body,
                         "account_settle 이 아직 프로필을 통째로 지운다")

    def test_a5_live_profile_is_never_touched(self):
        """살아 있는 claude 의 설정 디렉토리를 발밑에서 빼지 않는다."""
        _login(self.prof("dup@ex.com"), "dup@ex.com")
        live = self.prof("새-계정-3")
        _login(live, "dup@ex.com")
        p = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            env={**os.environ, "CLAUDE_CONFIG_DIR": live},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(p.kill)
        time.sleep(0.3)
        self.assertTrue(self.m.profile_in_use(live),
                        "살아 있는 프로세스를 못 본다")
        before = _fingerprint(live)
        self.m.account_rows()
        self.assertTrue(os.path.isdir(live), "살아 있는 프로필을 옮겼다/지웠다")
        self.assertEqual(_fingerprint(live), before)

    def test_a6_polling_path_is_read_only(self):
        """5초 폴(/api/chat/target)은 파일시스템을 변형하지 않는다."""
        stale = self.prof("새-계정-9")
        _login(stale, "poll@ex.com")
        before = _fingerprint(self.base)
        self.m.account_rows(settle=False)
        self.assertEqual(_fingerprint(self.base), before,
                         "조회가 디렉토리를 바꿨다")
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.find('elif parsed.path == "/api/chat/target"')
        j = src.find('elif parsed.path == "/api/accounts"', i)
        self.assertIn("settle=False", src[i:j],
                      "채팅 대상 폴이 아직 settle 을 돌린다")


class RemoveIsGuarded(Base):
    """A7~A8 — 로그인 전 자리만, 그리고 프로필 루트 안에서만."""

    def test_a7_removes_a_pre_login_slot(self):
        os.makedirs(self.prof("새-계정"))
        r = self.m.account_remove("새-계정")
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(r.get("action"), "removed")
        self.assertFalse(os.path.isdir(self.prof("새-계정")))

    def test_a7b_refuses_a_logged_in_slot(self):
        _login(self.prof("second@ex.com"), "second@ex.com")
        r = self.m.account_remove("second@ex.com")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("action"), "logged-in")
        self.assertTrue(r.get("message"), "거부에 사유가 없다")
        self.assertTrue(os.path.isdir(self.prof("second@ex.com")))

    def test_a7c_refuses_a_slot_a_live_session_is_using(self):
        live = self.prof("새-계정-4")
        os.makedirs(live)
        p = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            env={**os.environ, "CLAUDE_CONFIG_DIR": live},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(p.kill)
        time.sleep(0.3)
        r = self.m.account_remove("새-계정-4")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("action"), "in-use")
        self.assertTrue(os.path.isdir(live))

    def test_a8_path_escape_is_refused(self):
        """safe_name('..') == '..' — 붙이는 순간 홈 전체가 사정권에 든다."""
        for bad in ("..", ".", "../..", "a/b", "", "  ", "~"):
            r = self.m.account_remove(bad)
            self.assertFalse(r.get("ok"), f"{bad!r} 를 받아들였다")
            self.assertIn(r.get("action"), ("bad-name", "outside", "not-found"),
                          f"{bad!r} → {r}")
        self.assertTrue(os.path.isdir(self.home), "기본 계정 자리가 사라졌다")
        self.assertTrue(os.path.isdir(self.base))

    def test_a8b_symlink_is_refused(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        link = self.prof("링크")
        os.symlink(outside, link)
        r = self.m.account_remove("링크")
        self.assertFalse(r.get("ok"), r)
        self.assertTrue(os.path.isdir(outside), "링크 너머를 지웠다")

    def test_a8c_api_and_cli_both_exist(self):
        src = open(S9_SRC, encoding="utf-8").read()
        self.assertTrue("/api/account/remove" in src, "제거 API 가 없다")
        i = src.find("def cmd_account(")
        self.assertGreater(i, 0)
        self.assertIn("remove", src[i:i + 4000], "s9 account remove 가 없다")


class GoingHomeClearsTheEnv(unittest.TestCase):
    """A9 — @home 으로 돌아가는데 프로필이 상속되면 조용히 무효가 된다."""

    def test_a9_restart_loop_pops_the_config_dir(self):
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.find("m = _consume_restart_marker()")
        self.assertGreater(i, 0)
        blk = src[i:i + 1600]
        self.assertIn("CLAUDE_CONFIG_DIR", blk,
                      "@home 을 골라도 래퍼의 CLAUDE_CONFIG_DIR 이 그대로 "
                      "상속된다 — 기본 계정 복귀가 조용히 무효가 된다")


class TheServerSpeaksPolitelyHere(unittest.TestCase):
    """계정 지우기의 message 는 그대로 팝업이 된다 — 반말이 새면 화면이 반말을
    한다 (REQ-20260901-018 실사고: 「새 계정을 삭제할 때 팝업에서 갑자기 반말을
    한다」). 화면은 이유를 짓지 않는 계약이라, 존대는 서버 문장의 몫이다.

    갈래를 다 띄우기엔 무대가 비싸니 **원문**에서 잰다: account_remove 함수 안의
    모든 message 문장이 존대 어미로 끝난다."""

    def test_every_remove_message_ends_politely(self):
        s9 = os.path.join(HERE, "..", "bin", "s9.py")
        with open(s9, encoding="utf-8") as f:
            src = f.read()
        i = src.index("def account_remove(")
        body = src[i:src.index("\ndef ", i + 10)]
        import re as _re
        msgs = _re.findall(r'"message":\s*f?"([\s\S]*?)"\}', body)
        self.assertGreaterEqual(len(msgs), 8, "message 갈래를 못 읽었다")
        for m in msgs:
            sent = m.replace('"\n                           f"', "") \
                    .replace('"\n                           "', "")
            tailbit = sent.split("—")[-1].strip().rstrip(".").split(":")[0]
            self.assertRegex(
                tailbit, r"(습니다|입니다|니다|세요|\{e\}|\{safe\})\s*$",
                "반말이 팝업으로 샌다: %r" % sent)


if __name__ == "__main__":
    unittest.main()
