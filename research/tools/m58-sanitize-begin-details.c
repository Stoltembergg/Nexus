/* M58b companion: the synthetic FrameSink tick has no presentation details.
 * Passing the stale/diverged map through Mojo trips Chromium's serializer. */
extern int mprotect(void *, unsigned long, int);
extern int open(const char *, int, ...);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern int getpid(void);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);

struct Hook { unsigned char *target, saved[12]; unsigned long replacement; };
static struct Hook hooks[8];
static volatile int locks[8];
static unsigned char empty_details[24];
static void trace(unsigned event) {
    unsigned long record[2] = { (unsigned long)getpid(), event };
    int fd = open("/Volumes/SystemRoot/tmp/opencode/m58-sanitize.bin",
                  1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, record, sizeof(record)); close(fd); }
}

static void patch(struct Hook *h, int enabled) {
    unsigned char jump[12]; unsigned long page;
    unsigned i;
    page = (unsigned long)h->target & ~0xfffUL;
    mprotect((void *)page, 0x1000, 7);
    if (!enabled) {
        for (i = 0; i < 12; ++i) h->target[i] = h->saved[i];
        return;
    }
    jump[0] = 0x48; jump[1] = 0xb8;
    for (i = 0; i < 8; ++i)
        jump[i + 2] = (h->replacement >> (i * 8)) & 0xff;
    jump[10] = 0xff; jump[11] = 0xe0;
    for (i = 0; i < 12; ++i) h->target[i] = jump[i];
}
static void configure(unsigned n, unsigned char *base, unsigned long va,
                      void *replacement) {
    unsigned i;
    hooks[n].target = base + va;
    hooks[n].replacement = (unsigned long)replacement;
    for (i = 0; i < 12; ++i) hooks[n].saved[i] = hooks[n].target[i];
    patch(&hooks[n], 1);
}
static void bundle_begin(void *self, void *args, void *details) {
    trace(1);
    while (__sync_lock_test_and_set(&locks[0], 1)) { }
    patch(&hooks[0], 0);
    ((void (*)(void *, void *, void *))hooks[0].target)
        (self, args, empty_details);
    patch(&hooks[0], 1);
    __sync_lock_release(&locks[0]);
}
static void direct_begin(void *self, void *args, void *details) {
    trace(2);
    while (__sync_lock_test_and_set(&locks[1], 1)) { }
    patch(&hooks[1], 0);
    ((void (*)(void *, void *, void *))hooks[1].target)
        (self, args, empty_details);
    patch(&hooks[1], 1);
    __sync_lock_release(&locks[1]);
}
static void async_begin(void *self, void *args, void *details) {
    trace(3);
    while (__sync_lock_test_and_set(&locks[2], 1)) { }
    patch(&hooks[2], 0);
    ((void (*)(void *, void *, void *))hooks[2].target)
        (self, args, empty_details);
    patch(&hooks[2], 1);
    __sync_lock_release(&locks[2]);
}
static void pi_willbegin(void *self, void *args) {
    trace(4);
    while (__sync_lock_test_and_set(&locks[3], 1)) { }
    patch(&hooks[3], 0);
    ((void (*)(void *, void *))hooks[3].target)(self, args);
    patch(&hooks[3], 1);
    __sync_lock_release(&locks[3]);
}
static void needs_begin(void *self, int needs) {
    trace(5);
    while (__sync_lock_test_and_set(&locks[4], 1)) { }
    patch(&hooks[4], 0);
    ((void (*)(void *, int))hooks[4].target)(self, needs);
    patch(&hooks[4], 1);
    __sync_lock_release(&locks[4]);
}
static void submit_frame(void *self, void *frame, int hit_test_changed) {
    trace(6);
    while (__sync_lock_test_and_set(&locks[5], 1)) { }
    patch(&hooks[5], 0);
    ((void (*)(void *, void *, int))hooks[5].target)
        (self, frame, hit_test_changed);
    patch(&hooks[5], 1);
    __sync_lock_release(&locks[5]);
}
static int bind_sink(void *self, void *client) {
    int result;
    trace(7);
    while (__sync_lock_test_and_set(&locks[6], 1)) { }
    patch(&hooks[6], 0);
    result = ((int (*)(void *, void *))hooks[6].target)(self, client);
    patch(&hooks[6], 1);
    __sync_lock_release(&locks[6]);
    return result;
}
static void set_begin_source(void *self, void *source) {
    trace(8);
    while (__sync_lock_test_and_set(&locks[7], 1)) { }
    patch(&hooks[7], 0);
    ((void (*)(void *, void *))hooks[7].target)(self, source);
    patch(&hooks[7], 1);
    __sync_lock_release(&locks[7]);
}
__attribute__((constructor)) static void install(void) {
    unsigned i; unsigned char *base = 0;
    trace(99);
    for (i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework")) {
            base = (unsigned char *)_dyld_get_image_header(i); break;
        }
    }
    if (!base) return;
    trace(100);
    configure(0, base, 0x64fdfd0UL, bundle_begin);
    configure(1, base, 0x141bdc0UL, direct_begin);
    configure(2, base, 0x5e23140UL, async_begin);
    configure(3, base, 0x51f09f0UL, pi_willbegin);
    configure(4, base, 0x5e23520UL, needs_begin);
    configure(5, base, 0x5e22420UL, submit_frame);
    configure(6, base, 0x5e21c10UL, bind_sink);
    configure(7, base, 0x51ef920UL, set_begin_source);
}
