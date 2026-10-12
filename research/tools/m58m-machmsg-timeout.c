/* darling-lol M58m: mach_msg receive TIMEOUT accuracy repro (headerless).
 *
 * The UX browser process's event loop runs one turn every 2-13 s while
 * kevent/poll/cond timeouts are accurate. Chromium's main-thread message
 * pump waits for port messages with mach_msg(MACH_RCV_MSG|MACH_RCV_TIMEOUT).
 * If Darling mishandles that timeout, the pump wakes late and every
 * timer/IO callback is delayed. This measures an empty-port receive.
 *
 * PASS: elapsed ~= requested. BUG: elapsed >> requested.
 */
typedef unsigned int u32;

extern int printf(const char *, ...);
extern int fflush(void *);
extern unsigned int mach_task_self_;
extern int mach_port_allocate(u32, int, u32 *);
extern int mach_msg(void *, u32, u32, u32, u32, u32, u32);
extern unsigned long long mach_absolute_time(void);

#define MACH_PORT_RIGHT_RECEIVE 1
#define MACH_RCV_MSG 2
#define MACH_RCV_TIMEOUT 0x100
#define MACH_RCV_INTERRUPT 0x400

struct mach_msg_header {
	u32 msgh_bits;
	u32 msgh_size;
	u32 msgh_remote_port;
	u32 msgh_local_port;
	u32 msgh_voucher_port;
	int msgh_id;
};

static unsigned long long now_ns(void) { return mach_absolute_time(); }

static void test(u32 ms) {
	u32 port = 0;
	char buf[512];
	unsigned long long a, b;
	int rc;
	__builtin_memset(buf, 0, sizeof(buf));
	mach_port_allocate(mach_task_self_, MACH_PORT_RIGHT_RECEIVE, &port);
	((struct mach_msg_header *) buf)->msgh_bits = 0;
	a = now_ns();
	rc = mach_msg(buf, MACH_RCV_MSG | MACH_RCV_TIMEOUT, 0, sizeof(buf),
	    port, ms, 0);
	b = now_ns();
	printf("  mach_msg timeout %5ums -> elapsed %8.1fms rc=0x%08x\n", ms,
	    (double) (b - a) / 1e6, (unsigned) rc);
	fflush(0);
}

int main(void) {
	printf("M58M machmsg-timeout start\n"); fflush(0);
	test(0);
	test(10);
	test(50);
	test(100);
	test(250);
	test(1000);
	printf("M58M machmsg-timeout done\n"); fflush(0);
	return 0;
}
