/* darling-lol M58f3: looped psynch_cvwait overflow repro.
 * 12 iterations: each spawns a waiter with a TimeDelta::Max-shaped deadline
 * (now + 9.2e12 s) on a FRESH cond/mutex pair, sleeps 150 ms, and checks
 * whether the waiter already returned (correct: still waiting). Then signals.
 * Any early return = the overflow bit us (B1 mechanism).
 * Then 5x the C-case on fresh conds: 2 s timeout must return 45 (ETIMEDOUT),
 * never 0 — return-code mapping check.
 */
struct ts { long sec; long nsec; };
struct tv { long sec; int usec; int pad; };

extern int printf(const char *, ...);
extern int fflush(void *);
extern unsigned int sleep(unsigned int);
extern int usleep(unsigned int);
extern int gettimeofday(struct tv *, void *);
extern int pthread_mutex_init(void *, const void *);
extern int pthread_cond_init(void *, const void *);
extern int pthread_mutex_lock(void *);
extern int pthread_mutex_unlock(void *);
extern int pthread_cond_signal(void *);
extern int pthread_cond_timedwait(void *, void *, const struct ts *);
extern int pthread_create(unsigned long *, const void *, void *(*)(void *), void *);
extern int pthread_join(unsigned long, void **);

__attribute__((aligned(16))) static char mx[128];
__attribute__((aligned(16))) static char cv[128];

static double now_s(void) {
	struct tv tv;
	gettimeofday(&tv, (void *)0);
	return (double)tv.sec + (double)tv.usec / 1e6;
}

static volatile int done;
static int last_rc;

static void *waiter(void *arg) {
	struct ts dl;
	struct tv tv;
	double begin;
	int rc;
	(void)arg;

	gettimeofday(&tv, (void *)0);
	dl.sec = tv.sec + 9200000000000L;
	dl.nsec = tv.usec * 1000;

	begin = now_s();
	pthread_mutex_lock((void *)mx);
	rc = pthread_cond_timedwait((void *)cv, (void *)mx, &dl);
	pthread_mutex_unlock((void *)mx);
	last_rc = rc;
	done = 1;
	(void)begin;
	return 0;
}

static void *timeout_waiter(void *arg) {
	struct ts dl;
	struct tv tv;
	int rc;
	(void)arg;

	gettimeofday(&tv, (void *)0);
	dl.sec = tv.sec + 2;
	dl.nsec = tv.usec * 1000;

	pthread_mutex_lock((void *)mx);
	rc = pthread_cond_timedwait((void *)cv, (void *)mx, &dl);
	pthread_mutex_unlock((void *)mx);
	last_rc = rc;
	done = 1;
	return 0;
}

int main(void) {
	unsigned long th;
	int i, early = 0, rc0_expiry = 0;

	printf("M58F3LOOP start\n"); fflush(0);

	for (i = 0; i < 12; ++i) {
		done = 0;
		pthread_mutex_init((void *)mx, (void *)0);
		pthread_cond_init((void *)cv, (void *)0);
		pthread_create(&th, (void *)0, waiter, (void *)0);
		usleep(150000);
		if (done) {
			++early;
			printf("  iter %d: EARLY return rc=%d\n", i, last_rc);
			fflush(0);
		}
		pthread_mutex_lock((void *)mx);
		pthread_cond_signal((void *)cv);
		pthread_mutex_unlock((void *)mx);
		pthread_join(th, (void *)0);
	}
	printf("EARLY-COUNT: %d / 12\n", early); fflush(0);

	for (i = 0; i < 5; ++i) {
		done = 0;
		pthread_mutex_init((void *)mx, (void *)0);
		pthread_cond_init((void *)cv, (void *)0);
		pthread_create(&th, (void *)0, timeout_waiter, (void *)0);
		while (!done) sleep(1);
		pthread_join(th, (void *)0);
		if (last_rc == 0) { ++rc0_expiry; printf("  expiry %d: rc=0 (should be 45)\n", i); fflush(0); }
	}
	printf("RC0-EXPIRY-COUNT: %d / 5\n", rc0_expiry); fflush(0);
	printf("VERDICT: %s\n", (early || rc0_expiry) ? "BUGGY" : "CLEAN");
	fflush(0);
	return 0;
}
