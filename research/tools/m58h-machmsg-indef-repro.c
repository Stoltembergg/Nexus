/* darling-lol M58h: indefinite mach_msg receive — does it stay blocked?
 * waitable_event_mac.cc's Wait() is TimedWait(Max) →
 * mach_msg(MACH_RCV_MSG | timeout=MACH_MSG_TIMEOUT_NONE) — indefinite.
 * B1 (mojo::Wait returns UNKNOWN) fires ~105-120 s into the UX, which
 * matches an indefinite receive returning MACH_RCV_TIMED_OUT spuriously
 * after ~100 s. This repro: ONE indefinite receive held for 420 s with
 * NO signal; PASS = still blocked at the end; FAIL = woke early
 * (recv_kr printed: e.g. 0x10004003 = MACH_RCV_TIMED_OUT). */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned long long u64;
struct mach_hdr_s {
	u32 msgh_bits;
	u32 msgh_size;
	u32 msgh_remote_port;
	u32 msgh_local_port;
	u32 msgh_voucher_port;
	u32 msgh_id;
};
struct port_opts_s {
	u32 flags;
	u16 qlimit;
	u16 pad;
	u64 reserved1;
	u64 reserved2;
};
struct mach_rcv_s {
	struct mach_hdr_s hdr;
	u32 trailer[2];
	u32 pad;
};

extern int printf(const char *, ...);
extern int fflush(void *);
extern unsigned int sleep(unsigned int);
extern int pthread_create(unsigned long *, const void *, void *(*)(void *), void *);
extern int pthread_join(unsigned long, void **);
extern long mach_msg(struct mach_hdr_s *, u32, u32, u32, u32, u32, u32);
extern int mach_port_construct(u32, void *, u64, u32 *);
extern int mach_port_destroy(u32, u32);
extern unsigned int mach_task_self_;
extern int gettimeofday(unsigned long long *, unsigned int*);

static u32 ev_port;
static volatile int done_g;
static volatile long recv_kr;
static volatile unsigned long long wake_time_s, start_time_s;

static void *waiter(void *arg) {
	(void)arg;
	struct mach_rcv_s msg;
	__builtin_memset(&msg, 0, sizeof(msg));
	recv_kr = mach_msg(&msg.hdr, 2u /* MACH_RCV_MSG */, 0,
	                   sizeof(msg), ev_port, 0, 0);
	done_g = 1;
	return 0;
}

int main(void) {
	struct port_opts_s po;
	u32 name = 0;
	unsigned long th;
	int kr, i;
	unsigned long long tv[2];
	void *oops = (void *)&tv; (void)oops;
	/* gettimeofday-less clock: use sleep-loop timing */
	printf("M58H indefinite-machmsg start (hold 420s)\n"); fflush(0);

	__builtin_memset(&po, 0, sizeof(po));
	po.flags = 0x10u /* MPO_INSERT_SEND_RIGHT */ | 0x02u /* MPO_QLIMIT */;
	po.qlimit = 1;
	kr = (int) mach_port_construct(mach_task_self_, (void *)&po, 0, &name);
	printf("construct kr=%d\n", kr); fflush(0);
	ev_port = name;
	done_g = 0;

	/* mark the start time as "loop count 0" */
	for (i = 0; i < 420; ++i) {
		sleep(1);
		if (done_g) {
			printf("SPURIOUS at ~%d s: recv_kr=0x%x\n", i, (unsigned)recv_kr);
			fflush(0);
			break;
		}
	}
	if (!done_g) printf("STILL BLOCKED after 420 s (PASS)\n");
	fflush(0);

	/* cleanup signal so the thread can exit */
	{
		struct mach_hdr_s m;
		unsigned int skr;
		__builtin_memset(&m, 0, sizeof(m));
		m.msgh_bits = 19;
		m.msgh_size = sizeof(m);
		m.msgh_remote_port = ev_port;
		skr = 0;
		skr = (unsigned int) mach_msg(&m, 1u /*MACH_SEND_MSG*/, sizeof(m), 0, 0, 0, 0);
		printf("cleanup signal kr=%u\n", skr); fflush(0);
	}
	pthread_join(th, (void *)0);
	printf("recv_kr final=0x%x\n", (unsigned)recv_kr); fflush(0);
	printf("VERDICT: %s\n", done_g && i < 420 ? "BUGGY(spurious)" : "CLEAN");
	fflush(0);
	return 0;
}
