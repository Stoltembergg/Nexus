/* darling-lol M58f4: minimal cold-forward-subpath probe (no hot hooks).
 *
 * Only the two notification proxies, the LFH stub dispatch, and the controller's
 * cold per-message forward sub-path on the 0x3e468f0 branch:
 *   Message::Message(mojo::Message&&) copies at 0x3e46928 and 0x3e46942
 *   (the branch the controller takes when the message header flag 0x4 is set)
 * plus the inline tail-call site 0x3e467ca (no-forward path).
 *
 * Kept to cold paths so it does not perturb the renderer/repro.
 */
extern int printf(const char *, ...);
extern int fflush(void *);
extern int mprotect(void *, unsigned long, int);
extern int getpid(void);
extern void *mmap(void *, unsigned long, int, int, int, long);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);
extern void _dyld_register_func_for_add_image(void (*)(const void *, long));

#define ORD_DCL 0x10f795c8u
#define ORD_FL  0x4ced459cu
static const char *tag(unsigned o) {
    if (o == ORD_FL) return " DidFinishLoad";
    if (o == ORD_DCL) return " DidDispatchDOMContentLoadedEvent";
    return "";
}

struct thook { unsigned char *p; void *fn; unsigned char *tramp; int n; };
static struct thook TH[16]; static int nTH = 0;
static void *install_tramp(void *addr, void *fn, int n) {
    struct thook *t = &TH[nTH++];
    unsigned char *p = (unsigned char *) addr;
    unsigned long pg = (unsigned long) p & ~0xFFFUL;
    unsigned char *tr; int i;
    if (mprotect((void *) pg, 0x2000, 7) != 0) return 0;
    tr = (unsigned char *) mmap(0, 0x1000, 7, 0x1002, -1, 0);
    if (!tr || tr == (void *) -1) return 0;
    for (i = 0; i < n; i++) tr[i] = p[i];
    tr[n] = 0x48; tr[n+1] = 0xB8;
    { unsigned long a = (unsigned long)(p + n); for (i = 0; i < 8; i++) tr[n+2+i] = (a >> (8*i)) & 0xFF; }
    tr[n+10] = 0xFF; tr[n+11] = 0xE0;
    p[0] = 0x48; p[1] = 0xB8;
    { unsigned long a = (unsigned long) fn; for (i = 0; i < 8; i++) p[2+i] = (a >> (8*i)) & 0xFF; }
    p[10] = 0xFF; p[11] = 0xE0;
    t->p = p; t->fn = fn; t->tramp = tr; t->n = n;
    return tr;
}
static unsigned ctr = 0;
static inline void *hdr_of(void *m) { return m ? *(void **)((char *)m + 0x18) : 0; }
static inline unsigned ord_of(void *m) { void *h = hdr_of(m); return h ? *(unsigned *)((char *)h + 0xc) : 0; }

static int (*tramp_send_dcl)(void *);
static int (*tramp_send_fl)(void *, void *);
static int (*tramp_lfh)(void *, void *);
static void (*tramp_mm1)(void *, void *);
static void (*tramp_mm2)(void *, void *);
static void (*tramp_nf)(void *, void *);

static int f_send_dcl(void *self) { printf("M58F4 n=%u SEND_DCL pid=%d\n", ++ctr, getpid()); fflush(0); return tramp_send_dcl(self); }
static int f_send_fl(void *self, void *kurl) { printf("M58F4 n=%u SEND_FL pid=%d\n", ++ctr, getpid()); fflush(0); return tramp_send_fl(self, kurl); }
static int f_lfh(void *impl, void *msg) {
    unsigned o = ord_of(msg);
    printf("M58F4 n=%u LFH_DISPATCH pid=%d ord=0x%08x%s\n", ++ctr, getpid(), o, tag(o)); fflush(0);
    return tramp_lfh(impl, msg);
}
static void f_mm1(void *a, void *b) {
    unsigned o = ord_of(b);
    printf("M58F4 n=%u BRANCH_COPY1 pid=%d ord=0x%08x%s\n", ++ctr, getpid(), o, tag(o)); fflush(0);
    tramp_mm1(a, b);
}
static void f_mm2(void *a, void *b) {
    unsigned o = ord_of(b);
    printf("M58F4 n=%u BRANCH_COPY2 pid=%d ord=0x%08x%s\n", ++ctr, getpid(), o, tag(o)); fflush(0);
    tramp_mm2(a, b);
}
static void f_nf(void *self, void *msg) {
    unsigned o = ord_of(msg);
    printf("M58F4 n=%u NOFWD_TAILCALL pid=%d ord=0x%08x%s\n", ++ctr, getpid(), o, tag(o)); fflush(0);
    tramp_nf(self, msg);
}

static unsigned char *base = 0; static int installed = 0;
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
    tramp_send_dcl = install_tramp(base + 0x24c3970, (void *) f_send_dcl, 20);
    tramp_send_fl  = install_tramp(base + 0x24c3020, (void *) f_send_fl, 20);
    tramp_lfh      = install_tramp(base + 0x1331e90, (void *) f_lfh, 20);
    tramp_mm1      = install_tramp(base + 0x3e46928, (void *) f_mm1, 16);
    tramp_mm2      = install_tramp(base + 0x3e46942, (void *) f_mm2, 16);
    printf("M58F4 install pid=%d base=%p hooked=%d\n", getpid(), (void *) base, nTH); fflush(0);
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("M58F4 boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
