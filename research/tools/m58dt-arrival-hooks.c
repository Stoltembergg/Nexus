/* darling-lol M58dt: does the renderer's LocalFrameHost message reach the
 * browser's mojom dispatcher?
 *   blink::mojom::blink::LocalFrameHostProxy::DidDispatchDOMContentLoadedEvent  base+0x24c3970 (renderer send)
 *   blink::mojom::blink::LocalFrameHostProxy::DidFinishLoad                     base+0x24c3020 (renderer send)
 *   blink::mojom::LocalFrameHostStubDispatch::Accept(LocalFrameHost*, mojo::Message*) base+0x1331e90 (browser recv)
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

static struct hook *HS1, *HS2, *HA;
static unsigned long c_a = 0;
static void f_s1(void *s) { printf("ARRHOOK SEND DidDispatchDOMContentLoadedEvent pid=%d\n", getpid()); fflush(0); unhook(HS1); ((void (*)(void *)) HS1->p)(s); install(HS1); }
static void f_s2(void *s, void *u) { printf("ARRHOOK SEND DidFinishLoad pid=%d\n", getpid()); fflush(0); unhook(HS2); ((void (*)(void *, void *)) HS2->p)(s, u); install(HS2); }
static void f_a(void *impl, void *msg) {
    c_a++;
    /* mojo::Message: name (interface+method ordinal) is a uint32 in the header;
     * log both the entry and a couple of plausible header words for id. */
    unsigned *w = (unsigned *) msg;
    printf("ARRHOOK RECV Accept pid=%d n=%lu msg=%p w0=0x%x w1=0x%x w2=0x%x w3=0x%x\n",
        getpid(), c_a, msg, w ? w[0] : 0, w ? w[1] : 0, w ? w[2] : 0, w ? w[3] : 0);
    fflush(0);
    unhook(HA); ((void (*)(void *, void *)) HA->p)(impl, msg); install(HA);
}

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
    HA = mk(base + 0x1331e90, (void *) f_a);
    printf("ARRHOOK install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("ARRHOOK boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
