/* darling-lol M58dl: Blink post-parse chain (find where the commit stalls).
 *   blink::Document::FinishedParsing()                     base+0x5f36f60
 *   blink::FrameLoader::FinishedParsing()                  base+0x5923bf0
 *   blink::Document::CheckCompletedInternal()              base+0x5f29450
 *   blink::mojom::blink::LocalFrameHostProxy::DidDispatchDOMContentLoadedEvent() base+0x24c3970
 * All take only `this` (rdi), so the pass-through is safe.
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
    unsigned char *p = h->p; unsigned long pg = (unsigned long) p & ~0xFFFUL; int i;
    if (mprotect((void *) pg, 0x2000, 7) != 0) return;
    for (i = 0; i < 12; i++) h->orig[i] = p[i];
    p[0] = 0x48; p[1] = 0xB8;
    { unsigned long a = (unsigned long) h->fn; for (i = 0; i < 8; i++) p[2 + i] = (a >> (8 * i)) & 0xFF; }
    p[10] = 0xFF; p[11] = 0xE0;
}
static void unhook(struct hook *h) { int i; for (i = 0; i < 12; i++) h->p[i] = h->orig[i]; }
static struct hook *mk(void *addr, void *fn) { struct hook *h = &H[nH++]; h->p = (unsigned char *) addr; h->fn = fn; install(h); return h; }

static unsigned long c_fp = 0, c_ffp = 0, c_cc = 0, c_dcl = 0;
static struct hook *HFP, *HFFP, *HCC, *HDCL;

static void log1(const char *name, unsigned long *ctr) {
    (*ctr)++; if (*ctr <= 30) { printf("POSTHOOK %s pid=%d n=%lu\n", name, getpid(), *ctr); fflush(0); }
}
static void f_fp(void *s) { log1("Document::FinishedParsing", &c_fp); unhook(HFP); ((void (*)(void *)) HFP->p)(s); install(HFP); }
static void f_ffp(void *s) { log1("FrameLoader::FinishedParsing", &c_ffp); unhook(HFFP); ((void (*)(void *)) HFFP->p)(s); install(HFFP); }
static void f_cc(void *s) { log1("Document::CheckCompletedInternal", &c_cc); unhook(HCC); ((void (*)(void *)) HCC->p)(s); install(HCC); }
static void f_dcl(void *s) { log1("LocalFrameHostProxy::DidDispatchDOMContentLoadedEvent", &c_dcl); unhook(HDCL); ((void (*)(void *)) HDCL->p)(s); install(HDCL); }

static unsigned char *base = 0;
static int installed = 0;
static void try_install(void) {
    unsigned n, i;
    if (installed) return;
    n = _dyld_image_count();
    for (i = 0; i < n; i++) { const char *nm = _dyld_get_image_name(i); if (nm && strstr(nm, "Electron Framework")) { base = (unsigned char *) _dyld_get_image_header(i); break; } }
    if (!base) return;
    installed = 1;
    HFP = mk(base + 0x5f36f60, (void *) f_fp);
    HFFP = mk(base + 0x5923bf0, (void *) f_ffp);
    HCC = mk(base + 0x5f29450, (void *) f_cc);
    HDCL = mk(base + 0x24c3970, (void *) f_dcl);
    printf("POSTHOOK install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("POSTHOOK boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
