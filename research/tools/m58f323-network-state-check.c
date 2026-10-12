/* Validate real primary-interface data without printing addresses or app data. */
typedef const void *Ref;
typedef unsigned char Boolean;
extern Ref kSCDynamicStoreDomainState,kSCEntNetIPv4,kSCEntNetIPv6,kSCDynamicStorePropNetPrimaryInterface;
extern Ref SCDynamicStoreCreate(Ref,Ref,void *,void *);
extern Ref SCDynamicStoreKeyCreateNetworkGlobalEntity(Ref,Ref,Ref);
extern Ref SCDynamicStoreCopyValue(Ref,Ref);
extern Ref CFStringCreateWithCString(Ref,const char *,unsigned int);
extern Boolean CFEqual(Ref,Ref);
extern Ref CFDictionaryGetValue(Ref,Ref);
extern void CFRelease(Ref);
extern int printf(const char *,...);
int main(void){
 Ref label=CFStringCreateWithCString(0,"synthetic network probe",0x08000100);
 Ref store=SCDynamicStoreCreate(0,label,0,0);
 Ref key=SCDynamicStoreKeyCreateNetworkGlobalEntity(0,kSCDynamicStoreDomainState,kSCEntNetIPv4);
 Ref expected=CFStringCreateWithCString(0,"State:/Network/Global/IPv4",0x08000100);
 Ref value=SCDynamicStoreCopyValue(store,key);
 Ref primary=value?CFDictionaryGetValue(value,kSCDynamicStorePropNetPrimaryInterface):0;
 Ref unknown=CFStringCreateWithCString(0,"State:/Unknown",0x08000100);
 Ref absent=SCDynamicStoreCopyValue(store,unknown);
 int ok=CFEqual(key,expected)&&primary&&!absent;
 printf("NETWORK_STATE canonical_key=%d primary_present=%d unknown_absent=%d pass=%d\n",CFEqual(key,expected),primary!=0,absent==0,ok);
 if(value)CFRelease(value);CFRelease(unknown);CFRelease(expected);CFRelease(key);CFRelease(store);CFRelease(label);
 return !ok;
}
