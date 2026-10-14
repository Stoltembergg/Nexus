// Passive hardware-counter reader for one thread (the game's main thread).
// Uses perf_event_open in counting mode, user space only: the kernel counts
// events while the thread runs and this program reads the totals once a
// second. No samples, no instruction addresses, no registers, no memory.
// Exits when the thread disappears or after MAX_SECONDS.
//
// Output (one JSON object per line): {"t": seconds, "<event>": count, ...}
// Counts are scaled by time_enabled/time_running when the kernel had to
// multiplex more events than the CPU has counters.
//
// Usage: hw-counters TID OUTPUT MAX_SECONDS
#include <linux/perf_event.h>
#include <sys/syscall.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <csignal>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <chrono>
#include <string>
#include <thread>
#include <vector>

struct Counter {
	const char* name;
	uint32_t type;
	uint64_t config;
	int fd = -1;
	uint64_t last = 0;
};

static uint64_t cache(uint64_t id, uint64_t op, uint64_t result)
{
	return id | (op << 8) | (result << 16);
}

int main(int argc, char** argv)
{
	if (argc != 4) {
		fprintf(stderr, "usage: %s TID OUTPUT MAX_SECONDS\n", argv[0]);
		return 2;
	}
	const pid_t tid = atoi(argv[1]);
	const int seconds = atoi(argv[3]);
	FILE* out = fopen(argv[2], "w");
	if (!out) {
		perror(argv[2]);
		return 1;
	}

	// Raw events are AMD Zen 3 (family 19h) encodings: event | umask << 8.
	std::vector<Counter> counters = {
		{"cycles", PERF_TYPE_HARDWARE, PERF_COUNT_HW_CPU_CYCLES},
		{"instructions", PERF_TYPE_HARDWARE, PERF_COUNT_HW_INSTRUCTIONS},
		{"branch_misses", PERF_TYPE_HARDWARE, PERF_COUNT_HW_BRANCH_MISSES},
		{"l1i_misses", PERF_TYPE_HW_CACHE, cache(PERF_COUNT_HW_CACHE_L1I, PERF_COUNT_HW_CACHE_OP_READ, PERF_COUNT_HW_CACHE_RESULT_MISS)},
		{"l1d_misses", PERF_TYPE_HW_CACHE, cache(PERF_COUNT_HW_CACHE_L1D, PERF_COUNT_HW_CACHE_OP_READ, PERF_COUNT_HW_CACHE_RESULT_MISS)},
		{"itlb_l1_miss_l2_hit", PERF_TYPE_RAW, 0x0084},  // BpL1TlbMissL2TlbHit
		{"itlb_walks", PERF_TYPE_RAW, 0x0f85},           // BpL1TlbMissL2TlbMiss, all page sizes
		{"dtlb_l1_miss_l2_hit", PERF_TYPE_RAW, 0x0f45},  // LsL1DTlbMiss, L2 hits
		{"dtlb_walks", PERF_TYPE_RAW, 0xf045},           // LsL1DTlbMiss, L2 misses
		{"dtlb_walks_4k", PERF_TYPE_RAW, 0x1045},        // ... of which for 4 KiB pages
	};

	for (Counter& c : counters) {
		perf_event_attr attr;
		memset(&attr, 0, sizeof(attr));
		attr.size = sizeof(attr);
		attr.type = c.type;
		attr.config = c.config;
		attr.exclude_kernel = 1;
		attr.exclude_hv = 1;
		attr.read_format = PERF_FORMAT_TOTAL_TIME_ENABLED | PERF_FORMAT_TOTAL_TIME_RUNNING;
		c.fd = syscall(SYS_perf_event_open, &attr, tid, -1, -1, 0);
		if (c.fd < 0)
			fprintf(stderr, "hw-counters: %s unavailable: %s\n", c.name, strerror(errno));
	}

	auto start = std::chrono::steady_clock::now();
	for (int second = 1; second <= seconds; ++second) {
		std::this_thread::sleep_until(start + std::chrono::seconds(second));
		if (kill(tid, 0) != 0 && errno == ESRCH)
			break;
		char path[64];
		snprintf(path, sizeof(path), "/proc/%d/task/%d", tid, tid);
		if (access(path, F_OK) != 0)
			break;
		std::string line = "{\"t\": " + std::to_string(second);
		for (Counter& c : counters) {
			if (c.fd < 0)
				continue;
			uint64_t value[3];
			if (read(c.fd, value, sizeof(value)) != sizeof(value))
				continue;
			uint64_t scaled = value[2] ? (uint64_t)((double)value[0] * value[1] / value[2]) : 0;
			line += ", \"" + std::string(c.name) + "\": " + std::to_string(scaled - c.last);
			c.last = scaled;
		}
		line += "}\n";
		fputs(line.c_str(), out);
		fflush(out);
	}
	fclose(out);
	return 0;
}
