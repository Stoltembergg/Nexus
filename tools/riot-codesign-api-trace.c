/* Test-probe instrumentation only; never inserted into League or Vanguard. */
#include <Security/CMSDecoder.h>
#include <Security/SecTrust.h>
#include <stdio.h>
#include <unistd.h>
extern OSStatus CMSDecoderSetSearchKeychain(CMSDecoderRef, CFTypeRef);

static void report(const char *name, OSStatus status) {
    char line[160];
    int length = snprintf(line, sizeof(line), "CODESIGN_API %s=%d\n", name, (int)status);
    write(2, line, length);
}
#define TRACE(name, parameters, arguments) \
    static OSStatus trace_##name parameters { \
        OSStatus status = name arguments; report(#name, status); return status; \
    } \
    __attribute__((used, section("__DATA,__interpose"))) \
    static const struct { const void *replacement; const void *original; } \
    interpose_##name = { (const void *)trace_##name, (const void *)name };

TRACE(CMSDecoderCreate, (CMSDecoderRef *out), (out))
TRACE(CMSDecoderUpdateMessage, (CMSDecoderRef decoder, const void *bytes, size_t length),
    (decoder, bytes, length))
TRACE(CMSDecoderSetDetachedContent, (CMSDecoderRef decoder, CFDataRef data), (decoder, data))
TRACE(CMSDecoderFinalizeMessage, (CMSDecoderRef decoder), (decoder))
TRACE(CMSDecoderSetSearchKeychain, (CMSDecoderRef decoder, CFTypeRef keychain), (decoder, keychain))
TRACE(CMSDecoderCopySignerStatus, (CMSDecoderRef decoder, size_t index, CFTypeRef policies,
    Boolean evaluate, CMSSignerStatus *signer, SecTrustRef *trust, OSStatus *cert),
    (decoder, index, policies, evaluate, signer, trust, cert))
TRACE(SecTrustEvaluate, (SecTrustRef trust, SecTrustResultType *result), (trust, result))
