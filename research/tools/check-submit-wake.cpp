#include "indium/submit-thread.private.hpp"
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <vector>

int main() {
    using namespace Indium::SubmitThread;
    ensureStarted();
    std::atomic<unsigned> completed{0};
    // Race producers with the worker's transition into and out of its wait.
    for (unsigned round = 0; round < 100; ++round) {
        std::vector<std::thread> producers;
        for (unsigned producer = 0; producer < 4; ++producer)
            producers.emplace_back([&] {
                for (unsigned i = 0; i < 250; ++i)
                    post([&] { ++completed; });
            });
        for (auto& producer : producers) producer.join();
        drain();
        assert(completed == (round + 1) * 1000);
        std::this_thread::sleep_for(std::chrono::microseconds(100));
    }
    unsigned sequence = 0;
    for (unsigned i = 0; i < 1000; ++i)
        post([&, i] { assert(sequence++ == i); });
    drain();
    assert(sequence == 1000);
    // Posting from the active worker must also run without a wake.
    post([&] { post([&] { ++completed; }); });
    drain();
    assert(completed == 100001);
    puts("PASS: concurrent producers, idle restarts, FIFO and nested posting");
}
