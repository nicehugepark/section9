"""확인 창의 맨 Enter 는 물러나는 쪽에 선다 (REQ-20260830-008-62x6).

실사고: 세우기(중단) 확인 창이 바닥에 「그대로 두기 / 중단하기」를 세워 놓고
`safe` 를 안 들고 있었다. 창은 열리자마자 「중단하기」에 초점을 주었고, 창을
읽지 않고 Enter 를 치는 손이 도는 작업을 세웠다.

`s9dlg` 는 이미 이 판단을 내려 두었다(dialog.js: "되돌릴 수 없는 창은 물러나는
쪽에서 시작한다"). 문제는 그 판단이 **창마다 따로 손으로 켜지는 깃발**이라는
것이다 — 새 창을 만드는 사람은 깃발이 있는지도 모른 채 지나간다. 실제로
지나갔고, 훑어 보니 세우기 하나가 아니었다.

한 창만 다르면 그 차이가 곧 손의 습관을 배신한다. 그래서 초점을 **대장으로
못박는다**: 확인 창은 전부 이 표에 이름이 있어야 하고, 표가 적은 대로 초점을
둔다. 새 창을 만들면 이 시험이 먼저 막는다 — 초점을 정하지 않고는 못 지난다.

기준 하나: **되돌려도 그 사이에 잃는 것이 있으면 물러나는 쪽에서 시작한다.**
  · 파괴적 — 되돌릴 수 없는 소실(영구 삭제·비밀 삭제·빈 계정 자리)
  · 중단적 — 되돌릴 수 있어도 그 사이에 도는 작업이 하던 일을 잃는다
  둘 중 하나면 safe. 되돌리면 원상복구고 잃는 것이 없으면 주 행동에 둔다
  (휴지통으로·취소하기 — 창의 설명이 스스로 "되돌릴 수 있습니다"라고 적는다).

계약 넷:
  F1 확인 창은 전부 대장에 있다 (새 창은 초점을 정해야 지난다).
  F2 대장이 safe 라 적은 창만 `safe` 를 들고 있다.
  F3 `safe` 는 확인 창에만 선다 — 알림은 물러날 버튼이 없고, 쓰는 창은
     초점이 상자로 가므로 거기 붙은 safe 는 지키지 못할 약속이다.
  F4 세우기 창이 safe 를 들고 있다 (회귀).

실행: python3 tests/ dialog_safe
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
APP = os.path.join(ROOT, "web", "app")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


# ---- 창 모양 뽑기 ---------------------------------------------------------
# `s9dlg({...})` 로 바로 부르는 자리와, 진단(diag.js)이 미리 세워 두고 나중에
# 넘기는 모양 리터럴을 **함께** 잡아야 한다. 둘 다 결국 같은 창이 되고, 거울만
# 옛 초점이면 캡처가 거짓을 증언한다. 그래서 호출을 좇지 않고 `kind` 를 적은
# **객체 리터럴**을 좇는다.
_KIND = re.compile(r'kind:\s*"(alert|confirm|prompt|choose)"')


def _obj_span(src, at):
    """`at` 을 품은 가장 안쪽 `{...}` — 문자열·주석 안의 괄호는 세지 않는다."""
    open_at, stack = None, []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "\"'`":
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c:
                    break
                j += 1
            i = j + 1
            continue
        if c == "{":
            stack.append(i)
        elif c == "}":
            if not stack:
                i += 1
                continue
            start = stack.pop()
            if start <= at < i:
                return (start, i + 1)
        i += 1
    return (open_at, None)


def _field(body, key):
    """`key: "값"` 의 값, 또는 `key: IDENT` 의 이름. 없으면 None."""
    m = re.search(r'(?<![\w$])%s:\s*"([^"]*)"' % key, body)
    if m:
        return m.group(1)
    m = re.search(r'(?<![\w$])%s:\s*([A-Za-z_$][\w$]*)' % key, body)
    return m.group(1) if m else None


def dialog_shapes():
    """[(파일, kind, ok, cancel, safe인가)] — 화면이 세우는 창 전부.

    `kind` 를 적은 객체 리터럴을 좇되, **안 적은 것도 함께** 잡는다:
    `s9dlg` 의 기본값이 confirm 이라(`const kind = o.kind || "confirm"`)
    kind 없이 부른 창은 조용히 확인 창이 되고, 대장을 그냥 지나가 버린다."""
    out, seen = [], set()
    for fn in sorted(os.listdir(APP)):
        if not fn.endswith(".js"):
            continue
        src = read(os.path.join(APP, fn))
        spans = []
        for m in _KIND.finditer(src):
            spans.append((_obj_span(src, m.start()), m.group(1)))
        for m in re.finditer(r"s9dlg\(\{", src):
            spans.append((_obj_span(src, m.end()), "confirm"))
        for (a, b), kind in spans:
            if b is None or (fn, a, b) in seen:
                continue
            seen.add((fn, a, b))
            body = src[a:b]
            safe = re.search(r'(?<![\w$])safe:\s*true', body) is not None
            out.append((fn, kind, _field(body, "ok"),
                        _field(body, "cancel"), safe))
    return out


# ---- 대장 -----------------------------------------------------------------
# (파일, ok, cancel) → (safe 인가, 왜)
#
# 두 낱말을 함께 열쇠로 쓰는 것은 restart.js 가 같은 주 버튼(「중단하고 바꾸기」)
# 으로 창을 둘 세우기 때문이다 — 물러나는 낱말이 그 둘을 가른다.
CENSUS = {
    ("session.js", "지우기", "그만두기"):
        (True, "로그인 전 빈 자리를 지운다 — 되돌릴 수 없다"),
    ("userform.js", "그래도 넣기", "그만두기"):
        (False, "값을 하나 넣을 뿐이고, 넣어도 쓰이지 않는다"),
    ("userform.js", "지우기", "그만두기"):
        (True, "지운 비밀 값은 되살릴 수 없고 그 키를 쓰는 도구가 멈춘다"),
    # 세우기 창은 갈래(백그라운드 작업·창·일손)마다 문안이 다르지만 **자리는 하나**다
    # — 주 낱말이 표(STOP_KIND)에서 오므로 대장의 열쇠도 그 표를 읽는 이름이다
    # (REQ-20260830-035). 물러나는 낱말은 넷 다 「그대로 두기」로 같다.
    ("card.js", "stopAsk", "그대로 두기"):
        (True, "도는 작업을 세운다 — 되살려도 하던 일은 잃는다 (REQ-20260829-024)"),
    ("card.js", "취소하기", "그만두기"):
        (False, "창이 스스로 적는다 — 되돌리려면 다시 옮기면 된다"),
    ("restart.js", "중단하고 바꾸기", "그대로 두기"):
        (True, "이 세션이 하던 일을 중단한다"),
    ("restart.js", "중단하고 바꾸기", "그만두기"):
        (True, "도는 백그라운드 작업 여러 건을 한꺼번에 중단한다"),
    # 한도로 막힌 자리의 탈출구 (REQ-20260901-014). 누르면 모델 고르는 창이
    # 열릴 뿐이고, 거기서 한 번 더 「다시 시작」을 눌러야 무엇이 바뀐다 —
    # 이 창에서는 잃는 것도 도는 것도 없다. 게다가 여기는 **막다른 길**이라
    # 주 행동이 곧 나가는 문이다: 물러나는 쪽에서 시작하면 Enter 가 사람을
    # 같은 벽 앞에 다시 세운다.
    ("session.js", "다른 모델로 바꾸기", "닫기"):
        (False, "모델 고르는 창을 열 뿐이다 — 막힌 자리의 나가는 문이라 주 행동에 둔다"),
    ("tidy.js", "영구 삭제", "그만두기"):
        (True, "창 제목이 그대로 적는다 — 되돌릴 수 없다"),
    ("tidy.js", "휴지통으로", "그만두기"):
        (False, "휴지통에서 되돌릴 수 있다"),
    # 프로젝트 화면 (REQ-20260831-028). 문안이 PRJ_TEXT 한 표에서 오므로 열쇠도
    # 그 표를 읽는 이름이다 — card.js 의 `stopAsk` 와 같은 방식.
    ("project.js", "dlgOk", "dlgCancel"):
        (False, "새 프로젝트를 만든다 — 만들어 놓고 보관하면 그만이다"),
    ("project.js", "rmOk", "dlgCancel"):
        (False, "문서는 그대로 남고, 다시 넣으면 원상복구다 — 결과가 남에게 가는"
                " 관리 행위라 주 행동에서 시작한다"),
    # 나가는 것은 **결과가 나에게 온다** — 되돌리려면 남은 maintainer 이상이
    # 넣어 주어야 하고, 그 사이 나는 이 프로젝트를 못 본다 (REQ-20260831-029).
    ("project.js", "leaveOk", "dlgCancel"):
        (True, "제 자리를 버리는 행위다 — 혼자서는 되돌릴 수 없다"),
    # 백그라운드 작업 설정 (REQ-20260901-022). 켜는 쪽에만 마찰이 선다 — 끄는 쪽은
    # 권한을 거두는 방향이라 확인이 손만 는다. 창의 설명이 스스로 적는 대로,
    # 되돌려도 그 사이에 한 일은 못 되돌린다 (REQ-20260902-001).
    ("workercfg.js", "권한 주기", "그만두기"):
        (True, "이 창 밖에서 도는 백그라운드 작업에 GitHub 계정 권한을"
               " 준다 — 껐어도 켜져 있는 동안 한 일은 못 되돌린다"),
    # 화면에서 push (REQ-20260901-023). pull 은 창이 없다 — 되돌릴 수 있는 쪽에
    # 마찰을 물리지 않는다(022 의 gh 스위치가 세운 그 규칙: 켤 때만 창).
    #
    # push 를 safe 로 판정한 근거는 **되돌릴 수 없는 소실이 아니라 되돌릴 수
    # 없는 공개**다. 이 저장소의 origin 은 PUBLIC 이라 한 번 나간 것은 남이
    # 이미 가져갈 수 있고, 되돌리려면 갈래를 다시 쓰는 명령이 필요한데 그
    # 명령은 화면이 아예 부르지 못하게 짜여 있다(bin/s9 GIT_FORBIDDEN).
    # 「권한 주기」가 같은 축에서 safe 인 것보다 한 급 더 확정적이다.
    ("repo.js", "push", "그만두기"):
        (True, "GitHub 으로 나간 것은 남이 이미 가져갈 수 있다 — 이 화면은"
               " 되돌리는 명령을 부르지 못한다"),
    # 진단이 세우는 거울 — 본 창과 같은 표를 따른다
    ("diag.js", "취소하기", "그만두기"): (False, "card.js 취소하기의 거울"),
    ("diag.js", "지우기", "그만두기"): (True, "session.js 계정 자리 지우기의 거울"),
    ("diag.js", "중단하고 바꾸기", "그대로 두기"): (True, "restart.js 세션 중단의 거울"),
}


class DialogSafeFocus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shapes = dialog_shapes()
        cls.confirms = [s for s in cls.shapes if s[1] == "confirm"]

    def test_dialog_safe_focus(self):
        """DialogSafeFocus 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("f0_shapes_were_actually_read"):
                self.assertGreater(len(self.shapes), 20, "창 모양을 못 읽었다")
                self.assertGreater(len(self.confirms), 9, "확인 창을 못 읽었다")

            # ---- F1. 확인 창은 전부 대장에 있다 ----------------------------------
        with self.subTest("f1_every_confirm_is_on_the_census"):
                seen = set()
                for fn, _k, ok, cancel, _safe in self.confirms:
                    key = (fn, ok, cancel)
                    seen.add(key)
                    self.assertIn(key, CENSUS,
                                  f"{fn}: 대장에 없는 확인 창이다 ({ok} / {cancel}) — "
                                  f"맨 Enter 가 어디에 닿아야 하는지 tests/"
                                  f"test_dialog_safe.py 의 CENSUS 에 적어라")
                missing = sorted(set(CENSUS) - seen)
                self.assertEqual(missing, [], "대장에는 있는데 화면에 없는 창이다 — "
                                              "지웠으면 대장에서도 지워라")

            # ---- F2. 대장이 적은 대로 초점을 둔다 --------------------------------
        with self.subTest("f2_focus_matches_the_census"):
                for fn, _k, ok, cancel, safe in self.confirms:
                    want, why = CENSUS[(fn, ok, cancel)]
                    if want:
                        self.assertTrue(safe, f"{fn}: 「{ok}」 창이 물러나는 쪽에서 "
                                              f"시작하지 않는다 — {why}. `safe: true` 를 "
                                              f"세워라")
                    else:
                        self.assertFalse(safe, f"{fn}: 「{ok}」 창은 물러설 이유가 없다 "
                                               f"— {why}. `safe` 를 빼라")

            # ---- F3. safe 는 확인 창에만 선다 ------------------------------------
        with self.subTest("f3_safe_only_where_it_can_be_kept"):
                for fn, kind, ok, _cancel, safe in self.shapes:
                    if kind == "confirm" or not safe:
                        continue
                    self.fail(f"{fn}: {kind} 창(「{ok}」)에 safe 가 붙었다 — "
                              f"이 종류는 초점을 그리로 옮기지 않는다")

            # ---- F4. 세우기 창 (회귀) --------------------------------------------
        with self.subTest("f4_the_stop_dialog_starts_on_leaving_it_alone"):
                hit = [s for s in self.confirms
                       if s[0] == "card.js" and s[2] == "stopAsk"]
                self.assertEqual(len(hit), 1, "세우기 확인 창을 못 찾았다 — "
                                              "ok: stopAsk.ok 가 바뀌었나")
                self.assertEqual(hit[0][3], "그대로 두기", "물러나는 낱말이 바뀌었다")
                self.assertTrue(hit[0][4], "세우기 창의 맨 Enter 가 아직 「중단하기」에 "
                                           "닿는다 — 읽지 않고 Enter 를 치는 손이 도는 "
                                           "작업을 세운다 (REQ-20260830-008)")

            # ---- 바닥 힌트가 같은 깃발을 읽는다 ----------------------------------
        with self.subTest("f5_the_hint_reads_the_same_flag"):
                src = read(os.path.join(APP, "dialog.js"))
                self.assertIn('o.safe ? (o.cancel || "그만두기")', src,
                              "바닥 힌트가 safe 를 읽지 않는다")
                self.assertIn("(o.safe && no ? no : yes).focus()", src,
                              "초점이 safe 를 읽지 않는다")

            # ---- F6. 갈래마다 물어본다 (REQ-20260902-005 안전 함정) --------------
        with self.subTest("f6_every_running_kind_still_carries_a_question"):
            src = read(os.path.join(APP, "card.js"))
            m = re.search(r"const STOP_KIND = \{([\s\S]*?)\n\};", src)
            self.assertIsNotNone(m, "STOP_KIND 표를 못 찾았다")
            body = m.group(1)
            # 표의 한 급 들여쓴 이름만 = 갈래. 그 다음 갈래 전까지가 제 몫이다.
            keys = [(mm.group(1), mm.start()) for mm in
                    re.finditer(r"(?m)^  (\w+): \{", body)]
            self.assertTrue(keys, "갈래를 하나도 못 읽었다")
            slices = {}
            for i, (name, at) in enumerate(keys):
                end = keys[i + 1][1] if i + 1 < len(keys) else len(body)
                slices[name] = body[at:end]

            with open(os.path.join(ROOT, "bin", "s9"), encoding="utf-8") as f:
                s9 = f.read()
            # 갈래를 내는 함수 하나만 본다 — 파일 전체를 훑으면 「자리」의
            # main/worktree 같은 남의 kind 가 섞여 든다.
            fn = re.search(r"\ndef stoppable_verdict\([\s\S]*?\n\ndef ", s9)
            self.assertIsNotNone(fn, "stoppable_verdict 를 못 찾았다")
            server = set(re.findall(r'return \{"kind": "(\w+)"', fn.group(0)))
            self.assertTrue(server >= {"worker", "session", "agent", "idle"},
                            "서버가 내는 갈래를 못 읽었다: %s" % sorted(server))
            self.assertEqual(sorted(server), sorted(slices),
                             "서버가 내는 갈래와 화면의 문안 표가 어긋난다 — "
                             "빠진 갈래는 확인 창 없이 중단된다")

            for kind in sorted(server - {"idle"}):
                self.assertIn("ask: {", slices[kind],
                              "「%s」 갈래에 확인 창이 없다 — 되돌릴 수 없는 중단이 "
                              "말없이 실행된다 (card.js 의 `!stopAsk` 갈래)" % kind)
            # idle 만 예외이고, 그것도 **까닭이 있어서** 예외다: 붙어 있는 손이
            # 없어 잃는 것이 없고 「▶ 이어가기」 한 번으로 되돌아간다.
            self.assertNotIn("ask: {", slices["idle"],
                             "잃는 것이 없는 갈래에 확인 창을 세웠다 — 확인은 "
                             "되돌릴 수 없을 때만이다 (s9-design 4절)")

if __name__ == "__main__":
    unittest.main()
