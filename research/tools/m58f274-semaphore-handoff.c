/* Exercise wakeups racing with Mach semaphore suspension. No application data. */
extern unsigned mach_task_self_;
extern int semaphore_create(unsigned, unsigned *, int, int);
extern int semaphore_wait(unsigned), semaphore_signal(unsigned);
extern int semaphore_destroy(unsigned, unsigned);
extern int pthread_create(unsigned long *, void *, void *(*)(void *), void *);
extern int pthread_join(unsigned long, void **);
extern unsigned alarm(unsigned);
extern int printf(const char *, ...);
typedef struct { unsigned ready, ack; int completed, failed; } Pair;
static void *consumer(void *arg) {
    Pair *p = arg;
    for (int i = 0; i < 5000; ++i) {
        if (semaphore_wait(p->ready) || semaphore_signal(p->ack)) {
            p->failed = 1; return 0;
        }
        ++p->completed;
    }
    return 0;
}
static void *producer(void *arg) {
    Pair *p = arg;
    for (int i = 0; i < 5000; ++i)
        if (semaphore_signal(p->ready) || semaphore_wait(p->ack)) {
            p->failed = 1; return 0;
        }
    return 0;
}
int main(void) {
    Pair pairs[4] = {0}; unsigned long threads[8];
    alarm(60);
    for (int i = 0; i < 4; ++i) {
        if (semaphore_create(mach_task_self_, &pairs[i].ready, 0, 0) ||
            semaphore_create(mach_task_self_, &pairs[i].ack, 0, 0) ||
            pthread_create(&threads[2*i], 0, consumer, &pairs[i]) ||
            pthread_create(&threads[2*i+1], 0, producer, &pairs[i])) return 1;
    }
    int total = 0;
    for (int i = 0; i < 8; ++i) if (pthread_join(threads[i], 0)) return 1;
    for (int i = 0; i < 4; ++i) {
        if (pairs[i].failed || pairs[i].completed != 5000) return 1;
        total += pairs[i].completed;
        semaphore_destroy(mach_task_self_, pairs[i].ready);
        semaphore_destroy(mach_task_self_, pairs[i].ack);
    }
    printf("SEMA_HANDOFF completed=%d expected=20000\n", total);
    return 0;
}
