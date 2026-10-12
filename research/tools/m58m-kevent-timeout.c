/* darling-lol M58m: kevent TIMEOUT accuracy repro (headerless).
 *
 * The UX browser process's event loop runs timers seconds late
 * (setTimeout(100) fired at 7563 ms). Chromium's message pump drives its
 * timers through kevent(kq, ..., &timeout); if Darling mishandles the
 * timeout, every timer/I/O wake is delayed. This measures the actual
 * elapsed time for kevent with an idle kqueue and a given timeout, and
 * compares with poll().
 *
 * PASS: elapsed ~= requested. BUG: elapsed >> requested (e.g. 100ms -> 7s).
 */
typedef long long i64;

extern int printf(const char *, ...);
extern int fflush(void *);
extern int kqueue(void);
extern int kevent(int, const void *, int, void *, int, const void *);
extern int poll(void *, unsigned long, int);
extern unsigned long long mach_absolute_time(void);

struct ts { long sec; long nsec; };
struct kevent_s {
	unsigned long ident;
	short filter;
	unsigned short flags;
	unsigned int fflags;
	long data;
	void *udata;
};
struct pollfd { int fd; short events; short revents; };

static i64 now_ns(void) { return (i64) mach_absolute_time(); }

static void kev_test(long ms) {
	int kq = kqueue();
	struct ts t;
	struct kevent_s ev;
	i64 a, b;
	__builtin_memset(&ev, 0, sizeof(ev));
	t.sec = ms / 1000;
	t.nsec = (ms % 1000) * 1000000L;
	a = now_ns();
	kevent(kq, (const void *) 0, 0, &ev, 1, &t);
	b = now_ns();
	printf("  kevent  timeout %5ldms -> elapsed %8.1fms\n", ms, (double) (b - a) / 1e6);
	fflush(0);
}

static void poll_test(int ms) {
	struct pollfd p;
	i64 a, b;
	p.fd = -1; p.events = 0; p.revents = 0;
	a = now_ns();
	poll(&p, 0, ms);
	b = now_ns();
	printf("  poll    timeout %5dms -> elapsed %8.1fms\n", ms, (double) (b - a) / 1e6);
	fflush(0);
}

int main(void) {
	printf("M58M kevent-timeout start\n"); fflush(0);
	kev_test(0);
	kev_test(10);
	kev_test(50);
	kev_test(100);
	kev_test(250);
	kev_test(1000);
	poll_test(10);
	poll_test(100);
	poll_test(1000);
	printf("M58M kevent-timeout done\n"); fflush(0);
	return 0;
}
