"""받은 삭제를 목록에서도 지운다 (REQ-20260909-038).

실측 2026-09-09 10:56: 맥이 REQ-20260909-008-2n7g 를 지웠다(원본 삭제 + .trash 추가,
커밋 559b528c·23266cc9). 이 쪽 수신 폴이 받았는데 catalog 에는 줄이 남아 Board 에
없는 문서의 카드가 섰다. 까닭: git 이 그 둘을 rename 으로 접어 `diff --name-only`
가 새 경로(.trash)만 내고, 색인은 .trash 를 거르므로 옛 경로에 묘비가 서지 않았다.

로컬 bare 저장소 하나와 클론 둘로 재현한다 — 네트워크 없음.
실행: python3 tests/ sync_receive_drops_deleted
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
DOC_ID = "REQ-20260909-901-zzzz"
REL = "vault/requests/2026/09"


def git(cwd, *a):
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, f"git {' '.join(a)} 실패: {r.stderr}"
    return r


def doc_text(did, title="시험 문서"):
    return (f"---\nid: {did}\ntype: request\ntitle: {title}\nstatus: open\n"
            f"user: t\ncreated: 2026-09-09T10:00:00+09:00\n"
            f"updated: 2026-09-09T10:00:00+09:00\n---\n\n## Original\n\n본문\n")


def stat_key(path):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


class ReceiveDropsDeleted(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_SYNC")}
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        os.environ.pop("S9_SYNC", None)
        self.tmp = tempfile.mkdtemp(prefix="s9recvdrop-")
        self.bare = os.path.join(self.tmp, "origin.git")
        git(self.tmp, "init", "-q", "--bare", self.bare)
        # 이 쪽(수신하는 머신)
        self.root = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(self.root, REL))
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        with open(os.path.join(self.root, "vault", ".keep"), "w") as f:
            f.write("")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "첫")
        git(self.root, "remote", "add", "origin", self.bare)
        git(self.root, "push", "-q", "-u", "origin", "main")
        os.environ["S9_ROOT"] = self.root
        name = "s9recvdrop_" + os.path.basename(self.tmp)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.sync_set_mode("remote")
        self.m.rebuild_index(quiet=True, full=True)
        # 다른 쪽(지우는 머신)
        self.other = os.path.join(self.tmp, "other")
        git(self.tmp, "clone", "-q", self.bare, self.other)
        git(self.other, "config", "user.email", "o@example.com")
        git(self.other, "config", "user.name", "o")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ids(self):
        return {r["id"] for r in self.m.load_catalog()}

    def other_push(self, msg):
        git(self.other, "add", "-A")
        git(self.other, "commit", "-q", "-m", msg)
        git(self.other, "push", "-q", "origin", "main")

    def other_creates(self):
        os.makedirs(os.path.join(self.other, REL), exist_ok=True)
        with open(os.path.join(self.other, REL, DOC_ID + ".md"), "w",
                  encoding="utf-8") as f:
            f.write(doc_text(DOC_ID))
        self.other_push("new " + DOC_ID)

    def other_trashes(self):
        """s9 rm 과 같은 모양 — 원본을 .trash 로 옮긴다(삭제 + 추가)."""
        src = os.path.join(self.other, REL, DOC_ID + ".md")
        dst_dir = os.path.join(self.other, REL, ".trash")
        os.makedirs(dst_dir, exist_ok=True)
        os.replace(src, os.path.join(dst_dir, DOC_ID + ".md"))
        self.other_push("rm " + DOC_ID)

    # ---- S1. 받은 새 문서는 목록에 선다 ----------------------------------
    def test_s1_received_new_doc_enters_catalog(self):
        self.other_creates()
        self.assertEqual(self.m._sync_poll_once(), "ok")
        self.assertTrue(os.path.exists(os.path.join(self.root, REL, DOC_ID + ".md")))
        self.assertIn(DOC_ID, self.ids(), "받은 새 문서가 목록에 없다")

    # ---- S2. 받은 삭제(.trash 이동)는 목록에서도 지운다 ------------------
    def test_s2_received_trash_move_leaves_catalog(self):
        self.other_creates()
        self.assertEqual(self.m._sync_poll_once(), "ok")
        self.assertIn(DOC_ID, self.ids())
        self.other_trashes()
        self.assertEqual(self.m._sync_poll_once(), "ok")
        self.assertFalse(os.path.exists(os.path.join(self.root, REL, DOC_ID + ".md")),
                         "pull 이 원본을 지우지 않았다 — 시험 전제가 틀렸다")
        self.assertNotIn(DOC_ID, self.ids(),
                         "받은 삭제가 목록에 남아 있다 — Board 에 없는 문서의 카드가 선다")

    # ---- S3. 받은 것이 없으면 목록 파일은 그대로다 -----------------------
    def test_s3_nothing_received_leaves_catalog_untouched(self):
        self.other_creates()
        self.assertEqual(self.m._sync_poll_once(), "ok")
        cat = os.path.join(self.root, "index", "catalog.jsonl")
        before = (stat_key(cat), stat_key(cat + ".delta"))
        self.assertEqual(self.m._sync_poll_once(), "none")
        self.assertEqual((stat_key(cat), stat_key(cat + ".delta")), before,
                         "받은 것이 없는데 목록 파일이 바뀌었다")

    # ---- S4. 회귀: rename 으로 접히는 범위에서도 옛 경로에 묘비가 선다 -----
    def test_s4_range_folded_as_rename_still_tombstones_old_path(self):
        src = os.path.join(self.root, REL, DOC_ID + ".md")
        with open(src, "w", encoding="utf-8") as f:
            f.write(doc_text(DOC_ID))
        git(self.root, "add", "-A"); git(self.root, "commit", "-q", "-m", "new")
        before = git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.m.index_upsert(src)
        self.assertIn(DOC_ID, self.ids())
        trash = os.path.join(self.root, REL, ".trash")
        os.makedirs(trash)
        os.replace(src, os.path.join(trash, DOC_ID + ".md"))
        git(self.root, "add", "-A"); git(self.root, "commit", "-q", "-m", "rm")
        after = git(self.root, "rev-parse", "HEAD").stdout.strip()
        # git 은 이 범위를 rename 으로 본다 — 그것이 사고의 모양이다
        r = git(self.root, "diff", "--name-status", before, after, "--", "vault")
        self.assertTrue(r.stdout.startswith("R"), f"시험 전제: rename 이어야 한다: {r.stdout}")
        self.assertEqual(self.m.index_sync_range(before, after), 1)
        self.assertNotIn(DOC_ID, self.ids(), "rename 으로 접힌 삭제가 목록에 남았다")

    # ---- S5. 안전: 문서 이동(A+D 같은 id)은 새 자리의 행이 남는다 ---------
    def test_s5_moved_doc_keeps_row_at_new_path(self):
        src = os.path.join(self.root, REL, DOC_ID + ".md")
        with open(src, "w", encoding="utf-8") as f:
            f.write(doc_text(DOC_ID))
        git(self.root, "add", "-A"); git(self.root, "commit", "-q", "-m", "new")
        before = git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.m.index_upsert(src)
        new_dir = os.path.join(self.root, "vault", "requests", "2026", "10")
        os.makedirs(new_dir)
        dst = os.path.join(new_dir, DOC_ID + ".md")
        os.replace(src, dst)
        git(self.root, "add", "-A"); git(self.root, "commit", "-q", "-m", "move")
        after = git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(self.m.index_sync_range(before, after), 2)
        rows = {r["id"]: r for r in self.m.load_catalog()}
        self.assertIn(DOC_ID, rows, "옮긴 문서가 목록에서 사라졌다 — 묘비가 새 행을 지웠다")
        self.assertIn("2026/10", rows[DOC_ID].get("path", "").replace("\\", "/"),
                      "옮긴 문서의 경로가 새 자리가 아니다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
