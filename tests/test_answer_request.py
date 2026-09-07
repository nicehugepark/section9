"""「답 찾기」 — 뒤늦게 답을 찾는 손잡이 (REQ-20260907-041).

깨우기의 얇은 형제다. 판정만 다르고 스폰은 같은 문(`_spawn_worker`)을 지난다 —
경로를 새로 파면 킬스위치·예산·리스 같은 방어장치가 두 벌이 되고, 두 벌이면
성긴 쪽으로 샌다(REQ-20260830-002 가 배운 것).

고정하는 계약 다섯.
1. 거부 갈래마다 사람이 읽을 문장이 있다 — 눌렀는데 아무 일도 없고 이유도
   모르는 것이 제일 나쁘다.
2. 요청 사실이 문서에 남는다. 새로고침해도 「찾는 중」이 유지되고, 두 번 눌러
   작업자가 둘 붙지 않는다.
3. 표식은 스스로 삭는다 — 워커가 죽어도 손잡이가 영영 잠기면 사람이 할 수
   있는 일이 없어진다.
4. 「찾는 중」은 `agent-answer` 노트가 붙는 순간 걷힌다 — 작업자에게 뒷정리를
   시키면 잊는다.
5. 프롬프트가 **짓지 말고 찾으라**고 시킨다.

실행: python3 tests/ answer_request
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9-ansreq-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_ansreq", importlib.machinery.SourceFileLoader("s9_mod_ansreq", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class BusyMark(unittest.TestCase):
    def test_no_mark_is_not_busy(self):
        self.assertEqual(mod._answer_busy_since({}), "")
        self.assertEqual(mod._answer_busy_since({"answer_request": ""}), "")

    def test_a_fresh_mark_is_busy(self):
        now = mod.now_iso()
        self.assertEqual(mod._answer_busy_since({"answer_request": {"since": now}}), now)

    def test_a_bare_string_mark_also_counts(self):
        # 옛 꼴(문자열 하나)도 읽는다 — 화면이 둘 다 쓸 수 있게
        now = mod.now_iso()
        self.assertEqual(mod._answer_busy_since({"answer_request": now}), now)

    def test_a_stale_mark_expires(self):
        """워커가 죽어도 손잡이가 영영 잠기면 사람이 할 수 있는 일이 없어진다."""
        import datetime
        old = (datetime.datetime.now().astimezone()
               - datetime.timedelta(seconds=mod.ANSWER_BUSY_SEC + 60)).isoformat()
        self.assertEqual(mod._answer_busy_since({"answer_request": {"since": old}}), "")

    def test_garbage_mark_is_not_busy(self):
        # 못 읽는 값 때문에 손잡이가 잠기지 않는다
        self.assertEqual(mod._answer_busy_since({"answer_request": {"since": "쓰레기"}}), "")


class Refusals(unittest.TestCase):
    """거부에도 사람이 읽을 문장이 붙는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-ansreq-root-")
        self.env = dict(os.environ, S9_ROOT=self.root, S9_MACHINE="testbox",
                        S9_USER="tester")

    def _s9(self, *argv, inp=None):
        return subprocess.run([sys.executable, S9, *argv], input=inp,
                              capture_output=True, encoding="utf-8",
                              errors="replace", env=self.env, timeout=60)

    def _call(self, doc_id):
        code = (
            "import importlib.machinery, importlib.util, json, os, sys\n"
            f"spec = importlib.util.spec_from_loader('m', importlib.machinery."
            f"SourceFileLoader('m', {S9!r}))\n"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            f"print(json.dumps(m.answer_request({doc_id!r}, actor='tester')))\n")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           encoding="utf-8", env=self.env, timeout=60)
        import json
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_missing_doc(self):
        res = self._call("QST-19700101-001-zzzz")
        self.assertEqual(res["action"], "missing")
        self.assertTrue(res["message"])

    def test_not_a_question(self):
        out = self._s9("new", "request", "--title", "요청이다", "--summary", "s",
                       "--goal", "g", "--size", "S", inp="원문")
        res = self._call(out.stdout.split()[0])
        self.assertEqual(res["action"], "not-question")
        self.assertIn("질문", res["message"])

    def test_already_answered(self):
        out = self._s9("new", "question", "--title", "이미 답한 질문", inp="원문")
        did = out.stdout.split()[0]
        self._s9("note", did, "답이다", "--label", "answer")
        res = self._call(did)
        self.assertEqual(res["action"], "answered")
        self.assertTrue(res["message"])

    def test_every_refusal_says_why(self):
        for res in (self._call("QST-19700101-001-zzzz"),):
            self.assertFalse(res["ok"])
            self.assertTrue(res.get("message"), "거부에 사람이 읽을 문장이 없다")


class MarkClearsWhenTheAnswerLands(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-ansreq-clear-")
        self.env = dict(os.environ, S9_ROOT=self.root, S9_MACHINE="testbox",
                        S9_USER="tester")

    def _s9(self, *argv, inp=None):
        return subprocess.run([sys.executable, S9, *argv], input=inp,
                              capture_output=True, encoding="utf-8",
                              errors="replace", env=self.env, timeout=60)

    def test_agent_answer_note_clears_the_mark(self):
        out = self._s9("new", "question", "--title", "찾는 중인 질문", inp="원문")
        did = out.stdout.split()[0]
        # 찾는 중 표식을 직접 심는다 (스폰 없이 이 계약만 본다)
        import glob as _g
        f = _g.glob(os.path.join(self.root, "vault", "**", did + ".md"),
                    recursive=True)[0]
        s = open(f, encoding="utf-8").read()
        s = s.replace("\nstatus:", '\nanswer_request: {"since": "2026-09-07T15:00:00+09:00"}\nstatus:', 1)
        open(f, "w", encoding="utf-8").write(s)
        self.assertIn("answer_request", self._s9("show", did, "--meta").stdout)
        r = self._s9("note", did, "기록에서 답을 찾지 못했다", "--label", "agent-answer")
        self.assertEqual(r.returncode, 0, r.stderr)
        meta = self._s9("show", did, "--meta").stdout
        self.assertNotIn('answer_request: {"since"', meta,
                         "답이 붙었는데 「찾는 중」이 걷히지 않았다")

    def test_other_labels_do_not_clear_it(self):
        out = self._s9("new", "question", "--title", "다른 노트", inp="원문")
        did = out.stdout.split()[0]
        import glob as _g
        f = _g.glob(os.path.join(self.root, "vault", "**", did + ".md"),
                    recursive=True)[0]
        s = open(f, encoding="utf-8").read()
        s = s.replace("\nstatus:", '\nanswer_request: {"since": "2026-09-07T15:00:00+09:00"}\nstatus:', 1)
        open(f, "w", encoding="utf-8").write(s)
        self._s9("note", did, "그냥 메모", "--label", "response")
        self.assertIn('answer_request', self._s9("show", did, "--meta").stdout)


class ThePromptSaysFindNotInvent(unittest.TestCase):
    def test_the_worker_is_told_to_find(self):
        src = open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8").read()
        body = src.split("def _spawn_answer")[1].split("def answer_request")[0]
        self.assertIn("답을 짓지 마라", body)
        self.assertIn("agent-answer", body)
        self.assertIn("--parent", body, "일을 함의하면 요청을 세우라고 안 시킨다")

    def test_it_uses_the_single_spawn_door(self):
        src = open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8").read()
        body = src.split("def _spawn_answer")[1].split("def answer_request")[0]
        self.assertIn("_spawn_worker(", body)
        self.assertNotIn("Popen", body, "새 스폰 경로를 팠다 — 방어장치가 두 벌이 된다")

    def test_the_reason_is_a_human_one(self):
        # 사람이 누른 손잡이라 사람 예산을 쓴다 (REQ-20260907-038)
        self.assertTrue(mod.is_human_reason("answer"))


if __name__ == "__main__":
    unittest.main()
