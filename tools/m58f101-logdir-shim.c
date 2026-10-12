/* darling-lol M58F101/M58F116/M58F131: injected shim.
 *
 * 1) Absolutize a RELATIVE --log-dir in argv (else the app passes a relative
 *    path to Electron's app.setAppLogsPath(), which THROWS "Path must be
 *    absolute", aborting startup before createWindow -> no UX window).
 * 2) If RCLOL_NO_HWACCEL=1, drop any `--enableHardwareAcceleration` argv entry.
 * 3) If RCLOL_SAMPLE=1, install a SIGPROF profiling timer; the handler records
 *    the interrupted RIP from the signal ucontext; after ~45 s a dumper thread
 *    writes samples + dyld image ranges to @GUEST_HOME@/lolsamp-<pid>.txt.
 *    (SIGPROF/ITIMER_PROF samples the CPU-consuming thread = the UX main thread
 *    that M58F121 showed at ~40% CPU.)  Mach thread_get_state returned zeros
 *    (M58F127), so this ucontext route is used instead.
 *
 * Build (headerless, host clang, dynamic_lookup):
 *   clang -target x86_64-apple-macosx11.0 -fuse-ld=lld -dynamiclib \
 *     -nostdlib -nodefaultlibs -undefined dynamic_lookup -O2 \
 *     -o zzlogdir.dylib m58f101-logdir-shim.c -Wl,-install_name,/tmp/zzlogdir.dylib
 */
typedef unsigned long size_t;
typedef unsigned int u32;
typedef unsigned long long u64;

extern char*** _NSGetArgv(void);
extern int* _NSGetArgc(void);
extern char* getenv(const char*);
extern void* malloc(size_t);
extern int snprintf(char*, size_t, const char*, ...);
extern size_t strlen(const char*);
extern int getpid(void);
extern int usleep(unsigned int);
extern int open(const char*, int, int);
extern long write(int, const void*, size_t);
extern int close(int);
struct dart_tv { long s; long us; };
extern int gettimeofday(struct dart_tv*, void*);
/* signal / timer */
struct dart_sigaction { void (*handler)(int, void*, void*); u32 sa_mask; int sa_flags; };
extern int sigaction(int, const struct dart_sigaction*, struct dart_sigaction*);
struct dart_itimerval { struct dart_tv it_interval; struct dart_tv it_value; };
extern int setitimer(int, const struct dart_itimerval*, struct dart_itimerval*);
/* pthread / dyld */
extern int pthread_create(unsigned long*, const void*, void* (*)(void*), void*);
extern int _dyld_image_count(void);
extern void* _dyld_get_image_header(int);
extern long _dyld_get_image_vmaddr_slide(int);
extern const char* _dyld_get_image_name(int);
/* darling-lol M58F159: enable libsystem_kernel's long-wait trace (defined there;
 * the syscall wrapper must not call libc itself). */
extern void __lolsys_set_wake_trace(int);
extern long __lolsys_syscall(long, long, long, long, long, long, int);

#define SIGPROF_ 27
#define SA_SIGINFO 0x0040
#define ITIMER_PROF 2
#define SAMPLE_US 2000
#define DUMP_US 15000000L

static int logdir_prefix(const char* s)
{
	static const char p[] = "--log-dir=";
	int i;
	for (i = 0; i < 10; i++)
		if (s[i] != p[i]) return 0;
	return s[10] != 0;
}

static int has_substr(const char* s, const char* n)
{
	size_t i, j;
	for (i = 0; s[i]; i++) {
		for (j = 0; n[j] && s[i + j] == n[j]; j++) { }
		if (!n[j]) return 1;
	}
	return 0;
}

/* --- SIGPROF sampler ----------------------------------------------------- */
static u64 g_rip[16384];
static u64 g_rax[16384];   /* M58F164: also record rax (syscall number at the trap) */
static volatile int g_n;
static volatile int g_done;

static void sigprof_handler(int sig, void* info, void* uc)
{
	/* __darwin_mcontext64* at ucontext+48; __rip at mcontext+144, __rax at +0 */
	u64* mc;
	int n = g_n;
	if (n >= 16384 || !uc) return;
	mc = *(u64**)((char*)uc + 48);
	if (!mc) return;
	g_rip[n] = mc[18];
	g_rax[n] = mc[2];   /* __ss.__rax is at mcontext+16 (after 16-byte __es) */
	g_n = n + 1;
}

static long dart_now_us(void)
{
	struct dart_tv tv;
	tv.s = 0; tv.us = 0;
	gettimeofday(&tv, 0);
	return tv.s * 1000000L + tv.us;
}

static char* put_hex(char* o, u64 v)
{
	char* h = "0123456789abcdef";
	int i, st = 1;
	o[0] = '0'; o[1] = 'x'; o += 2;
	for (i = 60; i >= 0; i -= 4) {
		int d = (int)((v >> i) & 0xf);
		if (d || !st || i == 0) { *o++ = h[d]; st = 0; }
	}
	return o;
}
static char* put_str(char* o, const char* s) { while (*s) *o++ = *s++; return o; }

static void dump(void)
{
	char path[64], buf[512], *o;
	int i, fd, n = g_n;

	o = path; o = put_str(o, "@GUEST_HOME@/lolsamp-");
	{ char tmp[16]; int k = 0, v = getpid(); if (!v) tmp[k++] = '0';
	  while (v) { tmp[k++] = (char)('0' + v % 10); v /= 10; }
	  while (k) *o++ = tmp[--k]; }
	o = put_str(o, ".txt"); *o = 0;

	fd = open(path, 0x601, 0644);
	if (fd < 0) return;
	for (i = 0; i < _dyld_image_count() && i < 64; i++) {
		o = buf; o = put_str(o, "IMG ");
		o = put_hex(o, (u64)(size_t)_dyld_get_image_header(i)); *o++ = ' ';
		o = put_hex(o, (u64)_dyld_get_image_vmaddr_slide(i)); *o++ = ' ';
		o = put_str(o, _dyld_get_image_name(i) ? _dyld_get_image_name(i) : "?");
		*o++ = '\n';
		write(fd, buf, (size_t)(o - buf));
	}
	for (i = 0; i < n; i++) {
		o = buf; o = put_str(o, "RIP "); o = put_hex(o, g_rip[i]);
		o = put_str(o, " RAX "); o = put_hex(o, g_rax[i]); *o++ = '\n';
		write(fd, buf, (size_t)(o - buf));
	}
	write(fd, "END 1\n", 6);
	close(fd);
}

static void* dumper(void* a)
{
	long t0 = dart_now_us();
	struct dart_sigaction sa;
	struct dart_itimerval it;
	(void)a;
	/* M58F163: install the profiling timer LATE (from this thread, after the
	 * process has come up).  Installing it in the constructor broke the app. */
	while (dart_now_us() - t0 < 45000000L) usleep(200000);
	sa.handler = sigprof_handler;
	sa.sa_mask = 0;
	sa.sa_flags = SA_SIGINFO;
	sigaction(SIGPROF_, &sa, 0);
	it.it_interval.s = 0; it.it_interval.us = SAMPLE_US;
	it.it_value.s = 0; it.it_value.us = SAMPLE_US;
	setitimer(ITIMER_PROF, &it, 0);
	t0 = dart_now_us();
	while (dart_now_us() - t0 < DUMP_US) usleep(200000);
	/* stop the timer and dump */
	{ struct dart_itimerval z; u64* p = (u64*)&z; int i;
	  for (i = 0; i < 4; i++) p[i] = 0;  /* 32-byte struct */
	  setitimer(ITIMER_PROF, &z, 0); }
	dump();
	g_done = 1;
	return 0;
}

__attribute__((constructor))
static void darling_shim(void)
{
	char*** argvp = _NSGetArgv();
	int* argcp = _NSGetArgc();
	char** argv;
	const char* home;
	int i;


	/* Opt-in host debugging for this process only. Yama otherwise prevents
	 * attaching to the guest process spawned by shellspawn. */
	if (getenv("RCLOL_DEBUG_ATTACH"))
		__lolsys_syscall(0x59616d61 /* PR_SET_PTRACER */, -1, 0, 0, 0, 0,
		    157 /* Linux x86_64 prctl */);

	if (argvp && *argvp) {
		argv = *argvp;
		home = getenv("HOME");
		if (!home || home[0] != '/') home = "@GUEST_HOME@";
		for (i = 0; argv[i]; i++) {
			const char* v;
			size_t n;
			char* s;
			if (!logdir_prefix(argv[i])) continue;
			v = argv[i] + 10;
			if (v[0] == '/' || v[0] == '.') continue;
			n = strlen(home) + 1 + strlen(v) + 1;
			s = (char*) malloc(n + 10);
			if (!s) continue;
			snprintf(s, n + 10, "--log-dir=%s/%s", home, v);
			argv[i] = s;
		}
		if (getenv("RCLOL_NO_HWACCEL")) {
			int w = 0;
			for (i = 0; argv[i]; i++) {
				if (has_substr(argv[i], "enableHardwareAcceleration")) continue;
				argv[w++] = argv[i];
			}
			argv[w] = 0;
			if (argcp) *argcp = w;
		}
		/* M58F199: replace the product's hardware-acceleration switch in the
		 * original argv array.  Replacing _NSGetArgv's pointer does not update
		 * the argv pointer already passed to main(), which Electron reads. */
		{
			const char* extra = getenv("RCLOL_APP_ARGS");
			const char* slot = getenv("RCLOL_APP_ARGS_SLOT");
			int pass;
			static const char product[] = "/Riot Client";
			size_t path_len = strlen(argv[0]);
			size_t suffix_len = sizeof(product) - 1;
			if (extra && extra[0] && argcp && path_len >= suffix_len &&
			    !__builtin_strcmp(argv[0] + path_len - suffix_len, product)) {
				/* Each replacement is ONE argv entry. An opt-in second slot
				 * permits experiments without writing beyond the original argv
				 * or treating a space-separated string as multiple switches.
				 * The caller must explicitly select the second slot. */
				for (pass = 0; pass < 3; pass++) {
					if (pass) {
						extra = getenv(pass == 1 ? "RCLOL_APP_ARG2" : "RCLOL_APP_ARG3");
						slot = getenv(pass == 1 ? "RCLOL_APP_ARG2_SLOT" : "RCLOL_APP_ARG3_SLOT");
						if (!extra || !extra[0] || !slot || !slot[0]) break;
					}
				for (i = 0; argv[i]; i++) {
					if ((slot && slot[0] && has_substr(argv[i], slot)) ||
					    ((!slot || !slot[0]) &&
					     (has_substr(argv[i], "--enable-hardware-acceleration") ||
					      has_substr(argv[i], "--enableHardwareAcceleration")))) {
						argv[i] = (char*)extra;
						break;
					}
				}
				}
			}
		}

		/* League's own UI is a separate CEF app, not the Riot Client product, and the
		 * Riot-only block above never matched it.  Its browser process builds its Chromium
		 * switches in-process, so they are not in its argv; the GPU helper's argv does
		 * carry them.  Apply the same kind of single-entry replacement there, from
		 * RCLOL_UX_ARG<n> / RCLOL_UX_ARG<n>_SLOT (n = 1..4). */
		{
			static const char gpu[] = "/LeagueClientUx Helper (GPU)";
			size_t path_len = strlen(argv[0]);
			size_t suffix_len = sizeof(gpu) - 1;
			if (argcp && path_len >= suffix_len &&
			    !__builtin_strcmp(argv[0] + path_len - suffix_len, gpu)) {
				char arg_name[] = "RCLOL_UX_ARG0";
				char slot_name[] = "RCLOL_UX_ARG0_SLOT";
				int n;
				for (n = 1; n <= 4; n++) {
					const char* extra;
					const char* slot;
					arg_name[sizeof(arg_name) - 2] = (char)('0' + n);
					slot_name[sizeof("RCLOL_UX_ARG") - 1] = (char)('0' + n);
					extra = getenv(arg_name);
					slot = getenv(slot_name);
					if (!extra || !extra[0] || !slot || !slot[0]) continue;
					for (i = 0; argv[i]; i++) {
						if (has_substr(argv[i], slot)) {
							argv[i] = (char*)extra;
							break;
						}
					}
				}
			}
		}
	}

    /* GPU flags are parsed separately from the browser command line. */
    if (argvp && *argvp) {
        const char *gpuArg = getenv("RCLOL_GPU_ARG");
        const char *gpuSlot = getenv("RCLOL_GPU_ARG_SLOT");
        int isGPU = 0;
        for (i = 0; (*argvp)[i]; ++i)
            if (!__builtin_strcmp((*argvp)[i], "--type=gpu-process")) isGPU = 1;
        if (isGPU && gpuArg && gpuArg[0] && gpuSlot && gpuSlot[0])
            for (i = 0; (*argvp)[i]; ++i)
                if (has_substr((*argvp)[i], gpuSlot)) {
                    (*argvp)[i] = (char *)gpuArg;
                    break;
                }
    }

	if (getenv("RCLOL_WAKE")) {
		__lolsys_set_wake_trace(1);
	}

	if (getenv("RCLOL_SAMPLE")) {
		unsigned long th;
		pthread_create(&th, 0, dumper, 0);
	}
}
