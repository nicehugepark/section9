"""프로젝트 초대 화면 (REQ-20260913-012-62x6).

계약 B 를 **그대로 그리는** 화면이라, 이 시험이 지키는 것은 거의 전부 **양쪽이
같은 말을 하는가**다: 화면이 쓰는 이메일 잣대와 서버의 잣대 · 화면이 옮기는
사유 문장과 서버가 실제로 내는 문장 · Settings 의 SMTP 다섯 칸과 서버가 읽는
시크릿 키. 이 셋 중 하나라도 갈리면 화면은 조용히 거짓말을 시작한다 — 값은
멀쩡한데 사람이 읽는 문장만 틀리므로 캡처로도 안 잡힌다.

실브라우저 확인(눌러 보기·보내기·복사)은 REQ 문서의 캡처가 진다 — 여기서는
그 흐름을 지탱하는 규율만 본다.

실행: python3 tests/ invite_ui
"""
import importlib.machinery
import importlib.util
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PRJ = os.path.join(ROOT, "web", "app", "project.js")
JIRA = os.path.join(ROOT, "web", "app", "jira.js")


def src(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def invite_module():
    """bin/s9_invite.py 를 s9 없이 읽는다 — 여기서 보는 것은 상수뿐이라 bind 가 없어도 된다."""
    p = os.path.join(ROOT, "bin", "s9_invite.py")
    spec = importlib.util.spec_from_loader(
        "s9_invite_ro", importlib.machinery.SourceFileLoader("s9_invite_ro", p))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class InviteScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prj = src(PRJ)
        cls.jira = src(JIRA)
        cls.inv = invite_module()

    # ── S1. 초대 줄은 관리할 수 있는 사람에게만, 표의 두 얼굴 모두에 ──────────
    def test_s1_the_invite_line_follows_the_member_table(self):
        self.assertIn("function prjInviteLineHTML(", self.prj)
        # 멤버가 하나도 없어 추가 행이 설 수 없는 자리에서도 서야 한다 — 계정이
        # 없는 사람을 부르는 길은 그 막다른 자리에서 가장 필요하다.
        body = self.prj.split("function prjMembersHTML(")[1].split("\nfunction ")[0]
        self.assertIn('const inv = c.canManage ? prjInviteLineHTML(p) : "";', body)
        self.assertIn(") + inv;", body, "빈 표(멤버도 후보도 없는 자리)에 초대 줄이 없다")
        self.assertIn("\n    + inv\n", body, "있는 표에 초대 줄이 없다")
        # 회색 나열 금지 — 못 누르는 손잡이를 그리지 않는다(멤버 표의 규율 그대로)
        self.assertNotIn("disabled", src(PRJ).split("function prjInviteLineHTML(")[1]
                         .split("\n}")[0])

    # ── S2. 미리 보기는 저장이 아니다 ────────────────────────────────────────
    def test_s2_the_preview_writes_nothing(self):
        wire = self.prj.split("function prjInviteWire(")[1].split("\n/* 창 하나에")[0]
        self.assertIn("send: false", wire)
        # 다시 읽지 않는다 — 문서가 바뀐 것이 없다(reload 를 주면 판이 헛돈다)
        pre = wire.split("send: false")[1].split("});")[0]
        self.assertNotIn("reload", pre, "미리 보기가 판을 다시 읽는다 — 바뀐 것이 없다")
        # 명령 두 줄과 본문에 복사 손잡이 — 셋 다 같은 부품(글자 버튼)
        prev = self.prj.split("function prjInvitePrevHTML(")[1].split("\nfunction ")[0]
        self.assertIn("data-pjicopy", prev, "합류 명령 줄에 복사 손잡이가 없다")
        self.assertIn('data-pjicopy="body"', prev, "본문 복사가 없다 — 준비물 없는 자리의 유일한 길이다")
        self.assertIn("PRJ_TEXT.invCopyBody", prev)

    # ── S3. 준비물이 없으면 잠그고, 그 까닭은 한 곳에서 온다 ─────────────────
    def test_s3_without_smtp_the_send_is_locked(self):
        body = self.prj.split("function prjInviteBodyHTML(")[1].split("\nfunction ")[0]
        self.assertIn("st.smtp && !st.smtp.ready", body, "준비 여부를 서버에 묻지 않는다")
        self.assertIn("PRJ_TEXT.invNoSmtp", body)
        wire = self.prj.split("function prjInviteWire(")[1].split("\n/* 창 하나에")[0]
        self.assertIn("st.smtp.ready !== false", wire)
        self.assertIn("yes.disabled = !ok() || !ready", wire)
        # 모르면 잠그지 않는다 — 화면이 없는 사유를 지어내지 않는다(서버가 말한다)
        self.assertIn("!st || !st.smtp", wire)

    # ── S4. 서버가 내는 사유 문장을 화면이 실제로 잡는가 ─────────────────────
    def test_s4_the_screen_catches_the_sentences_the_server_really_sends(self):
        says = self.prj.split("errSay: [")[1].split("\n  ],")[0]
        pats = [re.compile(p) for p in re.findall(r"\[/([^/]+)/,", says)]
        for sentence in (self.inv.NOT_LINKED, self.inv.SMTP_MISSING):
            self.assertTrue(any(p.search(sentence) for p in pats),
                            f"서버 문장을 옮길 자가 없다: {sentence!r}")

    # ── S5. 이메일 잣대는 서버와 같다 ────────────────────────────────────────
    def test_s5_the_email_rule_is_the_servers_rule(self):
        m = re.search(r"const PRJ_EMAIL_RE = /\^(.+)\$/;", self.prj)
        self.assertTrue(m, "PRJ_EMAIL_RE 가 없다")
        with open(os.path.join(ROOT, "bin", "s9.py"), encoding="utf-8") as f:
            server = re.search(r'^EMAIL_RE = r"(.+)"', f.read(), re.M).group(1)
        self.assertEqual(m.group(1).replace("\\s", "\\s"), server,
                         "화면과 서버의 이메일 잣대가 갈렸다")
        wire = self.prj.split("function prjInviteWire(")[1].split("\n/* 창 하나에")[0]
        self.assertIn("PRJ_EMAIL_RE.test", wire, "형식 검사 없이 서버에 400 을 받으러 간다")

    # ── S6. Settings 의 다섯 칸 = 서버가 읽는 시크릿 키 ─────────────────────
    def test_s6_the_settings_rows_are_the_keys_the_server_reads(self):
        rows = self.jira.split("const SMTP_ROWS = [")[1].split("\n];")[0]
        keys = re.findall(r'key: "([^"]+)"', rows)
        self.assertEqual(keys, list(self.inv.SMTP_KEYS), "칸과 시크릿 키가 갈렸다")
        # 값은 시크릿 한 경로로만 들어간다 — user config 로 새지 않는다
        panel = self.jira.split("async function smtpPut(")[1].split("\n}")[0]
        self.assertIn("/api/secret/set", panel)
        self.assertNotIn("/api/user/config", panel)
        # Jira 스위치가 꺼져도 이 절은 선다(다른 서비스다)
        self.assertIn("return head + jira + smtpSectionHTML();", self.jira)


if __name__ == "__main__":
    unittest.main()
