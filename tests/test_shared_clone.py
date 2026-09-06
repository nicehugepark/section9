"""두 OS 가 함께 쓰는 clone 은 문 하나로 거부한다 (REQ-20260906-056).

state/ 는 이 머신의 살림이고 윈도우와 WSL 은 서로의 pid 를 못 보는 두 머신이다.
자리마다 고치지 않고 shared_clone_reason 한 곳이 판정하며 s9-install 과 s9 doctor 가
그것을 본다. 여는 길은 OS 마다 따로 clone 하고 GitHub 로 동기화하는 것이다.

실행: python3 tests/ shared_clone
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
INSTALL = os.path.join(HERE, "..", "bin", "s9-install")


class SharedClone(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9shared-")
        os.makedirs(os.path.join(self.root, "state"))
        self._env = os.environ.get("S9_ROOT")
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_shared", importlib.machinery.SourceFileLoader("s9_shared", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        if self._env is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = self._env
        shutil.rmtree(self.root, ignore_errors=True)

    def _serve(self, root):
        with open(os.path.join(self.root, "state", "serve-code.json"), "w", encoding="utf-8") as f:
            json.dump({"root": root, "port": 9909}, f)

    # R1. WSL 인데 clone 이 윈도우 드라이브 위 → 사유 + 여는 길
    def test_r1_wsl_clone_on_a_windows_drive_is_refused(self):
        why = self.m.shared_clone_reason(root="/mnt/c/Users/me/section9", platform="WSL", serve_root="")
        self.assertIn("/mnt/c", why)
        self.assertIn("여는 길", why)
        self.assertEqual(self.m.shared_clone_reason(root="/home/me/section9", platform="WSL", serve_root=""), "")

    # R2. 윈도우인데 대시보드를 띄운 root 가 유닉스 경로 → 사유
    def test_r2_windows_sees_a_posix_serve_root(self):
        why = self.m.shared_clone_reason(root=r"C:\Users\me\section9", platform="Windows",
                                         serve_root="/home/me/section9")
        self.assertIn("WSL", why)
        self.assertEqual(self.m.shared_clone_reason(root=r"C:\Users\me\section9", platform="Windows",
                                                    serve_root=r"C:\Users\me\section9"), "")

    # R3. 리눅스·WSL 인데 대시보드를 띄운 root 가 윈도우 경로 → 사유; serve-code.json 을 실제로 읽는다
    def test_r3_linux_sees_a_windows_serve_root_from_the_file(self):
        self._serve(r"C:\Users\me\section9")
        why = self.m.shared_clone_reason(platform="Linux")
        self.assertIn("윈도우", why)
        self._serve("/home/me/section9")
        self.assertEqual(self.m.shared_clone_reason(platform="Linux"), "")

    # R4. s9 doctor --shared-clone: 사유가 있으면 1, 없으면 0
    def test_r4_doctor_flag_exits_one_with_the_reason(self):
        env = {**os.environ, "S9_ROOT": self.root}
        self._serve(r"D:\work\section9")
        r = subprocess.run([S9, "doctor", "--shared-clone"], capture_output=True, text=True,
                           env=env, timeout=60)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("여는 길", r.stderr)
        self._serve(self.root)
        r = subprocess.run([S9, "doctor", "--shared-clone"], capture_output=True, text=True,
                           env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # R5. s9-install 은 설치 전에 멈춘다 — HOME 을 임시로 돌려 진짜 설치가 일어나지 않게 한다
    def test_r5_install_stops_before_touching_anything(self):
        self._serve(r"D:\work\section9")
        home = tempfile.mkdtemp(prefix="s9shared-home-")
        try:
            env = {**os.environ, "S9_ROOT": self.root, "HOME": home}
            r = subprocess.run([INSTALL], capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("여는 길", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(home, ".claude")), "거부했는데 설치를 했다")
            self.assertFalse(os.path.exists(os.path.join(self.root, "state", "installed_at")))
        finally:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
