"""늘어나는 것을 막는다 — 소스 글자 계약은 더 늘지 않는다 (REQ-20260903-009).

사용자: "테스트 항목이 너무 많아졌는데 이게 맞는건가 싶다. 줄일 수 없나?"
이어서: "본질은 테스트가 너무 오래걸리고 시스템에 부하를 준다는 사실을
해결하려는 것이다."

실측이 종류를 지목했다 — 시험 파일 290개·항목 3,281건·assert 8,253개 중
**소스 텍스트를 읽어 문자열을 검사하는 파일이 152개, 그 안의 assert 가 5,022개
(전체의 61%)** 였다. 그 종류가 나쁜 이유 셋:

  ① **동작을 안 잰다.** 「그 줄이 있다」와 「그 일이 된다」는 다르다.
  ② **리팩터에 깨진다.** 하루에 두 번 깨졌다 — 함수가 `assignDoc` 에서
     `assignPick` 으로 옮겨 갔을 때, 그리고 주석 한 문단이 소스 1400자
     검사 창을 밀어냈을 때.
  ③ **값싸다.** 그래서 끝없이 늘어난다. 이 그래프의 모양이 그것이다.

**그래서 이 시험은 라쳇이다.** 그런 파일의 수는 줄어들 수는 있어도 늘어날 수
없다. 새 시험을 막지는 않는다 — **동작을 재는 새 시험은 얼마든지 환영이다.**
막는 것은 "소스에 그 글자가 있나"를 새로 한 벌 더 만드는 일뿐이다.

## 그래도 소스 글자를 봐야 할 때

**없음을 증명해야 하는 것**은 부를 수가 없다 — 화면 문구의 금지어,
「경로가 하나뿐인가」 같은 중복 금지 검사가 그것이다. 그런 계약은 이미 있는
파일 안에서 늘려라. 새 파일을 세우려면 이 파일의 기준선을 사람이 올리면서
그 까닭을 함께 적으면 된다 — 막는 것이 아니라 **말없이 늘어나는 것**을 막는다.

실행: python3 tests/ test_budget
"""
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BUDGET = os.path.join(HERE, "BUDGET.json")

# 소스 텍스트를 읽어 들이는 모양 — 대문자 상수로 경로를 잡아 열거나
# `read_text()` 로 통째로 읽는 자리. 시험 자신의 임시 파일은 소문자 변수라
# 여기 안 걸린다.
# 헬퍼 경유도 센다 (REQ-20260905-011): read⟨S9_SRC⟩·_src⟨APP⟩ 처럼 소문자 이름의
# 헬퍼가 대문자 상수 경로를 받아 통째로 읽는 자리 — `open(` 만 보면 이 구멍으로 빠졌다.
# 그리고 tests 밖으로 나가는 경로(`os.path.join(HERE, ".."`)를 열어 읽는 자리도.
# 읽기 동사는 이름의 **끝**에 온다 (REQ-20260907-050). 종전엔 이름 어디에 있어도
# 세었는데, 그러면 소스와 아무 상관 없는 함수가 대문자 인자를 받는 것만으로 걸린다 —
# 실측: `browser_open_cmd(URL, …)` 가 「소스를 읽는다」로 세어져 완전히 동작만 재는
# 시험 파일(test_code_open.py)이 라쳇에 걸렸다. 진짜 소스 읽기는 `open(`·`read(`·
# `read_text(`·`slurp(` 처럼 동사로 끝난다. 좁힌 뒤 62개 목록은 그대로이고 그 오탐
# 하나만 빠졌다(전수 대조).
# 읽기 동사는 **이름의 한 마디**여야 한다 (REQ-20260908-009). 끝에 오는 것만으로는
# 모자랐다 — `_chat_context(SID, …)` 는 「context」의 끝 네 글자가 「text」라 걸렸고,
# 소스를 한 번도 안 읽는 파일(test_chat_documented.py)이 라쳇에 잡혔다. 마디 경계
# (`_` 또는 이름의 시작)를 요구하면 대문자 상수를 받는 `_src`·`read` 자리는 그대로
# 세면서 「context」·「pretext」 류만 빠진다. **이 주석에 그 호출 꼴을 그대로 적지
# 마라** — 이 파일 자신이 제 검사에 걸린다(실제로 한 번 걸렸다).
_VERB = r'_?(?:[A-Za-z0-9]+_)*(?:open|read|src|slurp|text)'
READS_SOURCE = re.compile(
    r'\b' + _VERB + r'\(\s*(?:S9|DOCTOR|SRC|RUNNER|APP|WEB|[A-Z][A-Z0-9_]{1,})\s*[,)]'
    r'|\.read_text\(\)'
    r'|\b' + _VERB + r'\(\s*os\.path\.join\(\s*HERE\s*,\s*"\.\."')


def scan(here=None):
    """(항목 수, 소스 글자 계약 파일 목록)."""
    here = here or HERE
    items, srcish = 0, []
    for name in sorted(os.listdir(here)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        try:
            with open(os.path.join(here, name), encoding="utf-8") as f:
                body = f.read()
        except OSError:
            continue
        items += len(re.findall(r"^    def test_", body, re.M))
        # **한 번 읽는 것은 이 종류가 아니다.** 동작 시험도 준비 삼아 소스를 한
        # 번 열 수 있다(모듈을 읽어 들이거나, 진입점 하나를 확인하거나).
        # 우리가 막으려는 것은 **소스를 몇 번이고 열어 글자만 대조하는 파일**이라,
        # 두 번 이상일 때만 그 종류로 센다. 실제로 이 문턱이 REQ-20260903-005 의
        # 윈도우 시험(대부분 동작인데 소스를 한 번 본다)을 오탐에서 건졌다.
        if len(READS_SOURCE.findall(body)) >= 2:
            srcish.append(name)
    return items, srcish


def read_budget(path=None):
    try:
        with open(path or BUDGET, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


class TheReadySignalIsMadeInOnePlace(unittest.TestCase):
    """실브라우저 시험은 준비 신호를 제 손으로 짓지 않는다 (REQ-20260907-057).

    판이 섰다는 신호는 스크립트가 실린 시점에 서고, 화면이 서버에서 받아 오는
    재료는 그 뒤 왕복으로 온다 — 그 틈이 병렬 실행에서 벌어져 **전체 실행에서만
    나는 간헐 실패**가 됐다(DOC-20260907-003). 파일마다 신호를 손으로 지으면 그
    틈을 파일마다 다시 발견하게 되므로, 신호는 `cdpreal.wait_ready` 한 자리에서
    짓는다. 여기서 막는 것은 **말없이 한 벌 더 생기는 것**이다 — 정말 달라야 할
    파일은 `cdpreal.HANDMADE_READY_OK` 에 사유를 적고 서면 된다.

    이 가드가 이 파일에 사는 까닭: 「없음을 증명하는」 계약은 부를 수가 없어
    소스를 봐야 하고, 그런 계약은 새 파일을 세우지 말고 이미 있는 파일 안에서
    늘리라는 것이 이 파일 머리의 규율이다.
    """

    def test_the_ready_signal_is_made_in_one_place(self):
        """준비 신호를 손으로 짓는 실브라우저 시험은 허용 목록에만 있다."""
        import cdpreal
        # 찾는 글자를 그대로 적으면 찾는 쪽이 먼저 걸린다 — 이름을 쪼개 둔다.
        needle = "__S9_APP" + "_READY"
        hand = []
        for name in sorted(os.listdir(HERE)):
            if not (name.startswith("test_") and name.endswith(".py")):
                continue
            with open(os.path.join(HERE, name), encoding="utf-8") as f:
                body = f.read()
            # 실브라우저 시험 = 공용 CDP 헬퍼를 쓰는 파일. web/ 이 그 신호를
            # 내보내는지 보는 시험은 신호를 기다리는 것이 아니라 계약을 보는
            # 것이라 여기 해당하지 않는다.
            if "cdpreal" in body and needle in body:
                hand.append(name)
        allowed = cdpreal.HANDMADE_READY_OK
        self.assertEqual(
            [n for n in hand if n not in allowed], [],
            "준비 신호를 제 손으로 짓는 실브라우저 시험이 있다 — "
            "cdpreal.wait_ready(needs=…, sels=…) 로 옮기거나, 정말 달라야 하면 "
            "cdpreal.HANDMADE_READY_OK 에 사유를 적어라")
        for name, why in allowed.items():
            self.assertTrue(str(why).strip(),
                            "허용 목록의 %s 에 사유가 없다 — 사유 없는 예외는 "
                            "다음 사람이 판정할 수 없다" % name)
            self.assertIn(name, hand,
                          "허용 목록의 %s 는 이제 손으로 안 짓는다 — 줄에서 빼라"
                          % name)


class TestBudget(unittest.TestCase):
    def test_the_source_string_contracts_do_not_grow(self):
        """라쳇 — 소스 글자 계약 파일은 줄어들 수는 있어도 늘 수 없다."""
        b = read_budget()
        self.assertIsNotNone(b, "tests/BUDGET.json 이 없다 — 기준선이 없으면 "
                                "라쳇이 아무것도 못 막는다")
        _items, srcish = scan()
        cap = int(b.get("source_contract_files", 0))
        if len(srcish) <= cap:
            return
        known = set(b.get("known", []))
        new = [n for n in srcish if n not in known]
        self.fail(
            f"소스 글자를 검사하는 시험 파일이 {cap} → {len(srcish)} 로 늘었다.\n"
            f"  새로 늘어난 것: {', '.join(new) or '(목록 밖)'}\n"
            "  이 종류는 동작을 재지 않고 리팩터에 깨지며 값싸서 끝없이 는다.\n"
            "  **동작을 재는 시험으로 바꿔라** — 불러서 값을 확인하면 된다.\n"
            "  없음을 증명해야 하는 계약(금지어·중복 금지 검사)이라 어쩔 수 "
            "없다면, tests/BUDGET.json 의 수를 올리고 그 까닭을 적어라.")

    def test_the_ratchet_tightens_when_we_do_better(self):
        """줄였으면 기준선도 따라 내려와야 한다 — 안 내리면 라쳇이 헐거워진다.

        느슨함을 조금 둔다(3): 파일 하나를 지웠다고 곧바로 실패하면 사람이
        이 시험을 미워하게 되고, 미움받는 검사는 오래 못 산다.
        """
        b = read_budget() or {}
        _items, srcish = scan()
        cap = int(b.get("source_contract_files", 0))
        self.assertLessEqual(
            cap - len(srcish), 3,
            f"실제 {len(srcish)}개인데 기준선이 {cap} 이다 — "
            "줄인 만큼 tests/BUDGET.json 을 낮춰 라쳇을 조여라")

    def test_the_numbers_are_visible(self):
        """숫자가 기록에 남아야 다음 사람이 방향을 안다."""
        items, srcish = scan()
        b = read_budget() or {}
        print(f"\n[시험 예산] 항목 {items} · 소스 글자 계약 파일 "
              f"{len(srcish)} (기준선 {b.get('source_contract_files')})")
        self.assertGreater(items, 0)


if __name__ == "__main__":
    unittest.main()
