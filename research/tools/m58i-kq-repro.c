/* darling-lol M58i: kqueue-on-socket readability repro (headerless).
 * Mirrors the browser's read pattern (MessagePumpKqueue on loopback):
 *   listen -> kevent(EVFILT_READ) fires -> accept -> kevent on accepted
 *   fd -> reads progress to EOF while the client pushes data.
 * PASS: 100000 bytes received and EOF seen via kevent-driven reads.
 * FAIL: kevent never fires (stall exactly like the network service).
 * Constants/structs from xnu event.h (Darwin LP64 kevent = 32 bytes).
 */
typedef unsigned int u32;
typedef unsigned short u16;

struct kevent_s {
	unsigned long ident;
	short filter;
	unsigned short flags;
	unsigned int fflags;
	long data;
	void *udata;
};
struct ts { long sec, nsec; };

extern int printf(const char *, ...);
extern int fflush(void *);
extern int usleep(unsigned int);
extern int pthread_create(unsigned long *, const void *, void *(*)(void *), void *);
extern int pthread_join(unsigned long, void **);
extern int socket(int, int, int);
extern int bind(int, const void *, u32);
extern int listen(int, int);
extern int accept(int, void *, u32 *);
extern int connect(int, const void *, u32);
extern int send(int, const void *, u32, int);
extern int recv(int, void *, u32, int);
extern int shutdown(int, int);
extern int getsockname(int, void *, unsigned int *);
extern int kqueue(void);
extern int kevent(int, const struct kevent_s *, int, struct kevent_s *, int, const struct ts *);
extern int dladdr(void *, void *);
static int kevent_trace(int kqfd, const struct kevent_s *chlist, int nch,
    struct kevent_s *evs, int evn, const struct ts *tmo) {
	/* instrumented wrapper: sets a flag we never read — just to carry
	 * the same struct kevent_s signature; calls real kevent */
	return kevent(kqfd, chlist, nch, evs, evn, tmo);
}

#define AF_INET 2
#define SOCK_STREAM 1
#define EVFILT_READ (-1)
#define EV_ADD 0x0001u
#define EV_EOF 0x8000u
struct dlinfo_s {
	const char *dli_fname;
	void       *dli_fbase;
	const char *dli_sname;
	void       *dli_saddr;
};
extern int dladdr(void *, void *);
#define SHUT_WR 1

struct sin_s { unsigned char sin_len; unsigned char sin_family; u16 port_net; u32 addr_be; u32 z1, z2; };

static u16 be16(u32 port) { return (u16)(((port & 0xffu) << 8) | ((port >> 8) & 0xffu)); }

static u32 g_port;              /* bound port, normal order */
static u32 g_total_rx;
static int g_attfd = -1;
static volatile int g_eof;
static volatile u32 g_data_events;

static void *client_thread(void *arg) {
	struct sin_s sa;
	int fd, i;
	char buf[10240];
	(void)arg;
	__builtin_memset(&sa, 0, sizeof(sa));
	sa.sin_len = 16;
	sa.sin_family = 2;
	sa.port_net = be16(g_port);
	sa.addr_be = 0x0100007fu;
	fd = socket(AF_INET, SOCK_STREAM, 0);
	if (fd < 0) { printf("client socket failed\n"); fflush(0); return 0; }
	if (connect(fd, (const void *)&sa, sizeof(sa)) != 0) {
		printf("client connect failed\n"); fflush(0);
		return 0;
	}
	for (int i = 0; i < 10; ++i) {
		__builtin_memset(buf, 'A', sizeof(buf));
		int r = send(fd, buf, sizeof(buf), 0);
		if (r < 0) { printf("client send failed at total=%d\n", i * 10240); fflush(0); break; }
		usleep(50000);
	}
	shutdown(fd, SHUT_WR);
	while (recv(fd, buf, sizeof(buf), 0) > 0) {}
	fflush(0);
	return 0;
}

int main(void) {
	int listener, kq, attfd = -1, r, i, e, n;
	struct sin_s sa;
	struct kevent_s ch;
	struct kevent_s evs[8];
	struct ts tmo;
	unsigned long th;
	char rxBuf[4096];

	printf("M58I kqueue-socket start\n"); fflush(0);
	listener = socket(AF_INET, SOCK_STREAM, 0);
	printf("listener fd=%d\n", listener); fflush(0);
	__builtin_memset(&sa, 0, sizeof(sa));
	sa.sin_len = 16;
	sa.sin_family = 2;
	sa.port_net = be16(49700);
	sa.addr_be = 0x0100007fu;
	r = bind(listener, (const void *)&sa, 16);
	printf("bind rc=%d\n", r); fflush(0);
	{
		struct sin_s got;
		unsigned int len = 16;
		getsockname(listener, (void *)&got, (unsigned int *)&len);
		g_port = (u32)((got.port_net >> 8) | ((got.port_net & 0xffu) << 8));
	}
	listen(listener, 8);
	printf("listening on port %u\n", g_port); fflush(0);

	kq = kqueue();
	printf("kq=%d\n", kq); fflush(0);
	{
		/* M58i5: STDCALL image identity — dladdr on our own servant fns */
		void *kqfp  = (void *)kqueue;
		void *kfev  = (void *)kevent;
		struct dlinfo_s di;
		int ok;
		__builtin_memset(&di, 0, sizeof(di));
		ok = dladdr(kfev, (void *)&di);
		printf("dladdr(kevent) ok=%d fname=%s sname=%s saddr=%p\n", ok,
			di.dli_fname ? di.dli_fname : "(null)",
			di.dli_sname ? di.dli_sname : "(null)",
			di.dli_saddr);
		(void)ok; (void)kqfp;
	}
	{
		struct kevent_s ch;
		__builtin_memset(&ch, 0, sizeof(ch));
		ch.ident = (unsigned long)listener;
		ch.filter = EVFILT_READ;
		ch.flags = EV_ADD;
		int nr = kevent(kq, &ch, 1, (void *)0, 0, (void *)0);
		printf("register listener n=%d\n", nr); fflush(0);
	}
	{ /* client thread */
		if (pthread_create(&th, (void *)0, client_thread, (void *)0) != 0) {
			printf("client spawn failed\n"); fflush(0);
			return 1;
		}
	}
	/* event loop */
	for (i = 0; i < 60; ++i) {
		tmo.sec = 5; tmo.nsec = 0;
		int n = kevent(kq, (void *)0, 0, evs, 8, &tmo);
		if (n <= 0) {
			printf("kevent round %d: timeout n=%d total_rx=%u eof=%d\n", i, n, g_total_rx, g_eof);
			fflush(0);
			continue;
		}
		for (e = 0; e < n; ++e) {
			int fd = (int)evs[e].ident;
			if ((int)evs[e].filter != EVFILT_READ) continue;
			if (fd == listener && attfd < 0) {
				int afd = accept(listener, (void *)0, (u32 *)0);
				printf("accepted fd=%d data=%d\n", afd, (int)evs[e].data);
				fflush(0);
				g_attfd = afd; attfd = afd;
				{
					struct kevent_s ch2;
					__builtin_memset(&ch2, 0, sizeof(ch2));
					ch2.ident = (unsigned long)afd;
					ch2.filter = EVFILT_READ;
					ch2.flags = EV_ADD;
					kevent(kq, &ch2, 1, (void *)0, 0, (void *)0);
				}
			} else if (fd == attfd) {
				++g_data_events;
				int rr = recv(attfd, rxBuf, sizeof(rxBuf), 0);
				if (0 == rr) { g_eof = 1; printf("EOF seen total=%u\n", g_total_rx); fflush(0); }
				else if (rr < 0) { printf("recv error\n"); fflush(0); }
				else g_total_rx += rr;
			}
		}
		if (g_eof) break;
	}
	printf("RESULT: total_rx=%u data_events=%u eof=%d\n", g_total_rx, g_data_events, g_eof);
	fflush(0);
	printf("VERDICT: %s\n", (g_total_rx == 102400 && g_eof) ? "CLEAN" : "STALL");
	fflush(0);
	return g_eof ? 0 : 1;
}
