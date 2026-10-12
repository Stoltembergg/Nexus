#!/usr/bin/env python3
"""Exercise the real cancellation wrapper with a controlled RPC transport."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = root / 'build/darling-src/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/impl/bsdthread/pthread_canceled.c'
body = '\n'.join(line for line in source.read_text().splitlines() if not line.startswith('#include'))
harness = r'''
#include <assert.h>
#include <stdlib.h>
#include <errno.h>
#include <pthread.h>
/* Model the guest's ENOSYS (78), distinct from Linux ENOSYS (38). */
#undef ENOSYS
#define ENOSYS 78
static int threads = 1, calls, answer = -38;
static int uses_threads(void) { return threads; }
static int errno_linux_to_bsd(int value) { return value == -38 ? -ENOSYS : value; }
static int dserver_rpc_pthread_canceled(int action) {
    __atomic_fetch_add(&calls, 1, __ATOMIC_RELAXED);
    return answer;
}
'''
checks = r'''
static void *hammer(void *unused) {
    for (int i = 0; i < 100000; ++i) assert(sys_pthread_canceled(0) == -ENOSYS);
    return NULL;
}
int main(int argc, char **argv) {
    switch (atoi(argv[1])) {
    case 0:
        for (int i = 0; i < 100000; ++i)
            for (int a = 0; a < 3; ++a) assert(sys_pthread_canceled(a) == -ENOSYS);
        assert(calls == 3);
        threads = 0;
        assert(sys_pthread_canceled(0) == -EINVAL);
        assert(calls == 3);
        break;
    case 1:
        answer = 0;
        for (int i = 0; i < 100; ++i) assert(sys_pthread_canceled(0) == 0);
        answer = -EINTR;
        for (int i = 0; i < 100; ++i) assert(sys_pthread_canceled(0) == -EINTR);
        assert(calls == 200);
        break;
    case 2:
        for (int i = 0; i < 100; ++i) {
            assert(sys_pthread_canceled(-1) == -ENOSYS);
            assert(sys_pthread_canceled(32) == -ENOSYS);
        }
        assert(calls == 200);
        break;
    case 3: {
        pthread_t workers[8];
        for (int i = 0; i < 8; ++i) assert(!pthread_create(&workers[i], NULL, hammer, NULL));
        for (int i = 0; i < 8; ++i) assert(!pthread_join(workers[i], NULL));
        assert(calls >= 1 && calls <= 8);
        break;
    }
    }
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='pthread-cache-') as folder:
    c = Path(folder) / 'check.c'
    binary = Path(folder) / 'check'
    c.write_text(harness + body + checks)
    subprocess.run(['cc', '-O2', '-pthread', '-fsanitize=undefined', str(c), '-o', str(binary)], check=True)
    for scenario in range(4):
        subprocess.run([str(binary), str(scenario)], check=True)
print('PASS: unsupported RPC reduction, supported/error forwarding, invalid actions, concurrent callers')
