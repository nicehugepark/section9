"""하네스는 OS 안쪽에 자리를 심지 않는다 (REQ-20260902-056 · DOC-20260903-004).

사용자 판정: "하네스 시스템이 os 시스템에 종속적인걸 원치 않는데, os 입장에서는
언제든지 사라질 수 있는데 애플리케이션이다. … 이런식으로 해결하는거라면 그냥
취소되는게 맞다."

가르는 물음 한 줄: **이 저장소를 지우면 그 설정도 함께 사라지는가.** 안 사라지면
OS 안쪽에 심은 것이고, 그건 해법이 아니라 취소 사유다.

**보는 것은 금지가 아니다.** `s9-doctor` 는 init 이 무엇인지 읽고 부팅이 왜
늦었는지 진단한다 — 그건 관찰이고, 심는 것과 다르다. 이 시험이 막는 것은
**등록·설치**뿐이다.

실행: python3 tests/ no_os_hooks
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 훑는 자리 — 우리가 실제로 실행하는 것들
SCAN_DIRS = ("bin", "harness")
SCAN_EXT = (".py", ".sh", ".cmd", ".md", "")

# 심는 행위. **관찰용 낱말(systemd·launchd 단독)은 여기 없다** — 그것까지 막으면
# 진단이 죽고, 진단은 이 규율의 반대편이 아니라 같은 편이다.
PLANT = {
    "systemd 유닛 등록": r"systemctl\s+(--user\s+)?(enable|link)\b",
    "launchd 등록": r"launchctl\s+(load|bootstrap)\b",
    "윈도우 작업 스케줄러 등록": r"schtasks\b[^\n]*/create",
    "cron 설치": r"crontab\s+(-|\S+\.cron)",
    "rc.local 쓰기": r">>?\s*/etc/rc\.local",
    "wsl.conf 쓰기": r"(tee|sed -i|>>)\s*[^\n]*?/etc/wsl\.conf",
    "시작 프로그램 레지스트리": r"CurrentVersion\\\\Run",
}


def _files():
    for d in SCAN_DIRS:
        base = os.path.join(ROOT, d)
        for dirpath, _dirnames, names in os.walk(base):
            if "__pycache__" in dirpath:
                continue
            for n in names:
                if n.endswith(SCAN_EXT):
                    yield os.path.join(dirpath, n)


def _code_lines(path):
    """주석·문서는 뺀다 — 이 규율을 **설명하는 글**까지 잡으면 시험이
    자기 문서를 물어뜯는다. 우리가 실행하는 줄만 본다."""
    try:
        with open(path, encoding="utf-8") as f:
            body = f.read()
    except (OSError, UnicodeDecodeError):
        return []
    out = []
    for i, ln in enumerate(body.splitlines(), 1):
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("//"):
            continue
        out.append((i, ln))
    return out


# ── 판을 가르는 자리는 문 하나를 지난다 (REQ-20260903-008) ────────────────
# 위의 규율이 「OS 안쪽에 심지 마라」라면, 이것은 그 형제다: **OS 를 가르는
# 일은 이름 붙은 문 안에서만 한다.** 문이 여럿이면 플랫폼 구멍도 여럿이 된다
# (REQ-20260829-037 이 그렇게 시작했다 — 맥에 `/proc` 이 없다는 사실이 네 자리에
# 흩어져 있었고, 그래서 네 자리가 다 틀렸다).
#
# 지금 서 있는 문 둘:
#   proc_backend  — 프로세스가 살아 있나·명령줄이 무엇인가 (proc/ps/win/none)
#   spawn_backend — 세션에서 떼어 띄우기 (fork/spawn)
#
# 아직 문이 없는 것들(`/proc` 직접 읽기·`ss` 호출·`fcntl`)은 **지금 수만큼만**
# 허용한다. 라쳇이라 늘 수 없고, 문을 세우면 줄어든다. 숫자를 여기 적어 두는
# 까닭은 그 숫자가 **남은 일의 크기**이기 때문이다 — 0 이 되면 이 판의 이식이
# 끝난 것이다.
PLATFORM_CALLS = {
    "os.fork": r"os\.fork\(",
    "/proc 직접 읽기": r'open\(\s*f?"/proc|open\("/proc',
    "ss 호출": r'"ss"\s*,|\bss -t',
    "fcntl": r"\bimport fcntl\b",
}

# 그 자리가 **문 안**이면 세지 않는다 — 문 안에서 가르는 것이 규율이 시키는
# 바로 그 일이다.
DOORS = ("_spawn_detached_fork", "_spawn_detached_subprocess", "spawn_backend",
         "proc_backend", "proc_table", "_proc_table_raw", "_proc_table_shared",
         "_proc_table_uncached", "pid_alive", "pid_cmdline", "pid_comm",
         # 회선에 붙어 있나 — 리눅스는 경로표, 맥·윈도우는 다른 자리다.
         # 문이 없는 판에서는 "모른다"고 답한다 (REQ-20260903-002).
         "link_backend")

# 2026-09-04 실측. **목표가 아니라 빚이다** — 내려갈 때만 고친다.
#
# `os.fork` 가 0 인 것은 이미 문을 세웠기 때문이다(REQ-20260903-005 가 계기와
# 감시자를 `spawn_detached` 로 옮겼다). 나머지 셋이 남은 일의 크기다:
#   /proc 16 — 가장 크고, 맥·윈도우가 **함께** 걸린다. `sys_backend()` 한 문이
#              필요하다(자원 표본·부팅 시각·소켓 통계·pid cmdline).
#   fcntl 4  — 잠금. 지금은 자리마다 `try/except ImportError` 라 import 는
#              살지만, 잠금 없이 도는 판의 계약이 어디에도 안 적혀 있다.
#   ss 1     — 소켓 목록. 맥은 `netstat`·`lsof` 다.
PLATFORM_BUDGET = {"os.fork": 0, "/proc 직접 읽기": 16, "ss 호출": 1,
                   "fcntl": 4}


def _outside_doors(path):
    """문 밖에서 판을 가르는 자리 — {이름: [줄번호…]}."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    door, out = False, {}
    for i, ln in enumerate(lines, 1):
        m = re.match(r"def (\w+)\(", ln)
        if m:
            door = m.group(1) in DOORS
        if door or ln.lstrip().startswith("#"):
            continue
        for what, pat in PLATFORM_CALLS.items():
            if re.search(pat, ln):
                out.setdefault(what, []).append(i)
    return out


class PlatformDoors(unittest.TestCase):
    """판을 가르는 자리가 늘지 않는다 — 문을 세우면 줄어든다."""

    def test_platform_branching_does_not_spread(self):
        found = _outside_doors(os.path.join(ROOT, "bin", "s9"))
        counts = {k: len(v) for k, v in found.items()}
        grew = {k: (counts.get(k, 0), cap)
                for k, cap in PLATFORM_BUDGET.items()
                if counts.get(k, 0) > cap}
        self.assertFalse(
            grew,
            "판을 가르는 자리가 문 밖에서 늘었다 — 문이 여럿이면 플랫폼 구멍도 "
            "여럿이 된다:\n"
            + "\n".join(f"  {k}: {now} (허용 {cap}) — 줄 "
                        f"{found.get(k, [])[:8]}" for k, (now, cap) in
                        grew.items())
            + "\n  `*_backend()` 문을 세워 그 안으로 옮겨라. 문이 이미 있으면 "
              "그 문을 불러라.")

    def test_the_budget_follows_us_down(self):
        """문을 세워 줄였으면 예산도 내려와야 한다 — 안 내리면 라쳇이 헐겁다."""
        found = _outside_doors(os.path.join(ROOT, "bin", "s9"))
        counts = {k: len(v) for k, v in found.items()}
        slack = {k: cap - counts.get(k, 0)
                 for k, cap in PLATFORM_BUDGET.items()
                 if cap - counts.get(k, 0) > 2}
        self.assertFalse(slack, f"줄인 만큼 PLATFORM_BUDGET 을 낮춰라: {slack}")

    def test_the_doors_are_actually_there(self):
        """예산만 있고 문이 없으면 이 시험은 숫자놀이다."""
        with open(os.path.join(ROOT, "bin", "s9"), encoding="utf-8") as f:
            src = f.read()
        for door in ("def proc_backend(", "def spawn_backend(",
                     "def spawn_detached(", "def pid_alive("):
            self.assertIn(door, src, f"{door} 문이 사라졌다")

    def test_the_numbers_are_visible(self):
        found = _outside_doors(os.path.join(ROOT, "bin", "s9"))
        print("\n[판 가르기] 문 밖: "
              + " · ".join(f"{k} {len(v)}" for k, v in sorted(found.items()))
              + f"  (예산 {PLATFORM_BUDGET})")
        self.assertIsInstance(found, dict)


class NoOsHooks(unittest.TestCase):
    def test_no_os_hooks(self):
        """죽지 않게 만들려고 OS 를 고치는 방향은 뿌리부터 틀렸다."""
        with self.subTest("n1_nothing_registers_itself_with_the_os"):
            hits = []
            for path in _files():
                for i, ln in _code_lines(path):
                    for what, pat in PLANT.items():
                        if re.search(pat, ln):
                            rel = os.path.relpath(path, ROOT)
                            hits.append(f"{rel}:{i} [{what}] {ln.strip()[:70]}")
            self.assertFalse(hits, "OS 안쪽에 자리를 심는 줄이 생겼다 — "
                                   "저장소를 지워도 남는 설정은 이 하네스의 것이 "
                                   "아니다 (DOC-20260903-004):\n" + "\n".join(hits))
        with self.subTest("n2_looking_is_still_allowed"):
            with open(os.path.join(ROOT, "bin", "s9-doctor"), encoding="utf-8") as f:
                src = f.read()
            self.assertIn("systemd", src, "init 을 읽는 진단이 사라졌다")
        with self.subTest("n3_the_rule_is_written_down_where_it_binds"):
            found = False
            vault = os.path.join(ROOT, "vault")
            for dirpath, _d, names in os.walk(vault):
                for n in names:
                    if not n.endswith(".md"):
                        continue
                    try:
                        with open(os.path.join(dirpath, n), encoding="utf-8") as f:
                            if "하네스는 OS 에 기대지 않는다" in f.read():
                                found = True
                    except (OSError, UnicodeDecodeError):
                        pass
            self.assertTrue(found, "규율 문서(DOC-20260903-004)를 못 찾았다")

if __name__ == "__main__":
    unittest.main()
