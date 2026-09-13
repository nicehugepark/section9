"""설정은 화면에 다 있어야 한다 — user config 키 전수 대장 (REQ-20260911-005-62x6).

주인 2026-09-11: 「명령어는 사실상 거의 쓰지 않는다. 명령어로 만들어진 것들
대부분 대시보드에서 설정으로 제공되어야 한다.」

한 번 세어서 답하고 끝나면 다음 키가 늘 때 같은 자리에서 또 넘어진다. 그래서
이 파일은 답이 아니라 **대장**이다: 코드가 읽는 user config 키를 한 줄씩
분류해 적고, 분류가 사실과 어긋나면 실패한다.

이 시험이 지키는 계약 넷:

  ① **대장에 없는 키를 코드가 읽으면 실패한다.** 새 설정을 만들면서 화면을
     잊는 것이 이 요청이 없애려는 증상이다 — 잊으면 여기서 걸린다.
  ② **`screen` 으로 적은 키는 그 화면에 이름과 함께 실제로 있다.** 대장만
     고치고 화면을 안 고치면 대장이 거짓말이 된다.
  ③ **두 번 서지 않는다.** 이름 붙은 행을 얻은 키는 「내 계정」의 `그 밖의 값`
     표에서 빠진다. 같은 값이 두 자리에 서면 어느 쪽이 참인지 화면이 말하지
     못한다 — 이 시험이 생기기 전에 jira 넷이 실제로 두 번 서 있었다.
  ④ **자리를 안 준 키에는 사유가 붙는다.** 사유 없는 `none` 은 대장에서
     거절한다(goal 이 요구한 「없는 것은 왜 없는지가 문서에 적힌다」).

실행: python3 tests/ config_on_screen
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web", "app")
S9_SRC = os.path.join(ROOT, "bin", "s9.py")   # bin/s9 는 발사대다


def find_node():
    """node 를 찾는다 — 없으면 실행으로 재는 항목만 건너뛴다.

    시험 파일은 표준 라이브러리 밖을 import 하지 않는다
    (tests/test_stdlib_only.py) — 그래서 이 몇 줄이 파일마다 산다."""
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


def _src(name):
    with open(os.path.join(WEB, name), encoding="utf-8") as f:
        return f.read()


# ─────────────────────────────────────────────────────────────────────────
# 대장 — (키, 자리, 사유). 자리는 화면의 판 이름이고, `none` 은 아직 이름 붙은
# 행이 없다는 뜻이다. `machine` 은 사람이 정하는 값이 아니라 **기계가 적어 두는
# 값**이라 설정 행을 주지 않는다 — 그것도 사유와 함께 적는다.
# ─────────────────────────────────────────────────────────────────────────
DISPLAY = "display"      # Settings → 디스플레이
ACCOUNT = "account"      # Settings → 내 계정
WORKER = "worker"        # Settings → 백그라운드 작업
JIRA = "jira"            # Settings → 외부 서비스
SYNC = "sync"            # Settings → 저장소 → 문서 동기화
MACHINE = "machine"      # 기계가 적는 값 — 설정 행 없음
NONE = "none"            # 아직 이름 붙은 행이 없다

ROSTER = {
    # ── 디스플레이 ──────────────────────────────────────────────────────
    "ui_skin": (DISPLAY, ""),
    "ui_tone": (DISPLAY, ""),
    "ui_density": (DISPLAY, ""),
    "timezone": (DISPLAY, ""),
    # ── 내 계정 ─────────────────────────────────────────────────────────
    "stream_mirror": (ACCOUNT, ""),
    "stream_keep_days": (ACCOUNT, ""),
    "digest_budget": (ACCOUNT, ""),
    "external_secrets_path": (ACCOUNT, ""),
    # ── 백그라운드 작업 ─────────────────────────────────────────────────
    "auto_resume": (WORKER, ""),
    "auto_resume_apply": (WORKER, ""),
    "auto_resume_gh": (WORKER, ""),
    "auto_resume_jira": (WORKER, ""),
    "worker_worktree": (WORKER, ""),
    "auto_resume_model": (WORKER, ""),
    "s9code_args": (WORKER, ""),
    "code_autoupdate": (WORKER, ""),
    "auto_resume_grace_sec": (WORKER, ""),
    "auto_resume_abandon_sec": (WORKER, ""),
    "auto_resume_cooldown_sec": (WORKER, ""),
    "auto_resume_max_inflight": (WORKER, ""),
    "auto_resume_wake_per_hour": (WORKER, ""),
    "auto_resume_wake_per_day": (WORKER, ""),
    "auto_resume_global_per_hour": (WORKER, ""),
    "auto_resume_global_per_day": (WORKER, ""),
    "auto_resume_rush_reserve": (WORKER, ""),
    # ── 외부 서비스 ─────────────────────────────────────────────────────
    "jira_enabled": (JIRA, ""),
    "jira_site": (JIRA, ""),
    "jira_email": (JIRA, ""),
    "jira_token_expires": (JIRA, ""),
    # ── 저장소 → 문서 동기화 ────────────────────────────────────────────
    "sync_alert_after": (SYNC, ""),
    "sync_request_after": (SYNC, ""),
    # ── 기계가 적는 값 ──────────────────────────────────────────────────
    "machine_fp": (
        MACHINE,
        "이 컴퓨터를 가르는 지문이다 — 처음 쓸 때 한 번 계산해 고정하고, "
        "사람이 고를 것이 없다. 설정 행을 주면 고쳐도 되는 값으로 읽힌다."),
    "last_model_choice": (
        MACHINE,
        "모델 창에서 방금 고른 것을 기억해 두는 자리다. 정책은 "
        "`auto_resume_model`·`s9code_args` 가 지고, 이것은 그 창의 1회 선택이다."),
    "jira_account_id": (
        MACHINE,
        "「연결 확인」이 Jira 에서 받아 적어 둔 계정 id 다 — 사람이 아니라 "
        "연결 확인이 채운다."),
    # ── 아직 이름 붙은 행이 없다 ────────────────────────────────────────
    "observe": (
        NONE,
        "admin 이 viewer 에게 주는 관찰 범위다 — 자리는 「사용자 관리」의 "
        "계정 편집 판인데 그 판은 일괄 저장이라, 즉시 저장 부품을 먼저 옮겨야 "
        "한다. 그때까지는 「그 밖의 값」 표에서 바꾼다."),
    "observe_until": (
        NONE,
        "위 관찰 범위의 만료일이다 — 같은 자리에 함께 선다."),
    "jira_auth": (
        NONE,
        "Jira 인증 방식(basic·bearer)이다. 기본값 basic 으로 모든 Atlassian "
        "Cloud 가 통해 아직 고를 일이 없었다 — bearer 를 쓰는 설치가 나오면 "
        "「외부 서비스」 판에 선다. 그때까지는 「그 밖의 값」 표에서 바꾼다."),
    "default_project": (
        NONE,
        "초대 명령(`s9 code --join <url> --project <slug>`)이 합류한 사람의 프로젝트로 "
        "적어 두고 다음 `s9 code` 가 세션의 프로젝트로 읽는다(REQ-20260913-013). 자리는 "
        "프로젝트 판(참여 프로젝트 목록)인데 그 판은 REQ-20260913-012 가 짓는 중이다. "
        "그때까지는 「그 밖의 값」 표에서 바꾼다."),
}

# 이름 붙은 행을 얻은 자리 — 이 자리의 키는 「그 밖의 값」에서 빠져야 한다.
PLACED = {DISPLAY, ACCOUNT, WORKER, JIRA, SYNC}


# ─────────────────────────────────────────────────────────────────────────
# 화면 원문에서 (키 → 이름) 을 실제로 떼어 온다 — 글자로 박아 두지 않는다.
# ─────────────────────────────────────────────────────────────────────────
def _chunk(src, head, tail):
    """`head` 로 시작해 처음 만나는 `tail` 까지 — 선언 하나를 통째로 뗀다."""
    m = re.search(re.escape(head) + r"[\s\S]*?" + re.escape(tail), src)
    assert m, "원문 조각을 찾지 못했다: %s" % head
    return m.group(0)


def _node(js):
    node = find_node()
    out = subprocess.run([node, "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _panel_rows():
    """세 판이 세우는 행의 (키, 이름) 전부 — node 로 그 목록을 그대로 읽는다."""
    w = _src("workercfg.js")
    j = _src("jira.js")
    r = _src("repo.js")
    js = "\n".join([
        _chunk(w, "const WCFG_SWITCHES = [", "];"),
        _chunk(w, "const WCFG_TEXTS = [", "];"),
        _chunk(w, "const WCFG_CAPS = [", "];"),
        _chunk(j, "const JIRA_ROWS = [", "];"),
        _chunk(j, "const JIRA_SWITCH = {", "};"),
        _chunk(r, "const SYNC_CAPS = [", "];"),
        "const out = {};",
        "for (const r of [].concat(WCFG_SWITCHES, WCFG_TEXTS, WCFG_CAPS))"
        "  out[r.key] = r.name;",
        "for (const r of JIRA_ROWS.concat([JIRA_SWITCH]))"
        "  if (r.kind !== 'ping') out[r.key] = r.name;",
        "for (const r of SYNC_CAPS) out[r.key] = r.name;",
        "console.log(JSON.stringify(out));",
    ])
    return _node(js)


def _extra_cfg(cfg):
    """「내 계정」의 `그 밖의 값` 표가 실제로 무엇을 남기는가 — 그 식을 실행한다."""
    u = _src("userform.js")
    w = _src("workercfg.js")
    j = _src("jira.js")
    r = _src("repo.js")
    m = re.search(r"const extraCfg = Object\.entries\(cfg\)[\s\S]*?;\n", u)
    assert m, "userform.js 에서 extraCfg 식을 찾지 못했다"
    js = "\n".join([
        _chunk(w, "const WCFG_SWITCHES = [", "];"),
        _chunk(w, "const WCFG_TEXTS = [", "];"),
        _chunk(w, "const WCFG_CAPS = [", "];"),
        _chunk(w, "const WCFG_KEYS = [].concat(", ");"),
        re.search(r"^const wcfgMine = .*?;$", w, re.M).group(0),
        _chunk(j, "const JIRA_ROWS = [", "];"),
        _chunk(j, "const JIRA_SWITCH = {", "};"),
        _chunk(j, "const JIRA_CFG_KEYS = ", ";"),
        _chunk(r, "const SYNC_CAPS = [", "];"),
        re.search(r"^const SYNC_CAP_KEYS = .*?;$", r, re.M).group(0),
        "const cfg = %s;" % json.dumps(cfg),
        m.group(0),
        "console.log(JSON.stringify(extraCfg.map(x => x[0])));",
    ])
    return _node(js)


# 코드가 user config 를 읽는 자리 — 받는 이름이 `cfg`·`ucfg`·`conf` 인 것만
# 본다. 넓게 훑으면 문서 필드(`row.get("status")`)까지 딸려 와 대장이 소음으로
# 찬다 — 좁게 보되 **걸린 것은 반드시 대장에 있어야 한다**로 쓴다.
CFG_GET_RE = re.compile(
    r'\b(?:cfg|ucfg|conf)\.get\(\s*"([a-z][a-z0-9_]*)"')


class TheRosterItself(unittest.TestCase):
    """④ 대장의 모양 — 사유 없는 빈자리를 허용하지 않는다."""

    def test_every_unplaced_key_says_why(self):
        """정상 — 자리를 안 준 키에는 사유가 붙는다."""
        for key, (where, why) in ROSTER.items():
            if where in (MACHINE, NONE):
                self.assertTrue(
                    why.strip(),
                    "%s 는 화면에 자리가 없는데 왜 없는지가 대장에 없다" % key)

    def test_placed_keys_do_not_carry_an_excuse(self):
        """경계 — 자리가 있는 키에 사유를 적으면 대장이 두 말을 한다."""
        for key, (where, why) in ROSTER.items():
            if where in PLACED:
                self.assertEqual(
                    "", why, "%s 는 화면에 자리가 있는데 사유가 붙어 있다" % key)


class WhatTheCodeReads(unittest.TestCase):
    """① 대장에 없는 키를 코드가 읽으면 실패한다."""

    def test_no_key_escapes_the_roster(self):
        """회귀 — 새 설정을 만들면서 화면을 잊으면 여기서 걸린다."""
        with open(S9_SRC, encoding="utf-8") as f:
            found = set(CFG_GET_RE.findall(f.read()))
        missing = sorted(k for k in found if k not in ROSTER)
        self.assertEqual(
            [], missing,
            "코드가 읽는데 대장에 없는 user config 키: %s — "
            "tests/test_config_on_screen.py 의 ROSTER 에 자리(또는 사유)를 "
            "적어라" % ", ".join(missing))


@unittest.skipUnless(find_node(), "node 없음 — 화면 조각을 실행할 수 없다")
class WhatTheScreenStands(unittest.TestCase):
    """② `screen` 으로 적은 키는 그 화면에 이름과 함께 실제로 있다."""

    def setUp(self):
        self.rows = _panel_rows()

    def test_panel_keys_have_a_korean_name(self):
        """정상 — 세 판(백그라운드 작업·외부 서비스·문서 동기화)의 행 전수."""
        for key, (where, _why) in ROSTER.items():
            if where not in (WORKER, JIRA, SYNC):
                continue
            self.assertIn(key, self.rows,
                          "%s 는 대장이 %s 라 적었는데 그 판에 행이 없다"
                          % (key, where))
            name = self.rows[key]
            self.assertTrue(name and name.strip(),
                            "%s 에 이름이 없다 — 키 이름만으로는 뜻이 안 선다" % key)
            self.assertRegex(
                name, r"[가-힣]",
                "%s 의 이름(%s)에 우리 말이 한 자도 없다" % (key, name))

    def test_the_two_sync_caps_stand_in_the_repo_panel(self):
        """정상 — 이 요청이 세운 둘이 저장소 판에 있다."""
        r = _src("repo.js")
        self.assertIn("sync_alert_after", r)
        self.assertIn("sync_request_after", r)
        # 판 안에서 「문서 동기화」 절 뒤에 선다 — 모드 옆이 그 자리다.
        i = r.index("문서 동기화")
        self.assertGreater(r.index("SYNC_CAPS", i), i,
                           "동기화 값이 「문서 동기화」 절과 이어져 있지 않다")

    def test_the_two_sync_caps_say_where_they_are_saved(self):
        """경계 — 한 표에 저장 자리가 둘이다. 안 적으면 그 표가 거짓말을 한다."""
        r = _src("repo.js")
        chunk = _chunk(r, "const SYNC_CAPS = [", "];")
        self.assertEqual(
            2, chunk.count("내 계정에만 적용됩니다"),
            "동기화 두 값이 저장 자리(내 계정)를 말하지 않는다 — "
            "바로 위 모드 행은 저장소 전체의 값이다")

    def test_defaults_are_the_ones_the_code_uses(self):
        """경계 — 빈 칸이 뜻하는 기본값이 코드와 같다(3회·10회)."""
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        chunk = _chunk(_src("repo.js"), "const SYNC_CAPS = [", "];")
        for key, default in (("sync_alert_after", "3"),
                             ("sync_request_after", "10")):
            self.assertRegex(
                chunk, re.escape(key) + r'[\s\S]*?def: "%s"' % default,
                "%s 의 화면 기본값이 %s 가 아니다" % (key, default))
            self.assertRegex(
                src, r"def %s\(cfg=None\)" % key,
                "%s 를 읽는 함수가 코드에 없다" % key)

    def test_an_opt_out_switch_reads_empty_as_on(self):
        """실패 자리 — 값이 없는 계정에서 화면과 코드가 갈리면 안 된다.

        `code_autoupdate` 는 **끄는 스위치**다: 값이 없으면 코드는 받으러
        간다. 다른 행의 규칙(빈 값 = 끔)을 그대로 쓰면 화면은 「끔」이라
        적는데 창을 열 때마다 업데이트를 확인한다 — 실제로 그랬다."""
        w = _src("workercfg.js")
        js = "\n".join([
            re.search(r"^const wcfgOn = [\s\S]*?;$", w, re.M).group(0),
            re.search(r"^const wcfgOff = [\s\S]*?;$", w, re.M).group(0),
            re.search(r"^const wcfgRowOn = [\s\S]*?;$", w, re.M).group(0),
            _chunk(w, "const WCFG_SWITCHES = [", "];"),
            "const r = WCFG_SWITCHES.find(x => x.key === 'code_autoupdate');",
            "console.log(JSON.stringify("
            "  [{}, {code_autoupdate: 'off'}, {code_autoupdate: 'on'}]"
            "    .map(c => wcfgRowOn(r, c))));",
        ])
        self.assertEqual(
            [True, False, True], _node(js),
            "빈 값 = 켬 이어야 한다 — 코드(`_maybe_update_claude`)가 "
            "`off`·`0`·`false` 만 끔으로 읽는다")
        # 코드 쪽 목록이 바뀌면 화면도 함께 바뀌어야 한다.
        with open(S9_SRC, encoding="utf-8") as f:
            self.assertIn('("off", "0", "false")', f.read(),
                          "코드가 보는 끔 목록이 바뀌었다 — 화면의 "
                          "`wcfgOff` 도 함께 고쳐라")

    def test_my_window_rows_do_not_hang_on_the_master_switch(self):
        """경계 — 「내 창」의 행은 맡기기를 꺼도 흐려지지 않는다.

        `s9 code` 로 여는 창은 백그라운드 작업과 무관하다 — 잠그면 멀쩡한
        설정을 못 고친다."""
        w = _src("workercfg.js")
        self.assertRegex(
            w, r"const wcfgGated = WCFG_SWITCHES\.filter\("
               r"r => !r\.master && !r\.free\);",
            "맡기기에 딸리는 스위치를 고르는 자리가 없다 — "
            "`slice(1)` 로 자르면 「내 창」의 행까지 잠긴다")
        self.assertNotIn(
            "WCFG_SWITCHES.slice(1)", w,
            "아직 순서로 자르고 있다 — 행 하나가 늘면 엉뚱한 행이 잠긴다")


@unittest.skipUnless(find_node(), "node 없음 — 화면 조각을 실행할 수 없다")
class NothingStandsTwice(unittest.TestCase):
    """③ 이름 붙은 행을 얻은 키는 「그 밖의 값」에 두 번 서지 않는다."""

    def test_placed_keys_leave_the_leftover_table(self):
        """회귀 — 네 판이 세우는 키 전수가 그 표에서 빠진다."""
        cfg = {k: "x" for k in ROSTER}
        left = set(_extra_cfg(cfg))
        twice = sorted(k for k, (w, _) in ROSTER.items()
                       if w in PLACED and k in left)
        self.assertEqual(
            [], twice,
            "제 행과 「그 밖의 값」에 두 번 서는 키: %s" % ", ".join(twice))

    def test_unplaced_keys_stay_visible(self):
        """경계 — 자리를 못 얻은 값은 **숨기지 않는다**.

        「그 밖의 값」이 그 자리다: 이름은 없어도 화면에서 바꿀 수는 있다.
        빼 버리면 명령어로만 되는 설정이 다시 생긴다."""
        cfg = {k: "x" for k in ROSTER}
        left = set(_extra_cfg(cfg))
        for key, (where, _why) in ROSTER.items():
            if where in (MACHINE, NONE):
                self.assertIn(
                    key, left,
                    "%s 가 화면에서 사라졌다 — 이름이 없는 것과 "
                    "자리가 없는 것은 다른 일이다" % key)
