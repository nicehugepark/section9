"""도는 워커는 그 자체로 클레임이다 (REQ-20260829-016-62x6).

실사고 2026-08-29 11:04~11:39: 반려 한 건에 워커가 넷 떴다(간격은 쿨다운 그대로).
워크트리 넷이 같은 답을 따로 냈고 시간당 상한 6건을 다 써서 사람의 깨우기가 막혔다.
스폰 판정이 보는 클레임에 "이 REQ 를 맡아 지금 도는 워커" 축이 없었기 때문이다.

원인은 클레임의 눈이다. `rework_claimed` 는 세션 바인딩(`chat_live`)과 위임
기여(`delegated_live`)만 본다. 스폰된 워커는 headless 라 inbox tail 도 attach_pid
도 없어 `chat_live` 가 서지 않는다 — 클레임이 워커의 협조 한 줄(`s9 last --add`)에
달려 있고, 그 한 줄이 실패한 워커는 쿨다운마다 자기 위에 자기를 다시 띄운다.
그런데 그 사실은 이미 기록되고 있다: 스폰이 `_auto_mark_pid` 로 대상 REQ 마커에
pid 를 적는다. 새 표를 만들지 않고 그 사실을 판정에 꽂는다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ worker_claim
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def s9mod(root, name):
    """bin/s9 를 모듈로 적재해 판정 함수를 직접 부른다(서브프로세스보다 정확)."""
    old = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if old is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = old


class LiveClaudeProcess:
    """`_pid_is_claude` 가 참을 내는 진짜 프로세스 한 벌 (comm=claude).

    pid 를 지어내면 안 된다: 이 판정의 핵심이 **pid 재사용 방어**이고, 그것을
    건너뛴 시험은 고장을 못 잡는다."""

    def __init__(self, tmp, m):
        self.path = os.path.join(tmp, "claude")
        os.symlink(shutil.which("sleep") or "/bin/sleep", self.path)
        self.proc = subprocess.Popen(
            [self.path, "60"], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):          # comm 은 exec 뒤에 바뀐다 — 잠깐 기다린다
            if m._pid_is_claude(self.proc.pid):
                break
            time.sleep(0.02)

    @property
    def pid(self):
        return self.proc.pid

    def kill(self):
        try:
            self.proc.kill()
            self.proc.wait(timeout=5)
        except Exception:
            pass


class WorkerClaim(unittest.TestCase):
    RID = "REQ-20260829-016-62x6"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9wclaim-")
        env = {**os.environ, "S9_ROOT": self.tmp, "S9_MACHINE": "testbox",
               "S9_USER": "tester", "S9_AUDIT": "off"}
        env.pop("S9_SESSION", None)
        env.pop("S9_PORT", None)
        subprocess.run([S9, "init"], capture_output=True, text=True,
                       env=env, timeout=60, stdin=subprocess.DEVNULL)
        self.m = s9mod(self.tmp, "s9wclaim")
        self.m.ROOT = self.tmp
        self.m.STATE = os.path.join(self.tmp, "state", "sessions")
        os.makedirs(self.m.STATE, exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "state", "auto_resume"),
                    exist_ok=True)
        self.live = LiveClaudeProcess(self.tmp, self.m)
        self.addCleanup(self.live.kill)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def marker(self, pid, last=None):
        p = os.path.join(self.tmp, "state", "auto_resume",
                         self.m.safe_name(self.RID) + ".json")
        with open(p, "w") as f:
            json.dump({"pid": pid, "last": last if last is not None
                       else time.time(), "count": 1}, f)

    def test_running_worker_holds_the_claim(self):
        """도는 워커가 있으면 워처는 손대지 않는다 — 겹침 스폰 차단."""
        self.assertFalse(self.m.rework_claimed(self.RID),
                         "마커가 없으면 클레임도 없다")
        self.marker(self.live.pid)
        self.assertTrue(self.m.rework_claimed(self.RID),
                        "도는 워커가 있는데 워처가 하나 더 띄운다")

    def test_dead_worker_releases_the_claim(self):
        """즉사한 워커의 마커는 클레임이 아니다 — 아무도 안 붙은 것이 사실이다."""
        self.live.kill()
        self.marker(self.live.pid)
        self.assertFalse(self.m.rework_claimed(self.RID))
        self.assertIsNone(self.m.worker_running(self.RID))

    def test_hung_worker_expires(self):
        """멎은 채 프로세스만 남은 워커는 한도가 지나면 클레임을 놓는다.

        한도가 없으면 그 클레임이 영원해져 멈춘 작업을 조용히 감춘다 —
        이 저장소가 반복해 겪은 실패다 (`delegated_running` 과 같은 이유)."""
        self.marker(self.live.pid, last=time.time() - self.m.WORKER_WIN - 60)
        self.assertFalse(self.m.rework_claimed(self.RID))
        self.assertIsNone(self.m.worker_running(self.RID))

    def test_worker_running_reports_who(self):
        """판정만 돌려주면 화면·로그가 이유를 지어낸다 — 근거를 함께 낸다."""
        # 나이는 **이 시험이 실제로 흘려보낸 시간**에 대 본다 (REQ-20260904-003).
        # 상수 60초에 대면 「마커가 제 나이를 안다」가 아니라 「이 기계가 60초
        # 안에 두 줄을 지난다」를 재게 되고, 부하가 걸린 병렬 실행에서 붉어진다.
        t0 = time.time()
        self.marker(self.live.pid)
        got = self.m.worker_running(self.RID)
        self.assertIsNotNone(got)
        self.assertEqual(got["pid"], self.live.pid)
        self.assertGreaterEqual(got["age"], 0)
        self.assertLessEqual(got["age"], (time.time() - t0) + 5,
                             "마커가 제 나이보다 오래된 것으로 보인다")

    def test_a_marker_without_pid_is_not_a_claim(self):
        """구 마커(pid 없음)를 클레임으로 치면 하루 종일 아무도 못 이어받는다."""
        p = os.path.join(self.tmp, "state", "auto_resume",
                         self.m.safe_name(self.RID) + ".json")
        with open(p, "w") as f:
            json.dump({"last": time.time(), "count": 1}, f)
        self.assertIsNone(self.m.worker_running(self.RID))

    def test_judgment_survives_a_broken_marker(self):
        """판정이 예외를 올리면 워처 스레드가 죽고 진행 보장이 통째로 사라진다."""
        p = os.path.join(self.tmp, "state", "auto_resume",
                         self.m.safe_name(self.RID) + ".json")
        with open(p, "w") as f:
            f.write("{not json")
        self.assertIsNone(self.m.worker_running(self.RID))
        self.assertFalse(self.m.rework_claimed(self.RID))


if __name__ == "__main__":
    unittest.main()
