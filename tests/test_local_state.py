"""기계마다 같은 이름으로 쓰는 살림 파일은 추적 폴더 밖에 산다 (REQ-20260909-024).

맥 실측: 두 기계가 각자 고치는 state/sessions/approvals_seen.json 이 옛 커밋에 추적된
채 남아 pull --ff-only 를 12시간 막았다. 새 자리는 state/local/ 이고, 옛 자리의 값은
처음 한 번만 옮겨 적는다.

실행: python3 tests/ local_state
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


class LocalState(unittest.TestCase):

    def setUp(self):
        self._root = os.environ.get("S9_ROOT")
        self.root = tempfile.mkdtemp(prefix="s9local-")
        os.environ["S9_ROOT"] = self.root
        name = "s9local_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.cmd_init(type("A", (), {})())

    def tearDown(self):
        if self._root is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = self._root
        shutil.rmtree(self.root, ignore_errors=True)

    def test_u1_the_old_value_moves_once(self):
        m = self.m
        old = os.path.join(m.STATE, "approvals_seen.json")
        os.makedirs(m.STATE, exist_ok=True)
        with open(old, "w") as f:
            json.dump({"REQ-1": "t"}, f)
        new = m.local_state_path("approvals_seen.json")
        self.assertEqual(new, os.path.join(self.root, "state", "local", "approvals_seen.json"))
        with open(new) as f:
            self.assertEqual(json.load(f), {"REQ-1": "t"}, "옛 값을 옮겨 적지 않았다")
        with open(new, "w") as f:
            json.dump({"REQ-2": "t"}, f)
        m.local_state_path("approvals_seen.json")
        with open(new) as f:
            self.assertEqual(json.load(f), {"REQ-2": "t"}, "두 번째부터는 옛 값이 새 값을 덮지 않는다")

    def test_u2_reading_uses_the_new_place_and_leaves_the_old_untouched(self):
        m = self.m
        old = os.path.join(m.STATE, "approvals_seen.json")
        os.makedirs(m.STATE, exist_ok=True)
        with open(old, "w") as f:
            json.dump({"REQ-x": "t"}, f)
        before = os.path.getmtime(old)
        m.approvals_unseen()                       # 읽기만으로도 새 자리가 선다(이주)
        new = os.path.join(self.root, "state", "local", "approvals_seen.json")
        self.assertTrue(os.path.exists(new))
        self.assertEqual(os.path.getmtime(old), before, "옛 자리를 건드렸다")
        # 소스에 옛 자리를 직접 여는 줄이 남아 있지 않다
        with open(S9, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn('os.path.join(STATE, "approvals_seen.json")', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
