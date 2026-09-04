"""상태가 거짓말하지 않게 하는 세 장치 (REQ-20260828-005-62x6).

사용자: "같은 문제가 발생하지 않게 해야지. 진지하게 검토부터 해. 단순 대응을 하지말고."

실측 — 커밋 시각과 문서가 done 이 된 시각의 차이다. 커밋 메시지에는 그 REQ
번호가 적혀 있었다. 필요한 정보는 이미 있었는데 잇는 것이 없었다.

    REQ-045   커밋 21:43   전이 23:03   1시간 20분
    REQ-074   커밋 23:05   전이 23:58      53분
    REQ-077   커밋 01:02   전이 07:18   6시간 16분
    REQ-078   클레임 23:57  착수 없음    7시간 30분

원인 셋과 장치 셋:

    커밋과 전이가 끊겨 있다      → post-commit 이 문서에 사실을 남긴다
    클레임이 착수를 뜻하지 않는다 → 움직이지 않은 클레임은 유예 뒤 풀린다
    경고가 넓어 안 읽힌다         → 고칠 명령이 분명한 둘만 낸다

**done 까지 자동으로 옮기지는 않는다.** 커밋이 곧 완료는 아니고 done 은 목표
대비 근거를 요구한다 — 근거 없는 자동 완료는 거짓 진행보다 나쁜 거짓 완료다.

실행: python3 tests/ state_truth
"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")


def _ago(secs):
    return (datetime.datetime.now().astimezone()
            - datetime.timedelta(seconds=secs)).isoformat(timespec="seconds")


class StateTruth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9truth-")
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "boxA"
        os.environ["S9_USER"] = "alice"
        cls.env = {**os.environ, "S9_SESSION": "abcd1234"}
        cls.cli("init")
        cls.cli("user", "add", "alice")
        spec = importlib.util.spec_from_loader(
            "s9_truth", importlib.machinery.SourceFileLoader("s9_truth", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def cli(cls, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=30)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def _backdate(self, rid, secs):
        """문서의 updated 를 과거로 — 진전의 시계는 문서가 바뀐 때다."""
        ts = _ago(secs)
        for dp, _dn, fns in os.walk(os.path.join(self.root, "vault")):
            for fn in fns:
                if fn.startswith(rid) and fn.endswith(".md"):
                    q = os.path.join(dp, fn)
                    t = open(q, encoding="utf-8").read()
                    t = "\n".join(
                        (f"updated: {ts}" if ln.startswith("updated:") else ln)
                        for ln in t.splitlines()) + "\n"
                    open(q, "w", encoding="utf-8").write(t)
                    self.cli("index", "rebuild")
                    return
        raise AssertionError(f"문서 없음: {rid}")

    def mk(self, title="무엇인가"):
        rid = self.cli("new", "request", "--title", title, "--summary", "s",
                       "--goal", "g", "--size", "S", "--user", "alice",
                       "--body", "x").split()[0]
        self.cli("status", rid, "in-progress", "--note", "착수")
        return rid

    def binding(self):
        p = os.path.join(self.root, "state", "sessions",
                         "boxA__abcd1234.json")
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def write_binding(self, b):
        p = os.path.join(self.root, "state", "sessions",
                         "boxA__abcd1234.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False)

    # ---- A. 커밋이 문서에 남는다 ----

    # N1. post-commit 훅이 설치된다 — 설치되지 않으면 아무 일도 안 일어난다
    def test_state_truth(self):
        """StateTruth 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_post_commit_installed"):
                src = open(INSTALL, encoding="utf-8").read()
                self.assertIn('"post-commit"', src)
                self.assertIn("commit-note", src)

            # N2. 커밋 메시지의 REQ 를 읽어 그 문서에 남긴다
        with self.subTest("n2_commit_recorded"):
                rid = self.mk("커밋될 것")
                subprocess.run(["git", "init", "-q"], cwd=self.root, timeout=20)
                subprocess.run(["git", "config", "user.email", "t@example.invalid"],
                               cwd=self.root, timeout=10)
                subprocess.run(["git", "config", "user.name", "t"], cwd=self.root,
                               timeout=10)
                with open(os.path.join(self.root, "f.txt"), "w") as f:
                    f.write("x")
                subprocess.run(["git", "add", "f.txt"], cwd=self.root, timeout=10)
                subprocess.run(["git", "commit", "-q", "-m", f"무엇을 고쳤다 ({rid})"],
                               cwd=self.root, timeout=20)
                self.cli("commit-note")
                t = self.cli("show", rid)
                self.assertIn("commit", t)
                self.assertIn("무엇을 고쳤다", t)

            # B1. 이미 끝난 문서에는 붙이지 않는다
        with self.subTest("b1_done_doc_skipped"):
                src = open(S9, encoding="utf-8").read()
                i = src.index("def cmd_commit_note(")
                self.assertIn('("done", "cancelled")',
                              src[i:src.index("\ndef ", i + 10)])

            # F1. done 으로 자동 전이하지 않는다 — 근거 없는 완료는 거짓 진행보다 나쁘다
        with self.subTest("f1_no_auto_done"):
                src = open(S9, encoding="utf-8").read()
                i = src.index("def cmd_commit_note(")
                seg = src[i:src.index("\ndef ", i + 10)]
                # 상태를 **읽는** 것은 맞다(끝난 문서를 건너뛰려면 봐야 한다).
                # 금지하는 것은 옮기는 것이다.
                self.assertNotIn("do_transition", seg)
                self.assertNotIn('"status",', seg,
                                 "커밋이 s9 status 를 불러 상태를 옮기고 있다")

            # ---- B. 착수 없는 클레임은 풀린다 ----

            # N3. 잡아만 놓고 유예가 지나면 클레임이 아니다
        with self.subTest("n3_idle_claim_expires"):
                rid = self.mk("잡아만 놓을 것")
                # 잡은 뒤로 문서가 한 번도 안 움직인 상황을 실제로 만든다 —
                # 잡기 전에 마지막으로 움직였고, 그 뒤 유예를 넘겼다.
                self._backdate(rid, self.m.CLAIM_GRACE + 1200)
                b = self.binding()
                b["active_reqs"] = [rid]
                b["claim_at"] = {rid: _ago(self.m.CLAIM_GRACE + 600)}
                self.write_binding(b)
                self.assertTrue(self.m.claim_dead(b, rid))
                self.assertNotIn(rid, self.m.binding_req_ids(b))

            # B2. 클레임 뒤 문서가 움직였으면 살아 있는 클레임이다
        with self.subTest("b2_moved_after_claim_is_alive"):
                rid = self.mk("일하는 중인 것")
                b = self.binding()
                b["active_reqs"] = [rid]
                b["claim_at"] = {rid: _ago(self.m.CLAIM_GRACE + 600)}
                self.write_binding(b)
                self.cli("note", rid, "진행 중")          # 문서가 움직인다
                self.assertFalse(self.m.claim_dead(b, rid))

            # B3. 방금 잡은 것은 놓지 않는다
        with self.subTest("b3_fresh_claim_kept"):
                rid = self.mk("방금 잡은 것")
                b = self.binding()
                b["active_reqs"] = [rid]
                b["claim_at"] = {rid: _ago(5)}
                self.write_binding(b)
                self.assertFalse(self.m.claim_dead(b, rid))

            # F2. 클레임 시각을 모르면 판정하지 않는다 — 근거 없이 남의 클레임을 뺏지 않는다
        with self.subTest("f2_unknown_claim_time_kept"):
                rid = self.mk("옛 바인딩")
                b = {"active_reqs": [rid]}
                self.assertFalse(self.m.claim_dead(b, rid))

            # N4. 클레임하면 시각이 남는다
        with self.subTest("n4_claim_stamped"):
                rid = self.mk("클레임할 것")
                self.cli("last", rid, "--add")
                self.assertIn(rid, self.binding().get("claim_at", {}))

            # ---- C. 경고를 좁힌다 ----

            # N5. 커밋됐는데 전이 안 된 것을 짚고, 고칠 명령을 함께 준다
        with self.subTest("n5_loose_names_the_fix"):
                rid = self.mk("커밋만 된 것")
                self.cli("note", rid, "커밋 abc1234 — 무엇을 고쳤다", "--label", "commit")
                rows = [r for r in self.m.loose_requests() if r["id"] == rid]
                self.assertTrue(rows, "커밋됐는데 전이 안 된 것을 못 잡는다")
                self.assertEqual(rows[0]["kind"], "committed")
                self.assertIn(f"s9 status {rid} done", rows[0]["fix"])

            # B4. 평범한 진행 중은 끼지 않는다 — 넓은 목록은 훑고 넘어가게 된다
        with self.subTest("b4_ordinary_not_listed"):
                rid = self.mk("그냥 진행 중")
                self.assertNotIn(rid, [r["id"] for r in self.m.loose_requests()])

            # N6. 프롬프트 훅이 매 턴 주입한다 — 표식만으로는 약하다
        with self.subTest("n6_hook_injects"):
            src = open(HOOK, encoding="utf-8").read()
            self.assertIn('"loose"', src)
            self.assertIn("{loose}", src)

if __name__ == "__main__":
    unittest.main()
