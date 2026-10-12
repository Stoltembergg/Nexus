/* darling-lol M58f3: psynch_cvwait absolute-time overflow repro (headerless) */
struct ts { long sec; long nsec; };
struct tv { long sec; int usec; int pad; };

extern int printf(const char *, ...);
extern int fflush(void *);
extern unsigned int sleep(unsigned int);
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

struct test {
	double add_sec;
	double signal_after;
	const char *name;
	int rc;
	double elapsed;
};

static void *waiter(void *arg) {
	struct test *t = (struct test *)arg;
	struct ts dl;
	struct tv tv;
	double begin;
	int rc;

	gettimeofday(&tv, (void *)0);
	dl.sec = tv.sec + (long)t->add_sec;
	dl.nsec = tv.usec * 1000;

	begin = now_s();
	pthread_mutex_lock((void *)mx);
	rc = pthread_cond_timedwait((void *)cv, (void *)mx, &dl);
	pthread_mutex_unlock((void *)mx);
	t->rc = rc;
	t->elapsed = now_s() - begin;
	printf("[%s] rc=%d (%s) elapsed=%.2fs\n", t->name, rc,
		rc == 141 ? "ETIMEDOUT" : (rc == 0 ? "OK" : "other"),
		t->elapsed);
	fflush(0);
	return 0;
}

int main(void) {
	/* ETIMEDOUT on darwin == 45 */
	struct test A = { 9200000000000.0, 3.0, (const char *)"A-Max", -1, -1 };
	struct test B = { 3600.0,          2.0, (const char *)"B-1h",  -1, -1 };
	struct test C = { 2.0,             0.0, (const char *)"C-2s",   -1, -1 };
	unsigned long ta, tb, tc;

	printf("M58F3 start\n"); fflush(0);

	pthread_mutex_init((void *)mx, (void *)0);
	pthread_cond_init((void *)cv, (void *)0);

	pthread_create(&ta, (void *)0, waiter, &A);
	sleep(3);
	pthread_mutex_lock((void *)mx); pthread_cond_signal((void *)cv); pthread_mutex_unlock((void *)mx);
	pthread_join(ta, (void *)0);

	pthread_create(&tb, (void *)0, waiter, &B);
	sleep(2);
	pthread_mutex_lock((void *)mx); pthread_cond_signal((void *)cv); pthread_mutex_unlock((void *)mx);
	pthread_join(tb, (void *)0);

	pthread_create(&tc, (void *)0, waiter, &C);
	pthread_join(tc, (void *)0);

	printf("VERDICT: A %s; B %s; C %s\n",
		(A.rc == 45 && A.elapsed < 2.9) ? "BUG-early-timeout" : ((A.rc == 0) ? "ok" : "odd"),
		(B.rc == 0 && B.elapsed < 2.9) ? "ok" : "BUG",
		(C.rc == 45 && C.elapsed >= 1.8) ? "ok" : "BUG");
	fflush(0);
	return 0;
}
