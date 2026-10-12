/* darling-lol M58dj: Blink document-load hooks (what runs after commit?).
 *   blink::Document::SetReadyState(DocumentReadyState)      base+0x5f1f6c0  (rdi=this, esi=state)
 *   blink::Document::ImplicitClose()                        base+0x5f29060
 *   blink::Document::FinishedParsing()                      base+0x5f36f60
 *   blink::FrameLoader::DidFinishNavigation(...)           base+0x5923e10
 *   blink::V8ScriptRunner::RunCompiledScript(...)           base+0x4f6b2b0
 */
extern int printf(const char *, ...);
extern int fflush(void *);
extern int mprotect(void *, unsigned long, int);
extern int getpid(void);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);
extern void _dyld_register_func_for_add_image(void (*)(const void *, long));

struct hook { unsigned char *p; unsigned char orig[12]; void *fn; };
static struct hook H[8];
static int nH = 0;

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

static unsigned long c_ready = 0, c_close = 0, c_fin = 0, c_dfn = 0, c_v8 = 0;
static struct hook *HR, *HC, *HF, *HD, *HV;

static void log1(const char *name, unsigned long *ctr, long extra, int has_extra) {
    (*ctr)++;
    if (*ctr <= 30) {
        if (has_extra)
            printf("LOADHOOK %s pid=%d n=%lu arg=%ld\n", name, getpid(), *ctr, extra);
        else
            printf("LOADHOOK %s pid=%d n=%lu\n", name, getpid(), *ctr);
        fflush(0);
    }
}

static void f_ready(void *self, int state) {
    log1("SetReadyState", &c_ready, state, 1);
    unhook(HR); ((void (*)(void *, int)) HR->p)(self, state); install(HR);
}
static void f_close(void *self) {
    log1("ImplicitClose", &c_close, 0, 0);
    unhook(HC); ((void (*)(void *)) HC->p)(self); install(HC);
}
static void f_fin(void *self) {
    log1("FinishedParsing", &c_fin, 0, 0);
    unhook(HF); ((void (*)(void *)) HF->p)(self); install(HF);
}
static void f_dfn(void *self, int st) {
    log1("DidFinishNavigation", &c_dfn, st, 1);
    unhook(HD); ((void (*)(void *, int)) HD->p)(self, st); install(HD);
}
static void f_v8(void *a, void *b, void *c, void *d) {
    log1("RunCompiledScript", &c_v8, 0, 0);
    unhook(HV); ((void (*)(void *, void *, void *, void *)) HV->p)(a, b, c, d); install(HV);
}

static unsigned char *base = 0;
static int installed = 0;
static void try_install(void) {
    unsigned n, i;
    if (installed) return;
    n = _dyld_image_count();
    for (i = 0; i < n; i++) {
        const char *nm = _dyld_get_image_name(i);
        if (nm && strstr(nm, "Electron Framework")) { base = (unsigned char *) _dyld_get_image_header(i); break; }
    }
    if (!base) return;
    installed = 1;
    HR = mk(base + 0x5f1f6c0, (void *) f_ready);
    HC = mk(base + 0x5f29060, (void *) f_close);
    HF = mk(base + 0x5f36f60, (void *) f_fin);
    HD = mk(base + 0x5923e10, (void *) f_dfn);
    HV = mk(base + 0x4f6b2b0, (void *) f_v8);
    printf("LOADHOOK install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }

__attribute__((constructor)) static void boot(void) {
    printf("LOADHOOK boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
