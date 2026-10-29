# Isolated ICNS JP2 experiment

This is not in the production manifest or installed runtime. The patch
`patches/experimental/cocotron-icns-jp2.patch` applies to the Cocotron source
after the existing ICNS PNG/legacy changes. The current test checkout already
has it applied. It only accepts boxed JP2 in `ic08`: 256x256, 8-bit unsigned,
unsubsampled sRGB with three channels or four including unassociated alpha,
no ICC profile, and at most 16 MiB compressed. Other representations fall back
to the existing behavior. This narrow set does not prove compatibility with
any particular client artwork.

The experiment used `wrapgen libopenjp2.so` and compiled its generated C with
the configured `src/native/CMakeFiles/png.dir/flags.make`, then linked it using
the PNG `link.txt` with the object/output/install name replaced. The patched
ICNS object was compiled using `Onyx2D.dir/flags.make` plus the OpenJPEG include
directory, and the configured Onyx2D `link.txt` was replayed with only the ICNS
object/output replaced and the generated wrapper added. This was an x86-64
manual staged build, **not CMake/package integration**. A production build would
need explicit wrapper, header, linker, runtime dependency and architecture wiring.

The resulting stage and generated synthetic RGB, RGBA and malformed fixtures
are under `build/openjpeg-compat-check/`. The source of the guest check is
`tools/icns-jp2-experimental-check.m`. The check decodes, inspects the first
pixel's premultiplied RGBA data, and draws it offscreen; it expects malformed
JP2 to produce zero images. Its log is `icns-render-guest-final.log` in that
build directory. The tests do not cover all malformed inputs, color profiles,
other component layouts, skip callbacks, i386, or window-manager publication.

To repeat using the existing stage, create a **new short, initially absent**
DPREFIX within a private parent inside this checkout. Run only the probe with
`darling shell env` and guest paths `/Volumes/SystemRoot` followed by absolute
host paths: set `DYLD_FRAMEWORK_PATH` and `DYLD_LIBRARY_PATH` to the stage,
then pass `icns-probe`, `rgb.icns`, `rgba.icns` and `bad.icns` in that order.
Use the same explicit DPREFIX for `darling shutdown` in a finally/cleanup path;
never shut down the normal prefix. The private namespace was shut down after
each test. Prefix directories were retained because Darling creates root-owned
work directories; do not remove them without separately verifying mounts and
ownership. No client or client artwork is required for this test.
