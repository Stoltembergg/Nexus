/* Failure must leave no disposable, freed converter handle. */
typedef struct {double rate;unsigned format,flags,packetBytes,packetFrames,frameBytes,channels,bits,reserved;} Format;
extern int AudioConverterNew(const Format *,const Format *,void **);
extern int AudioConverterDispose(void *);
extern int printf(const char *,...);
int main(void) {
 void *converter=(void*)0x1234;
 Format source={44100,0x6c70636d,12,4,1,4,0,16,0};
 Format dest={44100,0x6c70636d,12,4,1,4,2,16,0};
 int status=AudioConverterNew(0,&dest,&converter);
 if(!status||converter)return 1;
 converter=(void*)0x1234;
 status=AudioConverterNew(&source,&dest,&converter);
 printf("AUDIO failure_status=%d output_null=%d\n",status,converter==0);
 if (!status||converter!=0) return 2;
 source.channels=2;
 status=AudioConverterNew(&source,&dest,&converter);
 if (status||!converter) return 3;
 status=AudioConverterDispose(converter);
 printf("AUDIO valid_converter_dispose_status=%d\n",status);
 return status!=0;
}
