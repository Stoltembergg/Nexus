extern int __ulock_wait(unsigned,void *,unsigned long long,unsigned);
extern int *__error(void);extern int printf(const char *,...);
extern int __ulock_wake(unsigned,void *,unsigned long long);
int main(void){unsigned lock=3;*__error()=71;
int a=__ulock_wait(0x1000002,&lock,2,1000);
int b=__ulock_wait(0x1000002,&lock,3,1000);
int c=__ulock_wait(0x10000ff,&lock,3,1);
int d=__ulock_wake(0x10000ff,&lock,0);
int preserved=*__error();int e=__ulock_wait(2,&lock,3,1000), normal=*__error();
printf("ULOCK mismatch=%d timeout=%d bad_opcode=%d wake_bad=%d preserved_errno=%d normal=%d normal_errno=%d\n",a,b,c,d,preserved,e,normal);
return !(a>=0&&b==-60&&c==-22&&d==-22&&preserved==71&&e==-1&&normal==60);}
