"""Fail-closed cleanup for a freshly reserved probe namespace; never deletes files."""
import os
from pathlib import Path
import stat
import subprocess
import tempfile


class ProbePrefix:
    def __init__(self, root, label, name='p'):
        self.base = Path(tempfile.mkdtemp(prefix=label, dir=root))
        self.base_stat = self.base.stat()
        self.prefix = self.base / name
        if self.prefix.exists() or self.prefix.is_symlink():
            raise RuntimeError('probe prefix already exists')
        # Linux process start times are measured in clock ticks since boot.
        self.started = int(float(Path('/proc/uptime').read_text().split()[0]) * os.sysconf('SC_CLK_TCK'))

    def cleanup(self, darling='darling'):
        try:
            base = self.base.lstat()
            prefix = self.prefix.lstat()
            if (base.st_dev, base.st_ino) != (self.base_stat.st_dev, self.base_stat.st_ino):
                raise ValueError('private parent changed')
            if not stat.S_ISDIR(base.st_mode) or not stat.S_ISDIR(prefix.st_mode):
                raise ValueError('unsafe prefix path')
            if self.base.resolve() != self.base or self.prefix.resolve() != self.prefix:
                raise ValueError('prefix path changed')
            pidfile = self.prefix / '.init.pid'
            if not stat.S_ISREG(pidfile.lstat().st_mode):
                raise ValueError('unsafe pid file')
            pid = int(pidfile.read_text().strip())
            if pid <= 1:
                raise ValueError('invalid pid')
            proc = Path('/proc') / str(pid)
            fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            if fields[0] == 'Z' or int(fields[19]) < self.started:
                raise ValueError('pre-existing or exited server')
            if (proc / 'comm').read_text().strip() != 'darlingserver':
                raise ValueError('not a Darling server')
            # Darling's server clears DPREFIX but records its prefix as argv[1].
            # Require the exact argument and owner, never a substring or basename.
            argv = (proc / 'cmdline').read_bytes().split(b'\0')
            if len(argv) < 3 or argv[0] != b'darlingserver' or argv[1] != os.fsencode(self.prefix):
                raise ValueError('server command prefix does not match')
            if proc.stat().st_uid != os.getuid():
                raise ValueError('server owner does not match')
            environment = (proc / 'environ').read_bytes().split(b'\0')
            prefixes = [entry for entry in environment if entry.startswith(b'DPREFIX=')]
            if prefixes and prefixes != [b'DPREFIX=' + os.fsencode(self.prefix)]:
                raise ValueError('server environment prefix does not match')
            if int(pidfile.read_text().strip()) != pid or (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19] != fields[19]:
                raise ValueError('server identity changed')
            env = dict(os.environ, DPREFIX=str(self.prefix))
            subprocess.run([darling, 'shutdown'], env=env, timeout=15, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, ValueError, IndexError, subprocess.SubprocessError) as error:
            print('WARNING: probe shutdown skipped or failed; prefix retained:', self.prefix, error)
            return False
