"""Run the patched C aggregator against atomic transition regressions."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class DpuBandwidthTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "requires a native C compiler")
    def test_pending_bandwidth_transitions(self):
        patch = (Path(__file__).resolve().parents[1] / "patches/freedom/"
                 "0016-dpu-elden-check-pending-bandwidth.patch").read_text()
        added = "\n".join(line[1:] for line in patch.splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        start = added.index("static void dpu_core_perf_aggregate_atomic(")
        end = added.index("\n}", start) + 2
        production = added[start:end]
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
enum dpu_crtc_client_type { RT_CLIENT, NRT_CLIENT };
struct dpu_core_perf_params { uint64_t bw_ctl; unsigned max_per_pipe_ib; };
struct drm_atomic_state;
struct drm_crtc_state {
    bool active;
    struct drm_atomic_state *state;
    struct dpu_core_perf_params new_perf;
};
#define dpu_crtc_state drm_crtc_state
struct drm_device;
struct drm_crtc {
    int id;
    enum dpu_crtc_client_type type;
    struct drm_device *dev;
    struct drm_crtc_state *state;
};
struct drm_device { struct drm_crtc *crtcs[3]; int count; };
struct drm_atomic_state { struct drm_crtc_state *pending[3]; };
#define drm_for_each_crtc(c, d) \
    for (int i = 0; i < (d)->count && (((c) = (d)->crtcs[i]), 1); ++i)
#define to_dpu_crtc_state(s) (s)
#define dpu_crtc_get_client_type(c) ((c)->type)
#define max(a, b) ((a) > (b) ? (a) : (b))
static struct drm_crtc_state *drm_atomic_get_new_crtc_state(
    struct drm_atomic_state *s, struct drm_crtc *c) { return s->pending[c->id]; }
'''
        cases = r'''
int main(void) {
    struct drm_device dev = { .count = 3 };
    struct drm_atomic_state tx = {0};
    struct drm_crtc_state old[3] = {0}, next[3] = {0};
    struct drm_crtc crtc[3];
    for (int i = 0; i < 3; ++i) {
        crtc[i] = (struct drm_crtc){i, RT_CLIENT, &dev, &old[i]};
        dev.crtcs[i] = &crtc[i]; next[i].state = &tx;
    }
    tx.pending[0] = &next[0];
    old[0].active = next[0].active = true;
    old[0].new_perf.bw_ctl = 30047847000ULL;
    next[0].new_perf = (struct dpu_core_perf_params){10000000000ULL, 100};
    struct dpu_core_perf_params p = {0};
    dpu_core_perf_aggregate_atomic(&crtc[0], &next[0], &p);
    assert(p.bw_ctl == 10000000000ULL && p.bw_ctl / 1000 <= 28500000);
    /* An over-budget proposal must fail before it becomes committed. */
    old[0].new_perf.bw_ctl = 10000000000ULL;
    next[0].new_perf.bw_ctl = 30047847000ULL; p = (struct dpu_core_perf_params){0};
    dpu_core_perf_aggregate_atomic(&crtc[0], &next[0], &p);
    assert(p.bw_ctl / 1000 > 28500000);
    /* First frame after DPMS/resume counts despite inactive old state. */
    old[0].active = false;
    next[0].new_perf.bw_ctl = 10000000000ULL; p = (struct dpu_core_perf_params){0};
    dpu_core_perf_aggregate_atomic(&crtc[0], &next[0], &p);
    assert(p.bw_ctl == 10000000000ULL);
    /* Shutdown removes the old vote. */
    old[0].active = true; next[0].active = false; p = (struct dpu_core_perf_params){0};
    dpu_core_perf_aggregate_atomic(&crtc[0], &next[0], &p); assert(p.bw_ctl == 0);
    next[0].active = true;
    old[1].active = true;
    old[1].new_perf = (struct dpu_core_perf_params){2000000000ULL, 200};
    p = (struct dpu_core_perf_params){0};
    dpu_core_perf_aggregate_atomic(&crtc[0], &next[0], &p);
    assert(p.bw_ctl == 12000000000ULL && p.max_per_pipe_ib == 200);
    /* A second CRTC changed by this transaction uses its pending vote. */
    tx.pending[1] = &next[1]; next[1].active = true;
    next[1].new_perf = (struct dpu_core_perf_params){3000000000ULL, 300};
    p = (struct dpu_core_perf_params){0};
    dpu_core_perf_aggregate_atomic(&crtc[0], &next[0], &p);
    assert(p.bw_ctl == 13000000000ULL && p.max_per_pipe_ib == 300);
    /* Writeback belongs to a different client type. */
    crtc[1].type = NRT_CLIENT; p = (struct dpu_core_perf_params){0};
    dpu_core_perf_aggregate_atomic(&crtc[0], &next[0], &p);
    assert(p.bw_ctl == 10000000000ULL && p.max_per_pipe_ib == 100);
    puts("7 atomic bandwidth transition regressions passed");
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bandwidth.c"
            binary = Path(directory) / "bandwidth"
            source.write_text(harness + production + cases)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(source), "-o", str(binary)], check=True,
                           capture_output=True, text=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn("7 atomic bandwidth", result.stdout)


if __name__ == "__main__":
    unittest.main()
