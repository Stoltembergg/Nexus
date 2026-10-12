/* darling-lol M58az: cost of a cancelation-point syscall.
 *
 * M58ay found the browser main thread does ~2900 dserver RPC round-trips per
 * second, one per cancelable syscall/libcall (`CANCELATION_POINT()` ->
 * dserver_callnum_pthread_canceled). This measures the per-call cost by
 * timing N iterations of syscalls that do vs. don't hit that RPC.
 *
 * A large gap between the two is the evidence that cancelation points are
 * expensive (a dserver socket round-trip each), starving the event loop.
 */
typedef unsigned long u64;

extern int printf(const char *, ...);
extern int fflush(void *);
extern int open(const char *, int, ...);
extern long read(int, void *, unsigned long);
extern int close(int);
extern int getpid(void);
extern unsigned long long mach_absolute_time(void);

#define O_RDONLY 0

static u64 now_ns(void) { return mach_absolute_time(); }

static void bench(const char *label, int iters, int fd) {
	u64 t0, t1;
	int i;
	char b[1];
	volatile long sink = 0;

	t0 = now_ns();
	for (i = 0; i < iters; ++i)
		sink += read(fd, b, 0);   /* read() carries CANCELATION_POINT() */
	t1 = now_ns();
	printf("  %-24s %7d iters  %.3f us/call\n", label, iters,
	    (double) (t1 - t0) / 1000.0 / iters);
	fflush(0);

	t0 = now_ns();
	for (i = 0; i < iters; ++i)
		sink += getpid();          /* no cancelation point */
	t1 = now_ns();
	printf("  %-24s %7d iters  %.3f us/call\n", "getpid", iters,
	    (double) (t1 - t0) / 1000.0 / iters);
	fflush(0);
	(void) sink;
}

int main(void) {
	int fd;
	printf("M58AZ cancelation-point cost\n"); fflush(0);
	fd = open("/dev/null", O_RDONLY, 0);
	if (fd < 0) { printf("  open(/dev/null) failed\n"); fflush(0); return 1; }
	bench("read(/dev/null,0)", 20000, fd);
	close(fd);
	printf("M58AZ done\n"); fflush(0);
	return 0;
}
