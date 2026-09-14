"""배포판에는 코드만 담긴다 (REQ-20260908-069) · 배포판을 만드는 도구 (REQ-20260913-006-62x6).

주인 물음 2026-09-08 21:03: 「section9 을 깃헙에서 깨끗한 상태로 릴리스 태그를 따고
배포판을 만들 수는 없나? 압축파일처럼?」 — `git archive` 와 GitHub 릴리스의
Source code zip 은 `.gitattributes` 의 `export-ignore` 를 지킨다. 이 저장소가
track 하는 자기 문서(vault)·사용자(users)·프로젝트 자료(projects)·상태(state)는
하네스가 아니라 이 설치의 데이터라 배포판에 들어가면 안 된다.

두 번째 겹(B*): `bin/s9-release` 가 그 archive 로 배포판 둘을 만든다 —
section9-<ver>-linux-macos.tar.gz 와 section9-<ver>-windows.zip. 최상위는
section9/, zip 의 bin/*.cmd 는 CRLF, 같은 commit 이면 같은 sha256. 판은 VERSION
파일 하나에서 나와 `s9 --version` 과 화면(Settings › 시스템)이 같은 값을 읽는다.

세 번째 겹(B8): 이름은 운영체제마다 다른 규칙을 쓰지 않는다 (REQ-20260914-009-62x6,
주인 물음 「배포용 압축파일 네이밍룰이 os별로 다른 이유가 있나?」). 규칙 하나 —
`section9-<버전>-<쓰는 운영체제>.<그 운영체제의 기본 압축 형식>`. 확장자가 갈리는
것은 형식이 실제로 다른 일을 하기 때문이고(tar.gz 는 실행 비트, zip 은 CRLF),
그 밖의 꼬리표는 붙지 않는다.

실행: python3 tests/ release_archive
"""
import importlib.machinery
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RELEASE = os.path.join(ROOT, "bin", "s9-release")
S9 = os.path.join(ROOT, "bin", "s9")

DATA_DIRS = ("vault", "users", "projects", "state", "scratchpad")
CODE_DIRS = ("bin", "web", "harness", "tests", "docs")
PREFIX = "section9/"


def archive_top_level():
    """HEAD 를 git archive 로 묶어 최상위 이름을 센다 — 파일을 남기지 않는다.
    `--worktree-attributes`: 속성은 지금 working tree 의 .gitattributes 를 읽는다 —
    아니면 commit 전에는 옛 속성으로 재어 고친 것이 보이지 않는다."""
    raw = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", "--worktree-attributes", "HEAD"],
                         capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
        return {m.name.split("/")[0] for m in tf.getmembers()}


def version_file(ref="HEAD"):
    """배포판이 지어지는 그 ref 의 VERSION — 작업 트리의 파일이 아니다.

    build() 는 `--ref HEAD` 로 짓고 s9-release 는 그 ref 의 VERSION 을 읽는다. 판을
    올리는 commit 을 담기 전(작업 트리 0.9.1 · HEAD 0.9.0)에는 둘이 갈리므로, 작업
    트리를 읽으면 그 순간의 검사가 전부 「파일이 없다」로 선다(2026-09-14 0.9.1 실측).
    ref 를 못 읽는 자리(git 없음)에서만 작업 트리로 물러난다."""
    if ref:
        r = subprocess.run(["git", "-C", ROOT, "show", f"{ref}:VERSION"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def build(out, ref="HEAD"):
    return subprocess.run([sys.executable, RELEASE, "--ref", ref, "--out", out],
                          capture_output=True, text=True)


def second_level(names):
    """`section9/<x>/...` 의 <x> 들 — 최상위 접두 아래의 이름."""
    return {n[len(PREFIX):].split("/")[0] for n in names if n.startswith(PREFIX) and len(n) > len(PREFIX)}


def sha256_of(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class TheArchiveIsCodeOnly(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.top = archive_top_level()

    def test_a1_data_dirs_are_not_in_the_archive(self):
        leaked = sorted(d for d in DATA_DIRS if d in self.top)
        self.assertEqual(leaked, [], "배포판에 이 설치의 데이터가 담겼다 — "
                                     ".gitattributes 의 export-ignore 를 보라")
        self.assertNotIn(".s9-sync", self.top,
                         "동기화 표식이 담기면 받은 사람의 저장소가 인스턴스로 읽힌다")

    def test_a2_code_dirs_are_in_the_archive(self):
        missing = sorted(d for d in CODE_DIRS if d not in self.top)
        self.assertEqual(missing, [], "배포판에 코드가 빠졌다")
        for f in ("README.md", "CLAUDE.md", ".gitignore", ".gitattributes"):
            self.assertIn(f, self.top, f"{f} 가 배포판에 없다")


class TheReleaseBuild(unittest.TestCase):
    """bin/s9-release 는 클래스당 한 번 만든다(B6 의 재현성 비교만 한 번 더)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9rel-")
        cls.out = os.path.join(cls.tmp, "dist")
        cls.res = build(cls.out)
        cls.ver = version_file()
        cls.tgz = os.path.join(cls.out, f"section9-{cls.ver}-linux-macos.tar.gz")
        cls.zip = os.path.join(cls.out, f"section9-{cls.ver}-windows.zip")
        cls.tar_members = []
        cls.zip_names = []
        if os.path.exists(cls.tgz):
            with tarfile.open(cls.tgz, "r:gz") as tf:
                cls.tar_members = tf.getmembers()
        if os.path.exists(cls.zip):
            with zipfile.ZipFile(cls.zip) as zf:
                cls.zip_names = zf.namelist()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_b1_two_archives_and_sums_are_made_and_reported(self):
        self.assertEqual(self.res.returncode, 0, self.res.stderr)
        for p in (self.tgz, self.zip, os.path.join(self.out, "SHA256SUMS")):
            self.assertTrue(os.path.exists(p), f"{os.path.basename(p)} 가 없다")
        for p in (self.tgz, self.zip):
            line = [ln for ln in self.res.stdout.splitlines() if os.path.basename(p) in ln]
            self.assertEqual(len(line), 1, f"{os.path.basename(p)} 의 보고 줄이 없다:\n{self.res.stdout}")
            self.assertRegex(line[0], r"\b\d+ bytes\b.*sha256 [0-9a-f]{64}$")
            self.assertIn(sha256_of(p), line[0], "보고한 sha256 이 파일과 다르다")

    def test_b2_everything_sits_under_section9(self):
        self.assertTrue(self.tar_members and self.zip_names)
        for n in [m.name for m in self.tar_members] + self.zip_names:
            self.assertTrue(n == PREFIX.rstrip("/") or n.startswith(PREFIX), f"최상위가 section9/ 가 아니다: {n}")

    def test_b3_code_only_in_both(self):
        for label, names in (("tar.gz", [m.name for m in self.tar_members]), ("zip", self.zip_names)):
            top = second_level(names)
            leaked = sorted(d for d in DATA_DIRS + (".s9-sync",) if d in top)
            self.assertEqual(leaked, [], f"{label} 에 이 설치의 데이터가 담겼다")
            missing = sorted(d for d in CODE_DIRS + ("VERSION",) if d not in top)
            self.assertEqual(missing, [], f"{label} 에 코드가 빠졌다")

    def test_b4_zip_cmd_files_are_crlf(self):
        cmds = [n for n in self.zip_names if re.match(r"^section9/bin/[^/]+\.cmd$", n)]
        self.assertTrue(cmds, "zip 에 bin/*.cmd 가 없다")
        with zipfile.ZipFile(self.zip) as zf:
            for n in cmds:
                data = zf.read(n)
                self.assertNotIn(b"\r\r\n", data, f"{n}: CR 가 겹쳤다")
                self.assertEqual(data.replace(b"\r\n", b"").count(b"\n"), 0, f"{n}: LF 만인 줄이 있다")

    def test_b5_tar_keeps_the_executable_bit(self):
        # bin/ 의 확장자 없는 파일이 리눅스·맥의 실행 파일이다(s9 · s9-install · s9-release …).
        # 이름을 못박지 않는다 — 새 도구가 HEAD 에 담기기 전의 시험 실행에서도 뜻이 같아야 한다.
        launchers = {m.name: m.mode for m in self.tar_members
                     if m.isfile() and m.name.startswith("section9/bin/") and "." not in m.name.split("/")[-1]}
        self.assertIn("section9/bin/s9", launchers)
        self.assertGreater(len(launchers), 3)
        lost = sorted(n for n, mode in launchers.items() if not mode & 0o111)
        self.assertEqual(lost, [], "실행 비트가 없다 — 풀고 바로 bin/s9 code 가 안 된다")

    def test_b6_same_ref_same_bytes(self):
        out2 = os.path.join(self.tmp, "dist2")
        r = build(out2)
        self.assertEqual(r.returncode, 0, r.stderr)
        for p in (self.tgz, self.zip):
            self.assertEqual(sha256_of(p), sha256_of(os.path.join(out2, os.path.basename(p))),
                             f"{os.path.basename(p)}: 같은 ref 인데 바이트가 다르다")

    def test_b7_print_version_matches_the_version_file(self):
        r = subprocess.run([sys.executable, RELEASE, "--print-version"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), self.ver)
        self.assertRegex(self.ver, r"^\d+\.\d+\.\d+")
        with open(os.path.join(self.out, "SHA256SUMS"), encoding="utf-8") as f:
            sums = f.read()
        for p in (self.tgz, self.zip):
            self.assertIn(f"{sha256_of(p)}  {os.path.basename(p)}", sums)

    def test_b8_unknown_ref_fails_without_leaving_files(self):
        out3 = os.path.join(self.tmp, "dist3")
        r = build(out3, ref="no-such-ref-zzz")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("s9-release:", r.stderr)
        self.assertFalse(os.path.exists(out3) and os.listdir(out3), "실패했는데 파일을 남겼다")

    def test_b9_s9_version_flag(self):
        r = subprocess.run([sys.executable, S9, "--version"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        m = re.match(r"^section9 (\S+)( \([0-9a-f]{7,}\))?$", r.stdout.strip())
        self.assertIsNotNone(m, f"s9 --version 의 꼴이 다르다: {r.stdout!r}")
        # `s9 --version` 은 작업 트리의 VERSION 을 읽는다 — 배포판(HEAD)의 판과는 다른 물음이다
        self.assertEqual(m.group(1), version_file(ref=None), "s9 --version 과 VERSION 파일이 다르다")

    def test_b10_whoami_carries_the_version_and_the_screen_draws_it(self):
        # 서버가 주는 값(whoami_info — /api/whoami 와 /api/boot 묶음이 같은 함수)이
        # `s9 --version` 과 같고, Settings › 시스템 판이 그 값을 「버전」 줄로 그린다.
        root = os.path.join(self.tmp, "root")
        env = {**os.environ, "S9_ROOT": root, "S9_USER": "alice", "S9_MACHINE": "testbox"}
        env.pop("S9_SESSION", None)
        subprocess.run([sys.executable, S9, "init"], env=env, capture_output=True, check=True)
        keep = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_USER", "S9_MACHINE", "S9_SESSION")}
        try:
            os.environ.update({"S9_ROOT": root, "S9_USER": "alice", "S9_MACHINE": "testbox"})
            os.environ.pop("S9_SESSION", None)
            spec = importlib.util.spec_from_loader(
                "s9_rel_ver", importlib.machinery.SourceFileLoader("s9_rel_ver", S9 + ".py"))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            who = m.whoami_info()
        finally:
            for k, v in keep.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertEqual(who.get("version"), m.s9_version())
        self.assertTrue(who["version"].startswith(version_file(ref=None)), who["version"])
        with open(os.path.join(ROOT, "web", "app", "settings.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("<td>버전</td>", js, "Settings › 시스템 판에 「버전」 줄이 없다")
        self.assertIn("(window.__whoami||{}).version", js, "화면이 서버의 version 값을 읽지 않는다")

    def test_b11_one_naming_rule_for_every_os(self):
        """이름은 `section9-<버전>-<운영체제>.<그 운영체제의 기본 형식>` 하나다.

        주인 물음 2026-09-14 「배포용 압축파일 네이밍룰이 os별로 다른 이유가 있나?」
        (REQ-20260914-009-62x6) — 없었다. Windows 것에만 `-claude` 꼬리표가 붙어
        운영체제마다 규칙이 갈려 보였다. 두 겹으로 지킨다: 만들어진 이름이 한 규칙에
        맞는가, 그리고 옛 이름이 문서·코드 어딘가에 남아 있지 않은가.
        """
        rule = re.compile(r"^section9-" + re.escape(self.ver) + r"-(linux-macos|windows)\.(tar\.gz|zip)$")
        for p in (self.tgz, self.zip):
            self.assertRegex(os.path.basename(p), rule)
        self.assertEqual(sorted(n for n in os.listdir(self.out) if n != "SHA256SUMS"),
                         [f"section9-{self.ver}-linux-macos.tar.gz", f"section9-{self.ver}-windows.zip"],
                         "dist/ 에 규칙 밖의 파일이 있다")

    def test_b12_the_old_windows_name_is_gone_everywhere(self):
        """옛 이름이 문서·코드에 남아 있으면 사람이 없는 파일을 받으러 간다.

        찾는 말은 여기서 이어 붙인다 — 이 시험 파일 자신이 그 말을 글자로 품으면
        제가 저를 잡는다.
        """
        needle = "windows" + "-claude"
        r = subprocess.run(["git", "grep", "-lI", needle, "--",
                            "bin", "web", "harness", "tests", "docs", ".github", "README.md"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1,
                         f"옛 이름 {needle} 가 남아 있다 — 문서가 없는 파일을 가리킨다:\n" + r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
