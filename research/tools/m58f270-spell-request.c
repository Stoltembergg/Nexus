/* Compile with -fblocks; verify the asynchronous AppKit completion contract. */
typedef struct { unsigned long location, length; } Range;
extern void *objc_getClass(const char *), *sel_registerName(const char *);
extern void objc_msgSend(void);
extern void dispatch_main(void), exit(int);
extern unsigned alarm(unsigned);
extern int printf(const char *, ...);
static long expected;
static int returned;
int main(void) {
    ((void *(*)(void *, void *))objc_msgSend)(objc_getClass("NSAutoreleasePool"), sel_registerName("new"));
    void *checker = ((void *(*)(void *, void *))objc_msgSend)(objc_getClass("NSSpellChecker"), sel_registerName("sharedSpellChecker"));
    void *text = ((void *(*)(void *, void *, const char *))objc_msgSend)(objc_getClass("NSString"), sel_registerName("stringWithUTF8String:"), "");
    void (^completion)(long, void *, void *, long) = ^(long sequence, void *results, void *orthography, long words) {
        int pass = returned && sequence == expected && results != 0 && words == 0;
        printf("SPELL_REQUEST returned=%d sequence_matches=%d results_present=%d words=%ld\n", returned, sequence == expected, results != 0, words);
        exit(!pass);
    };
    Range range = {0, 0};
    expected = ((long (*)(void *, void *, void *, Range, unsigned long long, void *, long, void *))objc_msgSend)(
        checker, sel_registerName("requestCheckingOfString:range:types:options:inSpellDocumentWithTag:completionHandler:"),
        text, range, 2, 0, 0, (void *)completion);
    returned = 1;
    alarm(10);
    dispatch_main();
    return 1;
}
