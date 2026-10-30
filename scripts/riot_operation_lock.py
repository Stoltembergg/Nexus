"""Secure, non-blocking per-prefix lock shared by launcher and tray."""
import contextlib
import fcntl
import hashlib
import os
import stat


@contextlib.contextmanager
def operation_lock(prefix):
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime or not os.path.isabs(runtime):
        raise ValueError("XDG_RUNTIME_DIR must name a private absolute directory")
    # Reject symlinks in every component, not just the final directory.
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in runtime.split("/"):
            if not part or part == ".":
                continue
            if part == "..":
                raise ValueError("XDG_RUNTIME_DIR must not contain '..'")
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            os.close(directory)
            directory = child
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("XDG_RUNTIME_DIR must be owned by the user and have mode 0700")
        canonical = os.path.realpath(prefix)
        name = "riot-launcher-" + hashlib.sha256(os.fsencode(canonical)).hexdigest() + ".lock"
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError("unsafe lock file")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("another operation is already running for this prefix") from None
            yield
        finally:
            os.close(fd)
    finally:
        os.close(directory)
