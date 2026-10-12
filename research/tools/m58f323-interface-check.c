struct sa {unsigned char len,family;};
struct ifa {struct ifa *next;char *name;unsigned int flags;struct sa *addr,*netmask,*dst;void *data;};
extern int getifaddrs(struct ifa **);extern void freeifaddrs(struct ifa *);extern int printf(const char *,...);
int main(void){struct ifa *a=0;int r=getifaddrs(&a),total=0,up=0,nonloop=0;for(struct ifa *p=a;p;p=p->next){total++;if(p->flags&1){up++;if(!(p->flags&8)&&p->addr&&p->addr->family==2)nonloop++;}}if(a)freeifaddrs(a);printf("INTERFACES result=%d total=%d up=%d active_ipv4=%d\n",r,total,up,nonloop);return r||!nonloop;}
