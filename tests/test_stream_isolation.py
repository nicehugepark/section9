"""Stream 탭 열람 격리 테스트 (REQ-20260824-022, 부모 REQ-20260824-017).

Stream API(/api/streams, /api/stream)가 문서 가시성(doc_visible)과 동일한
가드레일을 따라, 비멤버가 다른 사용자 세션의 원문(transcript)을 우회
열람하지 못한다. 가시성 기준 = 그 세션(sid8)의 SES 문서 가시성; SES 문서가
없으면 그 세션 바인딩의 user 본인·admin만(보수적 기본).

신원은 서버 파생 whoami(REQ-20260824-027) — admin 서버의 ?as= 로 시점을
전환해 검증하고, 비admin 직접 시점은 bob 서버로 본다(017 테스트와 동일).

격리: S9_ROOT=mktemp + S9_MACHINE 고정 — 라이브 vault를 건드리지 않는다.
실행: python3 tests/test_stream_isolation.py
"""
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
MACHINE = "TESTMACH"

# sid8 고정 픽스처 (스트림 파일명은 full-SID 흉내로 접미사 부여)
SID_ALICE = "aaaa1111"   # SES 있음, 무소속 → 작성자 alice만
SID_PX = "pppp1111"      # SES 있음, project px → 멤버 alice + admin
SID_BOUND = "bbbb2222"   # SES 없음, 바인딩 user=bob → bob + admin
SID_ORPHAN = "oooo3333"  # SES 없음, 바인딩 없음 → admin만


# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402


TRANSCRIPT = (
    '{"type":"user","timestamp":"2026-08-24T05:00:00Z",'
    '"message":{"content":"hello stream"}}\n'
    '{"type":"assistant","timestamp":"2026-08-24T05:00:01Z",'
    '"message":{"content":[{"type":"text","text":"hi there"}]}}\n'
)


class TestStreamIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9strm-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": MACHINE,
                   "S9_REWORK_WATCH": "off"}
        cls.env.pop("S9_SESSION", None)
        cls.env.pop("S9_USER", None)

        def cli(*argv, expect=0):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=cls.env, timeout=15,
                               stdin=subprocess.DEVNULL)
            if expect is not None and r.returncode != expect:
                raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                     f"{r.stdout}{r.stderr}")
            return r
        cls.cli = staticmethod(cli)

        cli("init")
        cli("user", "add", "boss", "--role", "admin")
        cli("user", "add", "alice")
        cli("user", "add", "bob")
        cli("project", "add", "px", "--name", "PX", "--user", "alice")

        # SES 문서: alice 개인 세션(무소속) / px 프로젝트 세션
        cli("log", "alice private work", "--session", SID_ALICE,
            "--user", "alice")
        cli("log", "px project work", "--session", SID_PX, "--user", "alice")
        # px 세션의 SES 문서에 project 부여 (frontmatter 직접 편집 + 재인덱스)
        ses_px = cls._find_ses(SID_PX)
        with open(ses_px, encoding="utf-8") as f:
            text = f.read()
        assert "\nproject:" not in text
        with open(ses_px, "w", encoding="utf-8") as f:
            f.write(text.replace(f"session: {SID_PX}",
                                 f"session: {SID_PX}\nproject: px", 1))
        cli("index", "rebuild")

        # SES 없는 세션의 바인딩 (attach 산출물과 동일 형태)
        state = os.path.join(cls.tmp, "state", "sessions")
        os.makedirs(state, exist_ok=True)
        with open(os.path.join(state, f"{MACHINE}__{SID_BOUND}.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"machine": MACHINE, "session": SID_BOUND,
                       "user": "bob", "history": []}, f)

        # 스트림 미러 파일 (파일명 = full SID 흉내: sid8 + 접미사)
        streams = os.path.join(cls.tmp, "streams")
        os.makedirs(streams, exist_ok=True)
        for sid in (SID_ALICE, SID_PX, SID_BOUND, SID_ORPHAN):
            with open(os.path.join(streams, f"{sid}-full.jsonl"), "w",
                      encoding="utf-8") as f:
                f.write(TRANSCRIPT)

        cls.port = free_port()        # S9_USER=boss (admin)
        cls.port_bob = free_port()    # S9_USER=bob (비admin 직접 시점)
        cls.srvs = []
        for port, s9user in ((cls.port, "boss"), (cls.port_bob, "bob")):
            env = {**cls.env, "S9_USER": s9user}
            cls.srvs.append(subprocess.Popen(
                [S9, "serve", "--host", "127.0.0.1", "--port", str(port)],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        for port in (cls.port, cls.port_bob):
            wait_server(port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기

    @classmethod
    def _find_ses(cls, sid8):
        root = os.path.join(cls.tmp, "vault", "sessions")
        for dirpath, _, files in os.walk(root):
            for fn in files:
                p = os.path.join(dirpath, fn)
                with open(p, encoding="utf-8") as f:
                    if f"session: {sid8}" in f.read():
                        return p
        raise AssertionError(f"SES doc not found for {sid8}")

    @classmethod
    def tearDownClass(cls):
        for p in cls.srvs:
            p.terminate()
        for p in cls.srvs:
            p.wait(timeout=5)

    @classmethod
    def get(cls, path, port=None, **params):
        qs = urllib.parse.urlencode(params)
        url = f"http://127.0.0.1:{port or cls.port}{path}" \
              + (f"?{qs}" if qs else "")
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode())
            except (ConnectionError, urllib.error.URLError):
                # 기동 직후 loopback RST 플레이크 (WSL2) — 짧게 재시도
                if attempt == 2:
                    raise
                time.sleep(0.3)

    def stream_sids(self, viewer):
        # admin(boss) 서버에서 ?as=<viewer> 시점 전환 (boss 본인은 무지정)
        params = {} if viewer == "boss" else {"as": viewer}
        code, d = self.get("/api/streams", **params)
        self.assertEqual(code, 200)
        return {s["session"] for s in d["streams"]}

    # S1. 목록 필터: 비멤버 시점에서 타인 세션 스트림 제외
    def test_test_stream_isolation(self):
        """TestStreamIsolation 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("s1_list_filtered"):
                sids = self.stream_sids("bob")
                self.assertNotIn(f"{SID_ALICE}-full", sids)   # alice 개인 세션
                self.assertNotIn(f"{SID_PX}-full", sids)      # px 멤버 아님
                self.assertNotIn(f"{SID_ORPHAN}-full", sids)  # 기록 없는 세션
                self.assertIn(f"{SID_BOUND}-full", sids)      # 자기 바인딩 세션

            # S2. 직접 조회 404 — 미존재 스트림과 동일 응답 (존재 여부 비누설)
        with self.subTest("s2_direct_fetch_404"):
                code, d = self.get("/api/stream", session=f"{SID_ALICE}-full",
                                   **{"as": "bob"})
                self.assertEqual(code, 404)
                code2, d2 = self.get("/api/stream", session="nosuchsess-full",
                                     **{"as": "bob"})
                self.assertEqual(code2, 404)
                self.assertEqual(d, d2)  # 응답 본문까지 동일해야 비누설
                # 비admin 서버 직접 시점 + as 상승 시도도 차단
                code, _ = self.get("/api/stream", port=self.port_bob,
                                   session=f"{SID_ALICE}-full", **{"as": "boss"})
                self.assertEqual(code, 404)

            # S3. admin 전체 열람
        with self.subTest("s3_admin_sees_all"):
                sids = self.stream_sids("boss")
                for sid in (SID_ALICE, SID_PX, SID_BOUND, SID_ORPHAN):
                    self.assertIn(f"{sid}-full", sids)
                for sid in (SID_ALICE, SID_PX, SID_BOUND, SID_ORPHAN):
                    code, _ = self.get("/api/stream", session=f"{sid}-full")
                    self.assertEqual(code, 200)

            # S4. 본인·프로젝트 멤버 열람 허용
        with self.subTest("s4_owner_and_member_allowed"):
                sids = self.stream_sids("alice")
                self.assertIn(f"{SID_ALICE}-full", sids)  # 본인(무소속 SES=작성자)
                self.assertIn(f"{SID_PX}-full", sids)     # px 활성 멤버
                code, d = self.get("/api/stream", session=f"{SID_ALICE}-full",
                                   **{"as": "alice"})
                self.assertEqual(code, 200)
                code, _ = self.get("/api/stream", session=f"{SID_PX}-full",
                                   **{"as": "alice"})
                self.assertEqual(code, 200)
                # 비admin whoami 서버의 기본 시점 = 자기 자신 (bob 서버, as 없이)
                code, _ = self.get("/api/stream", port=self.port_bob,
                                   session=f"{SID_BOUND}-full")
                self.assertEqual(code, 200)

            # S5. SES 문서 없는 스트림 = 보수 기본 (바인딩 user 본인·admin만)
        with self.subTest("s5_no_ses_conservative"):
                self.assertIn(f"{SID_BOUND}-full", self.stream_sids("bob"))
                self.assertNotIn(f"{SID_BOUND}-full", self.stream_sids("alice"))
                code, _ = self.get("/api/stream", session=f"{SID_BOUND}-full",
                                   **{"as": "alice"})
                self.assertEqual(code, 404)
                # 바인딩조차 없으면 비admin 누구에게도 안 보인다
                for viewer in ("alice", "bob"):
                    self.assertNotIn(f"{SID_ORPHAN}-full", self.stream_sids(viewer))
                    code, _ = self.get("/api/stream", session=f"{SID_ORPHAN}-full",
                                       **{"as": viewer})
                    self.assertEqual(code, 404)

            # S6. 회귀: 가시 스트림의 파싱·증분(offset/after) 기존 동작 유지
        with self.subTest("s6_stream_parse_regression"):
            code, d = self.get("/api/stream", session=f"{SID_ALICE}-full",
                               **{"as": "alice"})
            self.assertEqual(code, 200)
            roles = [e["role"] for e in d["events"]]
            self.assertEqual(roles, ["user", "assistant"])
            self.assertEqual(d["events"][0]["text"], "hello stream")
            self.assertGreater(d["offset"], 0)
            # after=offset 증분 재조회 → 새 이벤트 없음
            code, d2 = self.get("/api/stream", session=f"{SID_ALICE}-full",
                                after=d["offset"], **{"as": "alice"})
            self.assertEqual(code, 200)
            self.assertEqual(d2["count"], 0)
            self.assertEqual(d2["offset"], d["offset"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
