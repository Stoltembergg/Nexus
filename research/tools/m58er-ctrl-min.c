/* darling-lol M58er: minimal probe of the browser's IPC-channel controller.
 *
 * Goal: read, at the ENTRY of the ChannelAssociatedGroupController::Accept copy
 * the dispatcher actually calls (base+0x3e46690), the interface id the controller
 * will route on (`[header+8]`) and the return, for the two dropped LocalFrameHost
 * notifications (0x10f795c8 / 0x4ced459c) vs. the eight that dispatch.
 *
 * The entry read happens AFTER MessageDispatcher::Accept has run its validator, so
 * this is the post-validation interface id the map lookup uses.
 *
 * Kept deliberately small (4 hooks) because the hot controller hook perturbs the
 * renderer when too much else is installed.
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
static int is_ours(unsigned o) { return o == ORD_DCL || o == ORD_FL; }
static int is_lfh8(unsigned o) {
    return o == 0x5b6c7979u || o == 0x125b9a70u || o == 0x5b22b2a9u ||
           o == 0x3aadd8c1u || o == 0x35e9147bu || o == 0x23969e3du;
}
static const char *tag(unsigned o) {
    if (o == ORD_FL) return " DidFinishLoad";
    if (o == ORD_DCL) return " DidDispatchDOMContentLoadedEvent";
    return "";
}

struct thook { unsigned char *p; void *fn; unsigned char *tramp; int n; };
static struct thook TH[8]; static int nTH = 0;
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
static inline unsigned ifid_of(void *m) { void *h = hdr_of(m); return h ? *(unsigned *)((char *)h + 0x8) : 0; }

static int (*tramp_send_dcl)(void *);
static int (*tramp_send_fl)(void *, void *);
static int (*tramp_lfh)(void *, void *);
static int (*tramp_ctrl)(void *, void *);

static int f_send_dcl(void *self) {
    printf("M58ER n=%u SEND_DCL pid=%d\n", ++ctr, getpid()); fflush(0);
    return tramp_send_dcl(self);
}
static int f_send_fl(void *self, void *kurl) {
    printf("M58ER n=%u SEND_FL pid=%d\n", ++ctr, getpid()); fflush(0);
    return tramp_send_fl(self, kurl);
}
static int f_lfh(void *impl, void *msg) {
    unsigned ord = ord_of(msg);
    printf("M58ER n=%u LFH_DISPATCH pid=%d ordinal=0x%08x ifid=%u%s\n", ++ctr, getpid(), ord, ifid_of(msg), tag(ord)); fflush(0);
    return tramp_lfh(impl, msg);
}
static int f_ctrl(void *self, void *msg) {
    unsigned ord = ord_of(msg);
    unsigned ifid = ifid_of(msg);
    int r;
    if (!is_ours(ord) && !is_lfh8(ord)) return tramp_ctrl(self, msg);
    r = tramp_ctrl(self, msg);
    printf("M58ER n=%u CAGC_ACCEPT pid=%d ordinal=0x%08x ifid=%u ret=%d%s\n", ++ctr, getpid(), ord, ifid, r & 0xff, tag(ord)); fflush(0);
    return r;
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
    /* The hot controller Accept hook perturbs the renderer helper and stops the
     * second send, so install it only in the browser (main) process. */
    {
        const char *img0 = _dyld_get_image_name(0);
        int is_helper = img0 && strstr(img0, "Helper") != 0;
        tramp_send_dcl = install_tramp(base + 0x24c3970, (void *) f_send_dcl, 20);
        tramp_send_fl  = install_tramp(base + 0x24c3020, (void *) f_send_fl, 20);
        if (!is_helper) {
            tramp_lfh  = install_tramp(base + 0x1331e90, (void *) f_lfh, 20);
            tramp_ctrl = install_tramp(base + 0x3e46690, (void *) f_ctrl, 20);
        }
        printf("M58ER install pid=%d img0=%s helper=%d ctrl=%p hooked=%d\n",
               getpid(), img0 ? img0 : "?", is_helper, (void *) tramp_ctrl, nTH); fflush(0);
    }
}
static void on_add(const void *h, long s) { (void) h; (void) s; try_install(); }
__attribute__((constructor)) static void boot(void) {
    printf("M58ER boot pid=%d\n", getpid()); fflush(0);
    _dyld_register_func_for_add_image((void (*)(const void *, long)) on_add);
    try_install();
}
