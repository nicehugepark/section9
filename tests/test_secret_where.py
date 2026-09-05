"""비밀을 **어디에 둘지 고르며** 넣는다 (REQ-20260828-017-62x6 — 재작업).

사용자(15:22): "external_secrets_path에 대해서 폴더는 만들었는데, key, value는
설정창에서 반영할 수는 없나? internal 항목이랑 좌우 형태로 같이 등록될 수 있으면
좋겠는데 말이야."

앞 판은 바깥 폴더를 **읽기만** 했다. 그래서 사용자가 화면에서 폴더를 만들어 놓고도
거기에는 값을 넣을 수 없었다 — 폴더는 화면 안에, 그 폴더를 채우는 일은 터미널에.
012 가 지적한 "CLI 에만 있으면 없는 기능"이 방향만 바꿔 되살아난 셈이다.

이 파일이 지키는 것은 넷이다.

  ① **쓰는 자리는 한 곳이다.** `s9 secret set` 도 `POST /api/secret/set` 도
     `secret_write()` 를 지난다. 두 벌이 되면 한 벌만 고쳐진다.
  ② **바깥이 안 되면 큰 소리로 안 된다.** 경로를 안 정했거나 폴더가 없으면
     저장을 거부한다 — 조용히 저장소 안으로 떨어뜨리면 사용자는 밖에 넣은 줄 안다.
  ③ **가려지는 것을 말한다.** 같은 이름이면 저장소 안이 이긴다(`secret_keys`).
     넣었는데 안 쓰이는 것이 이 기능에서 가장 나쁜 결말이라 넣기 전과 뒤에 말한다.
  ④ **지울 때 어느 쪽인지 말한다.** 줄은 하나여도 파일은 둘일 수 있다.

화면 몫은 "좌우 두 칸": 폼을 두 벌 세우는 대신 값은 한 번만 치고 **목적지만
고른다.** 못 고르는 칸은 잠기고, 왜 잠겼는지가 그 자리에 있다.

실행: python3 tests/ secret_where
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


class WhereWrite(unittest.TestCase):
    """CLI 로 실제로 넣어 본다 — 화면과 같은 함수를 지나므로 여기서 재면 둘 다다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9wr-")
        self.home = tempfile.mkdtemp(prefix="s9wh-")
        self.out = os.path.join(self.home, "keys")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                    "S9_USER": "alice"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "alice")

    def cli(self, *argv, expect=0, stdin=None):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=30,
                           input=stdin if stdin is not None else "",
                           stdin=None if stdin is not None else None)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def openpath(self):
        """바깥 폴더를 정한다 — 저장이 그 폴더를 만든다(REQ-20260828-017)."""
        self.cli("user", "config", "alice", "external_secrets_path", self.out)

    def inner(self, key):
        return os.path.join(self.root, "users", "alice", "secrets", key)

    def outer(self, key):
        return os.path.join(self.out, key)

    # ---------- ① 고른 곳이 곧 값이 가는 곳 ----------

    def test_n1_external_flag_writes_outside(self):
        """`--external` 이면 바깥 폴더에 파일이 생긴다. 권한은 나만."""
        self.openpath()
        self.cli("secret", "set", "TOKEN", "--external", stdin="outside-value")
        self.assertTrue(os.path.isfile(self.outer("TOKEN")),
                        "바깥에 넣으라고 했는데 파일이 없다")
        self.assertFalse(os.path.exists(self.inner("TOKEN")),
                         "바깥에 넣으라고 했는데 저장소 안에 썼다")
        self.assertEqual(stat.S_IMODE(os.stat(self.outer("TOKEN")).st_mode), 0o600,
                         "남이 읽을 수 있는 권한으로 썼다")
        self.assertRegex(self.cli("secret", "ls"), r"TOKEN\s+external")

    def test_n2_default_is_still_inside(self):
        """무지정은 저장소 안 — 정하지 않았는데 밖으로 가면 놀란다."""
        self.openpath()
        self.cli("secret", "set", "TOKEN", stdin="inside-value")
        self.assertTrue(os.path.isfile(self.inner("TOKEN")))
        self.assertFalse(os.path.exists(self.outer("TOKEN")))

    def test_n3_value_never_printed(self):
        """넣고 지우고 세는 어느 출력에도 값이 없다."""
        self.openpath()
        v = "s3cr3t-never-shown"
        out = self.cli("secret", "set", "TOKEN", "--external", stdin=v)
        out += self.cli("secret", "ls")
        out += self.cli("secret", "rm", "TOKEN")
        self.assertNotIn(v, out, "값이 출력에 샜다")

    # ---------- ② 바깥이 안 되면 큰 소리로 ----------

    def test_b1_unset_path_refuses_loudly(self):
        """경로를 안 정했으면 거부한다 — 조용히 안으로 떨어뜨리지 않는다."""
        out = self.cli("secret", "set", "TOKEN", "--external",
                       expect=1, stdin="v")
        self.assertIn("바깥 폴더", out, "왜 안 되는지 말하지 않는다")
        self.assertIn("external_secrets_path", out, "무엇을 하면 되는지 없다")
        self.assertFalse(os.path.exists(self.inner("TOKEN")),
                         "밖에 넣으라고 했는데 안에 들어갔다 — 제일 나쁜 결말")

    def test_b2_missing_folder_refuses_loudly(self):
        """정해 둔 폴더가 사라졌으면 거부한다."""
        self.openpath()
        os.rmdir(self.out)
        out = self.cli("secret", "set", "TOKEN", "--external",
                       expect=1, stdin="v")
        self.assertIn("없다", out)
        self.assertFalse(os.path.exists(self.inner("TOKEN")))

    def test_b3_both_flags_refused(self):
        """`--internal --external` 은 뜻이 없다 — 묻지 말고 막는다."""
        out = self.cli("secret", "set", "TOKEN", "--internal", "--external",
                       expect=1, stdin="v")
        self.assertIn("함께 못 쓴다", out)

    # ---------- ③ 가려지는 것을 말한다 ----------

    def test_b4_internal_wins_and_says_so(self):
        """같은 이름이면 안이 이긴다 — 넣는 그 자리에서 말해 줘야 한다."""
        self.openpath()
        self.cli("secret", "set", "TOKEN", stdin="inside")
        out = self.cli("secret", "set", "TOKEN", "--external", stdin="outside")
        self.assertIn("쓰이지 않는다", out, "넣었는데 안 쓰인다는 것을 말하지 않는다")
        self.assertEqual(self.cli("secret", "get", "TOKEN").strip(), "inside",
                         "바깥 값이 안쪽을 이겼다")
        self.assertIn("가려진다", self.cli("secret", "ls"),
                      "목록이 가려진 이름을 말하지 않는다")

    # ---------- ④ 지울 때 어느 쪽인지 ----------

    def test_n4_rm_says_which_side(self):
        self.openpath()
        self.cli("secret", "set", "TOKEN", "--external", stdin="outside")
        out = self.cli("secret", "rm", "TOKEN")
        self.assertIn("저장소 밖", out, "어느 쪽 것을 지웠는지 말하지 않는다")
        self.assertFalse(os.path.exists(self.outer("TOKEN")))

    def test_n5_rm_can_target_one_side(self):
        """가려진 것을 걷어내려면 한쪽만 지울 수 있어야 한다."""
        self.openpath()
        self.cli("secret", "set", "TOKEN", stdin="inside")
        self.cli("secret", "set", "TOKEN", "--external", stdin="outside")
        self.cli("secret", "rm", "TOKEN", "--internal")
        self.assertFalse(os.path.exists(self.inner("TOKEN")))
        self.assertEqual(self.cli("secret", "get", "TOKEN").strip(), "outside",
                         "안을 지웠는데 바깥 값이 살아나지 않는다")

    def test_n6_rm_without_flag_clears_both(self):
        """화면의 지우기는 처음부터 양쪽을 훑었다 — CLI 만 다르면 같은 말이 두 뜻."""
        self.openpath()
        self.cli("secret", "set", "TOKEN", stdin="inside")
        self.cli("secret", "set", "TOKEN", "--external", stdin="outside")
        out = self.cli("secret", "rm", "TOKEN")
        self.assertIn("저장소 안", out)
        self.assertIn("저장소 밖", out)
        self.assertFalse(os.path.exists(self.inner("TOKEN")))
        self.assertFalse(os.path.exists(self.outer("TOKEN")))

    def test_b5_rm_missing_key_is_an_error(self):
        self.assertIn("그런 비밀이 없다",
                      self.cli("secret", "rm", "NOPE", expect=1))


class OnePlaceWrites(unittest.TestCase):
    """쓰는 자리는 한 곳 — 이 저장소가 여러 번 겪은 '두 벌 중 한 벌만' 을 막는다."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(S9_SRC, encoding="utf-8").read()

    def test_f1_no_second_writer(self):
        """파일을 여는 자리는 secret_write() 하나뿐이다."""
        writer = self.src[self.src.index("def secret_write("):
                          self.src.index("def secret_remove(")]
        self.assertIn("os.open(", writer)
        # 핸들러도 CLI 도 직접 열지 않는다
        api = self.src[self.src.index('parsed.path == "/api/secret/set"'):
                       self.src.index('parsed.path == "/api/secret/rm"')]
        self.assertNotIn("os.open(", api)
        self.assertNotIn('open(fp, "w"', api)
        cli = self.src[self.src.index("def cmd_secret("):]
        cli = cli[:cli.index('if args.action == "get":')]
        self.assertNotIn("os.open(", cli)

    def test_f2_removing_is_one_place_too(self):
        api = self.src[self.src.index('parsed.path == "/api/secret/rm"'):]
        api = api[:api.index('parsed.path == "/api/note"')]
        self.assertIn("secret_remove(actor, key, where)", api)
        self.assertNotIn("os.remove(", api, "핸들러가 직접 지운다")


class WhereUI(unittest.TestCase):
    """좌우 두 칸 — "internal 항목이랑 좌우 형태로 같이 등록"."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(INDEX, encoding="utf-8").read()

    def _mine(self):
        i = self.src.index("${mySecrets ? `")
        return self.src[i:self.src.index('` : ""}', i)]

    def _paint(self):
        i = self.src.index("function paintWhere(")
        return self.src[i:self.src.index("if (whereBox){", i)]

    # N1. 두 칸이 나란히, 라디오로
    def test_where_u_i(self):
        """좌우 두 칸 — "internal 항목이랑 좌우 형태로 같이 등록"."""
        with self.subTest("n1_two_cells_side_by_side"):
                mine = self._mine()
                self.assertIn('id="sec-where"', mine, "둘 곳을 고르는 자리가 없다")
                self.assertIn('role="radiogroup"', mine, "키보드로 고를 수 없다")
                self.assertIn('data-w="internal"', mine)
                self.assertIn('data-w="external"', mine)
                self.assertIn("저장소 안", mine)
                self.assertIn("저장소 밖", mine)
                # 좌우로 세운다 — 위아래 목록이 아니라
                css = self.src[self.src.index(".secwhere{"):self.src.index(".secwhy{")]
                self.assertIn("display:flex", css, "두 칸이 좌우로 서지 않는다")
                # 값 칸은 한 벌뿐이다 — 두 벌이면 옮길 때 값을 다시 친다
                self.assertEqual(mine.count('id="sec-val"'), 1, "값 칸이 두 벌이다")

            # N2. 고른 곳이 서버로 간다
        with self.subTest("n2_the_choice_is_what_is_sent"):
                add = self.src[self.src.index("addBtn.addEventListener"):]
                add = add[:add.index("// 엔터로도 넣는다")]
                self.assertIn("where: secWhere", add, "고른 곳을 서버에 보내지 않는다")
                # 어디에 넣었는지 알림이 말한다 — 넣고 나서도 확인이 되어야 한다
                self.assertIn("WHERE_KO[res.where]", add,
                              "어디에 넣었는지 서버가 말한 것을 쓰지 않는다")

            # N3. 버튼이 목적지를 말한다 (동사+목적)
        with self.subTest("n3_the_button_names_the_destination"):
                self.assertIn("＋ ${WHERE_KO[secWhere]}에 넣기", self._paint(),
                              "버튼이 어디에 넣는지 말하지 않는다")

            # B1. 못 쓰면 잠기고, 이유가 그 자리에 있다
        with self.subTest("b1_locked_with_a_reason_in_place"):
                paint = self._paint()
                self.assertIn('const canExt = st === "ok"', paint,
                              "쓸 수 있는지를 서버 판정으로 정하지 않는다")
                self.assertIn('if (!canExt) secWhere = "internal"', paint,
                              "못 쓰는데 바깥이 골라진 채로 남는다")
                self.assertIn("r.disabled = off", paint, "잠긴 칸을 고를 수 있다")
                self.assertIn("EXTWHY[st]", paint, "왜 잠겼는지 말하지 않는다")
                # 칸에는 짧은 이름, 아래 줄에는 문장 — 같은 말을 두 번 하지 않는다
                self.assertIn("why[0]", paint, "칸이 짧은 상태 이름을 안 쓴다")
                self.assertIn("esc(why[1])", paint, "아래 줄이 문장을 안 쓴다")
                self.assertIn("경로부터 정해 주세요", paint, "다음 행동을 주지 않는다")
                self.assertIn('id="sec-gopath"', paint, "경로 칸으로 데려가지 않는다")
                why = self.src[self.src.index("const EXTWHY = {"):
                               self.src.index("let secWhere")]
                for state in ("unset:", "missing:", "inrepo:", "unknown:"):
                    self.assertIn(state, why, f"{state} 상태 문구가 없다")

            # B2. 판정은 서버 것 하나 — 화면이 다시 만들지 않는다
        with self.subTest("b2_the_verdict_still_comes_from_the_server"):
                paint = self._paint()
                self.assertIn("secData.external_state", paint)
                for reinvented in ("isdir", "/api/fs", "exists("):
                    self.assertNotIn(reinvented, paint,
                                     f"화면이 판정을 다시 만든다: {reinvented}")

            # B3. 가려질 값은 **넣기 전에** 말한다
        with self.subTest("b3_shadowing_is_said_before_it_happens"):
                add = self.src[self.src.index("addBtn.addEventListener"):]
                add = add[:add.index("// 엔터로도 넣는다")]
                i = add.index('kind: "confirm"')
                self.assertLess(i, add.index('postJSONRaw("/api/secret/set"'),
                                "넣고 나서 가려졌다고 말한다")
                self.assertIn("저장소 안의 값이 쓰입니다", add,
                              "어느 쪽이 이기는지 말하지 않는다")
                self.assertIn('ok: "그래도 넣기"', add, "확인 버튼이 동사+목적이 아니다")
                # 넣은 뒤에도 서버가 말한 사실을 그대로 전한다 (사이에 다른 세션이 넣었을 수 있다)
                self.assertIn("res.shadowed", add, "서버가 말한 가려짐을 흘린다")

            # B4. 목록이 가려진 줄을 표시한다
        with self.subTest("b4_the_list_marks_the_shadowed_row"):
                fn = self.src[self.src.index("async function loadSecrets("):
                              self.src.index("const secMsg =")]
                self.assertIn("k.shadowed", fn, "가려진 줄이 표시되지 않는다")
                self.assertIn("밖의 같은 이름은 가려짐", fn)

            # B5. 지울 때 어느 쪽인지 묻는 창이 말한다
        with self.subTest("b5_removing_names_the_side"):
                rm = self.src[self.src.index("secList.addEventListener"):]
                rm = rm[:rm.index("/* ?secdbg")]
                self.assertIn("저장소 안과 밖 양쪽", rm, "양쪽에 있을 때를 말하지 않는다")
                self.assertIn("에 있는 파일을 지웁니다", rm, "어디 것을 지우는지 말하지 않는다")
                self.assertIn("res.places", rm, "무엇이 사라졌는지 서버 답을 안 쓴다")

            # F1. 잉크 언어 — 색면·라운드·그림자 없음, 색만으로 구분하지 않는다
        with self.subTest("f1_ink_not_a_colour_field"):
                css = self.src[self.src.index(".secwlab{"):self.src.index(".cfg-h{")]
                for m in re.finditer(r"background:([^;}]+)", css):
                    self.assertIn(m.group(1).strip(), ("none", "var(--panel)",
                                                       "var(--text)", "var(--bg)"),
                                  "배경에 색면을 깐다")
                self.assertNotIn("border-left:", css, "세로 띠를 두른다")
                self.assertNotIn("border-radius", css, "라운드를 쓴다")
                self.assertNotIn("box-shadow", css, "그림자를 쓴다")
                websrc.no_hex(self, css, "색을 하드코딩한다")
                # 고른 칸은 색이 아니라 모양으로도 읽힌다
                self.assertIn('el.querySelector(".wm").textContent = on ? "●" : "○"',
                              self._paint(), "고른 칸이 색으로만 구분된다")
                self.assertIn(".wopt.on{border-bottom-color:var(--text)}", css,
                              "고른 칸이 잉크 밑줄로 서지 않는다")

            # F2. 손 없이 눌러 볼 길 — 그리고 진짜 비밀은 건드리지 않는다
        with self.subTest("f2_it_can_be_exercised_without_hands"):
            self.assertIn("[?&]secwdbg", self.src, "손 없이 눌러 볼 길이 없다")
            dbg = self.src[self.src.index("if (secList && /[?&]secwdbg/"):]
            dbg = dbg[:dbg.index("/* ?extdbg")]
            self.assertIn('const K = "S9DBG_WHERE"', dbg,
                          "진단이 진짜 비밀을 건드릴 수 있다")
            self.assertIn('host.querySelector("#sec-add").click()', dbg,
                          "진짜 버튼을 누르지 않는다")
            self.assertIn("dlg.querySelector(\".dlgyes\")", dbg,
                          "확인 창을 실제로 지나지 않는다")
            self.assertIn("되돌림", dbg, "넣어 본 것을 지우지 않는다")

if __name__ == "__main__":
    unittest.main(verbosity=2)
