extern int kqueue(void),pipe(int *),close(int),printf(const char *,...);
extern int gettimeofday(void *,void *);
struct timeval {long sec;int usec;};
static long now(void){struct timeval t;gettimeofday(&t,0);return t.sec*1000000L+t.usec;}
int main(void){int kq=kqueue();if(kq<0)return 1;long start=now();for(int i=0;i<200;i++){int f[2];if(pipe(f))return 2;close(f[0]);close(f[1]);}printf("KQUEUE_CLOSE cycles=200 elapsed_ms=%.2f\n",(now()-start)/1000.0);close(kq);return 0;}
