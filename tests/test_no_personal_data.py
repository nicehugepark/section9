"""이 설치의 개인정보는 배포되는 코드에 나오지 않는다 (REQ-20260921-024-62x6).

주인 지적 2026-09-21: 「개인정보를 기본 코드에 받아놓지 마!」. Settings 의 성·이름
칸 예시가 주인의 실제 이름이었고, 주석·시험·안내 문서에는 계정 id·컴퓨터 이름·
OS 계정·사내 메일이 250곳 넘게 박혀 있었다. 그 코드를 받는 팀은 남의 이름을
자기 화면에서 읽게 된다.

`test_no_secret_names` 와 같은 모양이다 — 금지어 목록을 손으로 적지 않고 **이
설치가 제 데이터에 적어 둔 값**에서 뽑는다. 그래야 어느 설치에서 돌려도 그
사람의 것을 지킨다.

재는 자리는 **배포되는 것**뿐이다: `.gitattributes` 의 `export-ignore` 가 빼는
`vault/`·`users/`·`projects/`·`state/` 는 이 설치의 데이터라 제 이름이 있는 것이
당연하다. 남는 `bin/`·`web/`·`harness/`·`tests/`·`docs/`·`.github/` 가 태그를 따
받는 사람의 저장소에 들어가는 것이다.

실행: python3 tests/ no_personal_data
"""
import json
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
USERS = os.path.join(REPO, "users")

# 제품이 화면과 시험에서 쓰는 **예시** 이름 — 실제 사람이 우연히 같은 이름이어도
# 이 글자들은 세지 않는다. 세면 예시 자체가 실패가 되어 아무도 못 고친다.
EXAMPLES = {"hong", "hgpark", "홍길동", "홍", "길동", "bob", "carol", "alice",
            "tester", "user1", "user2", "e7test"}
# 이 저장소가 늘 쓰는 낱말 — OS 계정이 우연히 같아도(CI 의 runner 처럼) 세지 않는다.
VOCAB = {"runner", "worker", "admin", "member", "viewer", "general", "claude",
         "agent", "section9", "docker", "ubuntu", "build", "guest", "local"}
SCAN = ("bin", "web", "harness", "tests", "docs", ".github", "README.md")
THIS = os.path.basename(__file__)


def profiles():
    """users/*/profile.md 의 프론트매터를 읽어 돌려준다."""
    if not os.path.isdir(USERS):
        return []
    out = []
    for name in sorted(os.listdir(USERS)):
        p = os.path.join(USERS, name, "profile.md")
        if not os.path.isfile(p):
            continue
        head = {}
        src = open(p, encoding="utf-8").read()
        if src.startswith("---"):
            for ln in src.split("---", 2)[1].splitlines():
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    head[k.strip()] = v.strip()
        out.append((name, head))
    return out


def candidates():
    """이 설치가 제 데이터에 적어 둔 개인 식별자들."""
    got = set()
    for name, head in profiles():
        # 예시 계정(user1 · e7test …)의 값은 예시다 — 그 사람의 것이 아니다.
        if name.lower() in EXAMPLES:
            continue
        got.add(name)
        for key in ("first_name", "last_name", "display", "full", "email", "github",
                    "registered_on"):
            got.add(head.get(key, ""))
        for key in ("os_accounts", "emails", "machines"):
            raw = head.get(key, "")
            if raw.startswith("["):
                try:
                    got.update(str(x) for x in json.loads(raw))
                except ValueError:
                    pass
        mj = os.path.join(USERS, name, "machines.json")
        if os.path.isfile(mj):
            try:
                got.update(json.load(open(mj, encoding="utf-8")).keys())
            except (ValueError, OSError):
                pass
    keep = set()
    for c in got:
        c = (c or "").strip().strip('"')
        low = c.lower()
        if not c or low in EXAMPLES or low in VOCAB:
            continue
        # 한글 이름은 두 글자면 사람 이름이고, 로마자는 다섯 글자부터 본다 —
        # 그보다 짧은 것은 이 저장소의 보통 낱말과 겹쳐 거짓 실패를 만든다.
        han = re.search(r"[가-힣]", c)
        if len(c) >= (2 if han else 5):
            keep.add(c)
    return sorted(keep)


def shipped():
    """배포되는 추적 파일 (export-ignore 가 빼는 데이터 경로는 제외)."""
    r = subprocess.run(["git", "ls-files", "--"] + list(SCAN),
                       cwd=REPO, capture_output=True, text=True, timeout=60)
    return [f for f in r.stdout.split() if os.path.basename(f) != THIS]


class NoPersonalData(unittest.TestCase):
    def test_this_installs_identity_does_not_ship(self):
        names = candidates()
        if not names:
            self.skipTest("이 설치에 등록된 사람 정보가 없다 — 지킬 재료가 없다")
        pat = re.compile("|".join(re.escape(n) for n in names))
        hits = []
        for rel in shipped():
            p = os.path.join(REPO, rel)
            try:
                src = open(p, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            for i, ln in enumerate(src.splitlines(), 1):
                m = pat.search(ln)
                if m:
                    hits.append("%s:%d  %s" % (rel, i, m.group(0)))
        self.assertFalse(hits, "배포되는 파일에 이 설치의 개인정보가 있습니다 —"
                         " 일반 예시(hong · 홍길동 · DESKTOP-1A2B3C)로 바꾸세요:\n  "
                         + "\n  ".join(hits[:40]))


if __name__ == "__main__":
    unittest.main()
