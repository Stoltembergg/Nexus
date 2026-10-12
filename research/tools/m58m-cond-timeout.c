/* darling-lol M58m: pthread_cond_timedwait EXPIRY accuracy repro (headerless).
 *
 * The UX browser process's event loop runs timers seconds late
 * (setTimeout(100) fired at 7563 ms) while kevent/poll timeouts are
 * accurate. Chromium's MessagePump can drive its delayed work through a
 * pthread_cond_timedwait, so this measures a pure-expiry timedwait (no
 * signal) for short timeouts, plus an already-expired deadline.
 *
 * PASS: elapsed ~= requested, rc == ETIMEDOUT.
 * BUG: elapsed >> requested (or an expired deadline that does not return).
 */
struct ts { long sec; long nsec; };
struct tv { long sec; int usec; int pad; };

extern int printf(const char *, ...);
extern int fflush(void *);
extern int gettimeofday(struct tv *, void *);
extern int pthread_mutex_init(void *, const void *);
extern int pthread_cond_init(void *, const void *);
extern int pthread_mutex_lock(void *);
extern int pthread_mutex_unlock(void *);
extern int pthread_cond_timedwait(void *, void *, const struct ts *);
extern unsigned long long mach_absolute_time(void);

__attribute__((aligned(16))) static char mx[128];
__attribute__((aligned(16))) static char cv[128];

static double now_s(void) {
	struct tv tv;
	gettimeofday(&tv, (void *) 0);
	return (double) tv.sec + (double) tv.usec / 1e6;
}

static void test(long ms) {
	struct ts dl;
	struct tv tv;
	double begin;
	int rc;

	gettimeofday(&tv, (void *) 0);
	dl.sec = tv.sec + ms / 1000;
	dl.nsec = (long) tv.usec * 1000 + (ms % 1000) * 1000000L;
	while (dl.nsec >= 1000000000L) { dl.sec++; dl.nsec -= 1000000000L; }
	while (dl.nsec < 0) { dl.sec--; dl.nsec += 1000000000L; }

	begin = now_s();
	pthread_mutex_lock((void *) mx);
	rc = pthread_cond_timedwait((void *) cv, (void *) mx, &dl);
	pthread_mutex_unlock((void *) mx);
	printf("  timedwait %6ldms -> elapsed %8.1fms rc=%d\n", ms,
	    (now_s() - begin) * 1000.0, rc);
	fflush(0);
}

int main(void) {
	printf("M58M cond-timeout start\n"); fflush(0);
	pthread_mutex_init((void *) mx, (void *) 0);
	pthread_cond_init((void *) cv, (void *) 0);
	test(0);
	test(-5);      /* already expired: must return immediately */
	test(5);
	test(10);
	test(50);
	test(100);
	test(250);
	test(1000);
	printf("M58M cond-timeout done\n"); fflush(0);
	return 0;
}
