"""질문 문서 타입(question/QST) — bin/ 층 테스트 (REQ-20260826-017, 설계 DOC-20260826-011).

이 파일이 잡는 것은 **bin/ 층**이다: TYPES 등록·QST 발번·문서 경로·id 해석·`answered`
파생·`--unanswered` 조회, 그리고 감사 훅 두 개(질문 턴의 문서 생성, Stop 훅의 답 캡처).
화면(web/index.html) 계약은 tests/test_question_type.py 가 따로 본다 — 경계가 다르므로
합치지 않는다.

사고: 사용자가 "cron/systemd 쓰나?"를 물었고 답했는데, 2시간 뒤 "답변을 했었나?"를
다시 물었다. 답이 없었던 게 아니라 **찾을 수 없었다** — 채팅은 흘러가고 노트는 무관한
요청 문서에 묻혔다.

고정하는 결정 세 가지 (근거 전문은 DOC-20260826-011):
1. 문서가 되는 질문 = 즉석 인터랙션이 아니고 20자 이상. 사전 기계 판정 + 답 자동 캡처.
   사람의 재량에 맡기는 경로는 이미 한 번 무너졌다.
2. QST는 **사건**(그때 무엇을 묻고 무엇이라 답했나), knowledge는 **규칙**. 승격은
   QST → DOC 한 방향이고 규칙 전문을 QST에 복사하지 않는다.
3. 미답은 status가 아니라 **파생**이다 — answer 라벨 노트 유무. 진실이 둘이면
   "답했는데 미답"이 생기고, 전이라는 새 규율을 사람에게 요구하게 된다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ question
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")
STOP_HOOK = os.path.join(HERE, "..", "bin", "s9-audit-response")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


s9 = _load("s9_mod_qst", S9)
hook = _load("s9_hook_qst", HOOK)


class Cli(unittest.TestCase):
    """S1~S5, S9, S10 — CLI 경로 (격리 vault)."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9qst-")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox",
                   "S9_USER": "tester", "S9_SYNC": "off", "S9_ORIGIN": "zz99"}
        cls.env.pop("S9_SESSION", None)
        cls.env.pop("S9_AUTO_RESUME", None)
        cls.s9run("init")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def s9run(cls, *argv, check=True, inp=None):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=30, input=inp,
                           stdin=None if inp is not None else subprocess.DEVNULL)
        if check and r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r

    def new_question(self, title, body="b"):
        return self.s9run("new", "question", "--title", title,
                          "--user", "tester", "--body", body).stdout.split()[0]

    def catalog(self):
        # 파일이 아니라 문으로 읽는다 — 증분 카탈로그 뒤로 갓 쓴 행은
        # base 가 아니라 델타에 있다 (REQ-20260902-035).
        out = self.s9run("index", "cat").stdout
        return [json.loads(l) for l in out.splitlines() if l.strip()]

    def row(self, doc_id):
        return next(r for r in self.catalog() if r["id"] == doc_id)

    # S1. 등록 — QST 발번, questions/ 경로, published 상태
    def test_s1_new_question(self):
        qid = self.new_question("cron, systemd 를 쓰고 있나?")
        self.assertRegex(qid, r"^QST-\d{8}-\d{3}-zz99$")
        path = os.path.join(self.root, self.row(qid)["path"])
        self.assertTrue(os.path.exists(path), path)
        self.assertIn(os.path.join("vault", "questions"), self.row(qid)["path"])
        self.assertEqual(self.row(qid)["status"], "published")

    # S2. 조회 — 타입 필터·검색에 잡힌다
    def test_s2_listed_and_searchable(self):
        qid = self.new_question("인덱스는 언제 재생성되나",
                                body="rebuild_index 호출 시점이 궁금하다")
        ls = self.s9run("ls", "--type", "question").stdout
        self.assertIn(qid, ls)
        self.assertIn(qid, self.s9run("search", "인덱스는").stdout)
        self.assertEqual(self.row(qid)["type"], "question")

    # S3. 미답 구분 — 답 노트가 붙으면 목록에서 빠진다 (파생 필드)
    def test_s3_unanswered_is_derived(self):
        qid = self.new_question("워처는 몇 초마다 스캔하나")
        self.assertFalse(self.row(qid)["answered"])
        self.assertIn(qid, self.s9run("ls", "--type", "question",
                                      "--unanswered").stdout)
        self.s9run("note", qid, "30초마다 스캔한다",
                   "--label", "answer", "--user", "tester")
        self.assertTrue(self.row(qid)["answered"])
        self.assertNotIn(qid, self.s9run("ls", "--type", "question",
                                         "--unanswered").stdout)

    # S4. 질문과 답이 한 문서에서 읽힌다
    def test_s4_question_and_answer_in_one_doc(self):
        qid = self.new_question("감시는 무엇이 도나",
                                body="cron 인가 serve 데몬 스레드인가")
        self.s9run("note", qid, "serve 데몬 스레드다 — crontab 호출은 0건",
                   "--label", "answer", "--user", "tester")
        shown = self.s9run("show", qid).stdout
        self.assertIn("cron 인가 serve 데몬 스레드인가", shown)
        self.assertIn("serve 데몬 스레드다", shown)
        self.assertIn("answer", shown)

    # S5. id 해석 — 짧은 지칭 정규화 + 본문 관계 추출
    def test_s5_id_resolution(self):
        qid = self.new_question("id 해석이 되는가 확인용 질문")
        short = re.match(r"^(QST-\d{8}-\d{3})-", qid).group(1)
        # 카탈로그를 이 vault로 보고 정규화해야 하므로 CLI 경로로 검증
        rid = self.s9run("new", "request", "--title", "짧은 지칭 정규화",
                         "--user", "tester", "--goal", "g", "--body", "b"
                         ).stdout.split()[0]
        self.s9run("note", rid, f"{short} 참조", "--user", "tester")
        self.assertIn(qid, self.s9run("show", rid).stdout,
                      "짧은 QST 지칭이 full-id로 확장되지 않았다")
        self.assertIn(qid, s9.DOC_ID_RE.findall(f"관련: {qid} 참조"))

    # S9. 회귀 — 기존 네 타입의 발번·경로·조회가 그대로
    def test_s9_existing_types_unchanged(self):
        expect = {"request": ("REQ", "requests"),
                  "knowledge": ("DOC", "knowledge"),
                  "session": ("SES", "sessions"),
                  "project": ("PRJ", "projects")}
        for t, (prefix, subdir) in expect.items():
            self.assertEqual(s9.TYPES[t][0], prefix)
            self.assertEqual(s9.TYPES[t][1], subdir)
        did = self.s9run("new", "knowledge", "--title", "회귀 지식",
                         "--user", "tester", "--body", "b").stdout.split()[0]
        self.assertTrue(did.startswith("DOC-"))
        before = len(self.catalog())
        self.s9run("index", "rebuild")
        self.assertEqual(len(self.catalog()), before, "재생성으로 문서가 사라졌다")
        self.assertIn(did, self.s9run("ls", "--type", "knowledge").stdout)
        self.assertNotIn(did, self.s9run("ls", "--type", "question").stdout)

    # S10. 회귀 — request 상태머신·게이트 불변
    def test_s10_request_gates_unchanged(self):
        rid = self.s9run("new", "request", "--title", "게이트 회귀",
                         "--user", "tester", "--body", "b").stdout.split()[0]
        self.s9run("status", rid, "in-progress", "--user", "tester")
        # goal 없는 done 은 여전히 거부된다
        r = self.s9run("status", rid, "done", "--user", "tester", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("goal", r.stdout + r.stderr)
        # question 은 상태머신 밖(published 고정, terminal)
        qid = self.new_question("상태 전이가 막히는지 확인하는 질문")
        r = self.s9run("status", qid, "in-progress", "--user", "tester",
                       check=False)
        self.assertNotEqual(r.returncode, 0, "question이 상태머신에 편입됐다")


class HookBoundary(unittest.TestCase):
    """S6 — 무엇이 질문 문서가 되는가의 경계 (사전 기계 판정)."""

    def test_s6_durable_questions(self):
        for t in ("cron, systemd 사용 유무에 대해서 답변을 했었나?",
                  "워처가 30초마다 도는 이유가 무엇인가요",
                  "인덱스 재생성은 왜 매 노트마다 도는 건가"):
            self.assertTrue(hook.is_durable_question(t), t)

    def test_s6_throwaway_questions(self):
        for t in ("왜", "이거 맞아?", "지금 되나요?", "됐어?",
                  "로그 좀 보여줘", "출력해줘", "대기해"):
            self.assertFalse(hook.is_durable_question(t), t)

    def test_s6_classify_unchanged(self):
        """분류 taxonomy 자체는 그대로 — 문서화 판정만 별도 축이다."""
        self.assertEqual(hook.classify("logout"), "fragment")
        self.assertEqual(hook.classify("ㅇㅋ"), "nothing")
        self.assertEqual(hook.classify("로그아웃 만들어줘"), "request")
        self.assertEqual(hook.classify("로그아웃 왜 안돼?"), "question")


class HookWiring(unittest.TestCase):
    """S7, S8 — 훅 배선: 질문 턴이 QST를 만들고 답이 자동으로 붙는다."""

    def setUp(self):
        self.calls = []

    def _record(self, env, *argv, inp=None):
        self.calls.append(argv)

        class R:
            returncode = 0
            stdout = ""
        if argv[:2] == ("new", "question"):
            R.stdout = "QST-20260826-001-zz99  vault/questions/x.md"
        elif argv[:2] == ("new", "request"):
            R.stdout = "REQ-20260826-099-zz99  vault/requests/x.md"
        elif argv[:2] == ("user", "current"):
            R.stdout = "tester"
        return R

    def _run_hook(self, prompt):
        import io
        import sys
        from unittest import mock
        data = {"prompt": prompt, "session_id": "abcd1234efgh",
                "cwd": "", "transcript_path": ""}
        buf = io.StringIO()
        with mock.patch.object(hook, "run", self._record), \
                mock.patch.object(hook, "pending_context", lambda *a: ""), \
                mock.patch.object(hook, "_claude_pid", lambda: 1), \
                mock.patch.dict(os.environ, {"S9_AUDIT": "on"}, clear=False), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps(data))), \
                mock.patch.object(sys, "stdout", buf):
            os.environ.pop("S9_AUTO_RESUME", None)
            hook.main()
        return buf.getvalue()

    # S7. 질문 턴이 문서를 만들고 답 포인터를 세운다
    def test_s7_question_turn_creates_doc(self):
        out = self._run_hook("cron 이나 systemd 를 이 시스템이 쓰고 있나?")
        self.assertIn(("new", "question"), [c[:2] for c in self.calls],
                      "질문 턴인데 QST를 만들지 않았다")
        self.assertIn(("bind", "last_qst", "QST-20260826-001-zz99"), self.calls,
                      "답 캡처 포인터(last_qst)가 세팅되지 않았다")
        self.assertIn("QST-20260826-001-zz99", out)

    # S7b. 짧은 확인 질문은 문서를 만들지 않는다 (기존 동작 유지)
    def test_s7b_throwaway_question_makes_no_doc(self):
        self._run_hook("이거 맞아?")
        self.assertNotIn(("new", "question"), [c[:2] for c in self.calls])

    # S7c. request 턴은 last_qst 를 남기지 않는다 (다음 턴 오귀속 차단)
    def test_s7c_request_turn_clears_pointer(self):
        self._run_hook("질문 문서 타입을 추가하고 훅에 연결해줘")
        self.assertIn(("new", "request"), [c[:2] for c in self.calls])
        self.assertIn(("bind", "last_qst", ""), self.calls,
                      "request 턴이 이전 질문 포인터를 비우지 않았다")

    # S8. Stop 훅: last_req 가 없으면 last_qst 로 폴백해 answer 로 붙인다
    def test_s8_stop_hook_answer_capture(self):
        stop = _load("s9_stop_qst", STOP_HOOK)
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append((argv, inp))

            class R:
                returncode = 0
                stdout = ""
            if argv == ("last", "--active"):
                R.stdout = ""          # 질문 턴 — 캡처 pause
            elif argv == ("bind",):
                R.stdout = json.dumps({"last_qst": "QST-20260826-001-zz99"})
            return R

        import sys
        from unittest import mock
        tp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8")
        tp.write(json.dumps({"type": "assistant", "message": {
            "model": "opus", "content": [
                {"type": "text", "text": "crontab 호출은 0건이다"}]}}) + "\n")
        tp.close()
        data = {"session_id": "abcd1234", "transcript_path": tp.name, "cwd": ""}
        with mock.patch.object(stop, "run", fake_run), \
                mock.patch.object(stop, "mirror_transcript", lambda *a: None), \
                mock.patch.object(sys, "stdin",
                                  __import__("io").StringIO(json.dumps(data))):
            stop.main()
        os.unlink(tp.name)
        noted = [c for c in calls if c[0][0] == "note"]
        self.assertTrue(noted, "질문 턴 응답이 어디에도 기록되지 않았다")
        argv, inp = noted[0]
        self.assertEqual(argv[1], "QST-20260826-001-zz99")
        self.assertIn("answer", argv)
        self.assertIn("crontab 호출은 0건", inp)
        self.assertIn(("bind", "last_qst", ""),
                      [c[0] for c in calls], "포인터가 소비 후 비워지지 않았다")

    # S8b. request 턴(last_req 존재)의 캡처는 그대로다
    def test_s8b_request_capture_unchanged(self):
        stop = _load("s9_stop_qst2", STOP_HOOK)
        calls = []

        def fake_run(env, *argv, inp=None):
            calls.append((argv, inp))

            class R:
                returncode = 0
                stdout = ""
            if argv == ("last", "--active"):
                R.stdout = "REQ-20260826-017-62x6"
            return R

        import sys
        from unittest import mock
        tp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8")
        tp.write(json.dumps({"type": "assistant", "message": {
            "model": "opus", "content": [
                {"type": "text", "text": "구현 보고"}]}}) + "\n")
        tp.close()
        data = {"session_id": "abcd1234", "transcript_path": tp.name, "cwd": ""}
        with mock.patch.object(stop, "run", fake_run), \
                mock.patch.object(stop, "mirror_transcript", lambda *a: None), \
                mock.patch.object(sys, "stdin",
                                  __import__("io").StringIO(json.dumps(data))):
            stop.main()
        os.unlink(tp.name)
        noted = [c for c in calls if c[0][0] == "note"]
        self.assertEqual(len(noted), 1)
        self.assertEqual(noted[0][0][1], "REQ-20260826-017-62x6")
        self.assertIn("response", noted[0][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
