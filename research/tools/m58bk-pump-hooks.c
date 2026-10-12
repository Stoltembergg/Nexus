/* darling-lol M58bk: pump hook, hardened: logs pid and whether the thread is
 * the process's main thread (captured at constructor time), and matches the
 * Framework image robustly. Targets:
 *   MessagePumpCFRunLoopBase::RunWorkSource = base + 0x381e370
 *   TaskAnnotator::RunTaskImpl              = base + 0x37c06c0
 * Prints LOLRT lines. */
extern int printf(const char *, ...);
extern int fflush(void *);
extern int mprotect(void *, unsigned long, int);
extern int getpid(void);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);
extern void *pthread_self(void);

struct hook { unsigned char *p; unsigned char orig[12]; void *fn; };
static struct hook H[4];
static int nH = 0;
static void *g_main_thread;

static void install(struct hook *h) {
    unsigned char *p = h->p;
    unsigned long pg = (unsigned long) p & ~0xFFFUL;
    int i;
    if (mprotect((void *) pg, 0x2000, 7) != 0) return;
    for (i = 0; i < 12; i++) h->orig[i] = p[i];
    p[0] = 0x48; p[1] = 0xB8;
    { unsigned long a = (unsigned long) h->fn; for (i = 0; i < 8; i++) p[2 + i] = (a >> (8 * i)) & 0xFF; }
    p[10] = 0xFF; p[11] = 0xE0;
}
static void unhook(struct hook *h) { int i; for (i = 0; i < 12; i++) h->p[i] = h->orig[i]; }
static struct hook *mk(void *addr, void *fn) {
    struct hook *h = &H[nH++];
    h->p = (unsigned char *) addr; h->fn = fn; install(h); return h;
}

static void note(const char *what, struct hook *h) {
    static void *tids[128];
    static unsigned int cnt[128];
    void *t = pthread_self();
    int i, slot = -1;
    for (i = 0; i < 128; ++i) if (tids[i] == t) { slot = i; break; }
    if (slot < 0) for (i = 0; i < 128; ++i) if (tids[i] == 0) { tids[i] = t; slot = i; break; }
    if (slot < 0) slot = 0;
    if (cnt[slot] < 3 || (cnt[slot] & 0x3ffff) == 0) {
        unhook(h);
        printf("LOLRT pid=%d %s main=%d n=%u\n", getpid(), what, t == g_main_thread, cnt[slot]);
        fflush(0);
        install(h);
    }
    cnt[slot]++;
}

static struct hook *HWs, *HRt;
static void f_ws(void *a) {
    note("RunWorkSource", HWs);
    unhook(HWs); ((void (*)(void *)) HWs->p)(a); install(HWs);
}
static void f_rt(void *self, void *task) {
    note("RunTaskImpl", HRt);
    unhook(HRt); ((void (*)(void *, void *)) HRt->p)(self, task); install(HRt);
}

__attribute__((constructor)) static void boot(void) {
    unsigned n = _dyld_image_count(), i;
    unsigned char *base = 0;
    g_main_thread = pthread_self();
    for (i = 0; i < n; i++) {
        const char *nm = _dyld_get_image_name(i);
        if (nm && strstr(nm, "Electron Framework")) { base = (unsigned char *) _dyld_get_image_header(i); break; }
    }
    printf("LOLRT pid=%d boot base=%p main=%p\n", getpid(), (void *) base, g_main_thread); fflush(0);
    if (!base) return;
    HWs = mk(base + 0x381e370, (void *) f_ws);
    HRt = mk(base + 0x37c06c0, (void *) f_rt);
    printf("LOLRT pid=%d hooked=%d\n", getpid(), nH); fflush(0);
}
