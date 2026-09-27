# SPDX-License-Identifier: BSD-3-Clause
# AudioReach topology source for the Lenovo Legion Y700 Gen4 (SM8750).
# MultiMedia1 feeds the two AW88461 speaker amps on Secondary MI2S (SD1);
# MultiMedia3 captures the builtin mics through the WCD9395 TX ADCs
# (SoundWire2 hanging off the VA macro).
include(`audioreach/audioreach.m4')
include(`audioreach/stream-subgraph.m4')
include(`audioreach/device-subgraph.m4')
include(`util/route.m4')
include(`util/mixer.m4')
include(`audioreach/tokens.m4')
dnl Playback MultiMedia1
STREAM_SG_PCM_ADD(audioreach/subgraph-stream-vol-playback.m4, FRONTEND_DAI_MULTIMEDIA1,
	`S16_LE', 48000, 48000, 2, 2,
	0x00004001, 0x00004001, 0x00006001, `110000')
dnl Capture MultiMedia3
STREAM_SG_PCM_ADD(audioreach/subgraph-stream-capture.m4, FRONTEND_DAI_MULTIMEDIA3,
	`S16_LE', 48000, 48000, 1, 2,
	0x00004003, 0x00004003, 0x00006020, `110000')
dnl Speaker amps: 2x AW88461 on SECONDARY MI2S, DSP drives the SD1 data line.
DEVICE_SG_ADD(audioreach/subgraph-device-i2s-playback.m4, `Secondary', SECONDARY_MI2S_RX,
	`S16_LE', 48000, 48000, 2, 2,
	LPAIF_INTF_TYPE_LPAIF, I2S_INTF_TYPE_SECONDARY, SD_LINE_IDX_I2S_SD1, DATA_FORMAT_FIXED_POINT,
	0x00004005, 0x00004005, 0x00006050, `SECONDARY_MI2S_RX')
dnl WCD9395 TX (builtin mics), SoundWire2 off the VA macro.
DEVICE_SG_ADD(audioreach/subgraph-device-codec-dma-capture.m4, `TX_CODEC_DMA_TX_3', TX_CODEC_DMA_TX_3,
	`S16_LE', 48000, 48000, 1, 2,
	LPAIF_INTF_TYPE_RXTX, CODEC_INTF_IDX_TX3, 0, DATA_FORMAT_FIXED_POINT,
	0x00004009, 0x00004009, 0x00006090)

STREAM_DEVICE_PLAYBACK_MIXER(SECONDARY_MI2S_RX, ``SECONDARY_MI2S_RX'', ``MultiMedia1'')
STREAM_DEVICE_PLAYBACK_ROUTE(SECONDARY_MI2S_RX, ``SECONDARY_MI2S_RX Audio Mixer'', ``MultiMedia1, stream0.logger1'')

STREAM_DEVICE_CAPTURE_MIXER(FRONTEND_DAI_MULTIMEDIA3, ``TX_CODEC_DMA_TX_3'')
STREAM_DEVICE_CAPTURE_ROUTE(FRONTEND_DAI_MULTIMEDIA3, ``MultiMedia3 Mixer'', ``TX_CODEC_DMA_TX_3, device120.logger1'')
