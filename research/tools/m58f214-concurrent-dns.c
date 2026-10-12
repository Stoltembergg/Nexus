/* Concurrent getaddrinfo regression probe for Darling's resolver state. */
/* Headerless build against Darling's incomplete SDK. */
#define NULL ((void *)0)
#define SOCK_STREAM 1
#define SIGALRM 14
typedef unsigned long pthread_t;
struct timeval { long tv_sec, tv_usec; };
struct addrinfo {
    int ai_flags, ai_family, ai_socktype, ai_protocol;
    unsigned int ai_addrlen;
    char *ai_canonname;
    void *ai_addr;
    struct addrinfo *ai_next;
};
extern int getaddrinfo(const char *, const char *, const struct addrinfo *, struct addrinfo **);
extern void freeaddrinfo(struct addrinfo *);
extern int pthread_create(pthread_t *, const void *, void *(*)(void *), void *);
extern int pthread_join(pthread_t, void **);
extern void (*signal(int, void (*)(int)))(int);
extern unsigned int alarm(unsigned int);
extern int printf(const char *, ...);
extern int fflush(void *);
extern void *__stdoutp;
extern int gettimeofday(struct timeval *, void *);
extern int usleep(unsigned int);
extern long write(int, const void *, unsigned long);
extern void _exit(int);

static volatile int start;
static int failures;
static const char *names[] = {
    "data.riotgames.com", "clientconfig.rpg.riotgames.com",
    "telemetry.sgp.pvp.net", "auth.riotgames.com"
};

static void deadline(int signo) {
    const char text[] = "DNS DEADLINE: concurrent lookups did not finish\n";
    write(2, text, sizeof(text) - 1);
    _exit(2);
}

static void *worker(void *arg) {
    long index = (long)arg;
    struct addrinfo hints = {0};
    hints.ai_socktype = SOCK_STREAM;
    while (!start) usleep(1000);
    for (int i = 0; i < 3; i++) {
        struct addrinfo *result = NULL;
        const char *name = names[(index + i) % 4];
        int code = getaddrinfo(name, "443", &hints, &result);
        if (code || !result) __sync_fetch_and_add(&failures, 1);
        printf("DNS thread=%ld round=%d name=%s status=%d\n", index, i, name, code);
        fflush(__stdoutp);
        if (result) freeaddrinfo(result);
    }
    return NULL;
}

int main(void) {
    pthread_t threads[8];
    struct timeval before, after;
    signal(SIGALRM, deadline);
    alarm(25);
    gettimeofday(&before, NULL);
    for (long i = 0; i < 8; i++)
        if (pthread_create(&threads[i], NULL, worker, (void *)i)) return 3;
    start = 1;
    for (int i = 0; i < 8; i++) pthread_join(threads[i], NULL);
    gettimeofday(&after, NULL);
    printf("DNS RESULT failures=%d elapsed_ms=%ld\n", failures,
           (after.tv_sec - before.tv_sec) * 1000 +
           (after.tv_usec - before.tv_usec) / 1000);
    return failures ? 1 : 0;
}
