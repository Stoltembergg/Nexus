/* darling-lol M58dv: decode the mojo method name at LocalFrameHostStubDispatch::Accept.
 *   blink::mojom::LocalFrameHostStubDispatch::Accept(LocalFrameHost*, mojo::Message*) base+0x1331e90
 * MessageHeader { u32 version@0; u32 interface_id@4; u32 name@8; u32 flags@12; u64 request_id@16 }
 * Message::header() == data(). Dump the Message's first qwords and try several
 * offsets for a payload/data pointer, reading a candidate (version, name) pair.
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
static void f_s1(void *s) { printf("MOJOHOOK SEND DidDispatchDOMContentLoadedEvent pid=%d\n", getpid()); fflush(0); unhook(HS1); ((void(*)(void*))HS1->p)(s); install(HS1); }
static void f_s2(void *s, void *u) { printf("MOJOHOOK SEND DidFinishLoad pid=%d\n", getpid()); fflush(0); unhook(HS2); ((void(*)(void*,void*))HS2->p)(s,u); install(HS2); }
static void f_a(void *impl, void *msg) {
    unsigned long long *q = (unsigned long long *) msg;
    unsigned long long w[8];
    int i;
    c_a++;
    for (i = 0; i < 8; ++i) w[i] = q[i];
    printf("MOJOHOOK ACCEPT pid=%d n=%lu msg=%p q0=%llx q1=%llx q2=%llx q3=%llx q4=%llx q5=%llx q6=%llx q7=%llx\n",
        getpid(), c_a, msg, w[0], w[1], w[2], w[3], w[4], w[5], w[6], w[7]);
    for (i = 1; i <= 3; ++i) {
        void *p = (void *) w[i];
        if ((unsigned long long) p > 0x10000ULL && (unsigned long long) p < 0x800000000000ULL) {
            const unsigned *h = (const unsigned *) p;
            printf("MOJOHOOK   off%llu->%p version=%u interface=%u name=%u(0x%x) flags=0x%x\n",
                (unsigned long long) (i * 8), p, h[0], h[1], h[2], h[2], h[3]);
        }
    }
    fflush(0);
    unhook(HA); ((void(*)(void*,void*))HA->p)(impl, msg); install(HA);
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
    printf("MOJOHOOK install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("MOJOHOOK boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
