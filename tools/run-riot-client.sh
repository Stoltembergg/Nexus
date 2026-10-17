#!/bin/sh
# Launch Riot Client using the Darling runtime, without library injection.
# Darling supplies Xlib Display pointers to EGL, so select X11 explicitly.
set -eu

close_inherited_fds() {
  if [ -d /proc/self/fd ]; then
    for fd_path in /proc/self/fd/*; do
      fd="${fd_path##*/}"
      case "$fd" in
        0|1|2|'*') ;;
        *)
          eval "exec ${fd}>&-" 2>/dev/null || true
          ;;
      esac
    done
  else
    _fd=3
    while [ "$_fd" -le 256 ]; do
      eval "exec ${_fd}>&-" 2>/dev/null || true
      _fd=$((_fd + 1))
    done
  fi
}

sanitize_host_environment() {
  _linux_vars=$(env | awk -F= '
    /^[A-Za-z_][A-Za-z0-9_]*=/ {
      k = $1
      if (k ~ /^(XDG_|MESA_|DRI_|ROCM_|LIBGL_|__GL_|DBUS_|SSH_|SYSTEMD_|GNOME_|KDE_|PULSE_|PIPEWIRE_|ALSA_|QT_|GTK_|GDK_|GIO_|GSETTINGS_|GJS_|GLIBC_|MEMORY_PRESSURE_|VIRTUAL_ENV|ZSH_TMUX_|GAMEMODE|VK_|VULKAN_|LIBVA_|VDPAU_|GBM_|FLATPAK_|SNAP_|DEBUGINFOD_|PAM_|SELINUX_|ANTIGRAVITY_|AGY_)/) {
        print k
      } else if (k ~ /^(WAYLAND_DISPLAY|DESKTOP_SESSION|DESKTOP_STARTUP_ID|GDMSESSION|GDM_LANG|GDM_SETUP_DISPLAY|GNOME_SETUP_DISPLAY|SESSION_MANAGER|INVOCATION_ID|JOURNAL_STREAM|MANAGERPID|MANAGERPIDFDID|NOTIFY_SOCKET|LISTEN_FDS|LISTEN_PID|LISTEN_FDNAMES|COLORTERM|VTE_VERSION|WINDOWID|WINDOWPATH|XCURSOR_THEME|XCURSOR_SIZE|CHROME_DESKTOP|FC_FONTATIONS|NO_AT_BRIDGE|MOTD_SHOWN|LD_PRELOAD|LD_LIBRARY_PATH|ELECTRON_RUN_AS_NODE|DYLD_INSERT_LIBRARIES|XAUTHORITY|mesa_glthread|SNAP|APPIMAGE|APPDIR|OWD|USERNAME|MAIL|LS_COLORS|COLORFGBG|VSSCRIPT_PATH|CHROME_DEVTOOLS_MCP_JS|LC_ADDRESS|LC_IDENTIFICATION|LC_MEASUREMENT|LC_NAME|LC_PAPER|LC_TELEPHONE|PAGER|GIT_PAGER|MANPAGER|MANROFFOPT|SHLVL|DISABLE_AUTO_UPDATE)$/) {
        print k
      }
    }
    /^BASH_FUNC_/ {
      k = $0
      sub(/%%=.*/, "", k)
      sub(/=.*/, "", k)
      print k
    }')
  for _var in $_linux_vars; do
    case "$_var" in
      BASH_FUNC_*)
        _fn="${_var#BASH_FUNC_}"
        _fn="${_fn%%%}"
        unset -f "$_fn" 2>/dev/null || true
        unset -v "$_var" 2>/dev/null || true
        ;;
      *)
        unset -v "$_var" 2>/dev/null || unset "$_var" 2>/dev/null || true
        ;;
    esac
  done
  unset _linux_vars _var _fn _fd
}

# Close leaked inherited host file descriptors > 2 early so sub-tools don't inherit them.
close_inherited_fds
# Strip Linux-specific host variables early so sub-tools run in a clean environment.
sanitize_host_environment
# Native guest crashes created large system core files and exhausted this disk.
# Address-only diagnostics suffice; bound this runner and its new namespace.
if [ "${RCLOL_CORE_DUMPS:-0}" != 1 ]; then
 ulimit -c 0
fi
runner_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 "$runner_dir/ensure-darling-runtime.py"
python3 "$runner_dir/ensure-darling-service-accounts.py"
python3 "$runner_dir/ensure-league-runtime-layout.py"
# Discard argument-rewriting settings from the former injected shim.
unset RCLOL_APP_ARGS RCLOL_APP_ARGS_SLOT RCLOL_APP_ARG2 RCLOL_APP_ARG2_SLOT
unset RCLOL_APP_ARG3 RCLOL_APP_ARG3_SLOT RCLOL_UX_ARG1 RCLOL_UX_ARG1_SLOT
unset RCLOL_UX_ARG2 RCLOL_UX_ARG2_SLOT
# The paired runtime presents completed GPU textures without CPU readback.
# Explicit 0 or an empty value selects the CPU fallback for diagnostics.
for option in RCLOL_GPU_DIRECT_PRESENT RCLOL_GPU_DIRECT_ASYNC RCLOL_GPU_DIRECT_VSYNC DARLING_CA_PRESENT_AT_COMMIT DARLING_CA_SKIP_LOCAL_IOSURFACE_RENDER RCLOL_FORWARD_MOUSE_MOVED RCLOL_MOUSE_CONFINEMENT; do
 eval 'value=${'"$option"'-1}'
 case "$value" in 0|'') unset "$option";; *) export "$option=$value";; esac
done
prefix=${DPREFIX:-$HOME/.darling}
# The first-time installer puts the client in /Users/Shared/Riot Games and then
# hands off through LaunchServices, which does not start it under Darling. Link
# the installed client where the normal launch expects it.
client="$prefix/Applications/Riot Client.app"
shared="$prefix/Users/Shared/Riot Games/Riot Client.app"
if [ -z "${RIOT_LAUNCHER_HOST:-}" ] && [ ! -e "$client" ]; then
 if [ ! -d "$shared" ]; then
  echo "Riot Client is not installed in $prefix; run scripts/installer.sh first" >&2
  exit 1
 fi
 if [ -L "$client" ]; then
  # An absolute link (/Users/Shared/...) resolves only inside the guest; the
  # guest still uses it for --app-root, but start the client by its real path.
  client=$shared
 else
  ln -s "../Users/Shared/Riot Games/Riot Client.app" "$client"
 fi
fi
A=${RIOT_LAUNCHER_HOST:-"$client/Contents/MacOS/RiotClientServices"}
# External XIM (for example Fcitx) consumes keys before Darling forwards them.
# Use Xlib's local input method; allow explicit testing of another modifier.
# Linux C.UTF-8 is not a supported codecvt locale in the macOS client.
# Keep this scoped to the guest; product region/locale arguments remain explicit.
# The first-time installer (RIOT_LAUNCHER_HOST) exits immediately when given --app-root for a
# Riot Client that is not installed yet; only pass it for the installed client.
# Its native intro screen renders image layers with a blue cover and does not take clicks
# under Darling, so start the install directly (the Riot Client UI that follows works).
if [ -n "${RIOT_LAUNCHER_HOST:-}" ]; then
 set -- --skip-to-install --launch-product=league_of_legends --launch-patchline=live
else
 set -- --app-root="/Applications/Riot Client.app"
 # The League login theme (video background, Install/Play button) is only shown when the client
 # is started for a product. RCLOL_LAUNCH_PRODUCT= (empty) starts the bare client instead.
 if [ -n "${RCLOL_LAUNCH_PRODUCT-league_of_legends}" ]; then
  set -- "$@" --launch-product="${RCLOL_LAUNCH_PRODUCT-league_of_legends}" \
    --launch-patchline="${RCLOL_LAUNCH_PATCHLINE-live}"
 fi
fi
# --- darling-lol perf: scheduling & driver latency hints ---
# Refresh rate for display link, async presenter, and frame pacing: the primary monitor's
# current mode (the first monitor without a primary); unset falls back to 60 Hz.
if [ -z "${RCLOL_REFRESH_HZ-}" ] && command -v xrandr >/dev/null 2>&1; then
  RCLOL_REFRESH_HZ=$(xrandr --current 2>/dev/null | awk '
    / connected/ { primary = / primary / }
    /\*/ { for (i = 2; i <= NF; i++) if ($i ~ /\*/) { rate = $i; sub(/[*+]+/, "", rate)
            if (primary) { print int(rate + 0.5); found = 1; exit } else if (first == "") first = int(rate + 0.5) } }
    END { if (!found && first != "") print first }')
fi
if [ -n "${RCLOL_REFRESH_HZ-}" ]; then export RCLOL_REFRESH_HZ; fi
# Sanitize and harden environment before guest launch:
# Strip Linux-specific host variables (WAYLAND_DISPLAY, XDG_*, MESA_*, DRI_*, ROCM_*,
# session variables, desktop/audio/toolkit leaks) so the guest receives a pure macOS environment.
sanitize_host_environment

# Ensure all host file descriptors > 2 are closed immediately prior to guest exec.
close_inherited_fds

guest_home="@GUEST_HOME@"
case "$guest_home" in
  '@'GUEST_HOME'@')
    guest_home="/Users/${USER:-$(id -un)}"
    ;;
esac

exec env \
  EGL_PLATFORM=x11 \
  LANG="${RCLOL_GUEST_LOCALE:-en_US.UTF-8}" \
  LC_ALL="${RCLOL_GUEST_LOCALE:-en_US.UTF-8}" \
  SHELL="/bin/zsh" \
  XMODIFIERS="${RCLOL_XMODIFIERS:-@im=none}" \
  DISPLAY="${DISPLAY:-:1}" \
  DYLD_LIBRARY_PATH="${DYLD_LIBRARY_PATH:-$guest_home/RuntimeLibraries}" \
  DYLD_FRAMEWORK_PATH="${DYLD_FRAMEWORK_PATH:-$guest_home/RuntimeFrameworks}" \
  DARLING_XSHM_LIBRARY="${DARLING_XSHM_LIBRARY:-$guest_home/libDarlingXShm.dylib}" \
  __CF_USER_TEXT_ENCODING="0x1F5:0x0:0x0" \
  APPLE_SUPPRESS_X11_THEMING=1 \
  darling "$A" --region="${RCLOL_REGION:-EUW}" --locale="${RCLOL_LOCALE:-en_GB}" \
    "$@" \
    --log-dir="$guest_home/Library/Logs/Riot Games/Riot Client"
