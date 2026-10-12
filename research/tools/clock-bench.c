/* Heat-soak clock benchmark for undervolt A/B: N busy threads (thread 0 pinned to CPU 1, like the game's main thread)
 * run a deterministic integer/FP mix and check its result every block, so a wrong result from too little voltage is
 * reported instead of going unnoticed. Prints the pinned thread's speed for each 10 s window.
 *   clock-bench [threads=4] [seconds=120] */
#define _GNU_SOURCE
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <math.h>
static volatile int stop;
static volatile uint64_t blocks[64], errors[64];
static uint64_t expected_hash; static double expected_sum;
static void block(uint64_t* hash, double* sum) {
    uint64_t h = 1469598103934665603ull; double s = 0;
    for (uint32_t i = 1; i <= 2000000; ++i) { h ^= i * 0x9E3779B97F4A7C15ull; h *= 1099511628211ull; h = (h << 13) | (h >> 51); s += sqrt((double)(h & 0xffff) + i) / (double)(i & 1023 ? i & 1023 : 7); }
    *hash = h; *sum = s;
}
static void* worker(void* arg) {
    long id = (long)arg; cpu_set_t set; CPU_ZERO(&set);
    if (id == 0) CPU_SET(1, &set); else for (int c = 2; c < 12; ++c) CPU_SET(c, &set);
    sched_setaffinity(0, sizeof(set), &set);
    while (!stop) { uint64_t h; double s; block(&h, &s); if (h != expected_hash || s != expected_sum) errors[id]++; blocks[id]++; }
    return 0;
}
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec / 1e9; }
static double tctl(void) { FILE* f = popen("sensors 2>/dev/null | awk '/Tctl/{gsub(/[^0-9.]/,\"\",$2); print $2}'", "r"); double v = 0; if (f) { if (fscanf(f, "%lf", &v) != 1) v = 0; pclose(f); } return v; }
int main(int argc, char** argv) {
    int threads = argc > 1 ? atoi(argv[1]) : 4, seconds = argc > 2 ? atoi(argv[2]) : 120;
    if (threads < 1 || threads > 64) return 1;
    block(&expected_hash, &expected_sum);
    pthread_t t[64];
    for (long i = 0; i < threads; ++i) pthread_create(&t[i], 0, worker, (void*)i);
    double start = now(), last = start; uint64_t lastBlocks = 0; double tail = 0; int tailN = 0;
    while (now() - start < seconds) {
        struct timespec ts = {10, 0}; nanosleep(&ts, 0);
        double t1 = now(); uint64_t b = blocks[0]; uint64_t all = 0, err = 0;
        for (int i = 0; i < threads; ++i) { all += blocks[i]; err += errors[i]; }
        double rate = (b - lastBlocks) / (t1 - last);
        FILE* f = fopen("/sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq", "r"); long khz = 0; if (f) { if (fscanf(f, "%ld", &khz) != 1) khz = 0; fclose(f); }
        printf("t=%3.0fs pinned thread %.2f blocks/s  cpu1 %.2f GHz  Tctl %.1f C  wrong results %llu\n", t1 - start, rate, khz / 1e6, tctl(), (unsigned long long)err);
        fflush(stdout);
        if (t1 - start > seconds - 35) { tail += rate; tailN++; }
        last = t1; lastBlocks = b;
    }
    stop = 1; for (int i = 0; i < threads; ++i) pthread_join(t[i], 0);
    uint64_t err = 0; for (int i = 0; i < threads; ++i) err += errors[i];
    printf("RESULT: last 30 s pinned thread %.2f blocks/s, wrong results %llu\n", tailN ? tail / tailN : 0, (unsigned long long)err);
    return err != 0;
}
