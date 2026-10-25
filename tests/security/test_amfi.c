/*
 * Guest-side M8 test: unknown AMFI calls fail closed and a non-entitled
 * process cannot attach to another task.
 */

#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/codesign.h>
#include <sys/ptrace.h>
#include <sys/syscall.h>

#define PT_ATTACHEXC 14

static void busy(unsigned long count) {
	volatile unsigned long i;
	for (i = 0; i < count; i++) {}
}

int main(void) {
	pid_t child;
	long result;
	int rc;

	errno = 0;
	result = syscall(381, "AMFI", 1234, (void*) 0);
	printf("unknown_amfi r=%ld errno=%d\n", result, errno);
	if (result != -1 || errno != ENOTSUP) {
		printf("AMFI_FAIL\n");
		return 1;
	}

	child = fork();
	if (child == 0) {
		busy(400000000UL);
		_exit(0);
	}
	if (child < 0) {
		printf("FORK_FAIL\n");
		return 1;
	}
	busy(30000000UL);

	if (seteuid(1000) != 0) {
		printf("SETEUID_FAIL errno=%d\n", errno);
		kill(child, SIGKILL);
		return 1;
	}
	errno = 0;
	rc = ptrace(PT_ATTACHEXC, child, (void*) 0, 0);
	printf("ptrace r=%d errno=%d\n", rc, errno);
	kill(child, SIGKILL);
	if (rc != -1 || errno != EPERM) {
		printf("PTRACE_FAIL\n");
		return 1;
	}

	printf("AMFI_OK\n");
	return 0;
}
