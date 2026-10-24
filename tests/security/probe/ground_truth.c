/*
 * ground_truth.c - read-only probe of the macOS code-signing / SIP surface.
 *
 * Runs on a real macOS host (developer machine, CI runner, or a volunteer's
 * Mac). Writes JSON to stdout so artifacts from different macOS versions can
 * be diffed. It never mutates signing state: no MARKINVALID/MARKHARD/SET_STATUS
 * calls, no ptrace, no file writes.
 *
 * Build:  clang -O2 -Wall -Wextra -o ground_truth ground_truth.c
 * Run:    ./ground_truth > ground-truth.json
 *
 * The public SDK exposes CS_OPS_* through <sys/codesign.h>, but the CS_* flag
 * values and the CSR bits live in kernel-private headers. They are ABI, so
 * this probe defines them locally with the XNU source as the reference
 * (osfmk/kern/cs_blobs.h, bsd/sys/csr.h). csrctl wrappers are resolved with
 * dlsym so a missing symbol degrades to a reported error instead of a link
 * failure.
 */

#include <sys/codesign.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>

#include <dlfcn.h>
#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifndef CS_CDHASH_LEN
#define CS_CDHASH_LEN 20
#endif
#ifndef CS_MAX_TEAMID_LEN
#define CS_MAX_TEAMID_LEN 64
#endif

/* osfmk/kern/cs_blobs.h */
#ifndef CS_VALID
#define CS_VALID 0x00000001
#define CS_ADHOC 0x00000002
#define CS_GET_TASK_ALLOW 0x00000004
#define CS_INSTALLER 0x00000008
#define CS_HARD 0x00000100
#define CS_KILL 0x00000200
#define CS_CHECK_EXPIRATION 0x00000400
#define CS_RESTRICT 0x00000800
#define CS_ENFORCEMENT 0x00001000
#define CS_REQUIRE_LV 0x00002000
#define CS_ENTITLEMENTS_VALIDATED 0x00004000
#define CS_RUNTIME 0x00010000
#define CS_LINKER_SIGNED 0x00020000
#endif

/* bsd/sys/csr.h */
#ifndef CSR_ALLOW_UNRESTRICTED_FS
#define CSR_ALLOW_UNTRUSTED_KEXTS 0x00000001u
#define CSR_ALLOW_UNRESTRICTED_FS 0x00000002u
#define CSR_ALLOW_TASK_FOR_PID 0x00000004u
#define CSR_ALLOW_KERNEL_DEBUGGER 0x00000008u
#define CSR_ALLOW_APPLE_INTERNAL 0x00000010u
#define CSR_ALLOW_UNRESTRICTED_DTRACE 0x00000020u
#define CSR_ALLOW_UNRESTRICTED_NVRAM 0x00000040u
#define CSR_ALLOW_DEVICE_CONFIGURATION 0x00000080u
#define CSR_ALLOW_ANY_RECOVERY_OS 0x00000100u
#define CSR_ALLOW_UNAPPROVED_KEXTS 0x00000200u
#define CSR_ALLOW_EXECUTABLE_POLICY_OVERRIDE 0x00000400u
#define CSR_ALLOW_UNAUTHENTICATED_ROOT 0x00000800u
#endif

typedef int (*csr_get_config_fn)(uint32_t *config);
typedef int (*csr_check_fn)(uint32_t mask);

static csr_get_config_fn csr_get_config_sym(void)
{
	static csr_get_config_fn fn;

	if (!fn) {
		void *h = dlopen("/usr/lib/libSystem.B.dylib", RTLD_LAZY);
		if (h)
			fn = (csr_get_config_fn)dlsym(h, "csr_get_active_config");
	}
	return fn;
}

static csr_check_fn csr_check_sym(void)
{
	static csr_check_fn fn;

	if (!fn) {
		void *h = dlopen("/usr/lib/libSystem.B.dylib", RTLD_LAZY);
		if (h)
			fn = (csr_check_fn)dlsym(h, "csr_check");
	}
	return fn;
}

static void print_hex(const unsigned char *p, size_t n)
{
	for (size_t i = 0; i < n; i++)
		printf("%02x", p[i]);
}

static void print_json_string(const char *s)
{
	putchar('"');
	for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
		switch (*p) {
		case '"':  fputs("\\\"", stdout); break;
		case '\\': fputs("\\\\", stdout); break;
		case '\n': fputs("\\n", stdout); break;
		case '\r': fputs("\\r", stdout); break;
		case '\t': fputs("\\t", stdout); break;
		default:
			if (*p < 0x20)
				printf("\\u%04x", *p);
			else
				putchar(*p);
		}
	}
	putchar('"');
}

static int read_blob(pid_t pid, unsigned int op, unsigned char **out, size_t *out_len)
{
	size_t cap = 65536;
	unsigned char *buf = malloc(cap);

	if (!buf)
		return -1;
	memset(buf, 0, cap);
	errno = 0;
	if (csops(pid, op, buf, cap) != 0) {
		int e = errno;
		free(buf);
		errno = e;
		return -1;
	}
	*out = buf;
	*out_len = cap;
	return 0;
}

static void probe_self(void)
{
	uint32_t flags = 0;
	unsigned char cdhash[CS_CDHASH_LEN];
	char teamid[CS_MAX_TEAMID_LEN];
	unsigned char *ents = NULL;
	size_t ents_len = 0;
	uint32_t pidoffset = 0;
	int r;

	printf("  \"self\": {\n");
	printf("    \"pid\": %d,\n", (int)getpid());

	errno = 0;
	r = csops(getpid(), CS_OPS_STATUS, &flags, sizeof(flags));
	printf("    \"status\": {\"rc\": %d, \"errno\": %d, \"flags\": \"0x%08x\", "
	       "\"valid\": %s, \"adhoc\": %s, \"runtime\": %s, \"require_lv\": %s, "
	       "\"get_task_allow\": %s, \"hard\": %s, \"kill\": %s, \"restrict\": %s},\n",
	       r, r ? errno : 0, flags,
	       (flags & CS_VALID) ? "true" : "false",
	       (flags & CS_ADHOC) ? "true" : "false",
	       (flags & CS_RUNTIME) ? "true" : "false",
	       (flags & CS_REQUIRE_LV) ? "true" : "false",
	       (flags & CS_GET_TASK_ALLOW) ? "true" : "false",
	       (flags & CS_HARD) ? "true" : "false",
	       (flags & CS_KILL) ? "true" : "false",
	       (flags & CS_RESTRICT) ? "true" : "false");

	memset(cdhash, 0, sizeof(cdhash));
	errno = 0;
	r = csops(getpid(), CS_OPS_CDHASH, cdhash, sizeof(cdhash));
	printf("    \"cdhash\": {\"rc\": %d, \"errno\": %d, \"value\": \"", r, r ? errno : 0);
	if (r == 0)
		print_hex(cdhash, sizeof(cdhash));
	printf("\"},\n");

	memset(teamid, 0, sizeof(teamid));
	errno = 0;
	r = csops(getpid(), CS_OPS_TEAMID, teamid, sizeof(teamid));
	printf("    \"teamid\": {\"rc\": %d, \"errno\": %d, \"value\": ", r, r ? errno : 0);
	if (r == 0) {
		teamid[sizeof(teamid) - 1] = '\0';
		print_json_string(teamid);
	} else {
		printf("null");
	}
	printf("},\n");

	if (read_blob(getpid(), CS_OPS_ENTITLEMENTS_BLOB, &ents, &ents_len) == 0) {
		size_t len = strnlen((const char *)ents, ents_len);
		printf("    \"entitlements\": {\"rc\": 0, \"length\": %zu, \"xml\": ", len);
		print_json_string((const char *)ents);
		printf("},\n");
		free(ents);
	} else {
		printf("    \"entitlements\": {\"rc\": -1, \"errno\": %d},\n", errno);
	}

	errno = 0;
	r = csops(getpid(), CS_OPS_PIDOFFSET, &pidoffset, sizeof(pidoffset));
	printf("    \"pidoffset\": {\"rc\": %d, \"errno\": %d, \"value\": %u}\n",
	       r, r ? errno : 0, pidoffset);

	printf("  },\n");
}

static void probe_child(void)
{
	pid_t child = fork();
	if (child < 0) {
		printf("  \"child_query\": {\"fork_errno\": %d},\n", errno);
		return;
	}
	if (child == 0) {
		for (;;)
			pause();
		_exit(0);
	}

	usleep(100000);

	uint32_t flags = 0;
	unsigned char cdhash[CS_CDHASH_LEN];
	char teamid[CS_MAX_TEAMID_LEN];

	errno = 0;
	int rs = csops(child, CS_OPS_STATUS, &flags, sizeof(flags));
	int es = errno;
	errno = 0;
	int rc = csops(child, CS_OPS_CDHASH, cdhash, sizeof(cdhash));
	int ec = errno;
	errno = 0;
	int rt = csops(child, CS_OPS_TEAMID, teamid, sizeof(teamid));
	int et = errno;

	printf("  \"child_query\": {\n");
	printf("    \"pid\": %d,\n", (int)child);
	printf("    \"status\": {\"rc\": %d, \"errno\": %d, \"flags\": \"0x%08x\"},\n",
	       rs, rs ? es : 0, flags);
	printf("    \"cdhash\": {\"rc\": %d, \"errno\": %d, \"value\": \"", rc, rc ? ec : 0);
	if (rc == 0)
		print_hex(cdhash, sizeof(cdhash));
	printf("\"},\n");
	printf("    \"teamid\": {\"rc\": %d, \"errno\": %d, \"value\": ", rt, rt ? et : 0);
	if (rt == 0) {
		teamid[sizeof(teamid) - 1] = '\0';
		print_json_string(teamid);
	} else {
		printf("null");
	}
	printf("}\n");
	printf("  },\n");

	kill(child, SIGKILL);
	waitpid(child, NULL, 0);
}

int main(void)
{
	struct utsname u;
	uint32_t config = 0;
	csr_get_config_fn get_config = csr_get_config_sym();
	csr_check_fn check = csr_check_sym();
	int cr = -1, ck_tfp = -1, ck_dbg = -1;

	if (uname(&u) != 0)
		memset(&u, 0, sizeof(u));

	if (get_config) {
		errno = 0;
		cr = get_config(&config);
	}
	if (check) {
		ck_tfp = check(CSR_ALLOW_TASK_FOR_PID);
		ck_dbg = check(CSR_ALLOW_KERNEL_DEBUGGER);
	}

	printf("{\n");
	printf("  \"uname\": {\"sysname\": ");
	print_json_string(u.sysname);
	printf(", \"release\": ");
	print_json_string(u.release);
	printf(", \"version\": ");
	print_json_string(u.version);
	printf(", \"machine\": ");
	print_json_string(u.machine);
	printf("},\n");
	printf("  \"pid\": %d,\n", (int)getpid());

	printf("  \"csr\": {\"rc\": %d, \"errno\": %d, \"config\": \"0x%08x\", "
	       "\"unrestricted_fs\": %s, \"task_for_pid\": %s, \"debugger\": %s, "
	       "\"unauthenticated_root\": %s},\n",
	       cr, cr ? errno : 0, config,
	       (config & CSR_ALLOW_UNRESTRICTED_FS) ? "true" : "false",
	       (config & CSR_ALLOW_TASK_FOR_PID) ? "true" : "false",
	       (config & CSR_ALLOW_KERNEL_DEBUGGER) ? "true" : "false",
	       (config & CSR_ALLOW_UNAUTHENTICATED_ROOT) ? "true" : "false");

	printf("  \"csr_check\": {\"task_for_pid\": %d, \"debugger\": %d},\n",
	       ck_tfp, ck_dbg);

	probe_self();
	probe_child();

	printf("  \"done\": true\n");
	printf("}\n");
	return 0;
}
