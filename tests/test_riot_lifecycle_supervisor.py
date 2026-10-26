"""Classify processes and check the supervisor's opt-out using a fake /proc only."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('supervisor', ROOT / 'tools/riot-lifecycle-supervisor.py')
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)

RIOT = '/Applications/Riot Client.app/Contents/MacOS/RiotClientServices'
UX = '/Applications/Riot Client.app/Contents/Frameworks/RiotClientUx.app/Contents/MacOS/RiotClientUx'
UX_HELPER = '/Applications/Riot Client.app/Contents/Frameworks/Riot Client Helper.app/Contents/MacOS/Riot Client Helper'
CLIENT = '/Applications/League of Legends.app/Contents/LoL/LeagueClient.app/Contents/MacOS/LeagueClient'
CRASH = '/Applications/League of Legends.app/Contents/LoL/LeagueClient.app/Contents/MacOS/LeagueCrashHandler'
GAME = '/Applications/LeagueofLegends.app/Contents/MacOS/LeagueofLegends'


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proc = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, pid, cmdline, maps=''):
        d = self.proc / str(pid)
        d.mkdir()
        (d / 'cmdline').write_bytes(cmdline.encode() + b'\0')
        (d / 'maps').write_text(maps)

    def test_classifies_launcher_client_game_and_helpers(self):
        self.add(101, RIOT)
        self.add(102, UX)
        self.add(103, UX_HELPER)
        self.add(104, CLIENT)
        self.add(105, CRASH + '\0--attachment=LeagueClient')
        self.add(106, GAME)
        self.add(107, '/usr/bin/bash')
        pids = supervisor.get_darling_pids(self.proc)
        self.assertEqual(pids['riot_services'], [101])
        self.assertEqual(pids['riot_ux'], [102])
        self.assertEqual(pids['league_client'], [104])
        self.assertEqual(pids['league_game'], [106])
        self.assertEqual(sorted(pids['helpers']), [103, 105])

    def test_game_found_through_mapped_binary(self):
        self.add(201, 'mldr', maps='7f00 r-xp 0 0:0 0 ' + GAME + '\n')
        self.assertEqual(supervisor.get_darling_pids(self.proc)['league_game'], [201])

    def test_skips_own_pid(self):
        self.add(os.getpid(), GAME)
        self.assertEqual(supervisor.get_darling_pids(self.proc)['league_game'], [])

    def test_opt_out_execs_command_directly(self):
        with patch.dict(os.environ, {'RCLOL_LIFECYCLE_SUPERVISOR': '0'}), \
             patch.object(supervisor.sys, 'argv', ['sup', 'darling', 'run']), \
             patch.object(supervisor.os, 'execvp', side_effect=SystemExit(0)) as execvp, \
             patch.object(supervisor.subprocess, 'Popen') as popen:
            with self.assertRaises(SystemExit):
                supervisor.main()
        execvp.assert_called_once_with('darling', ['darling', 'run'])
        popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
