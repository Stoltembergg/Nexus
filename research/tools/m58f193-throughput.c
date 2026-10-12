/* darling-lol M58F193: raw guest loopback throughput, isolated from any app
 * event loop.  Two processes (fork) do BLOCKING reads/writes:
 *   1. AF_UNIX socketpair
 *   2. TCP 127.0.0.1 listener/connect (the path the app's static server uses)
 * alarm(45) aborts a stalled run.  Headerless guest C.
 *
 * Build: see patches/m58f3-psynch-cvwait-overflow.patch recipe.
 */
typedef unsigned long size_t;
typedef unsigned int u32;
typedef unsigned long long u64;
typedef long ssize_t;

extern int printf(const char*, ...);
extern long write(int, const void*, unsigned long);
extern long read(int, const void*, unsigned long);
extern int socket(int, int, int);
extern int socketpair(int, int, int, int*);
extern int bind(int, const void*, unsigned int);
extern int listen(int, int);
extern int accept(int, void*, unsigned int*);
extern int connect(int, const void*, unsigned int);
extern int getsockname(int, void*, unsigned int*);
extern int close(int);
extern int fork(void);
extern void _exit(int);
extern unsigned int alarm(unsigned int);
extern int memset(void*, int, unsigned long);
extern void* mmap(void*, unsigned long, int, int, int, long);
struct tv { long s; long us; };
extern int gettimeofday(struct tv*, void*);

/* AF_UNIX=1, AF_INET=2, SOCK_STREAM=1, PROT_READ=1, PROT_WRITE=2, MAP_PRIVATE=2, MAP_ANON=0x1000 */
struct sockaddr_in { unsigned char sin_len; unsigned char sin_family; unsigned short sin_port; unsigned int sin_addr; char pad[8]; };

#define CHUNK (256*1024)

static char* g_buf;

static double now(void)
{
	struct tv t;
	gettimeofday(&t, 0);
	return t.s + t.us / 1000000.0;
}

static long pump_write(int fd, long total)
{
	long sent = 0;
	while (sent < total) {
		unsigned long n = (unsigned long)(total - sent);
		if (n > CHUNK) n = CHUNK;
		long w = write(fd, g_buf, n);
		if (w <= 0) break;
		sent += w;
	}
	return sent;
}

static long pump_read(int fd, long total)
{
	long got = 0;
	while (got < total) {
		unsigned long n = (unsigned long)(total - got);
		if (n > CHUNK) n = CHUNK;
		long r = read(fd, g_buf, n);
		if (r <= 0) break;
		got += r;
	}
	return got;
}

int main(void)
{
	long total = 16L * 1024 * 1024;
	int sv[2];
	struct sockaddr_in a;
	unsigned int sl;
	int pid;
	double t0, t1;
	long got;

	g_buf = mmap(0, CHUNK, 1 | 2, 2 | 0x1000, -1, 0);
	memset(g_buf, 0x41, CHUNK);

	/* ---- 1. AF_UNIX socketpair ---- */
	if (socketpair(1, 1, 0, sv) != 0) { printf("M58F193 socketpair() failed\n"); return 1; }
	alarm(45);
	pid = fork();
	if (pid == 0) { close(sv[0]); pump_write(sv[1], total); close(sv[1]); _exit(0); }
	close(sv[1]);
	t0 = now();
	got = pump_read(sv[0], total);
	t1 = now();
	close(sv[0]);
	printf("M58F193 socketpair  %ld bytes in %.3fs = %.2f MB/s (got %ld)\n",
	    total, t1 - t0, (got / 1048576.0) / (t1 - t0), got);

	/* ---- 2. TCP loopback ---- */
	{
		int ls = socket(2, 1, 0);
		int port;
		if (ls < 0) { printf("M58F193 socket() failed\n"); return 1; }
		memset(&a, 0, sizeof a);
		a.sin_len = sizeof a; a.sin_family = 2;
		a.sin_addr = 0x0100007f; /* 127.0.0.1 */
		if (bind(ls, &a, sizeof a) != 0) { printf("M58F193 bind() failed\n"); return 1; }
		listen(ls, 1);
		sl = sizeof a;
		getsockname(ls, &a, &sl);
		port = a.sin_port; /* network order, reuse as-is */
		alarm(45);
		pid = fork();
		if (pid == 0) {
			int c;
			close(ls);
			c = socket(2, 1, 0);
			a.sin_len = sizeof a; a.sin_family = 2; a.sin_addr = 0x0100007f; a.sin_port = (unsigned short) port;
			if (connect(c, &a, sizeof a) != 0) { printf("M58F193 connect() failed\n"); _exit(1); }
			pump_write(c, total);
			close(c);
			_exit(0);
		}
		{
			int c = accept(ls, &a, &sl);
			if (c < 0) { printf("M58F193 accept() failed\n"); return 1; }
			t0 = now();
			got = pump_read(c, total);
			t1 = now();
			close(c); close(ls);
			printf("M58F193 tcp-loop   %ld bytes in %.3fs = %.2f MB/s (got %ld)\n",
			    total, t1 - t0, (got / 1048576.0) / (t1 - t0), got);
		}
	}
	return 0;
}
