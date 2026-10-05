-- CSOT PP8807HB1-1 panel on the Lenovo Legion Tab Y700 Gen4 (SM8750, "elden").
--
-- The panel exposes no EDID, so gamescope synthesizes one (patch 0002) and
-- this profile supplies the identity the synthetic EDID lacks. The panel's
-- HDR static metadata is model-level and comes from the downstream device
-- tree (qcom,mdss-dsi-panel-hdr-color-primaries / -peak-brightness): the same
-- values on every unit, so they can be hardcoded here.
--
-- The panel is a 10-bit Gamma 2.2 LCD, not a PQ display, so HDR is presented
-- as a Gamma 2.2 output: gamescope maps PQ content into it through its own
-- color pipeline rather than asking the kernel for a PQ scanout.
gamescope.config.known_displays.csot_pp8807hb1_1 = {
    pretty_name = "CSOT PP8807HB1-1 (Lenovo Y700 Gen4)",
    hdr = {
        supported = true,
        force_enabled = false,
        eotf = gamescope.eotf.gamma22,
        -- Peak 1000 nits, from qcom,mdss-dsi-panel-peak-brightness.
        max_content_light_level = 1000,
        max_frame_average_luminance = 600,
        min_content_light_level = 0.5,
    },
    -- sRGB/Rec.709 primaries, from qcom,mdss-dsi-panel-hdr-color-primaries.
    colorimetry = {
        r = { x = 0.640, y = 0.340 },
        g = { x = 0.310, y = 0.600 },
        b = { x = 0.160, y = 0.060 },
        w = { x = 0.290, y = 0.310 },
    },
    matches = function(display)
        -- EDID-less internal DSI panel.
        if display.internal and not display.has_edid then
            debug("[csot_pp8807hb1_1] Matched internal EDID-less panel on "..display.connector)
            return 5000
        end
        return -1
    end,
}
debug("Registered CSOT PP8807HB1-1 (Lenovo Y700 Gen4) as a known display")
