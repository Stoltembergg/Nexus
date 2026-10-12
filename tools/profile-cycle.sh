#!/bin/sh
# One game cycle with optional diagnostics: restart the runtime, forward mouse movement,
# launch League and start a practice match. Profiling is disabled by default.
#
# Output: /tmp/dserver-call-stats.log (server request counts), /tmp/riot-runner.log (runner), /tmp/m712.log, /tmp/practice.log, guest /tmp/metal-trace.log
# (= ~/.darling/tmp/metal-trace.log), RADV hang reports under the guest home (~/.darling@GUEST_HOME@/radv_dumps_*).
# Run detached:  setsid nohup sh tools/profile-cycle.sh > /tmp/profile-cycle.log 2>&1 < /dev/null &
set -u
cd "$(dirname "$0")/.."
unset ELECTRON_RUN_AS_NODE VK_DRIVER_FILES
# Explicit experiment switch; inherited by the host Vulkan driver in Darling.
if [ "${CYCLE_SUBMIT_THREAD:-0}" = 1 ]; then
  export MESA_VK_ENABLE_SUBMIT_THREAD=1
else
  unset MESA_VK_ENABLE_SUBMIT_THREAD
fi

python3 -I tools/stop-darling-runtime.py < /dev/null 2>&1 | tail -1
: > /tmp/practice.log
: > /tmp/m712.log
rm -f "$HOME/.darling/tmp/metal-trace.log" "$HOME/.darling/tmp/metal-debug-timing" "$HOME/.darling/tmp/metal-debug-spirv" "$HOME/.darling/tmp/metal-snapshot" "$HOME/.darling/tmp/metal-validation" "$HOME/.darling/tmp/metal-validation-sync" "$HOME/.darling/tmp/metal-validation.log"

# Diagnostics reach the game through the runtime's environment (guest processes inherit it).
# CYCLE_RADV_HANG=1 turns on RADV's GPU hang reports (costly: it distorts frame rate, so off by default).
[ "${CYCLE_RADV_HANG:-0}" = 1 ] && export RADV_DEBUG=hang
# CYCLE_RENDERDOC=1 loads the RenderDoc capture layer and the capture bridge in the game. Request a frame with
#   echo 0 > build/renderdoc/capture-request      (captures land in build/renderdoc/captures/)
# The layer costs frame rate even when idle, so this is for artifact runs only.
if [ "${CYCLE_RENDERDOC:-0}" = 1 ]; then
  export RCLOL_RENDERDOC_CAPTURE=1 ENABLE_VULKAN_RENDERDOC_CAPTURE=1
  export VK_ADD_IMPLICIT_LAYER_PATH="$PWD/build/renderdoc"
  rm -f build/renderdoc/capture-request build/renderdoc/capture-status.log
fi
# CYCLE_SELECT_TRACE=1 enables the select() busy-loop trace of the kernel emulation (host /tmp/rclol-select-trace.log).
# Bounded frame captures are explicit; never leave them on for ordinary cycles.
rm -f "$HOME/.darling/tmp/metal-frame-interval-capture"
rm -f /tmp/rclol-select-trace /tmp/rclol-select-trace.log
[ "${CYCLE_SELECT_TRACE:-0}" = 1 ] && : > /tmp/rclol-select-trace
# CYCLE_RPC_TRACE=1 samples main-thread darlingserver requests with caller stacks (host /tmp/rclol-rpc-trace.log)
rm -f /tmp/rclol-rpc-trace /tmp/rclol-rpc-trace.log
[ "${CYCLE_RPC_TRACE:-0}" = 1 ] && : > /tmp/rclol-rpc-trace
if [ "${CYCLE_VALIDATION:-0}" = 1 ]; then
  export VK_LAYER_PATH="$PWD/build/vulkan-validation/usr/share/vulkan/explicit_layer.d"
fi
if [ "${CYCLE_SERVER_STATS:-0}" = 1 ]; then
  export DSERVER_CALL_STATS=/tmp/dserver-call-stats.log
else
  unset DSERVER_CALL_STATS
fi
if [ "${CYCLE_INPUT_TRACE:-0}" = 1 ]; then
  export RCLOL_INPUT_TRACE=1
else
  unset RCLOL_INPUT_TRACE
fi
RCLOL_FORWARD_MOUSE_MOVED=1 \
  setsid nohup sh tools/run-riot-ux-with-logdir-shim.sh > /tmp/riot-runner.log 2>&1 < /dev/null &

# Flag files only count when created from inside the guest. Never call `darling shell` before the runner has
# booted the runtime (it would start one without the diagnostic environment): wait for the Riot services process.
# (This script's own command line does not contain that name, so scanning /proc cannot match itself.)
i=0
while [ $i -lt 200 ]; do
  grep -a -l 'RiotClient[S]ervices' /proc/[0-9]*/cmdline 2>/dev/null | head -1 | grep -q . && break
  i=$((i + 1))
  sleep 3
done
i=0
guest_flags=
[ "${CYCLE_FRAME_INTERVALS:-0}" = 1 ] && guest_flags=/tmp/metal-frame-interval-capture
[ "${CYCLE_TIMING:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-debug-timing"
[ "${CYCLE_SPIRV:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-debug-spirv"
[ "${CYCLE_VALIDATION:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-validation"
[ "${CYCLE_VALIDATION_SYNC:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-validation-sync"
[ "${CYCLE_KEEP_STORAGE:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-keep-storage"
[ "${CYCLE_NO_POOL:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-no-pool"
[ "${CYCLE_GPU_TIMING:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-gpu-timing"
[ "${CYCLE_SUBMIT_THREAD:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-submit-thread"
[ "${CYCLE_NO_OPT_LAYOUTS:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-no-opt-layouts"
[ "${CYCLE_LAZY_PASS:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-lazy-pass"
[ "${CYCLE_SUBMIT_BATCH:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-submit-batch"
[ "${CYCLE_GPU_TIMING_DRAWS:-0}" = 1 ] && guest_flags="$guest_flags /tmp/metal-gpu-timing /tmp/metal-gpu-timing-draws"
if [ -n "$guest_flags" ]; then
while [ $i -lt 120 ]; do
  if timeout 30 darling shell sh -c "touch $guest_flags" > /tmp/guest-flag.log 2>&1 < /dev/null; then
    break
  fi
  i=$((i + 1))
  sleep 3
done
echo "diagnostic flags requested:$guest_flags"
else
echo "renderer diagnostic flags disabled"
fi

# m712-relaunch.py waits for the Riot Client UI itself; the practice driver waits for the League lockfile.
python3 -I tools/m712-relaunch.py > /tmp/m712.log 2>&1
python3 -I tools/lcu-practice-game.py --wait 400 > /tmp/practice.log 2>&1
