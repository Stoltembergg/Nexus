/* Minimal M58b renderer probe.  This deliberately does not alter cc state:
 * it only feeds a valid, paced BeginFrame to the bound Async sink on the
 * compositor thread that requested begin frames. */
extern int mprotect(void *, unsigned long, int);
extern int open(const char *, int, ...);
extern long write(int, const void *, unsigned long);
extern long read(int, void *, unsigned long);
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
#define BIND_VA 0x5e21c10UL
#define EXTERNAL_ONBEGIN_VA 0x51df5a0UL
#define SCHED_ONBEGIN_VA 0x51e3870UL
#define OBSERVER_ONBEGIN_VA 0x51ddf10UL
#define PROXY_SOURCE_VA 0x51ef920UL

struct Hook {
    unsigned char *target;
    unsigned char saved[12];
    unsigned long replacement;
};
static struct Hook needs_hook;
static struct Hook bind_hook;
static struct Hook external_hook;
static struct Hook sched_hook;
static struct Hook observer_hook;
static struct Hook proxy_hook;
static unsigned char *framework_base;
static volatile int hook_lock;
static volatile int pumping;

static const char *proxy_source_path(void) {
    static char path[96];
    static int initialized;
    if (!initialized) {
        snprintf(path, sizeof(path), "/dev/shm/m58-proxy-source-%d.state",
                 getpid());
        initialized = 1;
    }
    return path;
}

static void save_proxy_source(void *self, void *source) {
    unsigned long values[2] = {(unsigned long)self, (unsigned long)source};
    int fd = open(proxy_source_path(), 1 | 0x200 | 0x1000,
                  0644);
    if (fd >= 0) { write(fd, values, sizeof(values)); close(fd); }
}

static int load_proxy_source(unsigned long values[2]) {
    int fd = open(proxy_source_path(), 0, 0);
    if (fd < 0) return 0;
    long got = read(fd, values, sizeof(unsigned long) * 2); close(fd);
    return got == (long)(sizeof(unsigned long) * 2) && values[0] && values[1];
}

static void emit(unsigned event, unsigned long value) {
    unsigned long record[3] = {(unsigned long)getpid(), event, value};
    int fd = open("/Volumes/SystemRoot/tmp/opencode/m58-minimal-pump.bin",
                  1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, record, sizeof(record)); close(fd); }
}

static int renderer_process(void) {
    const char *name = getprogname();
    return name && strstr(name, "Renderer") != 0;
}

static unsigned char *find_framework(void) {
    for (unsigned i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework"))
            return (unsigned char *)_dyld_get_image_header(i);
    }
    return 0;
}

static void patch(int enabled) {
    unsigned char jump[12];
    unsigned long page = (unsigned long)needs_hook.target & ~0xfffUL;
    mprotect((void *)page, 0x1000, 7);
    if (!enabled) {
        for (unsigned i = 0; i < 12; ++i)
            needs_hook.target[i] = needs_hook.saved[i];
        return;
    }
    jump[0] = 0x48; jump[1] = 0xb8;
    for (unsigned i = 0; i < 8; ++i)
        jump[i + 2] = (needs_hook.replacement >> (i * 8)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (unsigned i = 0; i < 12; ++i)
        needs_hook.target[i] = jump[i];
}

static void patch_external(int enabled) {
    unsigned char jump[12];
    unsigned long page = (unsigned long)external_hook.target & ~0xfffUL;
    mprotect((void *)page, 0x1000, 7);
    if (!enabled) {
        for (unsigned i = 0; i < 12; ++i)
            external_hook.target[i] = external_hook.saved[i];
        return;
    }
    jump[0] = 0x48; jump[1] = 0xb8;
    for (unsigned i = 0; i < 8; ++i)
        jump[i + 2] = (external_hook.replacement >> (i * 8)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (unsigned i = 0; i < 12; ++i)
        external_hook.target[i] = jump[i];
}

static unsigned long now_us(void) {
    struct { unsigned numer, denom; } tb;
    mach_timebase_info(&tb);
    return mach_absolute_time() * (unsigned long)tb.numer /
           (tb.denom ? tb.denom : 1) / 1000UL;
}

static void begin_pump(void *sink) {
    unsigned char args[128] = {0};
    unsigned char details[24] = {0};
    unsigned long sequence = 0;
    for (unsigned tick = 0; tick < 900; ++tick) {
        unsigned long t = now_us();
        ++sequence;
        *(unsigned long *)(args + 0) = t;
        *(unsigned long *)(args + 8) = t + 16666;
        *(unsigned long *)(args + 16) = 16666;
        *(unsigned long *)(args + 24) = 0xffffffffUL;
        *(unsigned long *)(args + 32) = sequence;
        *(long *)(args + 40) = -1;
        *(unsigned *)(args + 48) = 1;
        args[52] = 1;
        unsigned char *base = find_framework();
        if (!base) return;
        emit(2, sequence);
        ((void (*)(void *, void *, void *))(base + ONBEGIN_VA))
            (sink, args, details);
        unsigned long until = now_us() + 16666;
        while (now_us() < until) { }
    }
}

static void rebind_proxy_source(void);

static void needs_begin(void *self, int needs) {
    while (__sync_lock_test_and_set(&hook_lock, 1)) { }
    patch(0);
    ((void (*)(void *, int))needs_hook.target)(self, needs);
    patch(1);
    __sync_lock_release(&hook_lock);
    emit(1, (unsigned long)needs);
    if (needs && renderer_process() &&
        !__sync_lock_test_and_set(&pumping, 1) ) {
        rebind_proxy_source();
        begin_pump(self);
    }
}

static int bind_to_client(void *self, void *client) {
    int result;
    while (__sync_lock_test_and_set(&hook_lock, 1)) { }
    patch(0);
    /* needs_hook.target is the only target understood by patch(); temporarily
     * use the same helper shape for the bind probe below. */
    unsigned char *target = bind_hook.target;
    unsigned long page = (unsigned long)target & ~0xfffUL;
    mprotect((void *)page, 0x1000, 7);
    for (unsigned i = 0; i < 12; ++i) target[i] = bind_hook.saved[i];
    result = ((int (*)(void *, void *))target)(self, client);
    unsigned char jump[12] = {0x48, 0xb8};
    for (unsigned i = 0; i < 8; ++i)
        jump[i + 2] = (bind_hook.replacement >> (i * 8)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (unsigned i = 0; i < 12; ++i) target[i] = jump[i];
    patch(1);
    __sync_lock_release(&hook_lock);
    emit(4, (unsigned long)self);
    return result;
}

static void external_on_begin(void *self, void *args) {
    patch_external(0);
    ((void (*)(void *, void *))external_hook.target)(self, args);
    patch_external(1);
    emit(3, (unsigned long)self);
}

static void patch_sched(int enabled) {
    unsigned char jump[12];
    unsigned long page = (unsigned long)sched_hook.target & ~0xfffUL;
    mprotect((void *)page, 0x1000, 7);
    if (!enabled) {
        for (unsigned i = 0; i < 12; ++i) sched_hook.target[i] = sched_hook.saved[i];
        return;
    }
    jump[0] = 0x48; jump[1] = 0xb8;
    for (unsigned i = 0; i < 8; ++i)
        jump[i + 2] = (sched_hook.replacement >> (i * 8)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (unsigned i = 0; i < 12; ++i) sched_hook.target[i] = jump[i];
}

static int scheduler_on_begin(void *self, void *args) {
    int result;
    patch_sched(0);
    result = ((int (*)(void *, void *))sched_hook.target)(self, args);
    patch_sched(1);
    emit(5, (unsigned long)self);
    return result;
}

static void observer_on_begin(void *self, void *args) {
    unsigned char jump[12];
    unsigned long page = (unsigned long)observer_hook.target & ~0xfffUL;
    mprotect((void *)page, 0x1000, 7);
    for (unsigned i = 0; i < 12; ++i)
        observer_hook.target[i] = observer_hook.saved[i];
    ((void (*)(void *, void *))observer_hook.target)(self, args);
    jump[0] = 0x48; jump[1] = 0xb8;
    for (unsigned i = 0; i < 8; ++i)
        jump[i + 2] = (observer_hook.replacement >> (i * 8)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (unsigned i = 0; i < 12; ++i) observer_hook.target[i] = jump[i];
    emit(6, (unsigned long)self);
}

static void patch_proxy(int enabled) {
    unsigned char jump[12];
    unsigned long page = (unsigned long)proxy_hook.target & ~0xfffUL;
    mprotect((void *)page, 0x1000, 7);
    if (!enabled) {
        for (unsigned i = 0; i < 12; ++i)
            proxy_hook.target[i] = proxy_hook.saved[i];
        return;
    }
    jump[0] = 0x48; jump[1] = 0xb8;
    for (unsigned i = 0; i < 8; ++i)
        jump[i + 2] = (proxy_hook.replacement >> (i * 8)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (unsigned i = 0; i < 12; ++i) proxy_hook.target[i] = jump[i];
}

static void proxy_set_source(void *self, void *source) {
    patch_proxy(0);
    ((void (*)(void *, void *))proxy_hook.target)(self, source);
    patch_proxy(1);
    save_proxy_source(self, source);
    emit(7, (unsigned long)source);
}

static void rebind_proxy_source(void) {
    unsigned long values[2];
    unsigned char *base = find_framework();
    if (!base || !load_proxy_source(values)) return;
    patch_proxy(0);
    ((void (*)(void *, void *))(base + PROXY_SOURCE_VA))
        ((void *)values[0], (void *)values[1]);
    patch_proxy(1);
    emit(8, values[1]);
}

__attribute__((constructor)) static void install(void) {
    framework_base = find_framework();
    if (!framework_base) return;
    needs_hook.target = framework_base + NEEDS_VA;
    needs_hook.replacement = (unsigned long)needs_begin;
    for (unsigned i = 0; i < 12; ++i)
        needs_hook.saved[i] = needs_hook.target[i];
    if (needs_hook.saved[0] != 0x55 || needs_hook.saved[1] != 0x48 ||
        needs_hook.saved[2] != 0x89 || needs_hook.saved[3] != 0xe5)
        return;
    emit(99, (unsigned long)framework_base);
    patch(1);

    bind_hook.target = framework_base + BIND_VA;
    bind_hook.replacement = (unsigned long)bind_to_client;
    for (unsigned i = 0; i < 12; ++i)
        bind_hook.saved[i] = bind_hook.target[i];
    if (bind_hook.saved[0] == 0x55 && bind_hook.saved[1] == 0x48 &&
        bind_hook.saved[2] == 0x89 && bind_hook.saved[3] == 0xe5) {
        unsigned char jump[12] = {0x48, 0xb8};
        unsigned long page = (unsigned long)bind_hook.target & ~0xfffUL;
        mprotect((void *)page, 0x1000, 7);
        for (unsigned i = 0; i < 8; ++i)
            jump[i + 2] = (bind_hook.replacement >> (i * 8)) & 0xff;
        jump[10] = 0xff; jump[11] = 0xe0;
        for (unsigned i = 0; i < 12; ++i) bind_hook.target[i] = jump[i];
    }

    if (renderer_process()) {
        external_hook.target = framework_base + EXTERNAL_ONBEGIN_VA;
        external_hook.replacement = (unsigned long)external_on_begin;
        for (unsigned i = 0; i < 12; ++i)
            external_hook.saved[i] = external_hook.target[i];
        if (external_hook.saved[0] == 0x55 &&
            external_hook.saved[1] == 0x48 &&
            external_hook.saved[2] == 0x89 &&
            external_hook.saved[3] == 0xe5) {
            unsigned char jump[12] = {0x48, 0xb8};
            unsigned long page = (unsigned long)external_hook.target & ~0xfffUL;
            mprotect((void *)page, 0x1000, 7);
            for (unsigned i = 0; i < 8; ++i)
                jump[i + 2] = (external_hook.replacement >> (i * 8)) & 0xff;
            jump[10] = 0xff; jump[11] = 0xe0;
            for (unsigned i = 0; i < 12; ++i)
                external_hook.target[i] = jump[i];
        }

        sched_hook.target = framework_base + SCHED_ONBEGIN_VA;
        sched_hook.replacement = (unsigned long)scheduler_on_begin;
        for (unsigned i = 0; i < 12; ++i)
            sched_hook.saved[i] = sched_hook.target[i];
        if (sched_hook.saved[0] == 0x55 && sched_hook.saved[1] == 0x48 &&
            sched_hook.saved[2] == 0x89 && sched_hook.saved[3] == 0xe5) {
            unsigned char jump[12] = {0x48, 0xb8};
            unsigned long page = (unsigned long)sched_hook.target & ~0xfffUL;
            mprotect((void *)page, 0x1000, 7);
            for (unsigned i = 0; i < 8; ++i)
                jump[i + 2] = (sched_hook.replacement >> (i * 8)) & 0xff;
            jump[10] = 0xff; jump[11] = 0xe0;
            for (unsigned i = 0; i < 12; ++i) sched_hook.target[i] = jump[i];
        }

        observer_hook.target = framework_base + OBSERVER_ONBEGIN_VA;
        observer_hook.replacement = (unsigned long)observer_on_begin;
        for (unsigned i = 0; i < 12; ++i)
            observer_hook.saved[i] = observer_hook.target[i];
        if (observer_hook.saved[0] == 0x55 &&
            observer_hook.saved[1] == 0x48 &&
            observer_hook.saved[2] == 0x89 &&
            observer_hook.saved[3] == 0xe5) {
            unsigned char jump[12] = {0x48, 0xb8};
            unsigned long page = (unsigned long)observer_hook.target & ~0xfffUL;
            mprotect((void *)page, 0x1000, 7);
            for (unsigned i = 0; i < 8; ++i)
                jump[i + 2] = (observer_hook.replacement >> (i * 8)) & 0xff;
            jump[10] = 0xff; jump[11] = 0xe0;
            for (unsigned i = 0; i < 12; ++i)
                observer_hook.target[i] = jump[i];
        }

        proxy_hook.target = framework_base + PROXY_SOURCE_VA;
        proxy_hook.replacement = (unsigned long)proxy_set_source;
        for (unsigned i = 0; i < 12; ++i)
            proxy_hook.saved[i] = proxy_hook.target[i];
        if (proxy_hook.saved[0] == 0x55 && proxy_hook.saved[1] == 0x48 &&
            proxy_hook.saved[2] == 0x89 && proxy_hook.saved[3] == 0xe5) {
            unsigned char jump[12] = {0x48, 0xb8};
            unsigned long page = (unsigned long)proxy_hook.target & ~0xfffUL;
            mprotect((void *)page, 0x1000, 7);
            for (unsigned i = 0; i < 8; ++i)
                jump[i + 2] = (proxy_hook.replacement >> (i * 8)) & 0xff;
            jump[10] = 0xff; jump[11] = 0xe0;
            for (unsigned i = 0; i < 12; ++i) proxy_hook.target[i] = jump[i];
        }
    }
}
