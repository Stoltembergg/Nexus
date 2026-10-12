/* Exercise the try/spin/block lock path used by PartitionAlloc. */
typedef struct {
  const char *file;
  void *base;
  const char *symbol;
  void *address;
} Image;
extern int dladdr(const void *, Image *);
typedef unsigned int Lock;
typedef unsigned long Thread;
extern void os_unfair_lock_lock(Lock *), os_unfair_lock_unlock(Lock *);
extern _Bool os_unfair_lock_trylock(Lock *);
extern int pthread_create(Thread *, const void *, void *(*)(void *), void *),
    pthread_join(Thread, void **), sched_yield(void), printf(const char *, ...);
static Lock lock;
static unsigned long counter;
static int inside, failed;
extern Thread pthread_self(void);
extern unsigned pthread_mach_thread_np(Thread);
static void *worker(void *arg) {
  unsigned long slot;
  __asm__ volatile("movq %%gs:24, %0" : "=r"(slot));
  printf("LOCK_OWNER tls_slot3=%lu pthread_port=%u\n", slot,
         pthread_mach_thread_np(pthread_self()));

  for (int i = 0; i < 200000; i++) {
    if (!os_unfair_lock_trylock(&lock))
      os_unfair_lock_lock(&lock);
    if (__sync_add_and_fetch(&inside, 1) != 1)
      __sync_add_and_fetch(&failed, 1);
    unsigned long next = counter + 1;
    if (!(i % 100))
      sched_yield();
    counter = next;
    if (__sync_sub_and_fetch(&inside, 1) != 0)
      __sync_add_and_fetch(&failed, 1);
    os_unfair_lock_unlock(&lock);
  }
  return arg;
}
int main(void) {
  Image image;
  dladdr(os_unfair_lock_lock, &image);
  printf("LOCK_BINDING lock=%s\n", image.file);
  dladdr(os_unfair_lock_trylock, &image);
  printf("LOCK_BINDING try=%s\n", image.file);
  dladdr(os_unfair_lock_unlock, &image);
  printf("LOCK_BINDING unlock=%s\n", image.file);
  os_unfair_lock_lock(&lock);
  printf("LOCK_SINGLE held=%u try_while_held=%d lock_fn=%p try_fn=%p\n", lock,
         os_unfair_lock_trylock(&lock), os_unfair_lock_lock,
         os_unfair_lock_trylock);
  os_unfair_lock_unlock(&lock);
  printf("LOCK_SINGLE released=%u\n", lock);
  Thread threads[8];
  for (int i = 0; i < 8; i++)
    if (pthread_create(&threads[i], 0, worker, 0))
      return 2;
  for (int i = 0; i < 8; i++)
    pthread_join(threads[i], 0);
  printf("UNFAIR_LOCK count=%lu expected=1600000 violations=%d\n", counter,
         failed);
  return failed || counter != 1600000;
}
