"""Explicit host API for an isolated, user-operated X-close experiment.

No command-line entry point, implicit start, process killing, or prefix cleanup.
"""
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = Path('/tmp/opencode')
FIXTURE = ROOT / 'build/reopen-probe/controlled-fixture'


class ProbeError(RuntimeError):
    pass


def _disjoint(a, b):
    return a != b and a not in b.parents and b not in a.parents


def _secure_base(path):
    base = Path(path)
    if not base.is_absolute() or base.resolve(strict=True) != base or not base.is_dir():
        raise ValueError('unsafe prefix parent')
    info = base.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('prefix parent must be owned by current user with mode 0700')
    return base


class ControlledProbe:
    """One use only. start(), reopen(), stop() are explicit host actions."""
    def __init__(self, configured_prefix, timeout=15):
        self.configured_prefix = Path(configured_prefix).expanduser().resolve()
        self.timeout = timeout
        self.prefix = None
        self.process = None
        self.sequence = 0
        self.xid = None
        self.state = 'new'
        self.close_count = 0

    def _error(self, message):
        self.state = 'failed'
        raise ProbeError(f'{message}; prefix retained: {self.prefix or "not created"}')

    def start(self):
        if self.state != 'new':
            self._error('start requires a new probe')
        try:
            status = Path('/proc/self/status').read_text()
            if not re.search(r'^NoNewPrivs:\s*0\s*$', status, re.M):
                raise ValueError('NoNewPrivs is not 0 or unavailable')
            display = os.environ.get('DISPLAY')
            if not display:
                raise ValueError('DISPLAY missing')
            try:
                base = _secure_base(BASE)
            except (OSError, ValueError):
                runtime = os.environ.get('XDG_RUNTIME_DIR')
                if not runtime:
                    raise ValueError('no secure prefix parent; XDG_RUNTIME_DIR missing')
                base = _secure_base(runtime)
            configured = [self.configured_prefix]
            if os.environ.get('DPREFIX'):
                configured.append(Path(os.environ['DPREFIX']).expanduser().resolve())
            if any(p == base or p in base.parents for p in configured):
                raise ValueError('configured prefix overlaps disposable parent')
            if not FIXTURE.is_file():
                raise ValueError('controlled fixture not built')
            self.prefix = Path(tempfile.mkdtemp(prefix='rp-', dir=base))
            os.chmod(self.prefix, 0o700)
            if self.prefix.resolve().parent != base or any(not _disjoint(self.prefix.resolve(), p) for p in configured):
                raise ValueError('prefix isolation check failed')
            self.nonce = secrets.token_hex(32)
            self.control = self.prefix / 'control'
            self.log = self.prefix / 'fixture.log'
            # Allow only display authentication and a fixed executable search path.
            self.env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(self.prefix),
                        'DPREFIX': str(self.prefix), 'DISPLAY': display, 'LANG': 'C'}
            if os.environ.get('XAUTHORITY'):
                self.env['XAUTHORITY'] = os.environ['XAUTHORITY']
            with self.log.open('xb') as log:
                self.process = subprocess.Popen(['darling', 'shell', '/Volumes/SystemRoot' + str(FIXTURE),
                    '/Volumes/SystemRoot' + str(self.control), self.nonce], env=self.env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            text = self._wait_log(r'^READY ([1-9][0-9]*)$', 0)
            self.xid = int(text.group(1))
            self.state = 'running'
            observation = self.observe()
            if observation['map_state'] != 'IsViewable':
                self._error('initial window is not IsViewable')
            return observation
        except Exception as exc:
            if isinstance(exc, ProbeError):
                raise
            self._error(str(exc))

    def _wait_log(self, pattern, offset):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            text = self.log.read_text(errors='replace')[offset:]
            match = re.search(pattern, text, re.M)
            if match:
                return match
            if self.process.poll() is not None:
                self._error('fixture exited before expected log')
            time.sleep(0.05)
        self._error('timeout waiting for fixture log')

    def observe(self):
        if self.state != 'running':
            self._error('observe requires running fixture')
        try:
            result = subprocess.run(['xwininfo', '-id', str(self.xid)], env=self.env,
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=self.timeout, check=True)
            match = re.search(r'^\s*Map State:\s*(Is\w+)\s*$', result.stdout, re.M)
            identity = re.search(r'^xwininfo: Window id: (0x[0-9a-fA-F]+)', result.stdout, re.M)
            if not match or not identity or int(identity.group(1), 16) != self.xid:
                raise ValueError('xwininfo map state or matching XID unavailable')
            return {'prefix': str(self.prefix), 'xid': self.xid, 'map_state': match.group(1),
                    'log': self.log.read_text(errors='replace')}
        except Exception as exc:
            self._error('xwininfo observation failed: ' + str(exc))

    def _command(self, command):
        if command == 'stop':
            if self.state not in ('running', 'failed') or self.process is None:
                self._error('stop requires a controllable fixture process')
            if self.process.poll() is not None:
                self._error('fixture process already exited; stop not sent')
        elif self.state != 'running':
            self._error(command + ' requires running fixture')
        try:
            offset = len(self.log.read_text(errors='replace'))
            self.sequence += 1
            temporary = self.prefix / 'control.new'
            temporary.write_text(f'{self.nonce} {self.sequence} {command}')
            os.replace(temporary, self.control)
            self._wait_log(r'^ACK ' + str(self.sequence) + ' ' + command + r'$', offset)
            return self.log.read_text(errors='replace')[offset:]
        except Exception as exc:
            if isinstance(exc, ProbeError):
                raise
            self._error(str(exc))

    def reopen(self):
        observation = self.observe()
        count = observation['log'].splitlines().count('CLOSED_BY_USER')
        if observation['map_state'] != 'IsUnMapped' or count <= self.close_count:
            self._error('physical X close not observed; reopen refused')
        self.close_count = count
        log = self._command('reopen')
        if log.splitlines().count('REOPEN_CALLBACK') != 1:
            self._error('expected exactly one reopen callback')
        observation = self.observe()
        if observation['xid'] != self.xid or observation['map_state'] != 'IsViewable':
            self._error('reopened window is not IsViewable with the original XID')
        return observation

    def stop(self):
        self._command('stop')
        try:
            result = self.process.wait(timeout=self.timeout)
            if result:
                self._error('fixture exited with status ' + str(result))
        except subprocess.TimeoutExpired:
            self._error('timeout stopping fixture; no signal sent')
        self.state = 'stopped'
        return {'prefix': str(self.prefix), 'log': str(self.log), 'server_shutdown_requested': False}
