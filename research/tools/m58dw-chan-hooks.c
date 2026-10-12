/* darling-lol M58dw: bracket the renderer->browser message loss at the channel.
 *   mojo::Connector::Accept(mojo::Message*)                        base+0x3afa280  (receive, per message)
 *   blink::mojom::LocalFrameHostStubDispatch::Accept(LFH*, Message*) base+0x1331e90
 *   renderer sends: LocalFrameHostProxy::DidDispatchDOMContentLoadedEvent 0x24c3970
 *                   LocalFrameHostProxy::DidFinishLoad                    0x24c3020
 * Name decode: payload() (0x3b17e80) -> header ~ payload-24; name = (u32*)header[2].
 * payload_num_bytes() (0x3b17eb0).
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

static const unsigned char *(*p_payload)(const void *);
static unsigned (*p_pnum)(const void *);

static struct hook *HS1, *HS2, *HR;
static unsigned long c_conn = 0, c_s1 = 0, c_s2 = 0;

static void f_s1(void *s) { c_s1++; printf("CHANHOOK SEND DidDispatchDOMContentLoadedEvent pid=%d n=%lu\n", getpid(), c_s1); fflush(0); unhook(HS1); ((void(*)(void*))HS1->p)(s); install(HS1); }
static void f_s2(void *s, void *u) { c_s2++; printf("CHANHOOK SEND DidFinishLoad pid=%d n=%lu\n", getpid(), c_s2); fflush(0); unhook(HS2); ((void(*)(void*,void*))HS2->p)(s,u); install(HS2); }
static void f_conn(void *self, void *msg) {
    c_conn++;
    if (c_conn <= 80) {
        unsigned nb = 0, nm = 0;
        const unsigned char *pl = p_payload ? p_payload(msg) : 0;
        if (p_pnum) nb = p_pnum(msg);
        if (pl) { const unsigned *h = (const unsigned *)(pl - 24); nm = h[2]; }
        printf("CHANHOOK RECV Connector::Accept pid=%d n=%lu bytes=%u name=%u pl=%p\n", getpid(), c_conn, nb, nm, (void*) pl);
        fflush(0);
    }
    unhook(HR); ((void(*)(void*,void*))HR->p)(self, msg); install(HR);
}

static unsigned char *base = 0; static int installed = 0;
static void try_install(void) {
    unsigned n, i;
    if (installed) return;
    n = _dyld_image_count();
    for (i = 0; i < n; i++) { const char *nm = _dyld_get_image_name(i); if (nm && strstr(nm, "Electron Framework")) { base = (unsigned char *) _dyld_get_image_header(i); break; } }
    if (!base) return;
    installed = 1;
    p_payload = (const unsigned char *(*)(const void *)) (base + 0x3b17e80);
    p_pnum = (unsigned (*)(const void *)) (base + 0x3b17eb0);
    HS1 = mk(base + 0x24c3970, (void *) f_s1);
    HS2 = mk(base + 0x24c3020, (void *) f_s2);
    HR = mk(base + 0x3afa280, (void *) f_conn);
    printf("CHANHOOK install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("CHANHOOK boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
