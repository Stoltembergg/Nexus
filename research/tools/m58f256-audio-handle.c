/* Validate opaque converter ownership and reject stale or invalid disposal. */
typedef struct {double rate;unsigned format,flags,packetBytes,packetFrames,frameBytes,channels,bits,reserved;} Format;
extern int AudioConverterNewSpecific(const Format *,const Format *,unsigned,const void *,void **);
extern int AudioConverterDispose(void *);
extern int printf(const char *,...);
int main(void) {
 if(AudioConverterDispose(0)!=-50 || AudioConverterDispose((void*)0x1234)!=-50)return 4;
 void *converter=(void*)0x1234;
 Format source={44100,0x6c70636d,12,4,1,4,0,16,0};
 Format dest={44100,0x6c70636d,12,4,1,4,2,16,0};
 int status=AudioConverterNewSpecific(0,&dest,0,0,&converter);
 if(!status||converter)return 1;
 converter=(void*)0x1234;
 status=AudioConverterNewSpecific(&source,&dest,0,0,&converter);
 printf("AUDIO failure_status=%d output_null=%d\n",status,converter==0);
 if (!status||converter!=0) return 2;
 source.channels=2;
 status=AudioConverterNewSpecific(&source,&dest,0,0,&converter);
 if (status||!converter) return 3;
 status=AudioConverterDispose(converter);
 printf("AUDIO valid_converter_dispose_status=%d\n",status);
 if(status)return 5;
 int stale=AudioConverterDispose(converter);
 printf("AUDIO stale_handle_status=%d\n",stale);
 return stale!=-50;
}
