"""프로젝트 없는 문서는 존재하지 않는다 (REQ-20260909-026).

주인 2026-09-09: 「이제부터 사실상 '프로젝트 없음' 문서는 존재하지 않아야 한다 — 새
설치에서도. 필터 조건의 '프로젝트 없음'은 없도록 정리」. 기본 프로젝트가 서는 뒤로는
요청·지식·세션 어느 문서도 project 가 비지 않는다: 새로 생기는 것은 기본 프로젝트를
받고(resolve_project · session_log_append), 비우는 길은 막히고(do_set), 옛 문서는
한 번에 채웠다(233건, project_source=backfill). 이 파일은 그 셋을 잰다 — 마지막 것은
이 저장소의 vault 를 그대로 걷는다.

실행: python3 tests/ no_projectless
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9.py")


def load(root):
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        name = "s9_npl_%d" % abs(hash(root))
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


class NothingIsBornWithoutAProject(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-npl-")
        self.m = load(self.root)
        self.m.cmd_init(type("A", (), {})())
        self.m.do_user_add("hong", role="admin")
        self.slug = self.m.ensure_default_project()
        self.assertEqual(self.slug, self.m.DEFAULT_PROJECT_SLUG)

    def test_p1_a_session_doc_gets_the_default_project(self):
        """정상 — 세션 문서도 프로젝트를 갖는다(세션에 묶인 것이 없으면 기본)."""
        ses_id = self.m.session_log_append("abcd1234", "hello", "hong")
        meta, _ = self.m.read_doc(self.m.locate(ses_id))
        self.assertEqual(meta.get("type"), "session")
        self.assertEqual(meta.get("project"), self.slug, "세션 문서가 프로젝트 없이 섰다")

    def test_p2_a_request_without_project_lands_in_the_default(self):
        """정상 — 명시 없이 만든 요청은 기본 프로젝트다(REQ-20260908-031 의 이음)."""
        args = type("A", (), {"project": None, "project_tag": None,
                              "doc_type": "request"})()
        got = self.m.resolve_project(args, "hong", "")
        proj = got[0] if isinstance(got, tuple) else got
        self.assertEqual(proj, self.slug)

    def test_p2b_a_knowledge_doc_lands_in_the_default_too(self):
        """정상 — 지식 문서도 명시 없이 만들면 기본 프로젝트다(실측: 작업자의 DOC-20260909-001)."""
        args = type("A", (), {"project": None, "project_tag": None,
                              "doc_type": "knowledge"})()
        got = self.m.resolve_project(args, "hong", "")
        proj = got[0] if isinstance(got, tuple) else got
        self.assertEqual(proj, self.slug)

    def test_p3_emptying_the_project_is_refused(self):
        """실패 — 비우는 길이 없다: set --project '' 는 거절하고 문서는 그대로다."""
        args = type("A", (), {"project": None, "project_tag": None,
                              "doc_type": "request"})()
        proj = self.m.resolve_project(args, "hong", "")
        proj = proj[0] if isinstance(proj, tuple) else proj
        doc_id = self.m.next_id("REQ", "requests")
        ts = self.m.now_iso()
        meta = {"id": doc_id, "type": "request", "title": "t", "summary": "s",
                "status": "open", "user": "hong", "project": proj,
                "created": ts, "updated": ts, "tags": []}
        p = os.path.join(self.root, "vault", "requests", ts[:4], ts[5:7], doc_id + ".md")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        self.m.write_doc(p, meta, "## Original\nt\n")
        with self.assertRaises(ValueError) as cm:
            self.m.do_set(doc_id, {"project": ""}, actor="hong")
        self.assertIn("비울 수 없", str(cm.exception))
        meta2, _ = self.m.read_doc(self.m.locate(doc_id))
        self.assertEqual(meta2.get("project"), proj)


class TheVaultHoldsNoBareDocument(unittest.TestCase):
    """회귀 — 이 저장소의 vault 에 project 가 빈 요청·지식·세션 문서가 없다.
    남아 있으면 그것은 필터로 볼 것이 아니라 고칠 결함이다."""

    def test_p4_every_document_names_a_project(self):
        import re
        bare = []
        for kind in ("requests", "knowledge", "sessions"):
            base = os.path.join(ROOT, "vault", kind)
            for dp, _dn, fns in os.walk(base):
                if ".trash" in dp:
                    continue
                for fn in fns:
                    if not fn.endswith(".md"):
                        continue
                    # 프론트매터가 4KB 를 넘는 문서가 흔하다(contributions) — 통째로 읽는다.
                    with open(os.path.join(dp, fn), encoding="utf-8", errors="replace") as f:
                        head = f.read()
                    if not head.startswith("---"):
                        continue
                    fm = head.split("\n---", 1)[0]
                    mm = re.search(r"^project:\s*(.*)$", fm, re.M)
                    val = (mm.group(1).strip().strip('"\'') if mm else "")
                    if not val:
                        bare.append(os.path.relpath(os.path.join(dp, fn), ROOT))
        self.assertEqual(bare, [], "프로젝트 없는 문서가 남았다 (REQ-20260909-026): "
                         + ", ".join(bare[:10]))


if __name__ == "__main__":
    unittest.main()
