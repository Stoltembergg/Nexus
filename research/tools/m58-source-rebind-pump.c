/* M58 diagnostic: repair the BeginFrameSource observer on the renderer's
 * compositor-thread view, then feed it paced frames. */
extern int mprotect(void *, unsigned long, int);
extern int open(const char *, int, ...);
extern long read(int, void *, unsigned long);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern int getpid(void);
extern int snprintf(char *, unsigned long, const char *, ...);
extern const char *getprogname(void);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);
extern unsigned long mach_absolute_time(void);
extern int mach_timebase_info(void *);

#define NEEDS_VA 0x5e23520UL
#define ONBEGIN_VA 0x5e23140UL
#define PROXY_SOURCE_VA 0x51ef920UL
#define PI_WILLBEGIN_VA 0x51f09f0UL
#define SCHED_SET_SOURCE_VA 0x51e2510UL
#define SCHED_ONBEGIN_VA 0x51e3870UL
#define PROXY_WILLBEGIN_VA 0x51f09f0UL
#define PROXY_SEND_BEGIN_VA 0x51f0af0UL
#define PROXY_FINISH_BEGIN_VA 0x51f0a30UL
#define PROXY_MAIN_VA 0x51f3020UL

struct Hook { unsigned char *target, saved[12]; unsigned long replacement; };
static struct Hook needs_hook, proxy_hook, pi_hook, sched_hook, main_hook;
static volatile int needs_lock, pumping;
static unsigned char *base_image;

static void emit(unsigned e, unsigned long v) {
    unsigned long r[3] = {(unsigned long)getpid(), e, v};
    int fd = open("/Volumes/SystemRoot/tmp/opencode/m58-rebind-pump.bin",
                  1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, r, sizeof(r)); close(fd); }
}

static int is_renderer(void) {
    const char *n = getprogname();
    return n && strstr(n, "Renderer") != 0;
}

static unsigned char *find_framework(void) {
    for (unsigned i = 0; i < _dyld_image_count(); ++i) {
        const char *n = _dyld_get_image_name(i);
        if (n && strstr(n, "Versions/A/Electron Framework"))
            return (unsigned char *)_dyld_get_image_header(i);
    }
    return 0;
}

static void write_jump(unsigned char *at, unsigned long fn) {
    unsigned char j[12] = {0x48, 0xb8};
    for (unsigned i = 0; i < 8; ++i) j[i + 2] = (fn >> (i * 8)) & 0xff;
    j[10] = 0xff; j[11] = 0xe0;
    for (unsigned i = 0; i < 12; ++i) at[i] = j[i];
}

static void patch_hook(struct Hook *h, int enabled) {
    unsigned long page = (unsigned long)h->target & ~0xfffUL;
    mprotect((void *)page, 0x1000, 7);
    if (enabled) write_jump(h->target, h->replacement);
    else for (unsigned i = 0; i < 12; ++i) h->target[i] = h->saved[i];
}

static const char *source_path(void) {
    static char p[96]; static int init;
    if (!init) {
        snprintf(p, sizeof(p), "/dev/shm/m58-source-%d.state", getpid());
        init = 1;
    }
    return p;
}

static const char *scheduler_path(void) {
    static char p[96]; static int init;
    if (!init) {
        snprintf(p, sizeof(p), "/dev/shm/m58-scheduler-%d.state", getpid());
        init = 1;
    }
    return p;
}

static void remember_source(void *self, void *source) {
    unsigned long v[2] = {(unsigned long)self, (unsigned long)source};
    int fd = open(source_path(), 1 | 0x200 | 0x1000, 0644);
    if (fd >= 0) { write(fd, v, sizeof(v)); close(fd); }
}

static int load_source(unsigned long v[2]) {
    int fd = open(source_path(), 0, 0);
    if (fd < 0) return 0;
    long got = read(fd, v, sizeof(unsigned long) * 2); close(fd);
    return got == (long)(sizeof(unsigned long) * 2) && v[0] && v[1];
}

static void remember_scheduler(void *self) {
    int fd = open(scheduler_path(), 1 | 0x200 | 0x1000, 0644);
    unsigned long v = (unsigned long)self;
    if (fd >= 0) { write(fd, &v, sizeof(v)); close(fd); }
}

static unsigned long load_scheduler(void) {
    unsigned long v = 0;
    int fd = open(scheduler_path(), 0, 0);
    if (fd >= 0) { read(fd, &v, sizeof(v)); close(fd); }
    return v;
}

static void proxy_set_source(void *self, void *source) {
    patch_hook(&proxy_hook, 0);
    ((void (*)(void *, void *))proxy_hook.target)(self, source);
    patch_hook(&proxy_hook, 1);
    remember_source(self, source);
    emit(4, (unsigned long)source);
}

static int pi_will_begin(void *self, void *args) {
    int result;
    patch_hook(&pi_hook, 0);
    result = ((int (*)(void *, void *))pi_hook.target)(self, args);
    patch_hook(&pi_hook, 1);
    emit(6, (unsigned long)self);
    return result;
}

static void scheduler_set_source(void *self, void *source) {
    patch_hook(&sched_hook, 0);
    ((void (*)(void *, void *))sched_hook.target)(self, source);
    patch_hook(&sched_hook, 1);
    remember_scheduler(self);
    emit(7, (unsigned long)self);
}

static void proxy_main_begin(void *self, void *state) {
    patch_hook(&main_hook, 0);
    ((void (*)(void *, void *))main_hook.target)(self, state);
    patch_hook(&main_hook, 1);
    emit(11, (unsigned long)state);
}

static void rebind_source(void) {
    unsigned long v[2];
    if (!load_source(v)) return;
    patch_hook(&proxy_hook, 0);
    ((void (*)(void *, void *))proxy_hook.target)((void *)v[0], (void *)v[1]);
    patch_hook(&proxy_hook, 1);
    emit(5, v[1]);
}

static unsigned long now_us(void) {
    struct { unsigned numer, denom; } tb;
    mach_timebase_info(&tb);
    return mach_absolute_time() * (unsigned long)tb.numer /
           (tb.denom ? tb.denom : 1) / 1000UL;
}

static void pump(void *sink) {
    unsigned char a[128] = {0}, d[24] = {0};
    for (unsigned n = 1; n <= 600; ++n) {
        unsigned long t = now_us();
        *(unsigned long *)(a + 0) = t;
        *(unsigned long *)(a + 8) = t + 16666;
        *(unsigned long *)(a + 16) = 16666;
        *(unsigned long *)(a + 24) = 0xffffffffUL;
        *(unsigned long *)(a + 32) = n;
        *(long *)(a + 40) = -1;
        *(unsigned *)(a + 48) = 1;
        a[52] = 1;
        unsigned char *b = find_framework();
        if (!b) return;
        emit(2, n);
        ((void (*)(void *, void *, void *))(b + ONBEGIN_VA))(sink, a, d);
        unsigned long scheduler = load_scheduler();
        unsigned long proxy_values[2];
        if (load_source(proxy_values)) {
            patch_hook(&pi_hook, 0);
            int can_begin = ((int (*)(void *, void *))(b + PROXY_WILLBEGIN_VA))
                ((void *)proxy_values[0], a);
            patch_hook(&pi_hook, 1);
            emit(9, (unsigned long)can_begin);
            ((void (*)(void *, void *))(b + PROXY_SEND_BEGIN_VA))
                ((void *)proxy_values[0], a);
            ((void (*)(void *, void *))(b + PROXY_FINISH_BEGIN_VA))
                ((void *)proxy_values[0], a);
            emit(10, proxy_values[0]);
        }
        if (scheduler) {
            int used = ((int (*)(void *, void *))(b + SCHED_ONBEGIN_VA))
                ((void *)scheduler, a);
            emit(8, (unsigned long)used);
        }
        unsigned long until = now_us() + 16666;
        while (now_us() < until) { }
    }
}

static void needs_begin(void *self, int needs) {
    while (__sync_lock_test_and_set(&needs_lock, 1)) { }
    patch_hook(&needs_hook, 0);
    ((void (*)(void *, int))needs_hook.target)(self, needs);
    patch_hook(&needs_hook, 1);
    __sync_lock_release(&needs_lock);
    emit(1, needs);
    if (needs && is_renderer() &&
        !__sync_lock_test_and_set(&pumping, 1)) {
        rebind_source();
        pump(self);
    }
}

__attribute__((constructor)) static void install(void) {
    base_image = find_framework();
    if (!base_image) return;
    needs_hook.target = base_image + NEEDS_VA;
    needs_hook.replacement = (unsigned long)needs_begin;
    for (unsigned i = 0; i < 12; ++i) needs_hook.saved[i] = needs_hook.target[i];
    if (needs_hook.saved[0] != 0x55 || needs_hook.saved[1] != 0x48 ||
        needs_hook.saved[2] != 0x89 || needs_hook.saved[3] != 0xe5) return;
    patch_hook(&needs_hook, 1);
    proxy_hook.target = base_image + PROXY_SOURCE_VA;
    proxy_hook.replacement = (unsigned long)proxy_set_source;
    for (unsigned i = 0; i < 12; ++i) proxy_hook.saved[i] = proxy_hook.target[i];
    if (proxy_hook.saved[0] == 0x55 && proxy_hook.saved[1] == 0x48 &&
        proxy_hook.saved[2] == 0x89 && proxy_hook.saved[3] == 0xe5)
        patch_hook(&proxy_hook, 1);
    if (is_renderer()) {
        pi_hook.target = base_image + PI_WILLBEGIN_VA;
        pi_hook.replacement = (unsigned long)pi_will_begin;
        for (unsigned i = 0; i < 12; ++i) pi_hook.saved[i] = pi_hook.target[i];
        if (pi_hook.saved[0] == 0x55 && pi_hook.saved[1] == 0x48 &&
            pi_hook.saved[2] == 0x89 && pi_hook.saved[3] == 0xe5)
            patch_hook(&pi_hook, 1);
        main_hook.target = base_image + PROXY_MAIN_VA;
        main_hook.replacement = (unsigned long)proxy_main_begin;
        for (unsigned i = 0; i < 12; ++i) main_hook.saved[i] = main_hook.target[i];
        if (main_hook.saved[0] == 0x55 && main_hook.saved[1] == 0x48 &&
            main_hook.saved[2] == 0x89 && main_hook.saved[3] == 0xe5)
            patch_hook(&main_hook, 1);
        sched_hook.target = base_image + SCHED_SET_SOURCE_VA;
        sched_hook.replacement = (unsigned long)scheduler_set_source;
        for (unsigned i = 0; i < 12; ++i) sched_hook.saved[i] = sched_hook.target[i];
        if (sched_hook.saved[0] == 0x55 && sched_hook.saved[1] == 0x48 &&
            sched_hook.saved[2] == 0x89 && sched_hook.saved[3] == 0xe5)
            patch_hook(&sched_hook, 1);
    }
    emit(99, (unsigned long)base_image);
}
