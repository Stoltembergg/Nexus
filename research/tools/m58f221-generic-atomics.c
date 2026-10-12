/* Guest ABI regression for the generic compiler-rt atomic entry points. */
typedef unsigned long size_t;
typedef unsigned long pthread_t;
extern void *dlsym(void *, const char *);
extern int printf(const char *, ...);
extern int pthread_create(pthread_t *, const void *, void *(*)(void *), void *);
extern int pthread_join(pthread_t, void **);
typedef void (*load_fn)(size_t, void *, void *, int);
typedef void (*store_fn)(size_t, void *, void *, int);
typedef void (*exchange_fn)(size_t, void *, void *, void *, int);
typedef int (*cas_fn)(size_t, void *, void *, void *, int, int);
static load_fn load;
static store_fn store;
static struct {unsigned long value, inverse;} pair = {0, ~0UL};
static void *writer(void *arg) {
    for (unsigned long i = 0; i < 10000; ++i) {
        struct {unsigned long value, inverse;} next = {i, ~i};
        store(sizeof(next), &pair, &next, 5);
    }
    return 0;
}
int main(void) {
    load = (load_fn)dlsym((void *)-2, "__atomic_load");
    store = (store_fn)dlsym((void *)-2, "__atomic_store");
    exchange_fn exchange = (exchange_fn)dlsym((void *)-2, "__atomic_exchange");
    cas_fn cas = (cas_fn)dlsym((void *)-2, "__atomic_compare_exchange");
    if (!load || !store || !exchange || !cas) return 1;
    unsigned long value = 3, desired = 9, out = 0, expected;
    store(sizeof(value), &value, &desired, 5);
    load(sizeof(value), &value, &out, 5);
    if (out != 9) return 2;
    desired = 12; exchange(sizeof(value), &value, &desired, &out, 5);
    if (out != 9 || value != 12) return 3;
    expected = 12; desired = 19;
    if (!cas(sizeof(value), &value, &expected, &desired, 5, 5) || value != 19) return 4;
    expected = 12;
    if (cas(sizeof(value), &value, &expected, &desired, 5, 5) || expected != 19) return 5;
    pthread_t thread;
    if (pthread_create(&thread, 0, writer, 0)) return 6;
    for (int i = 0; i < 10000; ++i) {
        struct {unsigned long value, inverse;} snapshot;
        load(sizeof(snapshot), &pair, &snapshot, 5);
        if (snapshot.inverse != ~snapshot.value) return 7;
    }
    pthread_join(thread, 0);
    printf("ATOMIC load/store/exchange/CAS and concurrent 16-byte reads: PASS\n");
    return 0;
}
