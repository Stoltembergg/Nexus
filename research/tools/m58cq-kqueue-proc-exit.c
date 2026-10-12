/* darling-lol M58cq: does EVFILT_PROC/NOTE_EXIT fire when a child exits?
 * Chromium's ChildProcessLauncher uses a ProcessWatcher; on macOS child exit
 * is observed via kqueue EVFILT_PROC/NOTE_EXIT. If that never fires, the
 * browser can never notice a dead network service (no reap, no restart).
 */
typedef unsigned int u32;
typedef unsigned short u16;

struct kevent_s {
	unsigned long ident;
	short filter;
	u16 flags;
	u32 fflags;
	long data;
	void *udata;
};
struct ts { long sec, nsec; };

extern int printf(const char *, ...);
extern int fflush(void *);
extern int kqueue(void);
extern int kevent(int, const struct kevent_s *, int, struct kevent_s *, int, const struct ts *);
extern int fork(void);
extern void _exit(int);
extern int waitpid(int, int *, int);
extern int getpid(void);
extern int usleep(unsigned int);

#define EVFILT_PROC (-5)
#define EV_ADD 0x0001
#define NOTE_EXIT 0x80000000u
#define WNOHANG 0x00000001

static void scenario(const char *name, int delay_exit_ms, int delay_add_ms) {
	int kq = kqueue();
	int child = fork();
	struct kevent_s ch, ev;
	struct ts t;
	int r, n, w, st = 0;

	if (child == 0) { if (delay_exit_ms) usleep(delay_exit_ms * 1000); _exit(0); }
	if (delay_add_ms) usleep(delay_add_ms * 1000);

	ch.ident = (unsigned long) child; ch.filter = EVFILT_PROC; ch.flags = EV_ADD;
	ch.fflags = NOTE_EXIT; ch.data = 0; ch.udata = 0;
	r = kevent(kq, &ch, 1, 0, 0, 0);

	t.sec = 3; t.nsec = 0;
	n = kevent(kq, 0, 0, &ev, 1, &t);

	st = 0;
	w = waitpid(child, &st, 0);

	printf("KQPROC %-20s kq=%d child=%d add=%d wait_n=%d fflags=0x%lx waitpid=%d status=%d\n",
	    name, kq, child, r, n, (n > 0) ? (unsigned long) ev.fflags : 0UL, w, st);
	fflush(0);
}

int main(void) {
	printf("KQPROC start pid=%d\n", getpid()); fflush(0);
	scenario("watch-then-exit", 300, 0);     /* normal case: watch first */
	scenario("exit-then-watch", 50, 300);    /* child already dead when added */
	scenario("exit-immediately", 0, 0);      /* child exits at once */
	return 0;
}
