/* Electron 108 runtime correction: hide, rather than create, empty datalists.
 * The on-disk product is unchanged. UUID and both functions' bytes must match.
 * The first17bytes contain only stack setup, so the trampoline needs no
 * instruction relocation. Nonempty suggestions execute the original function.
 */
typedef unsigned long size_t;
typedef unsigned long uintptr_t;
typedef long intptr_t;
extern void *_dyld_get_image_header(unsigned);
extern unsigned _dyld_image_count(void);
extern void _dyld_register_func_for_add_image(void (*)(const void *, intptr_t));
extern void *mmap(void *,size_t,int,int,int,long);
extern int mprotect(void *,size_t,int);
extern int munmap(void *,size_t);
extern void *memcpy(void *,const void *,size_t);
extern int memcmp(const void *,const void *,size_t);
extern long write(int,const void *,size_t);
static void (*original_show)(void *,const void *,const void *,const void *);
static void (*hide_popup)(void *);
static void show_popup(void *driver,const void *bounds,const void *values,const void *labels) {
    const void *const *vector=values;
    if (vector[0]==vector[1])
        hide_popup(driver);
    else
        original_show(driver,bounds,values,labels);
}
static void absolute_jump(unsigned char *p,const void *target) {
    p[0]=0x48;p[1]=0xb8;uintptr_t address=(uintptr_t)target;
    memcpy(p+2,&address,8);p[10]=0xff;p[11]=0xe0;
}
static void add_image(const void *header,intptr_t slide) {
    (void)slide;
    static int installed;
    if (installed) return;
    const unsigned *h=header;
    if (h[0]!=0xfeedfacf || h[1]!=0x01000007) return;
    static const unsigned char uuid[]={0x4c,0x4c,0x44,0x72,0x55,0x55,0x31,0x44,0xa1,0x43,0x03,0xd0,0x05,0xe4,0x38,0xed};
    const unsigned char *command=(const unsigned char *)header+32;
    int matched=0;
    for(unsigned i=0;i<h[4];i++) {
        const unsigned *c=(const unsigned *)command;
        if(c[0]==0x1b && c[1]==24 && !memcmp(command+8,uuid,16)) matched=1;
        if(c[1]<8) return;
        command+=c[1];
    }
    if(!matched)return;
    unsigned char *entry=(unsigned char *)header+0x44dbe0;
    unsigned char *hide=(unsigned char *)header+0x44dde0;
    static const unsigned char prologue[]={0x55,0x48,0x89,0xe5,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x83,0xec,0x58};
    static const unsigned char hide_bytes[]={0x55,0x48,0x89,0xe5,0x48,0x8b,0x7f,0x10,0x48,0x85,0xff,0x74,0x06,0x5d,0xe9,0x1d,0xa6,0x05,0x00,0x5d,0xc3};
    if(memcmp(entry,prologue,sizeof(prologue)) || memcmp(hide,hide_bytes,sizeof(hide_bytes)))return;
    unsigned char *trampoline=mmap(0,4096,3,0x1002,-1,0);
    if(trampoline==(void *)-1)return;
    memcpy(trampoline,prologue,sizeof(prologue));
    absolute_jump(trampoline+sizeof(prologue),entry+sizeof(prologue));
    if(mprotect(trampoline,4096,5)) {munmap(trampoline,4096);return;}
    void *page=(void *)((uintptr_t)entry&~(uintptr_t)4095);
    if(mprotect(page,4096,7)) {munmap(trampoline,4096);return;}
    original_show=(void *)trampoline;hide_popup=(void *)hide;
    unsigned char patch[sizeof(prologue)];
    for(unsigned i=0;i<sizeof(patch);i++)patch[i]=0x90;
    absolute_jump(patch,(const void *)show_popup);memcpy(entry,patch,sizeof(patch));
    mprotect(page,4096,5);installed=1;
    static const char message[]="EMPTY_AUTOFILL version-checked correction installed\n";
    write(2,message,sizeof(message)-1);
}
__attribute__((constructor)) static void initialize(void) {
    _dyld_register_func_for_add_image(add_image);
}
