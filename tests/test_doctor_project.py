"""doctor 의 프로젝트 검사 — 조용히 남는 두 어긋남을 세어 보여 준다 (REQ-20260908-025).

배경: 지금까지 doctor 에는 프로젝트 검사가 하나도 없었다. ① 두 설치의 vault 가
만나면 같은 slug 의 프로젝트 문서가 둘이 될 수 있고(git 충돌로 멈추지만 사람이
잘못 풀면 남는다), ② 문서가 `project: <slug>` 로 가리키는 프로젝트 문서가 아예
없을 수 있다. 둘 다 화면 어디에도 나타나지 않아 아무도 모른다.

판정(project_verdict)은 순수 함수라 실제 vault 상태에 기대지 않고 등급을 고정한다.
수집(project_info)은 임시 vault 를 만들어 확인한다 — 라이브 데이터는 읽기만 한다.

실행: python3 tests/ doctor_project
"""
import importlib.util
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
DOCTOR = os.path.join(HERE, "..", "bin", "s9-doctor")
REPO = os.path.dirname(HERE)

spec = importlib.util.spec_from_loader(
    "s9doctor_project", SourceFileLoader("s9doctor_project", DOCTOR))
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def make_vault(base, projects, docs):
    """projects: [(파일이름, 프론트매터 dict)] · docs: [(파일이름, project 값)]"""
    pdir = os.path.join(base, "vault", "projects")
    rdir = os.path.join(base, "vault", "requests")
    os.makedirs(pdir)
    os.makedirs(rdir)
    for fn, meta in projects:
        body = "".join(f"{k}: {v}\n" for k, v in meta.items())
        with open(os.path.join(pdir, fn), "w", encoding="utf-8") as f:
            f.write(f"---\n{body}---\n\n## Notes\n")
    for fn, slug in docs:
        with open(os.path.join(rdir, fn), "w", encoding="utf-8") as f:
            f.write(f"---\nid: {fn[:-3]}\ntype: request\n"
                    + (f"project: {slug}\n" if slug else "")
                    + "---\n\n## Notes\n")
    return base


class Clean(unittest.TestCase):
    """P1. 어긋남이 없으면 조용하다."""

    def test_clean_vault_is_ok_and_silent(self):
        with tempfile.TemporaryDirectory() as base:
            make_vault(base,
                       [("section9.md", {"id": "PRJ-20260823-001",
                                         "type": "project", "slug": "section9"})],
                       [("REQ-1.md", "section9"), ("REQ-2.md", "section9")])
            info = doctor.project_info(base)
            self.assertEqual(info["duplicates"], [])
            self.assertEqual(info["unknown"], [])
            v = doctor.project_verdict(info)
            self.assertEqual(v["level"], "ok", v)
            # ok 는 advise 에 실리지 않는다 — 어긋남이 없으면 화면에 한 줄도 안 나온다.
            self.assertEqual(doctor.system_advice({"system": [v]}), [])


class SameSlugTwoIds(unittest.TestCase):
    """P2. 같은 slug·다른 PRJ id — 두 vault 가 합류한 자국."""

    def test_duplicate_slug_is_critical_and_names_both(self):
        with tempfile.TemporaryDirectory() as base:
            make_vault(base, [
                ("section9.md", {"id": "PRJ-20260823-001", "slug": "section9"}),
                ("section9-2.md", {"id": "PRJ-20260907-004", "slug": "section9"}),
            ], [("REQ-1.md", "section9")])
            info = doctor.project_info(base)
            self.assertEqual([d["slug"] for d in info["duplicates"]], ["section9"])
            v = doctor.project_verdict(info)
            self.assertEqual(v["level"], "critical", v)
            for want in ("PRJ-20260823-001", "PRJ-20260907-004",
                         "section9.md", "section9-2.md"):
                self.assertIn(want, v["line"], v["line"])
            # 다음에 무엇을 하면 되는지가 함께 나온다.
            self.assertIn("s9 project rename", v["advice"])


class UnregisteredSlug(unittest.TestCase):
    """P3. 등록되지 않은 slug 를 가리키는 문서 N건."""

    def test_unknown_slug_counts_and_examples(self):
        with tempfile.TemporaryDirectory() as base:
            make_vault(base,
                       [("section9.md", {"id": "PRJ-1", "slug": "section9"})],
                       [("REQ-1.md", "ledger"), ("REQ-2.md", "ledger"),
                        ("REQ-3.md", "paper"), ("REQ-4.md", "section9"),
                        ("REQ-5.md", "")])
            info = doctor.project_info(base)
            self.assertEqual([(u["slug"], u["count"]) for u in info["unknown"]],
                             [("ledger", 2), ("paper", 1)])
            v = doctor.project_verdict(info)
            self.assertEqual(v["level"], "warn", v)
            self.assertIn("문서 3건", v["line"])
            self.assertIn("ledger 2건", v["line"])
            self.assertIn("REQ-1", v["line"])
            # 두 갈래(등록 / 값 수정)와 지금 등록된 slug 를 함께 준다.
            self.assertIn("s9 new project --slug", v["advice"])
            self.assertIn("section9", v["advice"])


class BothAtOnce(unittest.TestCase):
    """P4. 둘이 함께 있으면 하나가 다른 하나를 가리지 않는다."""

    def test_both_mismatches_show(self):
        with tempfile.TemporaryDirectory() as base:
            make_vault(base, [
                ("a.md", {"id": "PRJ-1", "slug": "section9"}),
                ("b.md", {"id": "PRJ-2", "slug": "section9"}),
            ], [("REQ-1.md", "ledger")])
            v = doctor.project_verdict(doctor.project_info(base))
            self.assertEqual(v["level"], "critical", v)
            self.assertIn("slug 하나에 프로젝트 문서가 2개", v["line"])
            self.assertIn("등록되지 않은 slug", v["line"])


class Unreadable(unittest.TestCase):
    """P5. 못 읽은 것을 이유로 사람을 깨우지 않는다 — unknown 은 경고보다 약하다."""

    def test_missing_projects_dir_is_unknown(self):
        with tempfile.TemporaryDirectory() as base:
            info = doctor.project_info(base)
            self.assertFalse(info["readable"])
            v = doctor.project_verdict(info)
            self.assertEqual(v["level"], "unknown", v)
            self.assertEqual(doctor.worst_level(["ok", v["level"]]), "unknown")


class SlugFallback(unittest.TestCase):
    """P6. slug 프론트매터가 없으면 파일 이름이 곧 slug 다 · 따옴표는 값이 아니다."""

    def test_filename_is_slug_and_quotes_stripped(self):
        with tempfile.TemporaryDirectory() as base:
            make_vault(base,
                       [("ledger.md", {"id": "PRJ-1", "type": "project"})],
                       [("REQ-1.md", '"ledger"')])
            info = doctor.project_info(base)
            self.assertIn("ledger", info["registered"])
            self.assertEqual(info["unknown"], [], info["unknown"])
            self.assertEqual(doctor.project_verdict(info)["level"], "ok")


class LiveRepo(unittest.TestCase):
    """P7. 이 저장소를 실제로 검사하면 어긋남이 없다 (실측 회귀)."""

    def test_this_repo_is_clean(self):
        info = doctor.project_info(REPO)
        self.assertTrue(info["readable"])
        self.assertEqual(info["duplicates"], [], info["duplicates"])
        self.assertEqual(info["unknown"], [], info["unknown"])
        self.assertGreater(info["docs"], 100)
        self.assertEqual(doctor.project_verdict(info)["level"], "ok")


class InTheList(unittest.TestCase):
    """P8. 검사가 목록에서 빠지지 않는다 — system_checks 가 프로젝트 행을 낸다."""

    def test_system_checks_carries_project(self):
        rows = doctor.system_checks()
        got = [r for r in rows if r["key"] == "project"]
        self.assertEqual(len(got), 1, [r["key"] for r in rows])
        self.assertTrue(got[0]["line"].strip())
        self.assertIn(got[0]["level"], ("ok", "warn", "critical", "unknown"))


if __name__ == "__main__":
    unittest.main()
