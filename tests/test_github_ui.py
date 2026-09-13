"""Settings 「저장소」 판의 GitHub 연동 화면 (REQ-20260913-009-62x6).

배포판을 풀어 쓰는 사람은 처음에 혼자 쓰는 자리에 있다 — origin 이 없고 기록이
이 컴퓨터 밖으로 나가지 않는다. 화면은 그 사실도, 이을 길도 말하지 않았다.
`web/app/github.js` 가 그 빈자리인데, 이 파일이 지키는 것은 하나다: **판정은
서버가 하고 화면은 그 응답을 그대로 그린다.** 화면이 제 판정을 한 벌 더 지으면
규칙이 둘이 되어 언젠가 갈린다(repo.js 가 pull·push 에 세운 그 규율).

그래서 시험은 문장을 짓는 순수 함수를 **node 로 실제로 불러** 값을 잰다 —
소스 글자를 대조하는 것이 아니라, 서버가 준 state 를 넣고 나온 문장을 읽는다.
낱말 한 갈래(G6)만은 「없음의 증명」이라 화면 원문을 본다.

실행: python3 tests/ github_ui
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "..", "web")


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


NODE = find_node()


def _src(name):
    with open(os.path.join(WEB, name), encoding="utf-8") as f:
        return f.read()


# 조각이 기대는 바깥 이름 둘(`esc`·`GH_DOING` 은 제 파일에 있다)만 세워 준다 —
# 나머지(document·fetch)는 순수 함수가 건드리지 않는다.
PRELUDE = """
function esc(t){return String(t==null?"":t).replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
"""


def probe(expr):
    """github.js 를 그대로 읽어 들여 식 하나를 계산한다."""
    js = PRELUDE + _src("app/github.js") + "\nconsole.log(JSON.stringify(" + expr + "));"
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True)
    if out.returncode != 0:
        raise AssertionError(out.stderr.strip()[:600])
    return json.loads(out.stdout)


LINKED = {"linked": True, "origin": "git@github.com:me/box.git",
          "web_url": "https://github.com/me/box", "sync_mode": "remote",
          "branch": "main", "token_key": "GITHUB_TOKEN",
          "auth": {"gh": True, "token": False, "login": "me"},
          "can": {"link": {"ok": True, "why": ""},
                  "create": {"ok": True, "why": ""}}}
ALONE = {"linked": False, "origin": "", "web_url": "", "sync_mode": "local",
         "branch": "main", "token_key": "GITHUB_TOKEN",
         "auth": {"gh": False, "token": False, "login": ""},
         "can": {"link": {"ok": True, "why": ""},
                 "create": {"ok": False, "why": "준비물이 없습니다 — gh CLI "
                                                "로그인(`gh auth login`) 또는 secret "
                                                "GITHUB_TOKEN 중 하나가 필요합니다."}}}


class Wiring(unittest.TestCase):
    """G1. 조각은 「저장소」 판 뒤에 실린다 — 그 판이 제 표를 세울 때 부른다."""

    def test_g1_the_piece_is_loaded_after_the_repo_panel(self):
        shell = _src("index.html")
        i, j = shell.find('app/github.js'), shell.find('app/repo.js')
        self.assertGreater(i, -1, "index.html 이 app/github.js 를 싣지 않는다")
        self.assertGreater(i, j, "github.js 는 repo.js 뒤에 서야 한다")
        # 판이 실제로 이 조각을 부른다 — 싣기만 하고 안 부르면 절이 안 선다.
        repo = _src("app/repo.js")
        self.assertIn("ghSectionHTML()", repo)
        self.assertIn("ghMount(", repo)


@unittest.skipUnless(NODE, "node 없음 — 화면 조각을 실행할 수 없다")
class TheSentencesComeFromTheState(unittest.TestCase):

    def test_g2_alone_says_where_the_record_stays(self):
        """G2. 이어지지 않은 자리 — 없는 것이 아니라 지금 어떤 상태인지를 말한다."""
        say = probe("ghStateSay(ALONE)".replace("ALONE", json.dumps(ALONE)))
        self.assertEqual(
            say, "GitHub 과 연결되어 있지 않습니다 — 지금은 이 컴퓨터에만 남습니다.")
        html = probe("ghStateHTML(%s)" % json.dumps(ALONE))
        self.assertNotIn("origin ", html)          # 없는 주소를 그리지 않는다
        self.assertNotIn("<a", html)

    def test_g3_linked_says_where_and_what_goes_out(self):
        """G3. 이어진 자리 — origin · branch · 나가는가. 동기화 모드가 갈린다."""
        self.assertEqual(
            probe("ghStateSay(%s)" % json.dumps(LINKED)),
            "origin https://github.com/me/box · main · 문서가 바뀔 때마다 push 합니다")
        local = dict(LINKED, sync_mode="local")
        self.assertTrue(probe("ghStateSay(%s)" % json.dumps(local))
                        .endswith("지금은 내보내지 않습니다(local)"))
        # 화면에서는 그 주소가 손잡이다 — 누르면 GitHub 이 열린다.
        html = probe("ghStateHTML(%s)" % json.dumps(LINKED))
        self.assertIn('href="https://github.com/me/box"', html)
        self.assertIn("ghlink", html)

    def test_g4_what_is_ready_and_who_i_am(self):
        """G4. 준비물 네 갈래 — 하나도 없을 때만 할 일을 말하고 길을 준다."""
        def say(gh, tok, login=""):
            st = dict(ALONE, auth={"gh": gh, "token": tok, "login": login})
            return probe("[ghPrepSay(%s), ghPrepNeeds(%s)]"
                         % (json.dumps(st), json.dumps(st)))
        s, need = say(True, False, "me")
        self.assertEqual(s, "gh 로 로그인했습니다 — GitHub 계정 me")
        self.assertFalse(need)
        s, need = say(False, True, "me")
        self.assertEqual(s, "GITHUB_TOKEN 을 저장해 두었습니다 — GitHub 계정 me")
        self.assertFalse(need)
        s, need = say(True, True, "me")
        self.assertIn("둘 다 있습니다", s)
        self.assertFalse(need)
        s, need = say(False, False)
        self.assertEqual(
            s, "gh 로 로그인하거나 외부 서비스 판에 GITHUB_TOKEN 을 저장하면 됩니다.")
        self.assertTrue(need, "준비물이 없을 때만 「외부 서비스 판 열기」가 선다")

    def test_g5_a_locked_hand_shows_the_servers_own_sentence(self):
        """G5. 막힌 사유는 서버의 문장 그대로 — 화면이 제 문장을 짓지 않는다."""
        why = ALONE["can"]["create"]["why"]
        self.assertEqual(probe("ghWhySay('create', %s, '')" % json.dumps(ALONE)), why)
        # 열린 자리에서는 무엇을 하는지 말한다(서버는 빈 문장을 보낸다).
        self.assertIn("첫 push",
                      probe("ghWhySay('link', %s, '')" % json.dumps(ALONE)))
        # 다른 손잡이가 도는 동안에는 그 사실이 먼저다.
        self.assertEqual(probe("ghWhySay('link', %s, 'create')" % json.dumps(ALONE)),
                         "지금 만드는 중입니다.")


class TheWords(unittest.TestCase):
    """G6. 낱말 — 남의 도구가 지은 이름은 원어로, 우리가 하는 일은 우리 말로."""

    def test_g6_the_screen_keeps_the_names_it_did_not_make(self):
        src = _src("app/github.js")
        # 화면에 서는 글자만 본다 — 주석은 설명이지 화면의 말이 아니다.
        screen = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        screen = re.sub(r"^\s*//.*$", "", screen, flags=re.M)
        # 찾는 글자를 그대로 적으면 test_button_word 가 이 줄을 잡는다 — 뜻은 같고 글자만 escape
        self.assertNotIn("\ub2e8\ucd94", screen, "버튼은 「버튼」이다 (용어표 DOC-20260906-002)")
        for word in ("push", "origin", "GitHub", "private", "public",
                     "gh", "GITHUB_TOKEN"):
            self.assertIn(word, screen, f"{word} 는 원어로 선다")
        for word in ("잇기", "끊기", "만들기", "저장소", "준비물"):
            self.assertIn(word, screen, f"「{word}」 는 우리 말로 선다")
        # 옮기기로 판정된 자리에 원어가 남아 있지 않다 (tech-writer 판정).
        self.assertNotIn("리포지토리", screen)
        self.assertNotIn("URL을", screen)     # 라틴 뒤에는 한 칸 띄운다


if __name__ == "__main__":
    unittest.main()
