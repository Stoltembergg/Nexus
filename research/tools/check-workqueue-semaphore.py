#!/usr/bin/env python3
"""Exercise the production workqueue token functions against Linux futexes."""
from pathlib import Path
import argparse
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=root / 'build/darling-src/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/impl/bsdthread/workq_kernreturn.c')
args = parser.parse_args()
source = args.source.read_text()
functions = source[source.index('int sem_down(int* sem, int timeout)'):source.index('#define __PTHREAD_PRIORITY_CBIT_USER_INTERACTIVE')]
preamble = r'''
#define _GNU_SOURCE
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <errno.h>
#include <time.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <linux/futex.h>
#define LINUX_SYSCALL(number, ...) raw_syscall(number, __VA_ARGS__)
static long raw_syscall(long number, ...) __attribute__((unused));
#include <stdarg.h>
static long raw_syscall(long number, ...) {
    va_list args; va_start(args, number);
    long result;
    if (number == SYS_clock_gettime) {
        int clock = va_arg(args, int);
        struct timespec *value = va_arg(args, struct timespec*);
        result = syscall(number, clock, value);
    } else {
        int *word = va_arg(args, int*);
        int operation = va_arg(args, int), value = va_arg(args, int);
        struct timespec *timeout = va_arg(args, struct timespec*);
        void *other = va_arg(args, void*);
        int value2 = va_arg(args, int);
        result = syscall(number, word, operation, value, timeout, other, value2);
    }
    va_end(args);
    return result < 0 ? -errno : result;
}
static int __linux_futex(int *word, int operation, int value,
                         const struct timespec *timeout, int *other, int value2) {
    return syscall(SYS_futex, word, operation, value, timeout, other, value2);
}
'''
test = r'''
enum { THREADS=4, TOKENS=50000 };
static int tokens;
static atomic_int failed, consumed, timed_done;
static void *producer(void *arg) {
    for (int i=0; i<TOKENS; ++i) { sem_up(&tokens); if ((i&31)==0) sched_yield(); }
    return NULL;
}
static void *consumer(void *arg) {
    for (int i=0; i<TOKENS; ++i) {
        if (!sem_down(&tokens, -1)) { failed=1; return NULL; }
        ++consumed;
    }
    return NULL;
}
static void handle_signal(int value) {}
static void *timed(void *arg) {
    struct timespec before, after;
    clock_gettime(CLOCK_MONOTONIC, &before);
    int acquired=sem_down(&tokens, 1);
    clock_gettime(CLOCK_MONOTONIC, &after);
    double elapsed=after.tv_sec-before.tv_sec+(after.tv_nsec-before.tv_nsec)/1e9;
    if (acquired || elapsed<.95 || elapsed>1.5) failed=1;
    printf("Interrupted timed wait: %.3f s acquired=%d\n", elapsed, acquired);
    timed_done=1;
    return NULL;
}
int main(void) {
    pthread_t producers[THREADS], consumers[THREADS], waiter;
    for (int i=0; i<THREADS; ++i) pthread_create(&consumers[i], NULL, consumer, NULL);
    for (int i=0; i<THREADS; ++i) pthread_create(&producers[i], NULL, producer, NULL);
    for (int i=0; i<THREADS; ++i) pthread_join(producers[i], NULL);
    for (int i=0; i<THREADS; ++i) pthread_join(consumers[i], NULL);
    int remaining=tokens;
    if (consumed!=THREADS*TOKENS || tokens || sem_down(&tokens,0)) failed=1;
    tokens=0; // Test interrupted timeout independently of a failed transfer test.
    struct sigaction action={.sa_handler=handle_signal};
    sigaction(SIGUSR1,&action,NULL);
    pthread_create(&waiter,NULL,timed,NULL);
    while (!timed_done) { usleep(1000); pthread_kill(waiter,SIGUSR1); }
    pthread_join(waiter,NULL);
    sem_up(&tokens); if (!sem_down(&tokens,0) || tokens) failed=1;
    printf("Tokens consumed=%d expected=%d remaining=%d pass=%d\n",
           consumed,THREADS*TOKENS,remaining,!failed);
    return failed;
}
'''
with tempfile.TemporaryDirectory(prefix='workqueue-check-') as directory:
    directory = Path(directory)
    c = directory / 'check.c'
    c.write_text(preamble + functions + test)
    binary = directory / 'check'
    subprocess.run(['cc', '-O2', '-pthread', str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], timeout=30, check=True)
