/* darling-lol M58m: CoreFoundation run-loop timeout / timer accuracy repro.
 *
 * The browser process's event loop turns are seconds apart while sync
 * syscalls are fast. Chromium's macOS browser pump is CoreFoundation
 * run-loop based (MessagePumpCFRunLoop), so this measures
 * CFRunLoopRunInMode's timeout and a CFRunLoopTimer's real fire time.
 *
 * PASS: elapsed ~= requested. BUG: elapsed >> requested.
 */
extern int printf(const char *, ...);
extern int fflush(void *);
extern void *CFRunLoopGetCurrent(void);
extern int CFRunLoopRunInMode(const void *mode, double seconds,
    unsigned char returnAfterSourceHandled);
extern double CFAbsoluteTimeGetCurrent(void);
extern void *CFRunLoopTimerCreate(void *allocator, double fireDate,
    double interval, unsigned long flags, long order, void *callout,
    void *context);
extern void CFRunLoopAddTimer(void *rl, void *timer, const void *mode);
extern const void *kCFRunLoopDefaultMode;

static double g_fire = -1.0;

static void callout(void *timer, void *info) {
	(void) timer; (void) info;
	g_fire = CFAbsoluteTimeGetCurrent();
}

static void runmode_test(double sec) {
	void *rl = CFRunLoopGetCurrent();
	double t0 = CFAbsoluteTimeGetCurrent();
	int r = CFRunLoopRunInMode(kCFRunLoopDefaultMode, sec, 0);
	double dt = CFAbsoluteTimeGetCurrent() - t0;
	printf("  CFRunLoopRunInMode(%.3fs) -> elapsed %8.3fs r=%d\n", sec, dt, r);
	fflush(0);
	(void) rl;
}

static void timer_test(double sec) {
	void *rl = CFRunLoopGetCurrent();
	void *t;
	double t0 = CFAbsoluteTimeGetCurrent();
	g_fire = -1.0;
	t = CFRunLoopTimerCreate((void *) 0, t0 + sec, 0.0, 0, 0,
	    (void *) callout, (void *) 0);
	CFRunLoopAddTimer(rl, t, kCFRunLoopDefaultMode);
	CFRunLoopRunInMode(kCFRunLoopDefaultMode, sec * 5.0 + 2.0, 0);
	printf("  CFRunLoopTimer(%.3fs) -> fired after %8.3fs (g_fire=%s)\n", sec,
	    g_fire < 0 ? -1.0 : g_fire - t0, g_fire < 0 ? "never" : "yes");
	fflush(0);
}

int main(void) {
	printf("M58M cfrunloop start\n"); fflush(0);
	runmode_test(0.1);
	runmode_test(0.5);
	runmode_test(1.0);
	timer_test(0.1);
	timer_test(0.5);
	printf("M58M cfrunloop done\n"); fflush(0);
	return 0;
}
