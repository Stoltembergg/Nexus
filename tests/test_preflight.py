"""Fake host probes; no compiler, GPU, Darling, account or network access."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nexus_preflight', ROOT / 'scripts/preflight.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)
VULKAN = 'GPU0:\n apiVersion = 1.4.354\n timelineSemaphore = true\n'


class PreflightTests(unittest.TestCase):
    def host(self, mode='build', *, missing=(), outputs=None, **changes):
        versions = {'cmake': 'cmake version 4.4.4', 'git-lfs': 'git-lfs/3.8.1',
                    'clang': 'clang version 23.1.4', 'llvm-config': '23.1.4',
                    'llvm-objdump': 'LLVM version 23.1.4', 'llvm-nm': 'LLVM version 23.1.4',
                    'pkg-config': '1.4.363', 'vulkaninfo': VULKAN, 'xdpyinfo': 'DISPLAY_OK'}
        versions.update(outputs or {})

        def which(name):
            return None if name in missing else '/fixture/bin/' + name

        def probe(command):
            return versions.get(Path(command[0]).name, 'OK')

        options = dict(which=which, probe=probe, kernel='7.3.0-custom', machine='x86_64',
                       system='Linux', python_version=(3, 14, 0), environ={'DISPLAY': ':fixture'})
        options.update(changes)
        return preflight.run_checks(mode, **options)

    def named(self, checks, name):
        return next(check for check in checks if check['name'] == name)

    def test_supported_host_passes(self):
        self.assertTrue(all(c['status'] == 'ok' for c in self.host('runtime')))

    def test_python_requirement_matches_current_tree(self):
        self.assertEqual(self.named(self.host(python_version=(3, 11, 9)), 'python')['status'], 'error')
        self.assertEqual(self.named(self.host(python_version=(3, 12, 0)), 'python')['status'], 'ok')

    def test_kernel_boundary_and_unrecognized_release(self):
        for kernel, status in [('5.13.99', 'error'), ('5.14.0-custom', 'ok'), ('unknown', 'error')]:
            with self.subTest(kernel=kernel):
                self.assertEqual(self.named(self.host(kernel=kernel), 'kernel')['status'], status)

    def test_non_linux_and_non_x86_hosts_are_rejected(self):
        self.assertEqual(self.named(self.host(system='Darwin'), 'system')['status'], 'error')
        self.assertEqual(self.named(self.host(machine='aarch64'), 'architecture')['status'], 'error')

    def test_old_tool_versions_are_rejected(self):
        for name, text in [('cmake', '3.19.9'), ('git-lfs', 'git-lfs/2.12.9'),
                           ('clang', 'clang version 15.0.7'), ('llvm-config', '15.0.7')]:
            with self.subTest(name=name):
                self.assertEqual(self.named(self.host(outputs={name: text}), name)['status'], 'error')

    def test_minimum_tool_versions_are_accepted(self):
        outputs = {'cmake': '3.20.0', 'git-lfs': 'git-lfs/2.13.0',
                   'clang': 'clang version 16.0.0', 'llvm-config': '16.0.0',
                   'llvm-objdump': 'LLVM version 16.0.0', 'llvm-nm': 'LLVM version 16.0.0'}
        self.assertFalse(any(c['status'] == 'error' for c in self.host(outputs=outputs)))
        self.assertEqual(self.named(self.host(outputs=outputs), 'llvm-alignment')['status'], 'warning')

    def test_missing_tools_fail_early(self):
        for name in ('clang', 'llvm-config', 'git-lfs', 'llvm-objdump', 'llvm-nm', 'make'):
            with self.subTest(name=name):
                self.assertEqual(self.named(self.host(missing=(name,)), name)['status'], 'error')

    def test_unversioned_llvm_tools_are_required_until_resolver_is_integrated(self):
        checks = self.host(missing=('llvm-objdump',))
        self.assertEqual(self.named(checks, 'llvm-objdump')['status'], 'error')

    def test_tool_version_failure_does_not_pass(self):
        for output in (None, 'not a version'):
            with self.subTest(output=output):
                self.assertEqual(self.named(self.host(outputs={'clang': output}), 'clang')['status'], 'error')

    def test_clang_and_llvm_major_mismatch_is_rejected(self):
        checks = self.host(outputs={'clang': 'clang version 22.1.0'})
        self.assertEqual(self.named(checks, 'llvm-alignment')['status'], 'error')

    def test_inspection_tools_must_match_llvm_major(self):
        checks = self.host(outputs={'llvm-objdump': 'LLVM version 22.1.0'})
        self.assertEqual(self.named(checks, 'llvm-objdump-alignment')['status'], 'error')

    def test_vulkan_headers_are_required_even_for_headless_build(self):
        checks = self.host(outputs={'pkg-config': None})
        self.assertEqual(self.named(checks, 'vulkan-headers')['status'], 'error')

    def test_graphics_failures_warn_for_build_and_block_runtime_install(self):
        for mode, status in [('build', 'warning'), ('runtime', 'error')]:
            with self.subTest(mode=mode):
                checks = self.host(mode, missing=('vulkaninfo',), environ={})
                self.assertEqual(self.named(checks, 'vulkan-device')['status'], status)
                self.assertEqual(self.named(checks, 'x11')['status'], status)

    def test_inaccessible_display_is_rejected_but_missing_probe_is_advisory(self):
        checks = self.host('runtime', outputs={'xdpyinfo': None})
        self.assertEqual(self.named(checks, 'x11')['status'], 'error')
        checks = self.host('runtime', missing=('xdpyinfo', 'glxinfo'))
        self.assertEqual(self.named(checks, 'x11')['status'], 'warning')

    def test_glxinfo_fallback(self):
        checks = self.host('runtime', missing=('xdpyinfo',))
        self.assertEqual(self.named(checks, 'x11')['status'], 'ok')

    def test_raw_probe_output_and_environment_are_not_reported(self):
        checks = self.host(outputs={'clang': 'PRIVATE_PATH clang version 23.1.4 PRIVATE_TOKEN'},
                           environ={'DISPLAY': ':fixture', 'XAUTHORITY': '/PRIVATE_ACCOUNT/cookie'})
        self.assertNotIn('PRIVATE', json.dumps(checks))

    def test_json_cli_failure_status(self):
        checks = [{'name': 'fixture', 'status': 'error', 'message': 'Requires fixture'}]
        with patch.object(preflight, 'run_checks', return_value=checks), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(preflight.main(['--json']), 1)
        report = json.loads(output.getvalue())
        self.assertFalse(report['passed'])
        self.assertEqual(report['checks'], checks)

    def test_query_timeout_and_failed_command_are_unknown(self):
        with patch.object(preflight.subprocess, 'run', side_effect=subprocess.TimeoutExpired('fixture', 20)):
            self.assertIsNone(preflight.query(['fixture']))
        with patch.object(preflight.subprocess, 'run', return_value=subprocess.CompletedProcess('fixture', 1, 'PRIVATE', 'PRIVATE')):
            self.assertIsNone(preflight.query(['fixture']))


class VulkanParsingTests(unittest.TestCase):
    def test_supported_single_gpu(self):
        self.assertIs(preflight.vulkan_capability(VULKAN), True)

    def test_gpu_capabilities_are_not_combined_across_devices(self):
        output = ('GPU0:\n apiVersion = 1.2.0\n timelineSemaphore = true\n'
                  'GPU1:\n apiVersion = 1.4.0\n timelineSemaphore = false\n')
        self.assertIs(preflight.vulkan_capability(output), False)

    def test_one_complete_supported_device_is_enough(self):
        self.assertIs(preflight.vulkan_capability('GPU0:\nunknown\n' + VULKAN.replace('GPU0:', 'GPU1:')), True)

    def test_missing_or_conflicting_capabilities_are_unknown(self):
        for output in ('', 'GPU0:\n apiVersion = 1.4.0\n',
                       VULKAN + ' timelineSemaphore = false\n'):
            with self.subTest(output=output):
                self.assertIsNone(preflight.vulkan_capability(output))


class EntryGateTests(unittest.TestCase):
    def test_failure_precedes_configuration_build_and_runtime_changes(self):
        for script in ('build.sh', 'install-runtime.sh'):
            with self.subTest(script=script), tempfile.TemporaryDirectory(prefix='preflight fixture ') as folder:
                root = Path(folder)
                (root / 'scripts').mkdir()
                (root / 'bin').mkdir()
                shutil.copy(ROOT / 'scripts' / script, root / 'scripts' / script)
                python = root / 'bin/python3'
                python.write_text('#!/bin/sh\ncase "$1" in\n'
                                  'scripts/preflight.py) printf preflight; exit 9;;\n'
                                  '*) printf UNEXPECTED_ACTION; exit 99;;\nesac\n')
                python.chmod(0o755)
                env = {**os.environ, 'PATH': str(root / 'bin') + ':' + os.environ['PATH']}
                env.pop('DARLING_WORKSPACE', None)
                result = subprocess.run(['sh', str(root / 'scripts' / script)],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 9, result.stderr)
                self.assertEqual(result.stdout, 'preflight')
                self.assertFalse((root / 'build').exists())


if __name__ == '__main__':
    unittest.main()
