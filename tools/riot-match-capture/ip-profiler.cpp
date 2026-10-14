// Passive instruction-address sampler for one process (all threads).
// Uses perf_event_open with the software CPU clock, user space only. Records
// thread id, timestamp and the executing instruction address; no call stacks,
// no register or memory contents. Exits when the process disappears.
#include <linux/perf_event.h>
#include <sys/syscall.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <dirent.h>
#include <unistd.h>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <chrono>
#include <map>
#include <set>
#include <thread>
#include <algorithm>

struct Event { int fd; perf_event_mmap_page *meta; size_t length; uint64_t tail = 0, samples = 0, lost = 0; };

static bool open_event(int tid, bool main_thread, Event &event) {
    perf_event_attr attr{};
    attr.size = sizeof(attr);
    attr.type = PERF_TYPE_SOFTWARE;
    attr.config = PERF_COUNT_SW_CPU_CLOCK;
    attr.sample_period = main_thread ? 1000000 : 4000000;
    attr.sample_type = PERF_SAMPLE_IP | PERF_SAMPLE_TID | PERF_SAMPLE_TIME;
    attr.disabled = 1;
    attr.exclude_kernel = 1;
    attr.exclude_hv = 1;
    attr.wakeup_events = 1 << 20;
    int fd = syscall(SYS_perf_event_open, &attr, tid, -1, -1, PERF_FLAG_FD_CLOEXEC);
    if (fd < 0) return false;
    size_t length = sysconf(_SC_PAGESIZE) * (main_thread ? 65 : 9);
    void *map = mmap(nullptr, length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (map == MAP_FAILED) { close(fd); return false; }
    event = {fd, static_cast<perf_event_mmap_page *>(map), length};
    ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);
    return true;
}

static void drain(Event &e, FILE *out) {
    uint64_t head = __atomic_load_n(&e.meta->data_head, __ATOMIC_ACQUIRE);
    char *data = (char *)e.meta + e.meta->data_offset;
    uint64_t size = e.meta->data_size;
    auto copy = [&](uint64_t offset, void *dst, size_t n) {
        size_t pos = offset % size, first = std::min(n, (size_t)size - pos);
        memcpy(dst, data + pos, first);
        if (first < n) memcpy((char *)dst + first, data, n - first);
    };
    while (e.tail < head) {
        perf_event_header h{};
        copy(e.tail, &h, sizeof(h));
        if (h.size < sizeof(h) || h.size > size || e.tail + h.size > head) { e.tail = head; break; }
        if (h.type == PERF_RECORD_SAMPLE) {
            struct { uint64_t ip; uint32_t pid, tid; uint64_t time; } s{};
            copy(e.tail + sizeof(h), &s, sizeof(s));
            fprintf(out, "%u %llu %llx\n", s.tid, (unsigned long long)s.time, (unsigned long long)s.ip);
            ++e.samples;
        } else if (h.type == PERF_RECORD_LOST) {
            uint64_t lost[2];
            copy(e.tail + sizeof(h), lost, sizeof(lost));
            e.lost += lost[1];
        }
        e.tail += h.size;
    }
    __atomic_store_n(&e.meta->data_tail, e.tail, __ATOMIC_RELEASE);
}

int main(int argc, char **argv) {
    if (argc != 4) { fprintf(stderr, "usage: %s PID OUTPUT MAX_SECONDS\n", argv[0]); return 2; }
    int pid = atoi(argv[1]);
    FILE *out = fopen(argv[2], "w");
    if (!out) { perror("output"); return 1; }
    double limit = atof(argv[3]);
    char path[64];
    snprintf(path, sizeof(path), "/proc/%d/task", pid);
    std::map<int, Event> events;
    std::set<int> failed;
    auto start = std::chrono::steady_clock::now();
    int round = 0;
    for (;; ++round) {
        if (round % 10 == 0) {
            DIR *dir = opendir(path);
            if (!dir) break;
            std::set<int> live;
            while (dirent *entry = readdir(dir)) {
                int tid = atoi(entry->d_name);
                if (tid <= 0) continue;
                live.insert(tid);
                if (events.count(tid) || failed.count(tid)) continue;
                Event event;
                if (open_event(tid, tid == pid, event)) events[tid] = event;
                else { failed.insert(tid); fprintf(stderr, "tid %d not sampled: %s\n", tid, strerror(errno)); }
            }
            closedir(dir);
            for (auto it = events.begin(); it != events.end();) {
                if (live.count(it->first)) { ++it; continue; }
                drain(it->second, out);
                munmap(it->second.meta, it->second.length);
                close(it->second.fd);
                it = events.erase(it);
            }
            if (!live.count(pid)) break;
        }
        for (auto &pair : events) drain(pair.second, out);
        if (std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count() > limit) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    uint64_t samples = 0, lost = 0;
    for (auto &pair : events) { drain(pair.second, out); samples += pair.second.samples; lost += pair.second.lost; }
    fclose(out);
    printf("{\"event\": \"profile_end\", \"live_thread_samples\": %llu, \"lost\": %llu, \"unsampled_threads\": %zu}\n",
           (unsigned long long)samples, (unsigned long long)lost, failed.size());
    return 0;
}
