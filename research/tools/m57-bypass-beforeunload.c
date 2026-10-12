/* Electron 22.3.27 diagnostic workaround for a navigation deadlock.
 * Force RenderFrameHostImpl::ShouldDispatchBeforeUnload() to return false.
 * This is version-specific and intended to prove that the renderer
 * beforeunload round-trip is the stalled boundary. */
extern int mprotect(void *, unsigned long, int);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);

static unsigned char should_dispatch_beforeunload(void *self, int check_subframes,
                                                   int *send_ipc) {
    (void)self;
    (void)check_subframes;
    if (send_ipc)
        *send_ipc = 0;
    return 0;
}

__attribute__((constructor)) static void install(void) {
    unsigned i;
    unsigned char *base = 0;
    unsigned char *target;
    unsigned long replacement = (unsigned long)should_dispatch_beforeunload;
    unsigned char jump[12] = {0x48, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0xff, 0xe0};

    for (i = 0; i < _dyld_image_count(); i++) {
        const char *name = _dyld_get_image_name(i);
        if (name && strstr(name, "Versions/A/Electron Framework")) {
            base = (unsigned char *)_dyld_get_image_header(i);
            break;
        }
    }
    if (!base)
        return;

    target = base + 0x2ccd5f0UL;
    for (i = 0; i < 8; i++)
        jump[2 + i] = (replacement >> (8 * i)) & 0xff;
    mprotect((void *)((unsigned long)target & ~0xfffUL), 0x2000, 7);
    for (i = 0; i < sizeof(jump); i++)
        target[i] = jump[i];
}
