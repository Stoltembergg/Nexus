/* darling-lol M58cz: does fileport_makeport() + mach_port_mod_refs() work?
 * Chromium's IOSurface mach port (from Darling's fileport fallback) fails
 * mach_port_mod_refs(task, port, MACH_PORT_RIGHT_SEND, 1) with KERN_INVALID_NAME.
 * Test the primitive in isolation.
 */
typedef unsigned int u32;
extern int printf(const char *, ...);
extern int fflush(void *);
extern int open(const char *, int, ...);
extern int close(int);
extern int unlink(const char *);
extern int fileport_makeport(int fd, unsigned int *name);
extern int fileport_makefd(unsigned int name, int *fd);
extern int mach_port_mod_refs(unsigned int task, unsigned int name, int right, int delta);
extern unsigned int task_self_trap(void);

#define KERN_SUCCESS 0
#define MACH_PORT_RIGHT_SEND 0
#define MACH_PORT_RIGHT_RECEIVE 1

int main(void) {
	int fd, fd2 = -1, kr;
	unsigned int port = 0, task;

	unlink("/tmp/fptest.bin");
	fd = open("/tmp/fptest.bin", 0x0202 /*O_RDWR|O_CREAT*/, 0644);
	printf("FPTEST open fd=%d\n", fd); fflush(0);
	if (fd < 0) return 1;

	task = task_self_trap();
	printf("FPTEST task_self=%u\n", task); fflush(0);

	kr = fileport_makeport(fd, &port);
	printf("FPTEST fileport_makeport kr=%d port=%u\n", kr, port); fflush(0);
	if (kr != KERN_SUCCESS || port == 0) return 2;

	kr = mach_port_mod_refs(task, port, MACH_PORT_RIGHT_SEND, 1);
	printf("FPTEST mod_refs(SEND,+1) kr=%d (0=ok,15=invalid name)\n", kr); fflush(0);

	kr = mach_port_mod_refs(task, port, MACH_PORT_RIGHT_SEND, -1);
	printf("FPTEST mod_refs(SEND,-1) kr=%d\n", kr); fflush(0);

	kr = fileport_makefd(port, &fd2);
	printf("FPTEST fileport_makefd kr=%d fd=%d\n", kr, fd2); fflush(0);
	if (fd2 >= 0) close(fd2);

	kr = mach_port_mod_refs(task, port, MACH_PORT_RIGHT_RECEIVE, 1);
	printf("FPTEST mod_refs(RECEIVE,+1) kr=%d\n", kr); fflush(0);

	close(fd);
	printf("FPTEST done\n"); fflush(0);
	return 0;
}
