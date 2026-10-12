/* darling-lol M58cv: can the guest fetch from the UX's own static server? */
typedef unsigned int u32;
extern int printf(const char *, ...);
extern int fflush(void *);
extern int socket(int, int, int);
extern int connect(int, const void *, u32);
extern int send(int, const void *, unsigned long, int);
extern int recv(int, void *, unsigned long, int);
extern int atoi(const char *);

struct sa {
	unsigned char len;
	unsigned char family;
	unsigned char port[2];
	unsigned char addr[4];
	unsigned char zero[8];
};

int main(int argc, char **argv) {
	int port, s, i, total = 0;
	struct sa a;
	char buf[512];
	char req[128];

	if (argc < 2) { printf("HTTPGET usage: httpget <port>\n"); fflush(0); return 1; }
	port = atoi(argv[1]);
	printf("HTTPGET connecting to 127.0.0.1:%d\n", port); fflush(0);

	s = socket(2, 1, 0);
	a.len = 16; a.family = 2;
	a.port[0] = (port >> 8) & 0xff; a.port[1] = port & 0xff;
	a.addr[0] = 127; a.addr[1] = 0; a.addr[2] = 0; a.addr[3] = 1;
	for (i = 0; i < 8; ++i) a.zero[i] = 0;

	i = connect(s, &a, 16);
	printf("HTTPGET connect=%d\n", i); fflush(0);
	if (i != 0) { printf("HTTPGET FAILED to connect\n"); fflush(0); return 2; }

	i = 0;
	{ const char *p = "GET /index.html HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n";
	  while (p[i]) { req[i] = p[i]; ++i; } req[i] = 0; }
	send(s, req, (unsigned long) i, 0);

	for (i = 0; i < 8; ++i) {
		int n = recv(s, buf + total, sizeof(buf) - total - 1, 0);
		if (n <= 0) { printf("HTTPGET recv n=%d after %d bytes\n", n, total); break; }
		total += n;
		if (total > 200) break;
	}
	buf[total] = 0;
	for (i = 0; i < total; ++i) if (buf[i] == '\r' || buf[i] == '\n') buf[i] = ' ';
	printf("HTTPGET got %d bytes: %.120s\n", total, buf);
	fflush(0);
	return 0;
}
