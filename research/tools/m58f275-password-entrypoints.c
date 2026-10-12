/* Verify password-focus imports and the owned TIS list without credentials. */
extern int EnableSecureEventInput(void), DisableSecureEventInput(void);
extern int TSMSetDocumentProperty(void *, unsigned, unsigned, void *);
extern int TSMRemoveDocumentProperty(void *, unsigned);
extern const void *TISCreateASCIICapableInputSourceList(void);
extern unsigned long CFGetTypeID(const void *), CFArrayGetTypeID(void);
extern long CFArrayGetCount(const void *);
extern void CFRelease(const void *);
extern int printf(const char *, ...);
int main(void) {
    int enable = EnableSecureEventInput(), disable = DisableSecureEventInput();
    int set = TSMSetDocumentProperty(0, 0, 0, 0);
    int remove = TSMRemoveDocumentProperty(0, 0);
    const void *list = TISCreateASCIICapableInputSourceList();
    int valid = list && CFGetTypeID(list) == CFArrayGetTypeID();
    printf("PASSWORD_API enable=%d disable=%d set=%d remove=%d array=%d count=%ld\n",
        enable, disable, set, remove, valid, valid ? CFArrayGetCount(list) : -1);
    if (list) CFRelease(list);
    return enable == -4 && disable == -4 && set == -4 && remove == -4 && valid ? 0 : 1;
}
