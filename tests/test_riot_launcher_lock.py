import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/riot-launcher-lock.py"
LAUNCHER = ROOT / "scripts/riot-launcher.sh"


class LauncherLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="riot lock ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.prefix = self.root / "prefix with spaces"
        self.prefix.mkdir()
        self.env = os.environ.copy()
        self.env.update(XDG_RUNTIME_DIR=str(self.runtime), DPREFIX=str(self.prefix))
        self.stub = self.root / "stub.sh"
        self.stub.write_text('printf "%s\\n" "$1" > "$MARKER"\nwhile [ ! -e "$RELEASE" ]; do sleep 0.02; done\n')
        self.marker = self.root / "marker"
        self.release = self.root / "release"
        self.env.update(MARKER=str(self.marker), RELEASE=str(self.release))

    def invoke(self, prefix=None, action="start"):
        return subprocess.run(["python3", str(HELPER), str(prefix or self.prefix), str(self.stub), action], env=self.env, capture_output=True, text=True, timeout=5)

    def test_serialization_alias_restart_and_release(self):
        alias = self.root / "alias"
        alias.symlink_to(self.prefix, target_is_directory=True)
        proc = subprocess.Popen(["python3", str(HELPER), str(self.prefix), str(self.stub), "restart"], env=self.env)
        try:
            for _ in range(200):
                if self.marker.exists():
                    break
                time.sleep(0.01)
            self.assertEqual(self.marker.read_text().strip(), "--locked-restart")
            for action in ("start", "stop", "restart"):
                result = self.invoke(alias, action)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("already running", result.stderr)
            self.release.touch()
            self.assertEqual(proc.wait(timeout=5), 0)
            self.assertEqual(self.invoke(alias).returncode, 0)
        finally:
            if proc.poll() is None:
                self.release.touch()
                proc.wait(timeout=5)

    def test_unsafe_runtime_and_lock_files(self):
        self.env.pop("XDG_RUNTIME_DIR")
        self.assertIn("XDG_RUNTIME_DIR", self.invoke().stderr)
        self.env["XDG_RUNTIME_DIR"] = str(self.runtime)
        self.runtime.chmod(0o755)
        self.assertNotEqual(self.invoke().returncode, 0)
        self.runtime.chmod(0o700)
        name = "riot-launcher-" + hashlib.sha256(os.fsencode(str(self.prefix.resolve()))).hexdigest() + ".lock"
        lock = self.runtime / name
        target = self.root / "target"
        target.write_text("untouched")
        lock.symlink_to(target)
        self.assertNotEqual(self.invoke().returncode, 0)
        lock.unlink()
        os.link(target, lock)
        target.chmod(0o600)
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertEqual(target.read_text(), "untouched")
        self.assertFalse(self.marker.exists())

    def test_status_without_runtime_and_start_fails_closed(self):
        self.env.pop("XDG_RUNTIME_DIR")
        result = subprocess.run([str(LAUNCHER), "start"], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("XDG_RUNTIME_DIR", result.stderr)
        result = subprocess.run([str(LAUNCHER), "status"], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_child_does_not_inherit_lock(self):
        self.stub.write_text('sleep 2 >/dev/null 2>&1 &\nexit 0\n')
        self.assertEqual(self.invoke().returncode, 0)
        self.release.touch()
        self.stub.write_text('exit 0\n')
        self.assertEqual(self.invoke().returncode, 0)

    def test_launcher_and_quit_exclude_each_other_and_release(self):
        action = ROOT / 'tools/riot-menu-action.py'
        script = '''
import importlib.util, os, pathlib, sys, time
spec = importlib.util.spec_from_file_location("menu", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.log = lambda msg: None
m.notify = lambda *args: pathlib.Path(os.environ["NOTICE"]).write_text(args[1])
def inspect(prefix):
    pathlib.Path(os.environ["QUIT_MARKER"]).touch()
    while not pathlib.Path(os.environ["QUIT_RELEASE"]).exists(): time.sleep(.01)
    return False
m.game_running = inspect
m.stop_session = lambda prefix: True
sys.exit(m.quit_action(pathlib.Path(sys.argv[2])))
'''
        notice = self.root / 'notice'
        marker = self.root / 'quit-marker'
        release = self.root / 'quit-release'
        env = dict(self.env, NOTICE=str(notice), QUIT_MARKER=str(marker), QUIT_RELEASE=str(release))
        cmd = ['python3', '-c', script, str(action)]
        launcher = subprocess.Popen(['python3', str(HELPER), str(self.prefix), str(self.stub), 'start'], env=env)
        try:
            for _ in range(200):
                if self.marker.exists(): break
                time.sleep(.01)
            self.assertTrue(self.marker.exists())
            result = subprocess.run(cmd + [str(self.prefix)], env=env, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(notice.exists())
            self.assertFalse(marker.exists())
            self.release.touch()
            self.assertEqual(launcher.wait(timeout=5), 0)
            quit_proc = subprocess.Popen(cmd + [str(self.prefix)], env=env)
            try:
                for _ in range(200):
                    if marker.exists(): break
                    time.sleep(.01)
                self.assertTrue(marker.exists())
                self.assertNotEqual(self.invoke().returncode, 0)
                other = self.root / 'other'
                other.mkdir()
                self.assertEqual(self.invoke(other).returncode, 0)
                release.touch()
                self.assertEqual(quit_proc.wait(timeout=5), 0)
                self.assertEqual(self.invoke().returncode, 0)
            finally:
                release.touch()
                quit_proc.wait(timeout=5)
        finally:
            self.release.touch()
            launcher.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
