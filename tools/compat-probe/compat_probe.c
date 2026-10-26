/*
 * Neutral macOS / Darling compatibility probe.
 *
 * Builds and runs as a Darwin guest program. Captures what common Darwin APIs
 * return on this prefix so two JSON dumps (real Mac vs Darling) can be compared.
 * Does not talk to Riot, does not alter platform identity, and is not a
 * client/game tool.
 *
 * Build on macOS (or inside a Darling guest with clang):
 *   clang -O2 -Wall -Wextra -o compat_probe compat_probe.c \
 *     -framework IOKit -framework CoreFoundation
 *
 * Optional window list (AppKit/ApplicationServices):
 *   clang ... -DCOMPAT_PROBE_WINDOWS=1 -framework ApplicationServices
 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <sys/utsname.h>
#include <unistd.h>

#if defined(__APPLE__)
#include <libproc.h>
#include <sys/mount.h>
#include <sys/codesign.h>
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#if defined(COMPAT_PROBE_WINDOWS) && COMPAT_PROBE_WINDOWS
#include <CoreGraphics/CGWindow.h>
#endif
#endif

static void json_escape(FILE *out, const char *s)
{
	if (!s) {
		fputs("null", out);
		return;
	}
	fputc('"', out);
	for (; *s; s++) {
		unsigned char c = (unsigned char)*s;
		switch (c) {
		case '\\': fputs("\\\\", out); break;
		case '"':  fputs("\\\"", out); break;
		case '\n': fputs("\\n", out); break;
		case '\r': fputs("\\r", out); break;
		case '\t': fputs("\\t", out); break;
		default:
			if (c < 0x20)
				fprintf(out, "\\u%04x", c);
			else
				fputc(c, out);
		}
	}
	fputc('"', out);
}

static void emit_sysctl_string(FILE *out, const char *name, int first)
{
	char buf[512];
	size_t len = sizeof(buf);
	int rc;

	if (!first)
		fputc(',', out);
	fputc('\n', out);
	fprintf(out, "    ");
	json_escape(out, name);
	fputs(": ", out);
	rc = sysctlbyname(name, buf, &len, NULL, 0);
	if (rc != 0) {
		fprintf(out, "{\"ok\":false,\"errno\":%d}", errno);
		return;
	}
	/* Ensure NUL even if the kernel wrote a raw buffer. */
	if (len >= sizeof(buf))
		len = sizeof(buf) - 1;
	buf[len] = '\0';
	/* Trim trailing NULs common in sysctl string returns. */
	while (len > 0 && buf[len - 1] == '\0')
		len--;
	buf[len] = '\0';
	fputs("{\"ok\":true,\"value\":", out);
	json_escape(out, buf);
	fputc('}', out);
}

static void emit_sysctl_u64(FILE *out, const char *name, int first)
{
	unsigned long long v = 0;
	size_t len = sizeof(v);
	int rc;

	if (!first)
		fputc(',', out);
	fputc('\n', out);
	fprintf(out, "    ");
	json_escape(out, name);
	fputs(": ", out);
	rc = sysctlbyname(name, &v, &len, NULL, 0);
	if (rc != 0) {
		fprintf(out, "{\"ok\":false,\"errno\":%d}", errno);
		return;
	}
	fprintf(out, "{\"ok\":true,\"value\":%llu}", v);
}

static void emit_sysctl_int(FILE *out, const char *name, int first)
{
	int v = 0;
	size_t len = sizeof(v);
	int rc;

	if (!first)
		fputc(',', out);
	fputc('\n', out);
	fprintf(out, "    ");
	json_escape(out, name);
	fputs(": ", out);
	rc = sysctlbyname(name, &v, &len, NULL, 0);
	if (rc != 0) {
		fprintf(out, "{\"ok\":false,\"errno\":%d}", errno);
		return;
	}
	fprintf(out, "{\"ok\":true,\"value\":%d}", v);
}

#if defined(__APPLE__)
static char *cf_to_c(CFTypeRef v)
{
	char tmp[512];

	if (!v)
		return NULL;
	if (CFGetTypeID(v) == CFStringGetTypeID()) {
		if (CFStringGetCString((CFStringRef)v, tmp, sizeof(tmp),
				       kCFStringEncodingUTF8))
			return strdup(tmp);
		return NULL;
	}
	if (CFGetTypeID(v) == CFDataGetTypeID()) {
		CFDataRef d = (CFDataRef)v;
		CFIndex n = CFDataGetLength(d);
		const UInt8 *p = CFDataGetBytePtr(d);
		size_t copy = (size_t)n;
		char *out;

		if (copy >= sizeof(tmp))
			copy = sizeof(tmp) - 1;
		memcpy(tmp, p, copy);
		tmp[copy] = '\0';
		/* Prefer printable C string view of NUL-terminated IOKit data. */
		out = strdup(tmp);
		return out;
	}
	return NULL;
}

static int is_identifier_key(const char *k)
{
	return strcmp(k, "IOPlatformSerialNumber") == 0 ||
	       strcmp(k, "IOPlatformUUID") == 0;
}

/* Coarse character-class shape only: "uuid", "alnum-upper" or "other". */
static const char *identifier_format(const char *s)
{
	size_t i, n = strlen(s);
	int upper_alnum = n > 0;

	if (n == 36 && s[8] == '-' && s[13] == '-' && s[18] == '-' && s[23] == '-')
		return "uuid";
	for (i = 0; i < n; i++)
		if (!((s[i] >= 'A' && s[i] <= 'Z') || (s[i] >= '0' && s[i] <= '9')))
			upper_alnum = 0;
	return upper_alnum ? "alnum-upper" : "other";
}

static void emit_iokit_platform(FILE *out)
{
	io_service_t service;
	CFMutableDictionaryRef props = NULL;
	static const char *keys[] = {
		"IOPlatformSerialNumber",
		"IOPlatformUUID",
		"model",
		"manufacturer",
		"board-id",
		"product-name",
		NULL
	};
	int i;

	fputs("  \"iokit_platform\": {\n", out);
#ifndef kIOMainPortDefault
#define kIOMainPortDefault kIOMasterPortDefault
#endif
	service = IOServiceGetMatchingService(
		kIOMainPortDefault,
		IOServiceMatching("IOPlatformExpertDevice"));
	if (!service) {
		fputs("    \"ok\": false,\n    \"error\": \"no IOPlatformExpertDevice\"\n  }", out);
		return;
	}
	if (IORegistryEntryCreateCFProperties(service, &props, kCFAllocatorDefault, 0)
	    != KERN_SUCCESS || !props) {
		IOObjectRelease(service);
		fputs("    \"ok\": false,\n    \"error\": \"IORegistryEntryCreateCFProperties failed\"\n  }", out);
		return;
	}
	fputs("    \"ok\": true", out);
	for (i = 0; keys[i]; i++) {
		CFStringRef k = CFStringCreateWithCString(NULL, keys[i],
							  kCFStringEncodingUTF8);
		CFTypeRef v = k ? CFDictionaryGetValue(props, k) : NULL;
		char *s = cf_to_c(v);

		fputs(",\n    ", out);
		json_escape(out, keys[i]);
		fputs(": ", out);
		if (s && is_identifier_key(keys[i])) {
			/* Never emit serials or UUIDs: record shape only. */
			fprintf(out, "{\"present\": true, \"length\": %zu, \"format\": \"%s\"}",
				strlen(s), identifier_format(s));
			free(s);
		} else if (s) {
			json_escape(out, s);
			free(s);
		} else {
			fputs("null", out);
		}
		if (k)
			CFRelease(k);
	}
	fputc('\n', out);
	CFRelease(props);
	IOObjectRelease(service);
	fputs("  }", out);
}

static void emit_csops(FILE *out)
{
	uint32_t flags = 0;
	int rc = csops(getpid(), CS_OPS_STATUS, &flags, sizeof(flags));

	fputs("  \"csops_status\": ", out);
	if (rc != 0)
		fprintf(out, "{\"ok\":false,\"errno\":%d}", errno);
	else
		fprintf(out, "{\"ok\":true,\"flags\":%u}", flags);
}

static void emit_mounts(FILE *out)
{
	struct statfs *bufs = NULL;
	int n, i;

	fputs("  \"mounts\": {\n", out);
	n = getfsstat(NULL, 0, MNT_NOWAIT);
	if (n < 0) {
		fprintf(out, "    \"ok\": false,\n    \"errno\": %d\n  }", errno);
		return;
	}
	bufs = calloc((size_t)n, sizeof(*bufs));
	if (!bufs) {
		fputs("    \"ok\": false,\n    \"error\": \"oom\"\n  }", out);
		return;
	}
	n = getfsstat(bufs, (int)(n * (int)sizeof(*bufs)), MNT_NOWAIT);
	if (n < 0) {
		fprintf(out, "    \"ok\": false,\n    \"errno\": %d\n  }", errno);
		free(bufs);
		return;
	}
	fprintf(out, "    \"ok\": true,\n    \"count\": %d,\n    \"fstypes\": [", n);
	for (i = 0; i < n; i++) {
		if (i)
			fputc(',', out);
		json_escape(out, bufs[i].f_fstypename);
	}
	fputs("]\n  }", out);
	free(bufs);
}

static void emit_processes(FILE *out)
{
	int bufsize;
	pid_t *pids;
	int n, i, shown = 0;

	fputs("  \"processes\": {\n", out);
	bufsize = proc_listpids(PROC_ALL_PIDS, 0, NULL, 0);
	if (bufsize <= 0) {
		fprintf(out, "    \"ok\": false,\n    \"errno\": %d\n  }", errno);
		return;
	}
	pids = calloc(1, (size_t)bufsize);
	if (!pids) {
		fputs("    \"ok\": false,\n    \"error\": \"oom\"\n  }", out);
		return;
	}
	bufsize = proc_listpids(PROC_ALL_PIDS, 0, pids, bufsize);
	if (bufsize <= 0) {
		fprintf(out, "    \"ok\": false,\n    \"errno\": %d\n  }", errno);
		free(pids);
		return;
	}
	n = bufsize / (int)sizeof(pid_t);
	fprintf(out, "    \"ok\": true,\n    \"count\": %d,\n    \"sample_names\": [", n);
	for (i = 0; i < n && shown < 16; i++) {
		char name[PROC_PIDPATHINFO_MAXSIZE];
		int nr;

		if (pids[i] <= 0)
			continue;
		memset(name, 0, sizeof(name));
		nr = proc_name(pids[i], name, (uint32_t)sizeof(name));
		if (nr <= 0)
			continue;
		if (shown)
			fputc(',', out);
		json_escape(out, name);
		shown++;
	}
	fputs("]\n  }", out);
	free(pids);
}

#if defined(COMPAT_PROBE_WINDOWS) && COMPAT_PROBE_WINDOWS
static void emit_windows(FILE *out)
{
	CFArrayRef list = CGWindowListCopyWindowInfo(
		kCGWindowListOptionAll, kCGNullWindowID);

	fputs("  \"windows\": ", out);
	if (!list) {
		fputs("{\"ok\":false,\"error\":\"CGWindowListCopyWindowInfo returned null\"}", out);
		return;
	}
	fprintf(out, "{\"ok\":true,\"count\":%ld}", (long)CFArrayGetCount(list));
	CFRelease(list);
}
#endif
#endif /* __APPLE__ */

int main(void)
{
	struct utsname u;
	int first;

	fputs("{\n", stdout);
	fputs("  \"probe\": \"compat-probe\",\n", stdout);
	fputs("  \"version\": 1,\n", stdout);

	if (uname(&u) == 0) {
		fputs("  \"uname\": {\n", stdout);
		fputs("    \"sysname\": ", stdout); json_escape(stdout, u.sysname); fputs(",\n", stdout);
		/* Hostname is personal; record only whether it is set. */
		fprintf(stdout, "    \"nodename\": {\"present\": %s},\n", u.nodename[0] ? "true" : "false");
		fputs("    \"release\": ", stdout); json_escape(stdout, u.release); fputs(",\n", stdout);
		fputs("    \"version\": ", stdout); json_escape(stdout, u.version); fputs(",\n", stdout);
		fputs("    \"machine\": ", stdout); json_escape(stdout, u.machine); fputs("\n", stdout);
		fputs("  },\n", stdout);
	} else {
		fprintf(stdout, "  \"uname\": {\"ok\":false,\"errno\":%d},\n", errno);
	}

	fputs("  \"sysctl\": {", stdout);
	first = 1;
	emit_sysctl_string(stdout, "hw.model", first); first = 0;
	emit_sysctl_string(stdout, "hw.machine", first);
	emit_sysctl_int(stdout, "hw.ncpu", first);
	emit_sysctl_int(stdout, "hw.physicalcpu", first);
	emit_sysctl_int(stdout, "hw.logicalcpu", first);
	emit_sysctl_u64(stdout, "hw.memsize", first);
	emit_sysctl_string(stdout, "machdep.cpu.brand_string", first);
	emit_sysctl_string(stdout, "kern.osproductversion", first);
	emit_sysctl_string(stdout, "kern.osversion", first);
	emit_sysctl_string(stdout, "kern.version", first);
	emit_sysctl_int(stdout, "kern.securelevel", first);
	emit_sysctl_u64(stdout, "kern.csr_config", first);
	emit_sysctl_int(stdout, "kern.secure_kernel", first);
	emit_sysctl_int(stdout, "hw.optional.arm64", first);
	fputs("\n  }", stdout);

#if defined(__APPLE__)
	fputs(",\n", stdout);
	emit_iokit_platform(stdout);
	fputs(",\n", stdout);
	emit_csops(stdout);
	fputs(",\n", stdout);
	emit_mounts(stdout);
	fputs(",\n", stdout);
	emit_processes(stdout);
#if defined(COMPAT_PROBE_WINDOWS) && COMPAT_PROBE_WINDOWS
	fputs(",\n", stdout);
	emit_windows(stdout);
#endif
#else
	fputs(",\n  \"note\": \"built without __APPLE__; only sysctl/uname sections are meaningful\"", stdout);
#endif

	fputs("\n}\n", stdout);
	return 0;
}
