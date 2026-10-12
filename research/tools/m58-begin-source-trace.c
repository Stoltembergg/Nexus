/* Narrow BeginFrame-source trace for the Electron 22.3.27 framework. */
extern int mprotect(void *, unsigned long, int);
extern int open(const char *, int, ...);
extern long write(int, const void *, unsigned long);
extern int close(int);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);
extern int getpid(void);

struct hook { unsigned char *target, saved[12]; unsigned long replacement; };
static struct hook hooks[6];
static volatile int locks[6];

static void emit(unsigned event, unsigned long value) {
    unsigned long record[3] = { (unsigned long)getpid(), event, value };
    int fd = open("/Volumes/SystemRoot/tmp/opencode/m58-begin-source.bin",
                  1 | 0x200 | 8, 0644);
    if (fd >= 0) { write(fd, record, sizeof(record)); close(fd); }
}
static void patch(struct hook *h, int enabled) {
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
        jump[2 + i] = (h->replacement >> (i * 8)) & 0xff;
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
static void enter(unsigned n, unsigned event, void *self, unsigned long value) {
    while (__sync_lock_test_and_set(&locks[n], 1)) { }
    patch(&hooks[n], 0); emit(event, value);
}
static void leave(unsigned n) {
    patch(&hooks[n], 1); __sync_lock_release(&locks[n]);
}
static void timer(void *self) {
    enter(0, 1, self, (unsigned long)self);
    ((void (*)(void *))hooks[0].target)(self);
    leave(0);
}
static void issue(void *self, void *observer, void *args) {
    enter(1, 2, self, (unsigned long)observer);
    ((void (*)(void *, void *, void *))hooks[1].target)(self, observer, args);
    leave(1);
}
static void group_begin(void *self, void *args) {
    enter(2, 3, self, (unsigned long)args);
    ((void (*)(void *, void *))hooks[2].target)(self, args);
    leave(2);
}
static void support_begin(void *self, void *args) {
    unsigned long client = *(unsigned long *)((unsigned char *)self + 0x20);
    unsigned long vtable = client ? *(unsigned long *)client : 0;
    unsigned long on_begin = vtable ? *(unsigned long *)(vtable + 0x28) : 0;
    enter(3, 4, self, on_begin);
    ((void (*)(void *, void *))hooks[3].target)(self, args);
    leave(3);
}
static void bundle_client_begin(void *self, void *args, void *details) {
    enter(4, 5, self, (unsigned long)args);
    ((void (*)(void *, void *, void *))hooks[4].target)
        (self, args, details);
    leave(4);
}
static void support_ctor(void *self, void *client, void *manager,
                         void *frame_sink_id, void *is_root) {
    enter(5, 6, self, (unsigned long)client);
    ((void (*)(void *, void *, void *, void *, void *))hooks[5].target)
        (self, client, manager, frame_sink_id, is_root);
    leave(5);
}
__attribute__((constructor)) static void install(void) {
    unsigned i; unsigned char *base = 0;
    for (i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework")) {
            base = (unsigned char *)_dyld_get_image_header(i); break;
        }
    }
    if (!base) return;
    configure(2, base, 0x64f7840UL, group_begin);
    configure(3, base, 0x64fb270UL, support_begin);
    configure(4, base, 0x64fdfd0UL, bundle_client_begin);
    configure(5, base, 0x64f7ab0UL, support_ctor);
}
