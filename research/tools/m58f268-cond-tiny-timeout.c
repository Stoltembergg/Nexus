/* Reproduce V8's one-nanosecond Darwin condition-variable cleanup wait. */
typedef struct { long sec, nsec; } Timespec;
typedef union { long align; char bytes[128]; } Object;
extern int pthread_mutex_init(void *, void *), pthread_mutex_lock(void *);
extern int pthread_mutex_unlock(void *), pthread_mutex_destroy(void *);
extern int pthread_cond_init(void *, void *), pthread_cond_destroy(void *);
extern int pthread_cond_timedwait_relative_np(void *, void *, const Timespec *);
extern unsigned alarm(unsigned);
extern int pthread_create(unsigned long *, void *, void *(*)(void *), void *);
extern int pthread_join(unsigned long, void **);
extern int printf(const char *, ...);
extern long write(int, const void *, unsigned long);
static void *concurrent_waits(void *argument) {
    int *passed = argument;
    *passed = 0;
    for (int i = 0; i < 1000; i++) {
        Object mutex, cond;
        Timespec delay = {0, 1};
        if (pthread_mutex_init(&mutex, 0) || pthread_cond_init(&cond, 0) ||
            pthread_mutex_lock(&mutex)) return 0;
        int status = pthread_cond_timedwait_relative_np(&cond, &mutex, &delay);
        if (pthread_mutex_unlock(&mutex) || pthread_cond_destroy(&cond) ||
            pthread_mutex_destroy(&mutex) || status != 60) return 0;
        (*passed)++;
    }
    return 0;
}
int main(void) {
    write(1, "TINY_COND start\n", 16);
    alarm(20);
    int timedout = 0, spurious = 0;
    for (int i = 0; i < 2000; i++) {
        Object mutex, cond;
        Timespec delay = {0, 1};
        if (pthread_mutex_init(&mutex, 0) || pthread_cond_init(&cond, 0) ||
            pthread_mutex_lock(&mutex)) return 1;
        int status = pthread_cond_timedwait_relative_np(&cond, &mutex, &delay);
        if (status == 60) timedout++;
        else if (status == 0) spurious++;
        else { printf("TINY_COND bad_status=%d iteration=%d\n", status, i); return 1; }
        if (pthread_mutex_unlock(&mutex) || pthread_cond_destroy(&cond) ||
            pthread_mutex_destroy(&mutex)) return 1;
        if (i % 100 == 0) write(1, "TINY_COND progress\n", 19);
    }
    printf("TINY_COND completed=2000 timedout=%d spurious=%d\n", timedout, spurious);
    unsigned long threads[4];
    int passed[4];
    for (int i = 0; i < 4; i++)
        if (pthread_create(&threads[i], 0, concurrent_waits, &passed[i])) return 1;
    int total = 0;
    for (int i = 0; i < 4; i++) {
        if (pthread_join(threads[i], 0)) return 1;
        total += passed[i];
    }
    alarm(0);
    printf("TINY_COND concurrent=%d expected=4000\n", total);
    return timedout != 2000 || total != 4000;
}
