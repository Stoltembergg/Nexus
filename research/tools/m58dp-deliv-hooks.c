/* darling-lol M58dp: does the renderer's notification REACH the browser?
 * renderer -> browser senders (Blink):
 *   LocalFrameHostProxy::DidDispatchDOMContentLoadedEvent() base+0x24c3970
 *   LocalFrameHostProxy::DidFinishLoad(KURL const&)         base+0x24c3020
 * browser receivers (RenderFrameHostImpl):
 *   RenderFrameHostImpl::DidDispatchDOMContentLoadedEvent() base+0x2cc6850
 *   RenderFrameHostImpl::DidFinishLoad(GURL const&)         base+0x2cc4e00
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

static struct hook *HS1, *HS2, *HR1, *HR2;
static void f_s1(void *s) { printf("DELIVHOOK SEND  DidDispatchDOMContentLoadedEvent pid=%d\n", getpid()); fflush(0); unhook(HS1); ((void (*)(void *)) HS1->p)(s); install(HS1); }
static void f_s2(void *s, void *u) { printf("DELIVHOOK SEND  DidFinishLoad pid=%d\n", getpid()); fflush(0); unhook(HS2); ((void (*)(void *, void *)) HS2->p)(s, u); install(HS2); }
static void f_r1(void *s) { printf("DELIVHOOK RECV  DidDispatchDOMContentLoadedEvent pid=%d\n", getpid()); fflush(0); unhook(HR1); ((void (*)(void *)) HR1->p)(s); install(HR1); }
static void f_r2(void *s, void *u) { printf("DELIVHOOK RECV  DidFinishLoad pid=%d\n", getpid()); fflush(0); unhook(HR2); ((void (*)(void *, void *)) HR2->p)(s, u); install(HR2); }

static unsigned char *base = 0; static int installed = 0;
static void try_install(void) {
    unsigned n, i;
    if (installed) return;
    n = _dyld_image_count();
    for (i = 0; i < n; i++) { const char *nm = _dyld_get_image_name(i); if (nm && strstr(nm, "Electron Framework")) { base = (unsigned char *) _dyld_get_image_header(i); break; } }
    if (!base) return;
    installed = 1;
    HS1 = mk(base + 0x24c3970, (void *) f_s1);
    HS2 = mk(base + 0x24c3020, (void *) f_s2);
    HR1 = mk(base + 0x2cc6850, (void *) f_r1);
    HR2 = mk(base + 0x2cc4e00, (void *) f_r2);
    printf("DELIVHOOK install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("DELIVHOOK boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
