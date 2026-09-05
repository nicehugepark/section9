"""멈춘 작업이 스스로 드러난다 (REQ-20260827-046-62x6).

실사고 2026-08-27 19:57~20:25. 리드가 REQ-20260827-042 를 in-progress 로 옮기고
이어진 다른 요청들로 옮겨 가며 손을 뗐다. 30분 뒤 **사용자가** "042 는 아무 세션도
진행을 안 하는데 어떻게 되고 있나"로 발견했다.

이 저장소에는 이미 "놓치지 않게 매 턴 눈앞에 밀어넣는" 장치가 있다 — `reopened`
(반려 대기)와 `untitled`(제목 미정리). 둘 다 프롬프트 훅이 매 턴 주입한다.
**표식만으로는 약하고 주입해야 실제 장치가 된다**는 것을 이미 배워서 그렇게
만들었다(REQ-20260825-062).

그런데 "클레임해 놓고 멈춘 것"에는 그 장치가 없었다. 대시보드는 회색 점으로
정직하게 표시하지만 그건 **사람이 화면을 볼 때만** 보인다. 리드는 화면을 안 본다.

판정은 대시보드의 live 판정(`catalog_with_live`)과 **같은 함수**를 쓴다. 두 벌이면
한 벌만 고쳐진다 — 이 저장소가 여러 번 겪은 일이다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ stalled_claim
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class StalledClaim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9stall-")
        cls.claude = os.path.join(cls.root, "cc")
        os.makedirs(os.path.join(cls.claude, "proj"), exist_ok=True)
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox",
                   "S9_CLAUDE_PROJECTS": cls.claude}
        cls.env.pop("S9_SESSION", None)
        cls.cli(None, "init")
        cls.cli(None, "user", "add", "alice")

        def mk(sess, title):
            rid = cls.cli(sess, "new", "request", "--title", title,
                          "--summary", "s", "--goal", "g", "--size", "S",
                          "--user", "alice", "--body", "x").split()[0]
            cls.cli(sess, "status", rid, "in-progress", "--note", "t")
            return rid

        # A: 오래 멈춘 것 · B: 지금 일하는 중 · C: done (대상 아님)
        cls.A = mk("aaaa1111", "오래 멈춘 것")
        cls.B = mk("bbbb2222", "일하는 중")
        cls.C = mk("cccc3333", "끝난 것")
        cls.cli("cccc3333", "status", cls.C, "done", "--note", "t")
        # D: blocked — 이미 사유가 붙어 있고 자리가 따로 있다
        cls.D = mk("dddd4444", "막힌 것")
        cls.cli("dddd4444", "status", cls.D, "blocked", "--note", "사유")
        # E: 무인 워커가 도는 중 — 멈춘 것이 아니다
        cls.E = mk("eeee5555", "워커가 도는 중")

        streams = os.path.join(cls.root, "streams")
        os.makedirs(streams, exist_ok=True)
        old = time.time() - 3600
        for sid, age in (("aaaa1111", old), ("bbbb2222", time.time()),
                         ("eeee5555", old)):
            p = os.path.join(streams, sid + ".jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"role": "assistant", "text": "x"}) + "\n")
            os.utime(p, (age, age))
        # A 는 "한 시간 전에 착수했고 그 뒤로 진전 없음" 이어야 한다.
        # 방금 착수한 것을 멈췄다고 부르면 안 되므로(착수 직후 유예) 문서의
        # status_since 를 과거로 돌려 실제 상황을 만든다.
        cls._backdate(cls.A, 3600)

        # E 만 살아 있는 워커 마커 (이 프로세스 pid)
        ar = os.path.join(cls.root, "state", "auto_resume")
        os.makedirs(ar, exist_ok=True)
        with open(os.path.join(ar, cls.E + ".json"), "w") as f:
            json.dump({"last": time.time() - 60, "count": 1,
                       "pid": os.getpid()}, f)

    @classmethod
    def _backdate(cls, rid, secs):
        import datetime
        ts = (datetime.datetime.now().astimezone()
              - datetime.timedelta(seconds=secs)).isoformat(timespec="seconds")
        for dp, _dn, fns in os.walk(os.path.join(cls.root, "vault")):
            for fn in fns:
                if fn.startswith(rid) and fn.endswith(".md"):
                    q = os.path.join(dp, fn)
                    t = open(q, encoding="utf-8").read()
                    # updated 도 함께 되돌린다 (REQ-20260827-074): 멈춤 판정의
                    # 시계는 "언제 착수했나"가 아니라 **"문서가 언제 마지막으로
                    # 바뀌었나"** 다. 착수만 과거로 돌리고 updated 를 지금으로
                    # 두면 "한 시간 전에 착수했는데 방금 뭔가 했다"가 되어,
                    # 만들려던 상황(착수 뒤 아무 일도 없음)이 아니다.
                    t = "\n".join(
                        (f"status_since: {ts}" if ln.startswith("status_since:")
                         else f"updated: {ts}" if ln.startswith("updated:")
                         else ln) for ln in t.splitlines()) + "\n"
                    open(q, "w", encoding="utf-8").write(t)
                    cls.cli(None, "index", "rebuild")
                    return
        raise AssertionError(f"문서 없음: {rid}")

    @classmethod
    def cli(cls, sess, *argv, expect=0):
        env = dict(cls.env)
        if sess:
            env["S9_SESSION"] = sess
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env, timeout=30)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def stalled(self, *extra):
        return self.cli(None, "stalled", *extra)

    # N1. 오래 멈춘 것이 뜬다
    def test_stalled_claim(self):
        """StalledClaim 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_stalled_listed"):
                self.assertIn(self.A, self.stalled())

            # N2. 방금 움직인 것은 안 뜬다 — 거짓 목록은 안 읽히는 목록이 된다
        with self.subTest("n2_working_not_listed"):
                self.assertNotIn(self.B, self.stalled())

            # B4. 세션이 살아 있다는 것만으로는 넘어가지 않는다 (REQ-20260827-074).
            #     리드 세션은 늘 살아 있고 여러 요청을 한꺼번에 클레임한다 — 그걸
            #     증거로 쳤더니 리드가 잡아 놓고 손을 뗀 경우를 하나도 못 잡았다.
            #     그게 이 장치가 겨냥한 바로 그 상황이었다.
            #     판정이 사는 자리는 2026-08-28 에 `stall_mins()` 하나로 옮겨졌다
            #     (REQ-20260828-036) — 화면이 옛 축에 남아 CLI 와 다른 말을 했기
            #     때문이다. 그래서 여기서 보는 곳도 그 자리다.
        with self.subTest("b4_live_session_is_not_evidence"):
                # 판정은 2026-08-29 에 `stall_verdict()` 로 한 번 더 옮겨졌다
                # (REQ-20260829-036) — 멈춤 하나로 부르던 것이 셋(멈춤·대기·미상)이라
                # 나뉘었기 때문이다. `stall_mins()` 는 그 함수의 껍데기다.
                src = open(S9_SRC, encoding="utf-8").read()
                i = src.index("def stall_verdict(")
                seg = src[i:src.index("\ndef ", i + 10)]
                self.assertNotIn('r.get("live_kind") in ("session"', seg,
                                 "세션 생존을 그 요청의 진전으로 치고 있다")
                self.assertIn('r.get("updated")', seg,
                              "진전의 시계로 문서 변경 시각을 쓰지 않는다")

            # B1. 무인 워커가 도는 중이면 멈춘 것이 아니다
        with self.subTest("b1_live_worker_not_stalled"):
                self.assertNotIn(self.E, self.stalled())

            # B2. in-progress 가 아닌 것은 대상이 아니다
        with self.subTest("b2_only_in_progress"):
                out = self.stalled()
                self.assertNotIn(self.C, out)
                self.assertNotIn(self.D, out)

            # B3. 매 턴 주입이라 길면 노이즈다 — 기본 3건까지만 보인다
        with self.subTest("b3_capped"):
                m = _load("s9_stall_mod", S9)
                self.assertLessEqual(m.STALLED_SHOW, 5)
                self.assertGreaterEqual(m.STALLED_SHOW, 1)

            # F1. 판정을 두 번 만들지 않는다 — 대시보드와 같은 함수를 쓴다
        with self.subTest("f1_single_judgment"):
                m = _load("s9_stall_mod2", S9)
                self.assertTrue(callable(getattr(m, "catalog_with_live", None)),
                                "live 판정이 모듈 최상위에 없다 — CLI 가 쓸 수 없다")
                src = open(S9_SRC, encoding="utf-8").read()
                i = src.index("def stalled_requests(")
                self.assertIn("catalog_with_live", src[i:i + 1200],
                              "stalled 이 live 판정을 다시 만들고 있다")

            # N3. 프롬프트 훅이 매 턴 주입한다 — 표식만으로는 약하다
        with self.subTest("n3_hook_injects"):
            src = open(HOOK, encoding="utf-8").read()
            self.assertIn('"stalled"', src, "훅이 stalled 를 부르지 않는다")
            i = src.index('"stalled"')
            self.assertIn("emit", src[i:i + 4000].replace("\n", " ") + "emit",
                          "부르기만 하고 주입하지 않는다")

if __name__ == "__main__":
    unittest.main()
