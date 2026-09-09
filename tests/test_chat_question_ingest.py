"""대시보드 채팅이 만든 질문의 첨부도 vault 로 옮긴다 (REQ-20260907-069).

첨부를 적는 자리가 셋이다: 터미널 훅(질문·요청)·대시보드 요청·대시보드 질문.
`ingest_assets` 가 요청 갈래에는 있었지만 **대시보드 질문 갈래에는 없어서**,
대시보드로 물은 질문에 붙인 그림이 `state/terminal/uploads/…` 절대경로로 남아
문서 화면에 파일 칩으로 섰다("첨부한 이미지가 또 렌더링 되지 않는다").

계약: `_chat_question` 이 만든 질문에 첨부가 있으면 문서 옆 `assets/<QST>/…` 로
옮겨지고 본문이 상대경로가 된다. 실제로 함수를 부른다.

실행: python3 tests/ chat_question_ingest
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class DashboardQuestionIngest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-cqi-")
        self.env = dict(os.environ, S9_ROOT=self.root, S9_MACHINE="testbox",
                        S9_USER="tester")
        # 모듈 ROOT 를 이 임시 루트로 — ingest 는 in-process 로 돈다
        self._prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_MACHINE"] = "testbox"
        spec = importlib.util.spec_from_loader(
            "s9_cqi", importlib.machinery.SourceFileLoader("s9_cqi", S9))
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def _upload(self, name="1.png"):
        d = os.path.join(self.root, "state", "terminal", "uploads", "tester")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        return p

    def test_a_dashboard_question_with_an_image_ingests_it(self):
        self.mod._chat_durable = lambda t: True   # 분류는 069 의 주제가 아니다
        img = self._upload()
        text = f"이거 왜 이러지?\n[Image: {img}]"
        qst = self.mod._chat_question(S9, self.env, text, "이거 왜 이러지?", "tester")
        self.assertTrue(qst and qst.startswith("QST-"), f"질문이 안 만들어졌다: {qst!r}")
        body = open(self.mod.locate(qst), encoding="utf-8").read()
        self.assertIn(f"[Image: assets/{qst}/1.png]", body,
                      "첨부가 문서 옆으로 안 옮겨졌다 — 화면에 파일 칩으로 선다")
        self.assertNotIn(img, body, "절대경로가 본문에 남았다")
        self.assertTrue(os.path.exists(
            os.path.join(os.path.dirname(self.mod.locate(qst)), "assets", qst, "1.png")))

    def test_a_dashboard_question_is_marked_human_even_inside_a_session(self):
        """사람 입구는 셋뿐이고 이 갈래는 그중 하나다 (REQ-20260909-109).

        2026-09-09 21:19 주인의 채팅이 물음으로 갈리며 origin=agent·lead 로 적혔다 —
        cmd_new 는 세션 안(S9_SESSION)에서 명시가 없으면 agent 로 판정한다. 요청
        갈래는 `--origin human` 을 넘기고 이 갈래만 안 넘겼다. 그 물음을 요청으로
        세우니 「만든 사람 리드」가 됐고 Jira 내보내기 검사(origin=human 만)에 걸렸다."""
        self.mod._chat_durable = lambda t: True   # 분류는 이 시험의 주제가 아니다
        env = dict(self.env, S9_SESSION="deadbeef")   # 사고의 조건 — 세션 안
        qst = self.mod._chat_question(S9, env, "이거 왜 이러지?", "이거 왜 이러지?", "tester")
        self.assertTrue(qst and qst.startswith("QST-"), f"질문이 안 만들어졌다: {qst!r}")
        meta = self.mod.read_doc(self.mod.find_path(qst))[0]
        self.assertEqual(meta.get("origin"), "human",
                         f"사람의 채팅이 {meta.get('origin')!r} 로 적혔다")
        self.assertFalse(meta.get("origin_actor"), "human 인데 origin_actor 가 남았다")

    def test_a_dashboard_question_without_an_image_is_unchanged(self):
        self.mod._chat_durable = lambda t: True
        qst = self.mod._chat_question(S9, self.env, "그냥 질문인가?", "그냥 질문인가?", "tester")
        self.assertTrue(qst and qst.startswith("QST-"))
        body = open(self.mod.locate(qst), encoding="utf-8").read()
        self.assertNotIn("[Image:", body)
        self.assertNotIn("assets/", body)


class EveryCreationPathIngests(unittest.TestCase):
    """첨부를 적는 자리가 넷이 되면 여기서 걸린다 — 두 벌·세 벌이면 한 벌만 고쳐진다.

    소스 글자를 대조하되 **없음이 아니라 있음**을 센다: 첨부를 붙인 `new question`·
    `new request` 호출부는 모두 그 뒤에 ingest 가 이어져야 한다. (budget: 이 파일은
    한 자리라 소스 글자 계약 목록에 든다 — BUDGET.json known 에 함께 넣는다.)
    """

    def test_the_dashboard_question_branch_calls_ingest(self):
        src = open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8").read()
        i = src.index("def _chat_question(")
        body = src[i:src.index("\ndef ", i + 1)]
        self.assertIn("ingest_assets(qst)", body,
                      "대시보드 질문 갈래가 ingest 를 안 부른다 (REQ-20260907-069)")


if __name__ == "__main__":
    unittest.main()
