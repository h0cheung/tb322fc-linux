"""Compile production arithmetic and test rotations and pending-state transitions."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


def patched_function(patch, name):
    # Keep the resulting C lines from unified-diff hunks (not removed lines).
    after = '\n'.join(line[1:] for line in patch.splitlines()
                      if line.startswith((' ', '+')) and not line.startswith('+++'))
    pos = after.index(name + '(')
    start = after.rfind('\n', 0, pos) + 1
    opening = after.index('{', pos)
    depth = 1
    end = opening + 1
    while depth:
        depth += (after[end] == '{') - (after[end] == '}')
        end += 1
    return after[start:end]


class DpuPlanePerformanceTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'), 'requires a native C compiler')
    def test_geometry_and_pending_performance(self):
        patch = (Path(__file__).resolve().parents[1] / 'patches/freedom/'
                 '0017-dpu-elden-candidate-plane-performance.patch').read_text()
        code = '\n'.join(patched_function(patch, name) for name in (
            '_dpu_plane_calc_bw', '_dpu_plane_calc_clk', 'dpu_plane_calc_perf',
            'dpu_core_perf_calc_atomic'))
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t u64;
typedef uint32_t u32;
#define PIPES_PER_PLANE 4
#define DRM_MODE_ROTATE_0 1
#define DRM_MODE_ROTATE_90 2
#define DRM_MODE_ROTATE_180 4
#define DRM_MODE_ROTATE_270 8
#define DRM_MODE_REFLECT_X 16
#define max(a,b) ((a) > (b) ? (a) : (b))
#define swap(a,b) do { int tmp = (a); (a) = (b); (b) = tmp; } while (0)
#define do_div(a,b) ((a) /= (b))
#define mult_frac(a,b,c) ((u64)(a) * (b) / (c))
#define drm_rotation_90_or_270(r) ((r) & (2 | 8))
struct drm_rect { int x1, y1, x2, y2; };
#define drm_rect_width(r) ((r)->x2 - (r)->x1)
#define drm_rect_height(r) ((r)->y2 - (r)->y1)
struct dpu_sw_pipe_cfg { struct drm_rect src_rect, dst_rect; unsigned rotation; };
struct drm_display_mode { int hdisplay, vdisplay, vtotal, vsync_start, vsync_end, fps; };
#define drm_mode_vrefresh(m) ((m)->fps)
struct msm_format { unsigned bpp; };
struct dpu_perf_cfg { unsigned min_prefill_lines, bw_inefficiency_factor, clk_inefficiency_factor; };
struct dpu_mdss_cfg { struct dpu_perf_cfg *perf; };
struct drm_plane { const struct dpu_mdss_cfg *catalog; };
#define dpu_plane drm_plane
#define to_dpu_plane(p) (p)
struct drm_plane_state { bool visible; struct msm_format *fb; struct drm_plane *plane; };
struct dpu_plane_state {
    struct drm_plane_state base;
    struct dpu_sw_pipe_cfg pipe_cfg[PIPES_PER_PLANE];
    u64 plane_fetch_bw, plane_clk;
};
#define to_dpu_plane_state(s) ((const struct dpu_plane_state *)(s))
#define msm_framebuffer_format(f) (f)
struct drm_crtc_state {
    struct drm_display_mode adjusted_mode;
    const struct drm_plane_state *planes[3];
    unsigned count;
};
#define drm_atomic_crtc_state_for_each_plane_state(p, ps, s) \
    for (unsigned n = 0; n < (s)->count && (((ps) = (s)->planes[n]), \
        ((p) = (ps)->plane), (void)(p), 1); ++n)
struct dpu_core_perf_params { u64 bw_ctl, core_clk_rate; };
static bool elden = true;
static bool of_machine_is_compatible(const char *s) { (void)s; return elden; }
static u64 dpu_core_perf_adjusted_mode_clk(u64 clk, const struct dpu_perf_cfg *cfg) {
    return cfg->clk_inefficiency_factor ? clk * cfg->clk_inefficiency_factor / 100 : clk;
}
'''
        cases = r'''
int main(void) {
    struct dpu_perf_cfg perf_cfg = {35, 120, 105};
    struct dpu_mdss_cfg catalog = {&perf_cfg};
    struct drm_plane plane = {&catalog};
    struct msm_format format = {4};
    struct drm_display_mode mode = {1904, 3040, 3120, 3050, 3060, 165};
    struct dpu_sw_pipe_cfg rotated = {{0, 0, 3040, 952}, {0, 0, 952, 3040}, 8};
    struct dpu_sw_pipe_cfg portrait = {{0, 0, 952, 3040}, {0, 0, 952, 3040}, 1};
    u64 single = 952ULL * 3120 * 165 * 4;
    assert(_dpu_plane_calc_bw(&catalog, &format, &mode, &rotated) == single);
    assert(_dpu_plane_calc_bw(&catalog, &format, &mode, &portrait) == single);
    rotated.rotation = 2 | DRM_MODE_REFLECT_X;
    assert(_dpu_plane_calc_bw(&catalog, &format, &mode, &rotated) == single);
    rotated.rotation = 8;
    portrait.rotation = 4;
    assert(_dpu_plane_calc_bw(&catalog, &format, &mode, &portrait) == single);
    // Other boards retain their old rotation estimate.
    elden = false;
    assert(_dpu_plane_calc_bw(&catalog, &format, &mode, &rotated) == 3040ULL * 3120 * 165 * 4);
    elden = true;
    // Fractional 1.9x downscale must not truncate to 1x.
    rotated.dst_rect.y2 = 1600;
    assert(_dpu_plane_calc_bw(&catalog, &format, &mode, &rotated) == single * 3040 / 1600);
    rotated.dst_rect.y2 = 3040;
    // Preserve a tighter blanking interval's prefill requirement.
    struct drm_display_mode tight = mode;
    tight.vtotal = 3056; tight.vsync_start = 3044; tight.vsync_end = 3048;
    assert(_dpu_plane_calc_bw(&catalog, &format, &tight, &rotated) ==
           952ULL * 3056 * 165 * 4 * 35 / 16);
    struct dpu_plane_state a = {.base = {true, &format, &plane},
        .pipe_cfg = {rotated, rotated}, .plane_fetch_bw = UINT64_MAX, .plane_clk = UINT64_MAX};
    struct dpu_plane_state b = a;
    struct drm_crtc_state state = {.adjusted_mode = mode, .planes = {&a.base, &b.base}, .count = 2};
    struct dpu_core_perf_params perf;
    struct dpu_plane_state snapshot = a;
    dpu_core_perf_calc_atomic(&perf_cfg, &state, &perf);
    assert(perf.bw_ctl == 9409720320ULL && perf.bw_ctl < 28500000000ULL);
    assert(perf.core_clk_rate == 1904ULL * 3120 * 165 * 105 / 100);
    assert(memcmp(&a, &snapshot, sizeof(a)) == 0); // Shared committed state is read-only.
    // Refresh-only transaction immediately uses 60 Hz, ignoring stale caches.
    state.adjusted_mode.fps = 60;
    dpu_core_perf_calc_atomic(&perf_cfg, &state, &perf);
    assert(perf.bw_ctl == 952ULL * 3120 * 60 * 4 * 4 * 120 / 100);
    assert(perf.core_clk_rate == 1904ULL * 3120 * 60 * 105 / 100);
    // One layer removed, then invisible, then no FB: none may retain old BW.
    state.count = 1;
    dpu_core_perf_calc_atomic(&perf_cfg, &state, &perf);
    assert(perf.bw_ctl == 952ULL * 3120 * 60 * 4 * 2 * 120 / 100);
    a.base.visible = false;
    dpu_core_perf_calc_atomic(&perf_cfg, &state, &perf); assert(perf.bw_ctl == 0);
    a.base.visible = true; a.base.fb = NULL;
    dpu_core_perf_calc_atomic(&perf_cfg, &state, &perf); assert(perf.bw_ctl == 0);
    a.base.fb = &format;
    // Smaller candidate geometry and changed pixel format update immediately.
    a.pipe_cfg[1].src_rect.x2 = 0;
    a.pipe_cfg[0].src_rect.y2 = 480; format.bpp = 2;
    dpu_core_perf_calc_atomic(&perf_cfg, &state, &perf);
    assert(perf.bw_ctl == 480ULL * 3120 * 60 * 2 * 120 / 100);
    // A costly downscale remains over budget, for rejection by the existing cap.
    a.pipe_cfg[0] = rotated; a.pipe_cfg[0].dst_rect.y2 = 100;
    format.bpp = 4; state.adjusted_mode = mode;
    dpu_core_perf_calc_atomic(&perf_cfg, &state, &perf);
    assert(perf.bw_ctl > 28500000000ULL);
    puts("rotation, prefill, geometry, refresh-only and read-only-state cases passed");
}
'''
        with tempfile.TemporaryDirectory() as temp:
            c = Path(temp) / 'perf.c'
            c.write_text(harness + code + cases)
            exe = Path(temp) / 'perf'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-sign-compare', '-fsanitize=undefined',
                            str(c), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
