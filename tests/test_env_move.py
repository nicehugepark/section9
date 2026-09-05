"""옛 흔적 이동 정리, 2차 (REQ-20260905-029).

1차(025)는 복사 백업·논리 차단·승계였다. 2차는 설치 시각 이전의 흔적(옛 transcript·
history·sessions·shell-snapshots·daemon·file-history)을 같은 파일시스템의 격리 자리로
rename 으로 옮긴다 — 삭제 명령은 없고, 저널이 항목마다 전·후를 적어 중간에 죽어도
역순으로 되돌린다. 살아 있는 claude 가 있으면 거부한다.
"""
import importlib.util
import json
import os
import shutil
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(HERE, "..", "bin", "s9_env.py")


def _load():
    spec = importlib.util.spec_from_file_location("s9_env_mv", MOD)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


class EnvMove(unittest.TestCase):
    def setUp(self):
        self.m = _load()
        self.base = tempfile.mkdtemp(prefix="s9mv-")
        self.home = os.path.join(self.base, "claude")     # 격리 자리는 claude.s9-moved/
        self.root = os.path.join(self.base, "repo")
        os.makedirs(os.path.join(self.home, "projects", "p1", "memory"))
        os.makedirs(os.path.join(self.home, "sessions")); os.makedirs(os.path.join(self.home, "shell-snapshots"))
        os.makedirs(os.path.join(self.home, "daemon")); os.makedirs(os.path.join(self.root, "state"))
        open(os.path.join(self.home, "history.jsonl"), "w").write('{"p":"옛 프롬프트"}\n')
        open(os.path.join(self.home, "sessions", "a.json"), "w").write("{}")
        open(os.path.join(self.home, "shell-snapshots", "snap.sh"), "w").write("#")
        open(os.path.join(self.home, "daemon.lock"), "w").write("1")
        open(os.path.join(self.home, "settings.json"), "w").write("{}")
        open(os.path.join(self.home, ".credentials.json"), "w").write("SECRET")
        open(os.path.join(self.home, "CLAUDE.md"), "w").write("규칙\n")
        open(os.path.join(self.home, "projects", "p1", "memory", "MEMORY.md"), "w").write("# m\n")
        # 옛 transcript(설치 전) 와 새 transcript(설치 후)
        old = os.path.join(self.home, "projects", "p1", "old.jsonl")
        open(old, "w").write("{}\n"); os.makedirs(old[:-6])          # 동명 디렉토리
        t_old = time.time() - 3600
        os.utime(old, (t_old, t_old))
        self.m.mark_installed(self.root)   # 지금
        new = os.path.join(self.home, "projects", "p1", "new.jsonl")
        open(new, "w").write("{}\n"); t_new = time.time() + 5; os.utime(new, (t_new, t_new))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def _plan_rels(self):
        return sorted(rel for rel, _ in self.m.move_plan(self.home, self.root))

    def test_m1_refuses_while_claude_is_alive(self):
        """M1. 살아 있는 claude 가 있으면 아무것도 옮기지 않고 사유를 낸다."""
        r = self.m.move_old(self.home, self.root, alive=[(123, "claude")])
        self.assertIn("claude 가 살아 있다", r["refused"]); self.assertEqual(r["moved"], [])
        self.assertTrue(os.path.exists(os.path.join(self.home, "history.jsonl")))
        self.assertFalse(os.path.exists(self.m.moved_root(self.home)))

    def test_m2_only_pre_install_transcripts_and_never_credentials(self):
        """M2. 계획에는 설치 전 transcript(와 동명 디렉토리)·history·sessions·snapshots·daemon 만 — 설치 후 transcript·자격증명·settings·메모리는 없다."""
        rels = self._plan_rels()
        self.assertIn("projects/p1/old.jsonl", rels); self.assertIn("projects/p1/old", rels)
        for must in ("history.jsonl", "sessions", "shell-snapshots", "daemon", "daemon.lock"):
            self.assertIn(must, rels)
        for never in ("projects/p1/new.jsonl", ".credentials.json", "settings.json", "CLAUDE.md", "projects/p1/memory"):
            self.assertNotIn(never, rels)

    def test_m3_moves_by_rename_same_inode_no_delete(self):
        """M3. 옮김은 rename 이다 — inode 가 같고, 원자리에는 없고, 격리 자리에 있다. 자격증명은 제자리."""
        ino = os.stat(os.path.join(self.home, "history.jsonl")).st_ino
        r = self.m.move_old(self.home, self.root, alive=[])
        self.assertFalse(r["refused"]); self.assertTrue(r["dir"].startswith(self.home + ".s9-moved"))
        self.assertFalse(os.path.exists(os.path.join(self.home, "history.jsonl")))
        self.assertEqual(os.stat(os.path.join(r["dir"], "history.jsonl")).st_ino, ino)
        self.assertTrue(os.path.isfile(os.path.join(r["dir"], "projects", "p1", "old.jsonl")))
        self.assertTrue(os.path.isfile(os.path.join(self.home, "projects", "p1", "new.jsonl")))
        self.assertEqual(open(os.path.join(self.home, ".credentials.json")).read(), "SECRET")
        self.assertEqual(oct(os.stat(r["dir"]).st_mode & 0o777), "0o700")

    def test_m4_journal_writes_before_and_after_each_item(self):
        """M4. 저널: started → 항목마다 moving 이 ok 보다 먼저 → done. 다시 부르면 옮길 것이 없다(멱등)."""
        r = self.m.move_old(self.home, self.root, alive=[])
        recs = [json.loads(l) for l in open(os.path.join(r["dir"], "journal.jsonl"))]
        self.assertEqual(recs[0]["phase"], "started"); self.assertEqual(recs[-1]["phase"], "done")
        states = [(x.get("rel"), x.get("state")) for x in recs if "rel" in x]
        for rel, _ in r["moved"]:
            i_mv = states.index((rel, "moving")); i_ok = states.index((rel, "ok"))
            self.assertLess(i_mv, i_ok, rel)
        again = self.m.move_old(self.home, self.root, alive=[])
        self.assertEqual(again["plan"], []); self.assertEqual(again["dir"], "")

    def test_m5_restore_reverses_in_order_and_steps_aside_for_new_files(self):
        """M5. 되돌리기는 역순 rename — 전부 제자리로 오고, 그 사이 생긴 같은 이름은 .s9-conflict 로 비켜 선다."""
        r = self.m.move_old(self.home, self.root, alive=[])
        open(os.path.join(self.home, "history.jsonl"), "w").write("새로 생긴 것\n")
        b = self.m.move_restore(self.home, "latest")
        self.assertEqual([rel for rel, _ in b["back"]], [rel for rel, _ in reversed(r["moved"])])
        self.assertEqual(open(os.path.join(self.home, "history.jsonl")).read(), '{"p":"옛 프롬프트"}\n')
        self.assertTrue(any(n.startswith("history.jsonl.s9-conflict-") for n in os.listdir(self.home)))
        self.assertTrue(os.path.isdir(os.path.join(self.home, "projects", "p1", "old")))
        self.assertEqual(self.m.move_plan(self.home, self.root) and sorted(rel for rel, _ in self.m.move_plan(self.home, self.root)), self._plan_rels())
        left = [n for n in os.listdir(b["dir"]) if n != "journal.jsonl"]
        # 옮겨 갔던 디렉토리 뼈대만 남을 수 있다 — 파일은 하나도 없어야 한다
        for dp, _dn, fns in os.walk(b["dir"]):
            self.assertEqual([f for f in fns if f != "journal.jsonl"], [], dp)

    def test_m6_crash_midway_leaves_a_journal_that_restore_completes(self):
        """M6. 두 번째 항목에서 죽으면 저널에 moving/failed 가 남고, 되돌리기가 옮겨진 것만 제자리로 올린다."""
        calls = []
        def flaky(src, dst):
            calls.append(src)
            if len(calls) == 2:
                raise OSError(5, "디스크가 빠졌다")
            os.replace(src, dst)
        r = self.m.move_old(self.home, self.root, alive=[], rename=flaky)
        self.assertIn("멈췄다", r["refused"]); self.assertEqual(len(r["moved"]), 1)
        recs = [json.loads(l) for l in open(os.path.join(r["dir"], "journal.jsonl"))]
        self.assertEqual(recs[-1].get("state"), "failed"); self.assertNotEqual(recs[-1].get("phase"), "done")
        first_rel = r["moved"][0][0]
        b = self.m.move_restore(self.home, os.path.basename(r["dir"]))
        self.assertEqual([rel for rel, _ in b["back"]], [first_rel])
        self.assertEqual(sorted(self._plan_rels()), self._plan_rels())   # 전부 제자리

    def test_m7_dry_run_moves_nothing_and_no_marker_means_no_transcripts(self):
        """M7. dry-run 은 계획만 내고 바이트 하나 안 옮긴다; 설치 표식이 없으면 transcript 는 계획에 없다(모르면 안 옮긴다)."""
        r = self.m.move_old(self.home, self.root, alive=[], dry_run=True)
        self.assertTrue(r["plan"]); self.assertEqual(r["moved"], []); self.assertEqual(r["dir"], "")
        self.assertTrue(os.path.exists(os.path.join(self.home, "history.jsonl")))
        self.assertFalse(os.path.exists(self.m.moved_root(self.home)))
        os.remove(self.m.installed_at_path(self.root))
        rels = self._plan_rels()
        self.assertNotIn("projects/p1/old.jsonl", rels); self.assertIn("history.jsonl", rels)


if __name__ == "__main__":
    unittest.main()
