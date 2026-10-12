/* darling-lol M58m: guest loopback socket WAKEUP-LATENCY repro (headerless).
 *
 * M58m measured (via the Electron main process) that guest loopback I/O has
 * multi-second per-round-trip latency, far worse on IPv4 (~7-8 s) than IPv6
 * (~1-2 s), and that it is not Nagle. This repro measures the same defect
 * outside Chromium and isolates it:
 *
 *   - AF_UNIX socketpair blocking-read wakeup
 *   - AF_INET  127.0.0.1   blocking-read wakeup
 *   - AF_INET6 ::1         blocking-read wakeup
 *   - AF_INET  127.0.0.1   kevent(EVFILT_READ) wakeup
 *
 * Method per round: a reader thread blocks in read()/kevent() on one end;
 * the main thread sleeps 200 ms (so the reader is definitely parked), then
 * writes 1 byte on the other end and records the time. The reader stamps
 * the time when it returns. latency = reader_return - writer_write.
 *
 * PASS: latency is sub-millisecond (loopback). FAIL/BUG: multi-second.
 * Build: see docs/m58i-browser-fetch-stall.md (M58m) — same recipe as
 *        tools/m58i-kq-repro.c.
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef unsigned long usize;
typedef long long i64;

extern int printf(const char *, ...);
extern int fflush(void *);
extern int usleep(unsigned int);
extern int pthread_create(unsigned long *, const void *, void *(*)(void *), void *);
extern int pthread_join(unsigned long, void **);
extern int socket(int, int, int);
extern int socketpair(int, int, int, int *);
extern int bind(int, const void *, u32);
extern int listen(int, int);
extern int accept(int, void *, u32 *);
extern int connect(int, const void *, u32);
extern long read(int, void *, usize);
extern long write(int, const void *, usize);
extern int close(int);
extern int getsockname(int, void *, u32 *);
extern int kqueue(void);
extern int kevent(int, const void *, int, void *, int, const void *);
extern unsigned long long mach_absolute_time(void);

#define AF_UNIX 1
#define AF_INET 2
#define AF_INET6 30
#define SOCK_STREAM 1

struct sin { u8 len; u8 fam; u16 port; u32 addr; u32 z1, z2; };
struct sin6 { u8 len; u8 fam; u16 port; u32 flow; u8 addr[16]; u32 scope; };
struct kevent_s {
	usize ident;
	short filter;
	u16 flags;
	u32 fflags;
	long data;
	void *udata;
};

#define EVFILT_READ (-1)
#define EV_ADD 0x0001u

static volatile int g_ready;
static volatile i64 g_twrite;
static volatile i64 g_tread;
static volatile long g_nread;

static i64 now_ns(void) { return (i64) mach_absolute_time(); }

static void *blocking_reader(void *arg) {
	int fd = (int) (long) arg;
	char buf[64];
	g_ready = 1;
	g_nread = read(fd, buf, sizeof(buf));
	g_tread = now_ns();
	return (void *) 0;
}

static void *kevent_reader(void *arg) {
	int fd = (int) (long) arg;
	int kq;
	struct kevent_s ch, ev;
	__builtin_memset(&ch, 0, sizeof(ch));
	__builtin_memset(&ev, 0, sizeof(ev));
	kq = kqueue();
	ch.ident = (usize) fd;
	ch.filter = EVFILT_READ;
	ch.flags = EV_ADD;
	kevent(kq, &ch, 1, (void *) 0, 0, (void *) 0);
	g_ready = 1;
	g_nread = kevent(kq, (const void *) 0, 0, &ev, 1, (const void *) 0);
	g_tread = now_ns();
	return (void *) 0;
}

static void measure(int rfd, int wfd, const char *label, int use_kevent,
                    i64 *minlat, i64 *maxlat, i64 *sum, int rounds) {
	int i;
	*minlat = (i64) 1 << 62;
	*maxlat = 0;
	*sum = 0;
	for (i = 0; i < rounds; ++i) {
		unsigned long th;
		i64 lat;
		g_ready = 0; g_twrite = 0; g_tread = 0; g_nread = -1;
		pthread_create(&th, (void *) 0,
		    use_kevent ? kevent_reader : blocking_reader, (void *) (long) rfd);
		while (!g_ready)
			usleep(1000);
		usleep(200000);              /* make sure the reader is parked */
		g_twrite = now_ns();
		write(wfd, "x", 1);
		pthread_join(th, (void *) 0);
		lat = g_tread - g_twrite;
		if (lat < 0)
			lat = -1;
		if (lat < *minlat) *minlat = lat;
		if (lat > *maxlat) *maxlat = lat;
		*sum += lat;
	}
	printf("  %-26s read=%ld  min=%lldus avg=%lldus max=%lldus\n", label,
	    g_nread, *minlat / 1000, (*sum / rounds) / 1000, *maxlat / 1000);
	fflush(0);
}

static void tcp_test(int family, const char *label) {
	int lfd, cfd, afd;
	struct sin sa;
	struct sin6 sa6;
	u32 len;
	i64 mn, mx, sm;

	lfd = socket(family, SOCK_STREAM, 0);
	if (family == AF_INET) {
		__builtin_memset(&sa, 0, sizeof(sa));
		sa.len = 16; sa.fam = 2; sa.port = 0; sa.addr = 0x0100007fu;
		bind(lfd, (const void *) &sa, 16);
		len = 16;
		getsockname(lfd, (void *) &sa, &len);
	} else {
		__builtin_memset(&sa6, 0, sizeof(sa6));
		sa6.len = 28; sa6.fam = 30; sa6.port = 0; sa6.addr[15] = 1;
		bind(lfd, (const void *) &sa6, 28);
		len = 28;
		getsockname(lfd, (void *) &sa6, &len);
	}
	listen(lfd, 8);
	cfd = socket(family, SOCK_STREAM, 0);
	if (family == AF_INET)
		connect(cfd, (const void *) &sa, 16);
	else
		connect(cfd, (const void *) &sa6, 28);
	afd = accept(lfd, (void *) 0, (u32 *) 0);
	measure(afd, cfd, label, 0, &mn, &mx, &sm, 5);
	if (family == AF_INET) {
		/* kevent-driven wakeup on the same accepted socket */
		measure(afd, cfd, "v4 kevent(EVFILT_READ)", 1, &mn, &mx, &sm, 5);
	}
	close(cfd); close(afd); close(lfd);
}

int main(void) {
	int sv[2];
	i64 mn, mx, sm;

	printf("M58M socket wakeup-latency start\n"); fflush(0);

	if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv) != 0) {
		printf("socketpair failed\n"); fflush(0);
		return 1;
	}
	measure(sv[1], sv[0], "socketpair blocking read", 0, &mn, &mx, &sm, 5);
	measure(sv[1], sv[0], "socketpair kevent(EVFILT_READ)", 1, &mn, &mx, &sm, 5);
	close(sv[0]); close(sv[1]);

	tcp_test(AF_INET, "127.0.0.1 blocking read");
	tcp_test(AF_INET6, "::1 blocking read");

	printf("M58M done\n"); fflush(0);
	return 0;
}
