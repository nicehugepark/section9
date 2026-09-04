"""막 뜬 백그라운드 작업은 **왜 떴는지**를 말한다 (REQ-20260831-025-62x6).

사용자: "그냥 요청을 하고, 멈췄고, 다시 시작을 했을 뿐인데 자동 작업인가?"

그 화면이 거짓말이 된 자리는 낱말 하나가 아니었다. 사실은 **이미 갈려
있었는데 화면까지 오지 못한 것**이다 — `bin/s9` 는 `reason == "wake"`(사람이
카드에서 ▶ 를 누른 것)를 워처와 다른 예산으로 세면서, 스폰 마커
(`state/auto_resume/<REQ>.json`)에는 `{last,count,pid}` 만 적고 그 까닭을
버렸다. 그래서 카드는 둘을 한 문장으로 부를 수밖에 없었고, 제 손으로 ▶ 를
누른 사람이 "저절로 떴다"는 결의 문장을 읽었다.

계약은 셋이다.
  ① 마커가 까닭을 **버리지 않는다** — `_auto_mark_pid` 가 한 칸 더 적는다.
  ② 카탈로그가 그 칸을 행에 그대로 실어 낸다(`spawn_reason`). 서버는 사실만
     나르고 문장은 화면이 짓는다 — 문장 두 벌 금지.
  ③ 화면이 세 갈래로 갈라 말한다: 사람이 누른 것은 「이어가기를 눌러…」,
     워처가 띄운 것만 사건+까닭("반려되어 저절로 다시 시작됐습니다"),
     모르는 것(옛 마커·CLI 재개)은 중립. **짐작해서 주어를 세우지 않는다.**

근거: DOC-20260831-005-62x6 (규칙 2·6) · REQ-20260831-024 designer 노트.
실행: python3 tests/ spawn_reason
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
CARD = os.path.join(HERE, "..", "web", "app", "card.js")


def _find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


NODE = _find_node()


def _isolate(prefix):
    """제 임시 루트를 세우고 **떠날 때 되돌린다**.

    러너는 샤드 하나에서 여러 시험 파일을 한 프로세스로 돈다 — 환경변수를
    바꿔 놓고 나가면 다음 파일이 없어진 루트를 본다. 세우는 쪽이 치운다."""
    tmp = tempfile.mkdtemp(prefix=prefix)
    keep = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
    os.environ["S9_ROOT"] = tmp
    os.environ["S9_MACHINE"] = "testbox"
    return tmp, keep


def _restore(tmp, keep):
    shutil.rmtree(tmp, ignore_errors=True)
    for k, v in keep.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class _Proc(object):
    """Popen 자리에 서는 최소한의 것 — 이 함수가 보는 것은 pid 하나다."""

    def __init__(self, pid):
        self.pid = pid


class TheMarkerKeepsTheReason(unittest.TestCase):
    """① 스폰 마커가 까닭을 버리지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.keep = _isolate("s9spawnwhy-")
        spec = importlib.util.spec_from_loader(
            "s9mod_why", importlib.machinery.SourceFileLoader("s9mod_why", S9))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        subprocess.run([S9, "init"], capture_output=True, text=True,
                       env={**os.environ}, timeout=30, check=True)

    @classmethod
    def tearDownClass(cls):
        _restore(cls.tmp, cls.keep)

    def _marker(self, doc_id):
        pf = os.path.join(self.mod._auto_dir(),
                          self.mod.safe_name(doc_id) + ".json")
        with open(pf, encoding="utf-8") as f:
            return json.load(f)

    def test_the_marker_keeps_the_reason(self):
        """① 스폰 마커가 까닭을 버리지 않는다."""
        with self.subTest("a_human_press_is_written_down"):
            self.mod._auto_mark_pid("REQ-WAKE", _Proc(4321), "wake")
            m = self._marker("REQ-WAKE")
            self.assertEqual(4321, m["pid"])
            self.assertEqual("wake", m["reason"],
                             "사람이 누른 사실이 마커에서 사라졌다")
        with self.subTest("a_watcher_spawn_is_written_down"):
            self.mod._auto_mark_pid("REQ-REWORK", _Proc(4322), "rework")
            self.assertEqual("rework", self._marker("REQ-REWORK")["reason"])
        with self.subTest("the_next_spawn_overwrites_the_last"):
            self.mod._auto_mark_pid("REQ-TWICE", _Proc(4323), "rework")
            self.mod._auto_mark_pid("REQ-TWICE", _Proc(4324), "wake")
            m = self._marker("REQ-TWICE")
            self.assertEqual("wake", m["reason"])
            self.assertEqual(4324, m["pid"])
        with self.subTest("no_reason_writes_no_key"):
            self.mod._auto_mark_pid("REQ-BLANK", _Proc(4325), "")
            self.assertNotIn("reason", self._marker("REQ-BLANK"))
        with self.subTest("a_broken_marker_does_not_raise"):
            pf = os.path.join(self.mod._auto_dir(),
                              self.mod.safe_name("REQ-JUNK") + ".json")
            os.makedirs(os.path.dirname(pf), exist_ok=True)
            with open(pf, "w", encoding="utf-8") as f:
                f.write("{not json")
            self.mod._auto_mark_pid("REQ-JUNK", _Proc(4326), "wake")
            self.assertEqual("wake", self._marker("REQ-JUNK")["reason"])
        with self.subTest("the_workspace_note_does_not_collide"):
            self.mod._auto_mark_pid("REQ-WS", _Proc(4327), "wake")
            self.mod._auto_mark_workspace("REQ-WS", "worktree", "본 저장소 사용 중")
            m = self._marker("REQ-WS")
            self.assertEqual("wake", m["reason"])
            self.assertEqual("worktree", m["workspace"]["kind"])

class TheRowCarriesTheReason(unittest.TestCase):
    """② 카탈로그가 그 칸을 행에 실어 낸다 — 새 통로를 파지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.keep = _isolate("s9spawnrow-")
        spec = importlib.util.spec_from_loader(
            "s9mod_row", importlib.machinery.SourceFileLoader("s9mod_row", S9))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        env = {**os.environ}
        run = lambda *a: subprocess.run([S9, *a], capture_output=True, text=True,
                                        env=env, timeout=30, check=True).stdout
        run("init")
        run("user", "add", "alice")
        cls.doc = run("new", "request", "--title", "막 뜬 것", "--summary", "s",
                      "--goal", "g", "--size", "S", "--user", "alice",
                      "--body", "b").split()[0]
        run("status", cls.doc, "in-progress", "--note", "t")

    @classmethod
    def tearDownClass(cls):
        _restore(cls.tmp, cls.keep)

    def _row(self, marker):
        """마커를 그대로 두고 카탈로그를 다시 읽는다.

        pid 생존 판정을 참으로 고정한다 — 이 시험이 재는 것은 '살아 있나'가
        아니라 '까닭이 행까지 오나'다. 고정하지 않으면 죽은 pid 로 판정이
        `spawn_failed` 로 떨어져 무엇을 쟀는지 알 수 없게 된다."""
        pf = os.path.join(self.mod._auto_dir(),
                          self.mod.safe_name(self.doc) + ".json")
        os.makedirs(os.path.dirname(pf), exist_ok=True)
        with open(pf, "w", encoding="utf-8") as f:
            json.dump(dict({"last": time.time()}, **marker), f)
        with mock.patch.object(self.mod, "_pid_is_claude", lambda p: True):
            rows = self.mod.catalog_with_live()
        return [r for r in rows if r["id"] == self.doc][0]

    def test_the_row_carries_the_reason(self):
        """② 카탈로그가 그 칸을 행에 실어 낸다 — 새 통로를 파지 않는다."""
        with self.subTest("the_human_reason_reaches_the_row"):
            r = self._row({"pid": 999001, "reason": "wake"})
            self.assertEqual("spawned", r.get("live_kind"))
            self.assertEqual("wake", r.get("spawn_reason"))
        with self.subTest("the_watcher_reason_reaches_the_row"):
            r = self._row({"pid": 999002, "reason": "rework"})
            self.assertEqual("rework", r.get("spawn_reason"))
        with self.subTest("an_old_marker_carries_nothing"):
            r = self._row({"pid": 999003})
            self.assertEqual("spawned", r.get("live_kind"))
            self.assertIsNone(r.get("spawn_reason"))
        with self.subTest("no_marker_no_branch"):
            pf = os.path.join(self.mod._auto_dir(),
                              self.mod.safe_name(self.doc) + ".json")
            if os.path.exists(pf):
                os.remove(pf)
            rows = self.mod.catalog_with_live()
            r = [x for x in rows if x["id"] == self.doc][0]
            self.assertNotEqual("spawned", r.get("live_kind"))
            self.assertIsNone(r.get("spawn_reason"))

@unittest.skipUnless(NODE, "node 가 없어 화면 조각을 못 돌린다")
class TheScreenSplitsTheSentence(unittest.TestCase):
    """③ 세 갈래가 서로 다른 문장을 받는다.

    조각은 원문(`web/app/card.js`)에서 떠 온다 — 여기 베껴 두면 두 벌이 되고,
    문장이 바뀔 때 한 벌만 고쳐진다(이 저장소가 판정 버튼에서 세 번 배운 것).
    """

    @classmethod
    def setUpClass(cls):
        with open(CARD, encoding="utf-8") as f:
            cls.src = f.read()

    def _tell(self, row):
        m = re.search(r"const SPAWN_TAIL = [^\n]*\n", self.src)
        f = re.search(r"(?ms)^function spawnTell\(r\)\{.*?^\}", self.src)
        self.assertTrue(m and f, "card.js 에서 조각을 못 떴다")
        js = ('const WAKE_LABEL = "이어가기";\n' + m.group(0) + f.group(0)
              + "\nprocess.stdout.write(spawnTell(%s));" % json.dumps(row))
        r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                           timeout=30)
        self.assertEqual(0, r.returncode, r.stderr)
        return r.stdout

    def test_the_screen_splits_the_sentence(self):
        """③ 세 갈래가 서로 다른 문장을 받는다."""
        with self.subTest("a_human_press_never_reads_as_by_itself"):
            t = self._tell({"live_age": 7, "spawn_reason": "wake"})
            self.assertIn("「이어가기」를 눌러", t)
            self.assertIn("7초 전", t)
            self.assertNotIn("저절로", t)
            self.assertNotIn("자동", t)
        with self.subTest("only_the_watcher_says_by_itself_and_says_why"):
            t = self._tell({"live_age": 12, "spawn_reason": "rework"})
            self.assertIn("저절로", t)
            self.assertIn("반려되어", t, "왜 저절로 떴는지가 빠졌다")
            self.assertIn("12초 전", t)
        with self.subTest("an_unknown_reason_stays_neutral"):
            for row in ({"live_age": 3},
                        {"live_age": 3, "spawn_reason": ""},
                        {"live_age": 3, "spawn_reason": "resume-item"}):
                t = self._tell(row)
                self.assertIn("3초 전에 다시 시작됐습니다", t)
                self.assertNotIn("저절로", t)
                self.assertNotIn("눌러", t)
        with self.subTest("every_branch_ends_with_the_same_promise"):
            tails = {self._tell({"live_age": 5, "spawn_reason": w})[-20:]
                     for w in ("wake", "rework", "")}
            self.assertEqual(1, len(tails), "갈래마다 꼬리가 갈렸다: %s" % tails)
            self.assertIn("이어받기까지", tails.pop(),
                          "재개의 동사가 「이어받다」가 아니다")

if __name__ == "__main__":
    unittest.main(verbosity=2)
