"""기존 환경의 승계·정리·백업 (REQ-20260905-025) — 1차 판: 백업·되돌리기·표식·승계 후보.

실행: python3 tests/ env_backup
"""
import datetime
import importlib.util
import json
import os
import stat
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(HERE, "..", "bin", "s9_env.py")


def _load():
    spec = importlib.util.spec_from_file_location("s9_env_t", MOD)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


class EnvBackup(unittest.TestCase):
    def setUp(self):
        self.m = _load()
        self.home = tempfile.mkdtemp(prefix="s9home-")
        self.root = tempfile.mkdtemp(prefix="s9bk-")
        os.makedirs(os.path.join(self.home, "projects", "p1", "memory"))
        open(os.path.join(self.home, "settings.json"), "w").write('{"hooks": {}}')
        open(os.path.join(self.home, "CLAUDE.md"), "w").write("# rules\n- 존댓말로 쓴다\n- 칭찬은 하지 않는다\n")
        open(os.path.join(self.home, "projects", "p1", "memory", "MEMORY.md"), "w").write("# Memory\n- [x](x.md) — 제목은 명사구\n")
        open(os.path.join(self.home, ".credentials.json"), "w").write('{"token": "sk-ant-SECRET"}')

    def test_e1_backup_copies_verifies_and_never_touches_credentials(self):
        """E1. manifest 의 sha256 이 원본과 같고, 자격증명은 목록·디렉토리 어디에도 없으며, 0700/0600."""
        r = self.m.backup(home=self.home, root=self.root, now=datetime.datetime(2026, 9, 5, 22, 0, 0))
        self.assertTrue(r["dir"].endswith("20260905-220000"))
        rels = sorted(e["rel"] for e in r["entries"])
        self.assertEqual(rels, ["CLAUDE.md", "projects/p1/memory/MEMORY.md", "settings.json"])
        self.assertFalse(os.path.exists(os.path.join(r["dir"], ".credentials.json")))
        blob = open(os.path.join(r["dir"], "manifest.json"), encoding="utf-8").read()
        self.assertNotIn("credentials", blob); self.assertNotIn("sk-ant", blob)
        self.assertEqual(stat.S_IMODE(os.stat(r["dir"]).st_mode), 0o700)
        for e in r["entries"]:
            p = os.path.join(r["dir"], e["rel"])
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
            self.assertEqual(self.m._sha256(p), e["sha256"])
        self.assertEqual(open(os.path.join(self.root, "LATEST")).read().strip(), "20260905-220000")

    def test_e2_restore_brings_bytes_back_and_steps_aside_for_new_files(self):
        """E2. restore 는 바이트를 되돌리고, 원위치에 다른 파일이 있으면 비켜 세우며, --dry-run 은 변경 0."""
        r = self.m.backup(home=self.home, root=self.root)
        orig = open(os.path.join(self.home, "settings.json")).read()
        open(os.path.join(self.home, "settings.json"), "w").write('{"hooks": {"changed": 1}}')
        os.remove(os.path.join(self.home, "CLAUDE.md"))
        d = self.m.restore("latest", home=self.home, root=self.root, dry_run=True)
        self.assertEqual(open(os.path.join(self.home, "settings.json")).read(), '{"hooks": {"changed": 1}}')
        self.assertFalse(os.path.exists(os.path.join(self.home, "CLAUDE.md")))
        self.assertEqual(sorted(d["restored"]), ["CLAUDE.md", "settings.json"])
        res = self.m.restore("latest", home=self.home, root=self.root)
        self.assertEqual(open(os.path.join(self.home, "settings.json")).read(), orig)
        self.assertTrue(os.path.exists(os.path.join(self.home, "CLAUDE.md")))
        self.assertEqual(len(res["conflicts"]), 1)
        aside = res["conflicts"][0][1]
        self.assertTrue(os.path.exists(aside) and aside.endswith(f".s9-conflict-{res['at']}"))
        self.assertIn("projects/p1/memory/MEMORY.md", res["skipped"])

    def test_e3_nothing_to_back_up_makes_no_directory(self):
        """E3. 옮길 것이 없으면 디렉토리를 만들지 않는다 — 멱등."""
        empty = tempfile.mkdtemp(prefix="s9empty-")
        r = self.m.backup(home=empty, root=self.root)
        self.assertEqual((r["dir"], r["entries"]), ("", []))
        self.assertEqual(self.m.list_backups(self.root), [])

    def test_e4_transcripts_older_than_install_are_not_ours(self):
        """E4. 설치 표식 이전의 transcript 는 설치 전의 것 — 표식이 없으면 모르니 빼지 않는다."""
        repo = tempfile.mkdtemp(prefix="s9repo-")
        old = os.path.join(self.home, "old.jsonl"); open(old, "w").write("{}\n")
        os.utime(old, (1_700_000_000, 1_700_000_000))
        self.assertFalse(self.m.predates_install(old, repo))              # 표식 없음
        self.assertTrue(self.m.mark_installed(repo, now=datetime.datetime(2026, 9, 5, 22, 0)))
        self.assertFalse(self.m.mark_installed(repo))                      # 두 번째는 안 바꾼다
        self.assertTrue(self.m.predates_install(old, repo))
        new = os.path.join(self.home, "new.jsonl"); open(new, "w").write("{}\n")
        self.assertFalse(self.m.predates_install(new, repo))

    def test_e5_inherit_candidates_are_list_items_from_the_backup_only(self):
        """E5. 승계 후보는 백업본의 CLAUDE.md·MEMORY.md 목록 항목뿐 — 데이터로 나열, 자동 채택 없음."""
        r = self.m.backup(home=self.home, root=self.root)
        cands = self.m.inherit_candidates(r["dir"])
        lines = [c[1] for c in cands]
        self.assertIn("존댓말로 쓴다", lines); self.assertIn("칭찬은 하지 않는다", lines)
        self.assertTrue(any("제목은 명사구" in l for l in lines))
        self.assertTrue(all(src in ("CLAUDE.md", "projects/p1/memory/MEMORY.md") for src, _ in cands))


if __name__ == "__main__":
    unittest.main()
