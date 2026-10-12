/* darling-lol M58dn: does the renderer pump still run after FinishedParsing?
 *   MessagePumpCFRunLoopBase::RunWorkSource(void*)  base+0x381e370  (once per pump work iteration)
 *   blink::FrameLoader::FinishedParsing()           base+0x5923bf0
 *   blink::Document::CheckCompletedInternal()       base+0x5f29450
 *   blink::LocalFrame::FinishedLoading(...)         base+0x53b6020
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
static struct hook H[8]; static int nH = 0;
static void install(struct hook *h) {
    unsigned char *p = h->p; unsigned long pg = (unsigned long) p & ~0xFFFUL; int i;
    if (mprotect((void *) pg, 0x2000, 7) != 0) return;
    for (i = 0; i < 12; i++) h->orig[i] = p[i];
    p[0] = 0x48; p[1] = 0xB8;
    { unsigned long a = (unsigned long) h->fn; for (i = 0; i < 8; i++) p[2 + i] = (a >> (8 * i)) & 0xFF; }
    p[10] = 0xFF; p[11] = 0xE0;
}
static void unhook(struct hook *h) { int i; for (i = 0; i < 12; i++) h->p[i] = h->orig[i]; }
static struct hook *mk(void *addr, void *fn) { struct hook *h = &H[nH++]; h->p = (unsigned char *) addr; h->fn = fn; install(h); return h; }

static unsigned long c_ws = 0, c_ffp = 0, c_cc = 0, c_fl = 0;
static struct hook *HWS, *HFFP, *HCC, *HFL;

static void f_ws(void *a) {
    c_ws++;
    if (c_ws <= 3 || (c_ws % 100) == 0) { printf("PUMPHOOK RunWorkSource pid=%d n=%lu\n", getpid(), c_ws); fflush(0); }
    unhook(HWS); ((void (*)(void *)) HWS->p)(a); install(HWS);
}
static void f_ffp(void *s) {
    c_ffp++; printf("PUMPHOOK FrameLoader::FinishedParsing pid=%d pumps=%lu\n", getpid(), c_ws); fflush(0);
    unhook(HFFP); ((void (*)(void *)) HFFP->p)(s); install(HFFP);
}
static void f_cc(void *s) {
    c_cc++; printf("PUMPHOOK CheckCompletedInternal pid=%d pumps=%lu\n", getpid(), c_ws); fflush(0);
    unhook(HCC); ((void (*)(void *)) HCC->p)(s); install(HCC);
}
static void f_fl(void *s, int st) {
    c_fl++; printf("PUMPHOOK LocalFrame::FinishedLoading pid=%d pumps=%lu\n", getpid(), c_ws); fflush(0);
    unhook(HFL); ((void (*)(void *, int)) HFL->p)(s, st); install(HFL);
}

static unsigned char *base = 0; static int installed = 0;
static void try_install(void) {
    unsigned n, i;
    if (installed) return;
    n = _dyld_image_count();
    for (i = 0; i < n; i++) { const char *nm = _dyld_get_image_name(i); if (nm && strstr(nm, "Electron Framework")) { base = (unsigned char *) _dyld_get_image_header(i); break; } }
    if (!base) return;
    installed = 1;
    HWS = mk(base + 0x381e370, (void *) f_ws);
    HFFP = mk(base + 0x5923bf0, (void *) f_ffp);
    HCC = mk(base + 0x5f29450, (void *) f_cc);
    HFL = mk(base + 0x53b6020, (void *) f_fl);
    printf("PUMPHOOK install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("PUMPHOOK boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
