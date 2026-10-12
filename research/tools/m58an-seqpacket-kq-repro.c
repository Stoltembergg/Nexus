/* darling-lol M58an: kevent readiness on a SOCK_SEQPACKET socketpair.
 *
 * M58am found the renderer's kqchan (an AF_UNIX, SOCK_SEQPACKET socketpair)
 * has a 12-byte message queued (Recv-Q=12) yet the client's
 * evfilt_machport_copyout() never runs -> its epoll-backed kevent
 * registration never reports the fd readable. This repro tests that in
 * isolation: create a socketpair (STREAM / DGRAM / SEQPACKET), register one
 * end with kqueue EVFILT_READ, write from the other end, and see whether
 * kevent reports it readable.
 *
 * PASS: kevent fires (readable). BUG: it never fires despite queued data.
 */
typedef unsigned short u16;
typedef unsigned int u32;

struct ts { long sec; long nsec; };
struct kevent_s {
	unsigned long ident;
	short filter;
	u16 flags;
	u32 fflags;
	long data;
	void *udata;
};

extern int printf(const char *, ...);
extern int fflush(void *);
extern int socketpair(int, int, int, int *);
extern int socket(int, int, int);
extern int write(int, const void *, unsigned long);
extern int read(int, void *, unsigned long);
extern int kqueue(void);
extern int kevent(int, const void *, int, void *, int, const void *);
extern int fcntl(int, int, int);
extern int fork(void);
extern int usleep(unsigned int);
extern void _exit(int);
extern int waitpid(int, int *, int);
extern unsigned long long mach_absolute_time(void);

#define AF_UNIX 1
#define SOCK_STREAM 1
#define SOCK_DGRAM 2
#define SOCK_SEQPACKET 5
#define EVFILT_READ (-1)
#define EV_ADD 0x0001u
#define F_GETFL 3
#define F_SETFL 4
#define F_DUPFD_CLOEXEC 67
#define O_NONBLOCK 0x0004

static void test(int type, const char *label) {
	int sv[2], kq, n, r;
	char buf[64];
	struct kevent_s ch, ev;
	struct ts tmo;

	if (socketpair(AF_UNIX, type, 0, sv) != 0) {
		printf("  %-22s socketpair failed\n", label); fflush(0); return;
	}
	kq = kqueue();
	__builtin_memset(&ch, 0, sizeof(ch));
	ch.ident = (unsigned long) sv[0];
	ch.filter = EVFILT_READ;
	ch.flags = EV_ADD;
	if (kevent(kq, &ch, 1, (void *) 0, 0, (void *) 0) != 0) {
		printf("  %-22s register failed\n", label); fflush(0); return;
	}

	/* peer writes 12 bytes (the kqchan notification size) */
	n = (int) write(sv[1], "ABCDEFGHIJKL", 12);

	__builtin_memset(&ev, 0, sizeof(ev));
	tmo.sec = 2; tmo.nsec = 0;
	r = kevent(kq, (const void *) 0, 0, &ev, 1, &tmo);
	if (r == 1) {
		long got = read(sv[0], buf, sizeof(buf));
		printf("  %-22s wrote=%d FIRED data=%ld (readable)\n", label, n, ev.data); fflush(0);
		(void) got;
	} else {
		printf("  %-22s wrote=%d NOT-FIRED r=%d (BUG)\n", label, n, r); fflush(0);
	}
}

static void test_dup(int type, const char *label) {
	int sv[2], kq, n, r, d;
	struct kevent_s ch, ev;
	struct ts tmo;

	if (socketpair(AF_UNIX, type, 0, sv) != 0) { printf("  %-22s socketpair failed\n", label); fflush(0); return; }
	d = fcntl(sv[0], F_DUPFD_CLOEXEC, 0);
	if (d < 0) { printf("  %-22s dup failed\n", label); fflush(0); return; }
	kq = kqueue();
	__builtin_memset(&ch, 0, sizeof(ch));
	ch.ident = (unsigned long) d;
	ch.filter = EVFILT_READ; ch.flags = EV_ADD;
	kevent(kq, &ch, 1, (void *) 0, 0, (void *) 0);
	n = (int) write(sv[1], "ABCDEFGHIJKL", 12);
	__builtin_memset(&ev, 0, sizeof(ev));
	tmo.sec = 2; tmo.nsec = 0;
	r = kevent(kq, (const void *) 0, 0, &ev, 1, &tmo);
	printf("  %-22s wrote=%d %s r=%d\n", label, n, r == 1 ? "FIRED (readable)" : "NOT-FIRED (BUG)", r); fflush(0);
}

static void test_fork(int type, const char *label) {
	int sv[2], kq, r, pid, st;
	struct kevent_s ch, ev;
	struct ts tmo;

	if (socketpair(AF_UNIX, type, 0, sv) != 0) { printf("  %-22s socketpair failed\n", label); fflush(0); return; }
	pid = fork();
	if (pid == 0) {
		usleep(150000);
		write(sv[1], "ABCDEFGHIJKL", 12);
		_exit(0);
	}
	kq = kqueue();
	__builtin_memset(&ch, 0, sizeof(ch));
	ch.ident = (unsigned long) sv[0];
	ch.filter = EVFILT_READ; ch.flags = EV_ADD;
	kevent(kq, &ch, 1, (void *) 0, 0, (void *) 0);
	__builtin_memset(&ev, 0, sizeof(ev));
	tmo.sec = 2; tmo.nsec = 0;
	r = kevent(kq, (const void *) 0, 0, &ev, 1, &tmo);
	printf("  %-22s %s r=%d\n", label, r == 1 ? "FIRED (readable)" : "NOT-FIRED (BUG)", r); fflush(0);
	waitpid(pid, &st, 0);
}

static void test_twice(int type, const char *label) {
	int sv[2], kq, r, i;
	char buf[64];
	struct kevent_s ch, ev;
	struct ts tmo;

	if (socketpair(AF_UNIX, type, 0, sv) != 0) { printf("  %-22s socketpair failed\n", label); fflush(0); return; }
	kq = kqueue();
	__builtin_memset(&ch, 0, sizeof(ch));
	ch.ident = (unsigned long) sv[0];
	ch.filter = EVFILT_READ; ch.flags = EV_ADD;
	kevent(kq, &ch, 1, (void *) 0, 0, (void *) 0);
	for (i = 1; i <= 3; ++i) {
		write(sv[1], "ABCDEFGHIJKL", 12);
		__builtin_memset(&ev, 0, sizeof(ev));
		tmo.sec = 2; tmo.nsec = 0;
		r = kevent(kq, (const void *) 0, 0, &ev, 1, &tmo);
		printf("  %-22s round %d: %s r=%d\n", label, i,
		    r == 1 ? "FIRED" : "NOT-FIRED (BUG)", r); fflush(0);
		if (r == 1) read(sv[0], buf, sizeof(buf));
	}
}

int main(void) {
	printf("M58AN seqpacket kevent readability\n"); fflush(0);
	test(SOCK_STREAM, "STREAM");
	test(SOCK_DGRAM, "DGRAM");
	test(SOCK_SEQPACKET, "SEQPACKET");
	test_dup(SOCK_SEQPACKET, "SEQPACKET+dup");
	test_fork(SOCK_SEQPACKET, "SEQPACKET+otherproc");
	test_fork(SOCK_STREAM, "STREAM+otherproc");
	test_twice(SOCK_STREAM, "twice STREAM");
	test_twice(SOCK_SEQPACKET, "twice SEQPACKET");
	printf("M58AN done\n"); fflush(0);
	return 0;
}
