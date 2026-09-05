"""비밀 바깥 경로 칸 (REQ-20260828-017-62x6).

사용자(14:16): "external_secrets_path 계정 설정값이면 settings 화면에 있어야하는데
안보이는데?"

REQ-20260828-012 는 비밀 키 목록을 화면에 냈지만 **바깥 경로를 정하는 칸은 안 냈다.**
그래서 012 가 제기한 문제("CLI 에만 있으면 없는 기능")가 이 한 칸에 그대로 남았다.

이 파일이 지키는 것은 두 가지다.

  ① **없으면 만든다.** 사용자(14:2x): "디렉토리가 없으면 만들면 되는 것 아닌가?"
     맞다 — 없다고 말만 하고 두면 사람이 터미널로 나갔다 돌아와야 한다. 경로를
     저장하면 그 자리에서 만든다. 만들지 **못했으면** 저장을 성공으로 치지 않고
     사유를 그대로 보인다. 조용히 넘어가면 "설정했는데 안 먹는다"가 되돌아온다.
  ② **만드는 자리는 저장 한 곳뿐이다.** 읽는 쪽(`external_secret_dir`)은 절대
     만들지 않는다 — 비밀을 읽을 때마다, 커밋 가드·훅에서도 불리는 함수다. 읽기가
     폴더를 만드는 부작용을 가지면 오타 하나가 엉뚱한 자리에 폴더를 만들고 그걸
     아무도 모른다.
  ③ **판정은 한 곳에서 한다.** 만든 뒤에도 폴더는 지워지고 마운트는 빠진다.
     지금 그 경로가 실제로 읽히는지는 `external_secret_state()` 한 곳이 내고
     CLI(`s9 secret ls`)와 대시보드가 같은 것을 읽는다.

덤으로 지키는 것: **저장소 안 경로는 뜻이 없다**(저장소는 공유·공개된다).

(2026-08-28 재작업: 처음에는 "s9 는 바깥 폴더를 **읽기만** 한다"가 여기 계약이었다.
사용자가 바로 그 비대칭을 지적해 — "key, value는 설정창에서 반영할 수는 없나?" —
이제 그 폴더에 **넣을 수도 있다**. 어디에 넣을지 고르는 자리는
tests/test_secret_where.py 가 지킨다. 이 파일은 계속 **경로 한 칸**만 본다.)

실행: python3 tests/ secret_external_path
"""
import json
import os
import re
import stat
import subprocess
import tempfile
import unittest

import websrc  # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
INDEX = index_path()


class ExternalPathVerdict(unittest.TestCase):
    """판정 — 지금 그 경로가 쓰이는가. CLI 출력으로 확인한다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9extv-")
        self.outside = tempfile.mkdtemp(prefix="s9extd-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                    "S9_USER": "alice"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "alice")

    def cli(self, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=30, stdin=subprocess.DEVNULL)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def set_path(self, value):
        # 비밀 위치 키는 추적되지 않는 자리(local.json)에만 산다
        # (REQ-20260902-031) — settings.json 에 적으면 user_config 가
        # 읽지 않는다. 원격이 밀어 넣을 수 있는 칸에 두지 않기 위해서다.
        cfgdir = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(cfgdir, exist_ok=True)
        p = os.path.join(cfgdir, "local.json")
        d = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        d["external_secrets_path"] = value
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f)

    # N1. 안 적었으면 안 적었다고 말한다
    def test_n1_unset_says_so(self):
        self.assertIn("external 미설정", self.cli("secret", "ls"))

    # N2. 리포 밖의 있는 폴더 = 지금 읽히는 상태 — 경고를 달지 않는다
    def test_n2_live_path_is_reported_plainly(self):
        self.set_path(self.outside)
        out = self.cli("secret", "ls")
        self.assertIn(f"external={self.outside}", out)
        self.assertNotIn("무시된다", out)
        self.assertNotIn("뜻이 없다", out)

    # B1. 폴더가 없으면 조용히 무시된다 — 그 침묵을 깬다.
    #     (설정을 손으로 고쳤거나, 만든 뒤 폴더가 지워진 자리)
    def test_b1_missing_folder_is_said_out_loud(self):
        self.set_path(os.path.join(self.outside, "nope"))
        out = self.cli("secret", "ls")
        self.assertIn("무시된다", out,
                      "폴더가 없어 무시되는데 화면·CLI 어디서도 말하지 않는다")

    # B2. 저장소 안을 가리키면 '바깥'의 뜻이 없다 — 폴더가 실제로 있어도 그렇다
    def test_b2_inside_the_repo_is_pointless(self):
        inside = os.path.join(self.root, "users")
        self.assertTrue(os.path.isdir(inside))
        self.set_path(inside)
        out = self.cli("secret", "ls")
        # 화면 낱말이 「리포」에서 「저장소」로 섰다 — 이 제품이 스스로 지은
        # 말은 우리 말로 세운다(CLAUDE.md 말과 태도 2).
        self.assertIn("저장소 안", out, "저장소 안 경로를 그냥 통과시킨다")

    # B3. 저장소 안 + 폴더 없음 = 저장소 얘기를 먼저 한다.
    #     "폴더를 만드세요"라고 안내하면 사고를 거드는 셈이다
    def test_b3_inside_the_repo_wins_over_missing(self):
        self.set_path(os.path.join(self.root, "nope-not-here"))
        out = self.cli("secret", "ls")
        self.assertIn("저장소 안", out)
        self.assertNotIn("폴더가 없어", out)


class ExternalPathCreate(unittest.TestCase):
    """"디렉토리가 없으면 만들면 되는 것 아닌가?" — 정하는 순간 만든다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9extc-")
        self.home = tempfile.mkdtemp(prefix="s9exth-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                    "S9_USER": "alice"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "alice")

    def cli(self, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=30, stdin=subprocess.DEVNULL)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def saved_cfg(self):
        """읽는 값은 하나다 — 추적 파일 위에 비추적 local.json 을 겹친다.

        비밀이 **어디 있는지**도 리포에 싣지 않기로 해서(REQ-20260828-028 부수
        발견) 이 키는 `config/local.json`(gitignore)에 저장된다. 읽는 쪽은
        갈린 것을 몰라야 하므로 여기서도 합쳐서 본다.
        """
        d = os.path.join(self.root, "users", "alice", "config")
        cfg = {}
        for fn in ("settings.json", "local.json"):
            try:
                with open(os.path.join(d, fn), encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except (OSError, ValueError):
                pass
        return cfg

    def tracked_cfg(self):
        """git 이 추적하는 쪽만 — 비밀 위치가 여기 있으면 안 된다."""
        p = os.path.join(self.root, "users", "alice", "config", "settings.json")
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def setpath(self, value, expect=0):
        return self.cli("user", "config", "alice", "external_secrets_path",
                        value, expect=expect)

    # N1. **핵심** — 없는 폴더는 저장하는 그 순간 생긴다. 권한은 나만
    def test_n1_saving_creates_the_folder(self):
        want = os.path.join(self.home, "keys")
        self.setpath(want)
        self.assertTrue(os.path.isdir(want), "저장했는데 폴더가 안 생겼다")
        self.assertEqual(stat.S_IMODE(os.stat(want).st_mode), 0o700,
                         "남이 읽을 수 있는 권한으로 만들었다")
        # 그리고 그 즉시 쓰이는 상태여야 한다 — 설명만 하고 남겨 두지 않는다
        self.assertIn(f"external={want}", self.cli("secret", "ls"))

    # N2. 저장되는 값은 `~` 를 편 절대 경로다 — 나중에 재는 자가 헷갈리지 않게
    def test_n2_tilde_is_expanded_on_save(self):
        env_home = {**self.env, "HOME": self.home}
        r = subprocess.run([S9, "user", "config", "alice",
                            "external_secrets_path", "~/kk"],
                           capture_output=True, text=True, env=env_home,
                           timeout=30, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        saved = self.saved_cfg()["external_secrets_path"]
        self.assertEqual(saved, os.path.join(self.home, "kk"))
        self.assertTrue(os.path.isdir(saved))
        # 그리고 그 값은 **추적되는 파일에 없어야 한다** (REQ-20260828-028 부수
        # 발견): 이 리포의 origin 은 공개이고 이 파일은 거기 올라간다.
        self.assertNotIn("external_secrets_path", self.tracked_cfg())

    # B1. 못 만들면 **성공으로 치지 않는다** — 여기서 조용하면 "설정했는데
    #     안 먹는다"가 그대로 되돌아온다
    def test_b1_failure_is_not_swallowed(self):
        out = self.setpath("/nope/s9-cannot-make/deeper", expect=1)
        self.assertIn("만들지 못했다", out, "못 만들었는데 사유를 말하지 않는다")
        self.assertNotIn("external_secrets_path", self.saved_cfg(),
                         "못 만들었는데 설정만 저장해 뒀다")

    # B2. 저장소 안은 거부한다 — 저장소는 공유·공개된다
    def test_b2_inside_the_repo_is_refused(self):
        out = self.setpath(os.path.join(self.root, "mine"), expect=1)
        self.assertIn("저장소 안에는 둘 수 없다", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "mine")),
                         "거부하면서 폴더는 만들어 뒀다")

    # B3. 이미 있는 폴더의 권한은 건드리지 않는다 — 남의 폴더다
    def test_b3_existing_folder_keeps_its_own_mode(self):
        d = os.path.join(self.home, "shared")
        os.makedirs(d, mode=0o755)
        os.chmod(d, 0o755)
        self.setpath(d)
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o755,
                         "남의 폴더 권한을 덮어썼다")

    # B4. 폴더가 지워진 뒤 같은 경로로 다시 저장하면 되살아난다
    #     (설정값이 같아 일찍 돌아가더라도 폴더는 먼저 만든다)
    def test_b4_resaving_the_same_path_revives_it(self):
        want = os.path.join(self.home, "keys")
        self.setpath(want)
        os.rmdir(want)
        self.assertIn("무시된다", self.cli("secret", "ls"))
        self.setpath(want)
        self.assertTrue(os.path.isdir(want), "같은 경로로 다시 저장해도 안 만든다")

    # F1. **읽기는 절대 만들지 않는다.** 비밀을 읽을 때마다·커밋 가드·훅에서도
    #     불리는 함수다. 오타 하나가 엉뚱한 자리에 폴더를 만들면 아무도 모른다
    def test_f1_reading_never_creates(self):
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index("def external_secret_dir(user):")
        body = src[i:src.index("def ensure_external_secret_dir(")]
        for mk in ("makedirs", "mkdir"):
            self.assertNotIn(mk, body, "읽는 쪽이 폴더를 만든다")
        ghost = os.path.join(self.home, "never-made")
        cfgdir = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(cfgdir, exist_ok=True)
        with open(os.path.join(cfgdir, "settings.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"external_secrets_path": ghost}, f)
        self.cli("secret", "ls")
        self.assertFalse(os.path.exists(ghost), "읽기가 폴더를 만들어 버렸다")


class ExternalPathApi(unittest.TestCase):
    """서버가 판정을 준다 — 값 비노출 규율은 그대로."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(S9_SRC, encoding="utf-8").read()
        i = cls.src.index('parsed.path == "/api/secrets"')
        cls.listing = cls.src[i:cls.src.index('parsed.path == "/api/users"')]

    def test_n1_state_and_path_are_served(self):
        self.assertIn('"external_state"', self.listing, "판정을 주지 않는다")
        self.assertIn("external_secret_state(me)", self.listing,
                      "판정을 핸들러가 따로 만든다 — 한 곳에서 내야 한다")
        self.assertIn('"external_path"', self.listing,
                      "내가 적은 경로를 돌려주지 않는다")

    def test_n2_it_is_still_my_own_only(self):
        """대리(as)를 받지 않는 신원 위에서만 준다 — 남의 경로가 섞일 자리 없음."""
        self.assertIn('me = whoami_info().get("user", "")', self.listing)
        self.assertNotIn("as_user", self.listing)

    def test_b1_values_still_never_leave(self):
        self.assertNotIn("secret_value", self.listing, "목록이 값을 읽는다")
        # 어느 키 파일이 어디 있는지는 여전히 주지 않는다 (REQ-012 의 계약)
        self.assertNotIn("os.path.relpath(p0", self.listing)


class ExternalPathUI(unittest.TestCase):
    """칸 하나 + 그 옆의 한 줄."""

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def _mine(self):
        """내 계정 판에서만 그리는 구간 (${mySecrets ? ` … `} 안쪽)."""
        i = self.src.index("${mySecrets ? `")
        j = self.src.index('` : ""}', i)
        return self.src[i:j]

    # N1. 칸이 있다 — 그리고 내 계정 판에서만
    def test_n1_the_box_exists_on_my_own_panel(self):
        mine = self._mine()
        self.assertIn('id="sec-ext"', mine, "바깥 경로 칸이 없다")
        self.assertIn('aria-label="바깥 폴더 경로"', mine, "칸에 이름이 없다")
        self.assertIn("cfg.external_secrets_path", mine,
                      "지금 저장된 경로를 칸에 띄우지 않는다")
        self.assertIn('id="sec-ext-state"', mine, "판정을 그릴 자리가 없다")
        self.assertIn('aria-live="polite"', mine, "바뀐 판정을 읽어 주지 않는다")

    # N2. 저장은 다른 설정과 같은 길로
    def test_n2_saving_goes_through_user_config(self):
        blk = self.src[self.src.index("const extBtn ="):]
        blk = blk[:blk.index("});", blk.index("extIn.addEventListener")) + 3]
        self.assertIn('postJSONRaw("/api/user/config"', blk, "저장 경로가 다르다")
        self.assertIn('key: "external_secrets_path"', blk, "다른 키를 저장한다")
        self.assertIn("extIn.value.trim()", blk)
        # 경로가 살아나면 그 폴더의 키가 목록에 나타나야 한다 — 저장만 하고
        # 목록을 그대로 두면 화면이 옛말을 한다
        self.assertIn("loadSecrets()", blk, "저장 뒤 목록을 다시 받지 않는다")

    # B1. **판정을 화면에서 새로 만들지 않는다**
    def test_b1_the_verdict_comes_from_the_server(self):
        self.assertIn("d.external_state", self.src,
                      "서버 판정을 안 쓴다 — 화면이 따로 재면 답이 갈린다")
        blk = self.src[self.src.index("const EXTSAY = {"):
                       self.src.index("async function loadSecrets(")]
        for reinvented in ("isdir", "startsWith(", "/api/fs", "exists"):
            self.assertNotIn(reinvented, blk,
                             f"화면이 판정을 다시 만든다: {reinvented}")

    # B2. 네 상태를 다 그린다 — 특히 '무시됨'
    def test_b2_every_verdict_is_worded(self):
        blk = self.src[self.src.index("const EXTSAY = {"):
                       self.src.index("function extSay(")]
        for state in ("ok:", "missing:", "inrepo:", "unset:"):
            self.assertIn(state, blk, f"{state} 상태 문구가 없다")
        self.assertIn("경로 저장을 다시 누르면 만듭니다", blk,
                      "폴더가 사라졌을 때 무엇을 하면 되는지 말하지 않는다")
        self.assertIn("저장소는 다른 사람과 공유", blk,
                      "저장소 안이 왜 안 되는지 말하지 않는다")
        # 색만으로 구분하지 않는다 — 낱말이 먼저 답한다
        self.assertIn('"읽는 중"', blk)
        self.assertIn('"폴더 없음"', blk)

    # B2b. 없는 폴더는 저장할 때 만든다는 것을 미리 말한다
    def test_b2b_it_promises_to_create_the_folder(self):
        mine = self._mine()
        note = mine[mine.index("바깥 폴더 —"):mine.index('id="sec-ext"')]
        self.assertIn("없는 폴더는 저장할 때 만들어 드립니다", note,
                      "만들어 준다는 것을 말하지 않는다 — 사람이 터미널로 나간다")

    # B3. **경로를 정하면 거기에 넣을 수도 있다** (REQ-20260828-017 재작업).
    #     처음에는 "읽기만 합니다"라고 적어 두었는데, 사용자가 바로 그 비대칭을
    #     지적했다: "key, value는 설정창에서 반영할 수는 없나?" 이제 넣을 수
    #     있으므로 그 문장은 거짓이 됐다 — 대신 **경로가 그 칸을 연다**는 것을
    #     말한다. 경로부터 정해야 한다는 순서가 안 보이면 잠긴 칸이 고장으로 읽힌다.
    def test_b3_the_path_is_what_unlocks_writing_outside(self):
        mine = self._mine()
        note = mine[mine.index("바깥 폴더 —"):mine.index('id="sec-ext"')]
        self.assertNotIn("읽기만 합니다", note,
                         "이제 여기에 넣을 수 있는데 읽기 전용이라고 말한다")
        self.assertIn("고를 수 있습니다", note,
                      "경로를 정하면 넣기에서 고를 수 있다는 것을 말하지 않는다")
        self.assertIn("잠겨", note, "정하기 전에는 잠긴다는 것을 말하지 않는다")
        self.assertIn("파일 이름이 곧 키 이름", note,
                      "그 폴더에 직접 둔 파일은 어떻게 읽히는지 말하지 않는다")

    # B4. 손 없이 눌러 볼 길이 있다 — 그리고 진짜 비밀은 건드리지 않는다.
    #     코드를 읽어서는 "저장하면 폴더가 생긴다"를 확인했다고 말할 수 없다.
    def test_b4_it_can_be_exercised_without_hands(self):
        self.assertIn("[?&]extdbg", self.src, "손 없이 눌러 볼 길이 없다")
        dbg = self.src[self.src.index("if (extIn && /[?&]extdbg/"):]
        dbg = dbg[:dbg.index('host.querySelector("#pf-save")')]
        self.assertIn('host.querySelector("#sec-ext-save").click()', dbg,
                      "진짜 저장 버튼을 누르지 않는다")
        self.assertIn("/nope/s9-extdbg", dbg, "못 만드는 자리를 재 보지 않는다")
        self.assertIn("저장 못 함", dbg, "사유가 떴는지 재지 않는다")
        self.assertIn("읽는 중", dbg, "폴더가 생겼는지 재지 않는다")
        self.assertIn("await save(was)", dbg,
                      "진단이 사용자의 설정을 바꿔 놓고 끝난다")
        # 진단이 손대는 것은 경로 하나뿐이다 — 비밀 키는 건드리지 않는다
        for forbidden in ("/api/secret/set", "/api/secret/rm", "#sec-val"):
            self.assertNotIn(forbidden, dbg, f"진단이 비밀을 건드린다: {forbidden}")

    # F1. 색면·세로 띠·라운드 없음 (REQ-20260828-012 와 같은 계약)
    def test_f1_ink_not_a_colour_field(self):
        css = self.src[self.src.index(".secsub{"):self.src.index(".cfg-h{")]
        for m in re.finditer(r"background:([^;}]+)", css):
            self.assertIn(m.group(1).strip(), ("none", "var(--panel)",
                                               "var(--text)", "var(--bg)"),
                          "배경에 색면을 깐다")
        self.assertNotIn("border-left:", css, "세로 띠를 두른다")
        self.assertNotIn("border-radius", css, "라운드를 쓴다")
        self.assertNotIn("box-shadow", css, "그림자를 쓴다")
        websrc.no_hex(self, css, "색을 하드코딩한다")
    # F2. 자동 설정 목록의 '기타' 로 새지 않는다 — 자기 칸이 생겼으므로
    def test_f2_no_longer_dumped_into_the_leftovers_line(self):
        i = self.src.index("const extraCfg =")
        self.assertIn("external_secrets_path",
                      self.src[i:i + 400],
                      "칸이 생겼는데 '기타' JSON 에도 그대로 남는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
