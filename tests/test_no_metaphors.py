"""시험 결과의 비유(붉음·초록)는 코드에도 남지 않는다 (REQ-20260906-064).

규칙(PROTOCOL 2조)을 읽고도 리드가 「붉었습니다」로 되돌아갔다(2026-09-06 12:24).
그때 러너·guard·시험 안에 그 비유가 190여 곳 남아 있었다 — 에이전트는 읽은 말을
되쓴다. 이 시험은 소스에서 s9 의 금지 용어(BANNED_TERMS)를 찾는다. 화면의 색을
말하는 줄(「붉은 글자」「초록 점」)은 banned_terms_in 이 건너뛴다.
없음을 증명하는 계약이라 tests/BUDGET.json 의 소스 글자 계약 수에 들어 있다.

실행: python3 tests/ no_metaphors
"""
import glob
import importlib.machinery
import importlib.util
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")
# 용어 자체를 다루는 자리는 뺀다: 검사 정의·용어 시험·이 시험
SKIP = {"test_no_metaphors.py", "test_banned_terms.py"}
SKIP_LINE = ("BANNED_TERMS", "→「", "(→", "쓰지 않는 말", '", "실패', '", "통과')
# 화면 코드(web/app)는 색을 말하는 자리가 대부분이라 뜻이 하나뿐인 꼴만 본다
WEB_ONLY = ("붉음", "붉었", "붉으면", "초록 기록")


def _sources():
    pats = ["bin/s9.py", "bin/s9-guard", "bin/s9-install", "bin/s9-audit-*", "bin/s9-doctor",
            "tests/__main__.py", "tests/*.py", "harness/claude/gen_roster.py",
            "harness/common/PROTOCOL.md", "harness/common/onboarding/*.md",
            "web/app/*.js", "docs/*.md", "README.md"]
    out = []
    for pat in pats:
        out += [p for p in glob.glob(os.path.join(ROOT, pat)) if os.path.basename(p) not in SKIP]
    return sorted(set(out))


class NoMetaphors(unittest.TestCase):
    def test_test_result_metaphors_are_not_in_the_sources(self):
        spec = importlib.util.spec_from_loader(
            "s9_nometa", importlib.machinery.SourceFileLoader("s9_nometa", S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        # 시험 결과 비유만 — 나머지 표 항목(「봉투」「잔재」…)은 별도 손질 대상이라 여기서 세지 않는다
        terms = [(a, b) for a, b in m.BANNED_TERMS if a.startswith(("붉", "초록"))]
        offenders = []
        for path in _sources():
            with open(path, encoding="utf-8", errors="replace") as f:
                for no, line in enumerate(f, 1):
                    if any(k in line for k in SKIP_LINE):
                        continue
                    scope = terms if "/web/" not in path.replace(os.sep, "/") else \
                        [(a, b) for a, b in terms if a in WEB_ONLY]
                    hits = [a for a, _ in scope if a in line]
                    if not hits:
                        continue
                    # 색을 말하는 줄은 banned_terms_in 과 같은 기준으로 건너뛴다
                    if not [a for a, _ in m.banned_terms_in(line) if a.startswith(("붉", "초록"))]:
                        continue
                    offenders.append(f"{os.path.relpath(path, ROOT)}:{no} {hits}")
        self.assertEqual(offenders, [], "시험 결과의 비유가 소스에 남아 있다 — 실패·통과로 쓰라 "
                         "(규약 2조 ④, DOC-20260906-002):\n" + "\n".join(offenders[:40]))


# gate 를 「문」·「관문」·「게이트」로 부르던 비유 (REQ-20260907-071).
# 주인 지적 2026-09-07 20:24: 「문 확인에서 문이 뭐야?」 — 용어표
# DOC-20260906-002 이 이미 「문·커밋 문·게이트 → 검사」로 판정해 두고도 소스에는
# 683곳이 남아 있었다. 뜻은 넷으로 갈린다: 막는 장치 = 검사 / 모두가 지나는 한
# 자리 = 경로 / 들어오는 자리 = 진입점 / 나가는 자리 = 나가는 경로.
# 코드 식별자(concurrent_gate·s9-git-gate·wide_gate)는 이 저장소가 지은 **이름**이라
# 그대로 둔다 — 사람이 파일 이름과 함수 이름으로 다시 만나는 글자다.
GATE_RX = re.compile(
    r"(?<![가-힣])(관문|게이트|문)(?![서자제구장법맥의단화헌항명체양형물고건안답기턱예방])")
# 우리말 동사 「물다」의 활용 — 「한글을 문 것」·「상수를 문다」는 비유가 아니다
GATE_OK = re.compile(r"(을|를|글자를|상수를) 문[ 다것]")


class NoGateMetaphor(unittest.TestCase):
    """gate 를 「문」으로 부르지 않는다 — 검사·경로·진입점으로 적는다."""

    def test_the_gate_is_called_a_check_not_a_door(self):
        offenders = []
        for path in [p for p in _sources()] :
            in_table = False
            with open(path, encoding="utf-8", errors="replace") as f:
                for no, line in enumerate(f, 1):
                    # 용어를 다루는 표 자신은 그 용어를 적을 수밖에 없다 (BANNED_TERMS 블록)
                    if line.startswith("BANNED_TERMS = ("):
                        in_table = True
                    elif in_table and line.startswith(")"):
                        in_table = False
                    if in_table or not GATE_RX.search(line) or GATE_OK.search(line):
                        continue
                    offenders.append(f"{os.path.relpath(path, ROOT)}:{no} {line.strip()[:80]}")
        self.assertEqual(offenders, [], "gate 의 비유가 소스에 남아 있다 — 막는 것은 「검사」, "
                         "모두가 지나는 한 자리는 「경로」, 들어오는 자리는 「진입점」이다 "
                         "(규약 2조 ④, DOC-20260906-002):\n" + "\n".join(offenders[:40]))

    def test_the_english_name_door_is_not_a_test_name(self):
        """시험 이름·식별자에도 door 를 쓰지 않는다 — gate·path·entry 로 적는다."""
        rx = re.compile(r"(?<![A-Za-z])[Dd]oors?(?![A-Za-z])")
        offenders = [f"{os.path.relpath(p, ROOT)}:{no}"
                     for p in _sources()
                     for no, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1)
                     if rx.search(line)]
        self.assertEqual(offenders, [], "식별자에 door 가 남아 있다:\n" + "\n".join(offenders[:40]))


if __name__ == "__main__":
    unittest.main()
