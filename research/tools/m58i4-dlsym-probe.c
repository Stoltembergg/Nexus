/* darling-lol M58i4: resolve the TRUE serving image for guest kqueue/kevent.
 * Uses dladdr on the resolved symbols — prints dli_fname/dli_sname/dli_saddr.
 */
typedef unsigned int u32;
extern int printf(const char *, ...);
extern int fflush(void *);
extern void *dlsym(void *, const char *);
extern int dladdr(void *, void *);
extern unsigned int sleep(unsigned int);
extern int kqueue(void);

struct dlinfo {
	const char *dli_fname;
	void       *dli_fbase;
	const char *dli_sname;
	void       *dli_saddr;
};

#define RTLD_DEFAULT ((void *)0)  /* RTLD_DEFAULT = 0 on darwin */

int main(void) {
	void *sym;
	struct dlinfo info;
	int i;
	const char *names[4] = {(const char *)"kqueue", (const char *)"kevent",
	                        (const char *)"kevent64_impl", (const char *)"kevent_impl"};
	printf("M58I4 dladdr probe start\n"); fflush(0);
	for (i = 0; i < 4; ++i) {
		sym = dlsym(RTLD_DEFAULT, names[i]);
		printf("%s -> %p\n", names[i], sym);
		fflush(0);
		if (sym) {
			__builtin_memset(&info, 0, sizeof(info));
			int ok = dladdr(sym, (void *)&info);
			printf("  dladdr ok=%d fname=%s sname=%s saddr=%p\n", ok,
				info.dli_fname ? info.dli_fname : "(null)",
				info.dli_sname ? info.dli_sname : "(null)",
				info.dli_saddr);
			fflush(0);
		}
	}
	return 0;
}
