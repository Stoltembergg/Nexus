typedef unsigned long pthread_t;
/* darling-lol M58j: raw epoll on accepted socket — bypasses libkqueue.
 * Uses Darling's __linux_epoll_* shims (exported from libsystem_kernel).
 * PASS = epoll_wait fires for the accepted socket.
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned long long u64;
typedef unsigned long ul;

struct sin_s { unsigned char len, fam; u16 port_net; u32 addr_be; u32 z1, z2; };
struct ep_evt_s { u32 events; u32 pad; ul data; };

extern int printf(const char*,...);
extern int fflush(void*);
extern int socket(int,int,int);
extern int bind(int,const void*,u32);
extern int listen(int,int);
extern int accept(int,void*,u32*);
extern int connect(int,const void*,u32);
extern int write(int,const void*,u32);
extern int read(int,void*,u32);
extern int close(int);
extern int usleep(unsigned);
extern int pthread_create(ul*,const void*,void*(*)(void*),void*);

/* Darling's exported epoll shims (from libsystem_kernel's for-libkqueue) */
extern int __linux_epoll_create1(int);
extern int __linux_epoll_ctl(int,int,int,void*);
extern int __linux_epoll_wait(int,void*,int,int);

static int lfd=-1, cfd=-1, sfd=-1;

static void *client_fn(void *a) {
    struct sin_s sa;
    __builtin_memset(&sa,0,sizeof(sa));
    sa.len=16; sa.fam=2;
    sa.port_net=(u16)(((5736&0xff)<<8)|((5736>>8)&0xff));
    sa.addr_be=0x0100007f;
    usleep(300000);
    cfd=socket(2,1,0);
    int r=connect(cfd,(void*)&sa,16);
    printf("client connect rc=%d\n",r); fflush(0);
    char b[500]; __builtin_memset(b,'E',500);
    write(cfd,b,500);
    usleep(100000);
    return 0;
}

int main(void) {
    printf("M58J-RAWEPOLL start\n"); fflush(0);
    lfd=socket(2,1,0);
    struct sin_s sa;
    __builtin_memset(&sa,0,sizeof(sa));
    sa.len=16; sa.fam=2;
    sa.port_net=(u16)(((5736&0xff)<<8)|((5736>>8)&0xff));
    sa.addr_be=0x0100007f;
    bind(lfd,(void*)&sa,16);
    listen(lfd,5);

    pthread_t th;
    pthread_create(&th,(void*)0,client_fn,(void*)0);
    usleep(500000);

    sfd=accept(lfd,(void*)0,(u32*)0);
    printf("accepted sfd=%d\n",sfd); fflush(0);

    int ep = __linux_epoll_create1(0);
    printf("epfd=%d\n",ep); fflush(0);
    struct ep_evt_s ee;
    __builtin_memset(&ee,0,sizeof(ee));
    ee.events=1; /* EPOLLIN */
    ee.data=sfd;
    int cr = __linux_epoll_ctl(ep,1,sfd,&ee);
    printf("epoll_ctl ret=%d\n",cr); fflush(0);

    struct ep_evt_s evs[4];
    int n = __linux_epoll_wait(ep,evs,4,5000);
    printf("epoll_wait n=%d\n",n); fflush(0);
    if(n>0){
        char b[1024];
        int rr=read(sfd,b,sizeof(b));
        printf("read %d bytes — PASS\n",rr);
    } else {
        printf("epoll_wait no events — FAIL\n");
    }
    fflush(0);
    return 0;
}
