/* darling-lol M58h2: cross-thread heap visibility through a dispatch-fired
 * callback — the M58b "separate memory view" test.
 * Chromium's mojo::Wait trap-notification thread writes TriggerContext's
 * heap fields; the waiting thread reads them. If Darling's callback firing
 * context writes land in a separate memory view (M58b round 7), the waiter
 * sees stale data -> wait_result_ stays UNKNOWN -> B1.
 * PASS: the dispatch-thread write is visible from main (1337), then the
 *       pthread control write (42) is also visible.
 */
typedef unsigned int u32;

extern int printf(const char *, ...);
extern int fflush(void *);
extern unsigned int sleep(unsigned int);
extern int pthread_create(unsigned long *, const void *, void *(*)(void *), void *);
extern int pthread_join(unsigned long, void **);
extern void *dispatch_get_global_queue(long, unsigned long);
extern void dispatch_async_f(void *, void *, void (*)(void *));

static volatile long shared_state;   /* 0 init, 42 pthread, 1337 dispatch */
static volatile int pthread_done;
static volatile int dispatch_done;

static void *pthread_writer(void *arg) {
	(void)arg;
	shared_state = 42;
	pthread_done = 1;
	return 0;
}

static void dispatch_writer(void *ctx) {
	(void)ctx;
	shared_state = 1337;
	dispatch_done = 1;
}

int main(void) {
	unsigned long th;
	void *gq;
	printf("M58H2 start\n"); fflush(0);

	/* control: pthread writer visible from main */
	shared_state = 0;
	pthread_done = 0;
	pthread_create(&th, (void *)0, pthread_writer, (void *)0);
	sleep(2);
	printf("control: done=%d state=%ld (want 42)\n", pthread_done, shared_state);
	fflush(0);

	/* dispatch-fired write (async, global queue): main reads */
	shared_state = 0;
	dispatch_done = 0;
	gq = dispatch_get_global_queue(0, 0);
	printf("gq=%p\n", (void *)gq); fflush(0);
	if (gq) dispatch_async_f(gq, (void *)0, dispatch_writer);
	for (int i = 0; i < 6 && !dispatch_done; ++i) sleep(1);
	printf("after dispatch: dispatch_done=%d state=%ld (want 1337)\n",
		dispatch_done, shared_state);
	fflush(0);

	printf("VERDICT: %s\n", dispatch_done ? "CLEAN(shared view)" : "STUCK(dispatch cb never ran/visible)");
	fflush(0);
	return 0;
}
