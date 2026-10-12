/* darling-lol M58F163: validate the SIGPROF/ucontext RIP sampling used to
 * attribute the UX browser main thread's CPU (Mach thread_get_state returns
 * zeros; CDP profiling times out).  Headerless guest C.
 *
 * Build: same recipe as m58m-sock-latency.c (see patches/m58f3-... .patch).
 */
typedef unsigned long size_t;
typedef unsigned int u32;
typedef unsigned long long u64;
typedef long long i64;

extern int printf(const char*, ...);
extern int usleep(unsigned int);
extern int getpid(void);
extern void exit(int);
extern int close(int);
struct tv { long s; long us; };
extern int gettimeofday(struct tv*, void*);
extern long write(int, const void*, unsigned long);

/* sigaction (Darwin, __DARWIN_UNIX03 layout) */
struct dart_sigaction { void (*handler)(int, void*, void*); u32 sa_mask; int sa_flags; };
extern int sigaction(int, const struct dart_sigaction*, struct dart_sigaction*);
struct dart_itimerval { struct tv it_interval; struct tv it_value; };
extern int setitimer(int, const struct dart_itimerval*, struct dart_itimerval*);

#define SIGPROF_ 27
#define SA_SIGINFO 0x0040
#define ITIMER_PROF 2

static volatile u64 g_rip[4096];
static volatile int g_n;
static volatile int g_bad;

static void handler(int sig, void* info, void* uc)
{
	u64* mc;
	if (g_n >= 4096) return;
	if (!uc) { g_bad = 1; return; }
	mc = *(u64**)((char*)uc + 48);      /* uc_mcontext */
	if (!mc) { g_bad = 2; return; }
	g_rip[g_n++] = mc[18];              /* mcontext + 144 = __rip */
}

static void spin(void)
{
	volatile u64 x = 1;
	u64 i;
	for (i = 0; i < 60000000ULL; i++) x = x * 6364136223846793005ULL + 1;
}

int main(void)
{
	struct dart_sigaction sa;
	struct dart_itimerval it;
	int i;
	printf("M58F163 sigprof test pid=%d main=%p\n", getpid(), (void*)&main);
	sa.handler = handler; sa.sa_mask = 0; sa.sa_flags = SA_SIGINFO;
	if (sigaction(SIGPROF_, &sa, 0) != 0) { printf("sigaction failed\n"); return 1; }
	it.it_interval.s = 0; it.it_interval.us = 2000;
	it.it_value.s = 0; it.it_value.us = 2000;
	if (setitimer(ITIMER_PROF, &it, 0) != 0) { printf("setitimer failed\n"); return 1; }
	spin();
	spin();
	/* stop */
	it.it_interval.s = 0; it.it_interval.us = 0; it.it_value.s = 0; it.it_value.us = 0;
	setitimer(ITIMER_PROF, &it, 0);
	printf("M58F163 samples=%d bad=%d\n", g_n, g_bad);
	for (i = 0; i < g_n && i < 8; i++) printf("  RIP %p\n", (void*)g_rip[i]);
	return 0;
}
