/* Verify NULL-now, timeval units, and invalid microsecond handling. */
struct TV { long seconds; int microseconds; int pad; };
extern int open(const char *,int,...),close(int),futimes(int,const struct TV *),printf(const char*,...);
extern int *__error(void);
int main(int argc,char **argv){
 int fd=open("/private/tmp/riot-m291-utime-test",0x201,0600);if(fd<0)return 1;
 struct TV tv[2]={{1234567890,123456,0},{1234567890,654321,0}};
 int invalid=argc>1&&argv[1][0]=='i';if(invalid)tv[0].microseconds=1000000;
 int result=futimes(fd,argc>1&&argv[1][0]=='n'?0:tv),error=*__error();close(fd);
 int ok=invalid?(result==-1&&error==22):result==0;
 printf("FUTIMES kind=%c result=%d errno=%d pass=%d\n",argc>1?argv[1][0]:'e',result,error,ok);return ok?0:1;
}
