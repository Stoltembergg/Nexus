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
 * Constants come from the SDK headers shipped with XNU:
 *   sys/codesign.h  (CS_OPS_*, CS_* flags)
 *   sys/csr.h       (CSR_ALLOW_*, csr_get_active_config)
 */

#include <sys/codesign.h>
#include <sys/csr.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>

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

/*
 * csops blob getters do not report the blob length. Try increasing sizes and
 * treat the first success as authoritative. ERANGE/ENOMEM mean "grow".
 */
static int read_blob(pid_t pid, unsigned int op, unsigned char **out, size_t *out_len)
{
	size_t cap = 65536;
	unsigned char *buf = malloc(cap);
	if (!buf)
		return -1;
	memset(buf, 0, cap);

	errno = 0;
	int r = csops(pid, op, buf, cap);
	if (r != 0) {
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

/*
 * Cross-process query: fork a child that just pauses, query it from the
 * parent, then kill it. This is the behaviour darlingserver has to match,
 * including the EPERM cases.
 */
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

	usleep(100000); /* let the child get scheduled */

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
	csr_config_t config = 0;

	if (uname(&u) != 0)
		memset(&u, 0, sizeof(u));

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

	errno = 0;
	int cr = csr_get_active_config(&config);
	printf("  \"csr\": {\"rc\": %d, \"errno\": %d, \"config\": \"0x%08x\", "
	       "\"unrestricted_fs\": %s, \"task_for_pid\": %s, \"debugger\": %s, "
	       "\"unauthenticated_root\": %s},\n",
	       cr, cr ? errno : 0, config,
	       (config & CSR_ALLOW_UNRESTRICTED_FS) ? "true" : "false",
	       (config & CSR_ALLOW_TASK_FOR_PID) ? "true" : "false",
	       (config & CSR_ALLOW_KERNEL_DEBUGGER) ? "true" : "false",
	       (config & CSR_ALLOW_UNAUTHENTICATED_ROOT) ? "true" : "false");

	printf("  \"csr_check\": {\"task_for_pid\": %d, \"debugger\": %d},\n",
	       csr_check(CSR_ALLOW_TASK_FOR_PID),
	       csr_check(CSR_ALLOW_KERNEL_DEBUGGER));

	probe_self();
	probe_child();

	printf("  \"done\": true\n");
	printf("}\n");
	return 0;
}
