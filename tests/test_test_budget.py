"""늘어나는 문을 닫는다 — 소스 글자 계약은 더 늘지 않는다 (REQ-20260903-009).

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
「문이 하나뿐인가」 같은 중복 금지 게이트가 그것이다. 그런 계약은 이미 있는
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
READS_SOURCE = re.compile(
    r'\b[A-Za-z_]*(?:open|read|src|slurp|text)[A-Za-z_]*\(\s*(?:S9|DOCTOR|SRC|RUNNER|APP|WEB|[A-Z][A-Z0-9_]{1,})\s*[,)]'
    r'|\.read_text\(\)'
    r'|\b[A-Za-z_]*(?:open|read|src|slurp|text)[A-Za-z_]*\(\s*os\.path\.join\(\s*HERE\s*,\s*"\.\."')


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
            "  없음을 증명해야 하는 계약(금지어·중복 금지 게이트)이라 어쩔 수 "
            "없다면, tests/BUDGET.json 의 수를 올리고 그 까닭을 적어라.")

    def test_the_ratchet_tightens_when_we_do_better(self):
        """줄였으면 기준선도 따라 내려와야 한다 — 안 내리면 라쳇이 헐거워진다.

        느슨함을 조금 둔다(3): 파일 하나를 지웠다고 곧바로 붉어지면 사람이
        이 시험을 미워하게 되고, 미움받는 게이트는 오래 못 산다.
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
