/* Boundary/overlap checks and video-sized fill benchmark; no app data. */
typedef unsigned long size_t;
typedef unsigned int uint32_t;
struct timespec {
  long tv_sec, tv_nsec;
};
extern void *dlopen(const char *, int), *dlsym(void *, const char *);
extern int puts(const char *), printf(const char *, ...), getpagesize(void);
extern void *malloc(size_t), *mmap(void *, size_t, int, int, int, long);
extern void free(void *);
extern int mprotect(void *, size_t, int), munmap(void *, size_t),
    clock_gettime(int, struct timespec *);
extern unsigned long long mach_absolute_time(void);
struct mach_timebase_info { unsigned int numer, denom; };
extern int mach_timebase_info(struct mach_timebase_info *);
#define NULL ((void *)0)
#define RTLD_NOW 2
#define RTLD_LOCAL 4
#define RTLD_DEFAULT ((void *)-2)
#define PROT_NONE 0
#define PROT_READ 1
#define PROT_WRITE 2
#define MAP_PRIVATE 2
#define MAP_ANON 0x1000
#define CLOCK_MONOTONIC 6
typedef void *(*Move)(void *, const void *, size_t);
typedef void (*Pattern)(void *, const void *, size_t);
static unsigned char actual[8192], expected[8192];
static double now(void) {
  struct mach_timebase_info t;
  if (mach_timebase_info(&t) || !t.denom) return 0;
  return mach_absolute_time() * ((double)t.numer / t.denom) / 1e9;
}
int main(int argc, char **argv) {
  void *library =
      argc > 1 ? dlopen(argv[1], RTLD_NOW | RTLD_LOCAL) : RTLD_DEFAULT;
  Move move = dlsym(library, "_platform_memmove");
  Pattern fill[3] = {dlsym(library, "_platform_memset_pattern4"),
                     dlsym(library, "_platform_memset_pattern8"),
                     dlsym(library, "_platform_memset_pattern16")};
  if (!move || !fill[0] || !fill[1] || !fill[2]) {
    puts("SYMBOL_FAIL");
    return 1;
  }
  for (size_t length = 0; length < 2048; length += length < 64 ? 1 : 37)
    for (int offset = -33; offset <= 33; offset++) {
      for (int i = 0; i < 8192; i++)
        actual[i] = expected[i] = (i * 71 + 19) & 255;
      unsigned char saved[2048];
      for (size_t i = 0; i < length; i++)
        saved[i] = expected[2048 + i];
      for (size_t i = 0; i < length; i++)
        expected[2048 + offset + i] = saved[i];
      if (move(actual + 2048 + offset, actual + 2048, length) !=
          actual + 2048 + offset)
        return 2;
      for (int i = 0; i < 8192; i++)
        if (actual[i] != expected[i]) {
          printf("MOVE_FAIL %zu %d %d\n", length, offset, i);
          return 3;
        }
    }
  size_t page = getpagesize();
  unsigned char *guard =
      mmap(NULL, page * 3, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
  mprotect(guard + page, page, PROT_READ | PROT_WRITE);
  for (int k = 0; k < 3; k++)
    for (size_t length = 0; length < 2048; length += length < 64 ? 1 : 37) {
      size_t size = 4u << k;
      unsigned char pattern[16];
      for (size_t i = 0; i < 16; i++)
        pattern[i] = i * 13 + 3;
      unsigned char *p = guard + 2 * page - length;
      for (size_t i = 0; i < page; i++)
        guard[page + i] = 0xa5;
      fill[k](p, pattern, length);
      for (size_t i = 0; i < length; i++)
        if (p[i] != pattern[i % size])
          return 4;
      for (size_t i = 0; i < page - length; i++)
        if (guard[page + i] != 0xa5)
          return 5;
      /* Input pattern may alias the destination. */
      for (size_t i = 0; i < 8192; i++)
        actual[i] = 0xa5;
      for (size_t i = 0; i < size; i++)
        actual[2048 + i] = pattern[i];
      fill[k](actual + 2048, actual + 2048, length);
      for (size_t i = 0; i < length; i++)
        if (actual[2048 + i] != pattern[i % size])
          return 6;
    }
  munmap(guard, page * 3);
  size_t bytes = 1536 * 864 * 4;
  unsigned char *frame = malloc(bytes);
  uint32_t pattern = 0x20202020;
  double start = now();
  for (int i = 0; i < 200; i++)
    fill[0](frame, &pattern, bytes);
  printf("MEMORY_PRIMITIVES pass fill_200_frames_ms=%.2f checksum=%u\n",
         (now() - start) * 1000, frame[bytes - 1]);
  free(frame);
  return 0;
}
