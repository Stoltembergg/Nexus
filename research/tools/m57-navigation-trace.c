/* Narrow Electron 22.3.27 navigation trace: browser request milestones and
 * renderer-side NavigationClient Mojo dispatch only. */
extern int open(const char *, int, ...);
extern long write(int, const void *, unsigned long);
extern int close(int), mprotect(void *, unsigned long, int), getpid(void);
extern unsigned _dyld_image_count(void);
extern const char *_dyld_get_image_name(unsigned);
extern const char *_dyld_get_image_header(unsigned);
extern char *strstr(const char *, const char *);

enum { LOADED=1, START, START_EXIT, DID_START, DID_START_EXIT, BEGIN,
       COMMIT, READY_TO_COMMIT, STUB_DISPATCH };
static const unsigned long offsets[] = {
    0, 0, 0x2c84b30UL, 0, 0x2e38660UL, 0, 0x2c88820UL,
    0x2c89670UL, 0x416030UL, 0x14d0d20UL
};
struct record { unsigned pid, event; unsigned long value; };
struct hook { unsigned char *p, saved[12]; unsigned long fn; };
static struct hook hooks[9];
static volatile int locks[9];

static void emit(unsigned event, unsigned long value) {
    struct record r={(unsigned)getpid(),event,value};
    int fd=open("/Volumes/SystemRoot/tmp/opencode/m57-navigation.bin",1|0x200|8,0644);
    if(fd>=0){write(fd,&r,sizeof(r));close(fd);}
}
static void patch(struct hook*h,int on){unsigned char j[12];int i;
    mprotect((void*)((unsigned long)h->p&~0xfffUL),0x2000,7);
    if(!on){for(i=0;i<12;i++)h->p[i]=h->saved[i];return;}
    j[0]=0x48;j[1]=0xb8;for(i=0;i<8;i++)j[2+i]=(h->fn>>(8*i))&255;
    j[10]=0xff;j[11]=0xe0;for(i=0;i<12;i++)h->p[i]=j[i];
}
static void call0(unsigned n,unsigned exit_n,void*s){while(__sync_lock_test_and_set(&locks[n],1)){}
    patch(&hooks[n],0);emit(n,(unsigned long)s);((void(*)(void*))hooks[n].p)(s);emit(exit_n,(unsigned long)s);
    patch(&hooks[n],1);__sync_lock_release(&locks[n]);}
static void start(void*s){call0(START,START_EXIT,s);}
static void did_start(void*s,void*h){while(__sync_lock_test_and_set(&locks[DID_START],1)){}
    patch(&hooks[DID_START],0);emit(DID_START,(unsigned long)h);
    ((void(*)(void*,void*))hooks[DID_START].p)(s,h);emit(DID_START_EXIT,(unsigned long)h);
    patch(&hooks[DID_START],1);__sync_lock_release(&locks[DID_START]);}
static void begin(void*s){call0(BEGIN,0,s);}
static void commit(void*s){call0(COMMIT,0,s);}
static void ready(void*s,void*h){while(__sync_lock_test_and_set(&locks[READY_TO_COMMIT],1)){}
    patch(&hooks[READY_TO_COMMIT],0);emit(READY_TO_COMMIT,(unsigned long)h);
    ((void(*)(void*,void*))hooks[READY_TO_COMMIT].p)(s,h);
    patch(&hooks[READY_TO_COMMIT],1);__sync_lock_release(&locks[READY_TO_COMMIT]);}
static unsigned stub(void*i,void*m,void*r){unsigned out;
    while(__sync_lock_test_and_set(&locks[STUB_DISPATCH],1)){}
    patch(&hooks[STUB_DISPATCH],0);emit(STUB_DISPATCH,(unsigned long)m);
    out=((unsigned(*)(void*,void*,void*))hooks[STUB_DISPATCH].p)(i,m,r);
    patch(&hooks[STUB_DISPATCH],1);__sync_lock_release(&locks[STUB_DISPATCH]);return out;}
static void setup(struct hook*h,unsigned char*b,unsigned n,void*fn){int i;
    h->p=b+offsets[n];h->fn=(unsigned long)fn;for(i=0;i<12;i++)h->saved[i]=h->p[i];patch(h,1);}
__attribute__((constructor))static void install(void){unsigned i;unsigned char*b=0;
    for(i=0;i<_dyld_image_count();i++){const char*n=_dyld_get_image_name(i);
        if(n&&strstr(n,"Versions/A/Electron Framework")){b=(unsigned char*)_dyld_get_image_header(i);break;}}
    if(!b)return;emit(LOADED,(unsigned long)b);
    setup(&hooks[COMMIT],b,COMMIT,commit);}
