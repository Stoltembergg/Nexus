/* darling-lol M58g: mach Port/Signal/Receive matrix under Darling.
 * Vector table (Chromium waitable_event_mac.cc uses variant A exactly):
 *   A: mach_port_construct(MPO_INSERT_SEND_RIGHT|MPO_QLIMIT, qlimit=1)
 *   B: mach_port_construct(MPO_INSERT_SEND_RIGHT|MPO_QLIMIT, qlimit=5)
 *   C: mach_port_construct(MPO_INSERT_SEND_RIGHT)  (default qlimit)
 *   D: mach_port_allocate(RECEIVE) + insert(MAKE_SEND) (default)
 * Each iteration: waiter thread does MACH_RCV_MSG with a 8 s timeout;
 * main sleeps 1 s then Signal()s (empty COPY_SEND send with SEND_TIMEOUT).
 * Observed PASS: waiter wakes KERN_SUCCESS with the message, signal ok.
 */
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
struct mach_rcv_s {
	struct mach_hdr_s hdr;
	u32 trailer[2];    /* mach_msg_trailer_t: type + size (8 bytes min) */
	u32 pad;
};
struct port_opts_s {
	u32 flags;
	u16 qlimit;
	u16 pad;
	u64 reserved1;
	u64 reserved2;
};

extern int printf(const char *, ...);
extern int fflush(void *);
extern unsigned int sleep(unsigned int);
extern int pthread_create(unsigned long *, const void *, void *(*)(void *), void *);
extern int pthread_join(unsigned long, void **);
extern long mach_msg(struct mach_hdr_s *, u32, u32, u32, u32, u32, u32);
extern int mach_port_construct(u32, void *, u64, u32 *);
extern int mach_port_allocate(u32, u32, u32 *);
extern int mach_port_insert_right(u32, u32, u32, u32);
extern int mach_port_destroy(u32, u32);
extern unsigned int mach_task_self_;

#define KERN_SUCCESS            0
#define MACH_SEND_MSG           1u
#define MACH_RCV_MSG            2u
#define MACH_SEND_TIMEOUT       16u
#define MACH_RCV_TIMEOUT        0x100u
#define MACH_MSG_TIMEOUT_NONE   0u
#define MACH_MSG_TYPE_COPY_SEND 19u
#define MACH_MSG_TYPE_MAKE_SEND 20u
#define MACH_PORT_RIGHT_RECEIVE 1u
#define MACH_PORT_LIMITS_INFO   1u
#define MACH_RCV_TIMED_OUT      0x10004003u
#define MPO_QLIMIT              0x02u
#define MPO_INSERT_SEND_RIGHT   0x10u

static u32 ev_port;
static volatile int done_g;
static volatile long recv_kr;

static void *waiter(void *arg) {
	(void)arg;
	/* mach_msg_empty_rcv_t: header(24) + mach_msg_trailer_t(8) = 32 bytes,
	 * exactly like base/synchronization/waitable_event_mac.cc's
	 * sizeof(mach_msg_empty_rcv_t). */
	struct mach_rcv_s msg;
	__builtin_memset(&msg, 0, sizeof(msg));
	recv_kr = mach_msg(&msg.hdr, MACH_RCV_MSG, 0,
	                   sizeof(msg), ev_port, 0 /* MACH_MSG_TIMEOUT_NONE */, 0);
	done_g = 1;
	return 0;
}

static int do_signal(void) {
	struct mach_hdr_s m;
	__builtin_memset(&m, 0, sizeof(m));
	m.msgh_bits = 19; /* MACH_MSG_TYPE_COPY_SEND */
	m.msgh_size = sizeof(m);
	m.msgh_remote_port = ev_port;
	return (int) mach_msg(&m, MACH_SEND_MSG | MACH_SEND_TIMEOUT, sizeof(m), 0, 0, 0, 0);
}

static void run_variant(const char *name, int mode) {
	/* mode 0=A qlimit1, 1=B qlimit5, 2=C construct-default, 3=D alloc */
	int bad_signal = 0, no_wake = 0, good = 0, other = 0, i;
	unsigned long th;
	printf("VARIANT %s (mode %d)\n", name, mode); fflush(0);
	for (i = 0; i < 5; ++i) {
		int kr, wkr;
		u32 name_port = 0;
		if (mode <= 2) {
			struct port_opts_s po;
			__builtin_memset(&po, 0, sizeof(po));
			po.flags = MPO_INSERT_SEND_RIGHT | (mode < 2 ? MPO_QLIMIT : 0);
			po.qlimit = (mode == 0) ? 1 : 5;
			kr = (int) mach_port_construct(mach_task_self_, (void *)&po, 0, &name_port);
			if (kr != 0) { printf("  iter %d construct kr=%d\n", i, kr); fflush(0); ++other; continue; }
		} else {
			kr = (int) mach_port_allocate(mach_task_self_, MACH_PORT_RIGHT_RECEIVE, &name_port);
			if (kr != 0) { printf("  iter %d alloc kr=%d\n", i, kr); fflush(0); ++other; continue; }
			kr = (int) mach_port_insert_right(mach_task_self_, name_port, name_port, MACH_MSG_TYPE_MAKE_SEND);
			if (kr != 0) { printf("  iter %d insert kr=%d\n", i, kr); fflush(0); ++other; continue; }
		}
		ev_port = name_port;
		done_g = 0;
		pthread_create(&th, (void *)0, waiter, (void *)0);
		sleep(1);
		/* signal */
		{ int skr = do_signal();
		  if (skr != 0) { ++bad_signal; printf("  iter %d: SIGNAL FAILED kr=0x%x\n", i, (unsigned)skr); fflush(0); } }
		pthread_join(th, (void *)0);
		wkr = recv_kr;
		if (wkr == 0) ++good;
		else { /* no message received even though we signaled */
			++no_wake;
			printf("  iter %d: recv kr=0x%x (rc=%d done=%d)\n", i, (unsigned)wkr, bad_signal, done_g);
			fflush(0);
		}
		if (mode == 3) mach_port_destroy(mach_task_self_, name_port);
	}
	printf("=> %s: good=%d bad_signal=%d no_wake=%d other=%d\n\n", name, good, bad_signal, no_wake, other);
	fflush(0);
}

static void gen_i(void) { }
int main(void) {
	printf("M58G-MACHMSG start\n"); fflush(0);
	run_variant("A construct qlimit=1", 0);
	run_variant("B construct qlimit=5", 1);
	run_variant("C construct default", 2);
	run_variant("D allocate+insert", 3);
	printf("DONE\n"); fflush(0);
	return 0;
}
