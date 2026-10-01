/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Lenovo Legion Y700 Gen 4 (TB322FC) Gyroscope & Motion Sensor Bridge
 *
 * Streams 6-axis IMU (gyroscope & accelerometer) measurements from
 * Qualcomm Snapdragon Sensor Core (SSC) and exposes them through:
 * 1. Cemuhook DSU protocol on UDP port 26760 (for Cemu, Yuzu, Ryujinx, Dolphin, Citra, etc.)
 * 2. Linux /dev/uinput motion sensors device with INPUT_PROP_ACCELEROMETER (for SDL2/3 and Steam)
 */

#include <glib.h>
#include <gio/gio.h>
#include <libssc/libssc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <math.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <linux/uinput.h>

#define DSU_MAGIC_SERVER "DSUS"
#define DSU_MAGIC_CLIENT "DSUC"
#define DSU_PROTOCOL_VERSION 1001
#define DSU_DEFAULT_PORT 26760

#define MSG_TYPE_VERSION         0x100000
#define MSG_TYPE_CONTROLLER_INFO 0x100001
#define MSG_TYPE_DATA            0x100002

#define MAX_CLIENTS 8
#define CLIENT_TIMEOUT_SEC 5

typedef struct __attribute__((packed)) {
    char magic[4];
    uint16_t version;
    uint16_t length;
    uint32_t crc32;
    uint32_t id;
} DSUHeader;

typedef struct __attribute__((packed)) {
    DSUHeader header;
    uint32_t msg_type;
    uint16_t version;
} DSUVersionResponse;

typedef struct __attribute__((packed)) {
    DSUHeader header;
    uint32_t msg_type;
    uint8_t slot;
    uint8_t slot_state;
    uint8_t device_model;
    uint8_t connection_type;
    uint8_t mac[6];
    uint8_t battery;
} DSUControllerInfoResponse;

typedef struct __attribute__((packed)) {
    DSUHeader header;
    uint32_t msg_type;
    uint8_t slot;
    uint8_t slot_state;
    uint8_t device_model;
    uint8_t connection_type;
    uint8_t mac[6];
    uint8_t battery;
    uint8_t is_connected;
    uint32_t packet_num;
    uint8_t buttons1;
    uint8_t buttons2;
    uint8_t ps_touch_button;
    uint8_t reserved;
    uint8_t left_stick_x;
    uint8_t left_stick_y;
    uint8_t right_stick_x;
    uint8_t right_stick_y;
    uint8_t analog_dpad[4];
    uint8_t analog_buttons[8];
    uint8_t touch_1[6];
    uint8_t touch_2[6];
    uint64_t timestamp_us;
    float accel_x;
    float accel_y;
    float accel_z;
    float gyro_pitch;
    float gyro_yaw;
    float gyro_roll;
} DSUDataResponse;

typedef struct {
    struct sockaddr_in addr;
    gint64 last_active_us;
    gboolean active;
} DSUClientEntry;

typedef struct {
    int udp_fd;
    int uinput_fd;
    GMainLoop *loop;
    GIOChannel *udp_channel;
    guint udp_watch_id;

    SSCSensorGyroscope *gyro;
    SSCSensorAccelerometer *accel;

    gfloat cur_accel_x, cur_accel_y, cur_accel_z;
    gfloat cur_gyro_x, cur_gyro_y, cur_gyro_z;

    uint32_t packet_counter;
    DSUClientEntry clients[MAX_CLIENTS];
} GyroBridge;

static GyroBridge *g_bridge = NULL;

static void on_signal(int sig) {
    (void)sig;
    if (g_bridge && g_bridge->loop && g_main_loop_is_running(g_bridge->loop)) {
        g_main_loop_quit(g_bridge->loop);
    }
}

static uint32_t crc32_ieee(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            crc = (crc >> 1) ^ (0xEDB88320 & (-(crc & 1)));
        }
    }
    return ~crc;
}

static void dsu_header_init(DSUHeader *hdr, uint16_t payload_len) {
    memcpy(hdr->magic, DSU_MAGIC_SERVER, 4);
    hdr->version = DSU_PROTOCOL_VERSION;
    hdr->length = payload_len;
    hdr->crc32 = 0;
    hdr->id = 0x00010001;
}

static void dsu_packet_finalize(DSUHeader *hdr, size_t total_size) {
    hdr->crc32 = 0;
    hdr->crc32 = crc32_ieee((const uint8_t *)hdr, total_size);
}

static void update_client_subscription(GyroBridge *bridge, struct sockaddr_in *addr) {
    gint64 now = g_get_monotonic_time();
    for (int i = 0; i < MAX_CLIENTS; i++) {
        if (bridge->clients[i].active &&
            bridge->clients[i].addr.sin_addr.s_addr == addr->sin_addr.s_addr &&
            bridge->clients[i].addr.sin_port == addr->sin_port) {
            bridge->clients[i].last_active_us = now;
            return;
        }
    }
    for (int i = 0; i < MAX_CLIENTS; i++) {
        if (!bridge->clients[i].active) {
            bridge->clients[i].addr = *addr;
            bridge->clients[i].last_active_us = now;
            bridge->clients[i].active = TRUE;
            g_print("DSU client subscribed: %s:%d\n",
                    inet_ntoa(addr->sin_addr), ntohs(addr->sin_port));
            return;
        }
    }
}

static void send_dsu_data_to_clients(GyroBridge *bridge) {
    gint64 now = g_get_monotonic_time();
    DSUDataResponse resp;
    memset(&resp, 0, sizeof(resp));

    dsu_header_init(&resp.header, sizeof(resp) - sizeof(DSUHeader));
    resp.msg_type = MSG_TYPE_DATA;
    resp.slot = 0;
    resp.slot_state = 2; // connected
    resp.device_model = 2; // full gyro
    resp.connection_type = 2; // USB
    resp.mac[5] = 0x01;
    resp.battery = 0x05; // Full
    resp.is_connected = 1;
    resp.packet_num = bridge->packet_counter++;
    resp.left_stick_x = 128;
    resp.left_stick_y = 128;
    resp.right_stick_x = 128;
    resp.right_stick_y = 128;
    resp.timestamp_us = (uint64_t)g_get_real_time();

    /* Convert accel from m/s^2 to G (1G = 9.80665 m/s^2) */
    resp.accel_x = bridge->cur_accel_x / 9.80665f;
    resp.accel_y = bridge->cur_accel_y / 9.80665f;
    resp.accel_z = bridge->cur_accel_z / 9.80665f;

    /* Convert gyro from rad/s to deg/s */
    resp.gyro_pitch = bridge->cur_gyro_x * (180.0f / (float)G_PI);
    resp.gyro_yaw   = bridge->cur_gyro_z * (180.0f / (float)G_PI);
    resp.gyro_roll  = bridge->cur_gyro_y * (180.0f / (float)G_PI);

    dsu_packet_finalize(&resp.header, sizeof(resp));

    for (int i = 0; i < MAX_CLIENTS; i++) {
        if (bridge->clients[i].active) {
            if (now - bridge->clients[i].last_active_us > CLIENT_TIMEOUT_SEC * G_USEC_PER_SEC) {
                bridge->clients[i].active = FALSE;
                continue;
            }
            sendto(bridge->udp_fd, &resp, sizeof(resp), 0,
                   (struct sockaddr *)&bridge->clients[i].addr,
                   sizeof(bridge->clients[i].addr));
        }
    }
}

static void emit_uinput_motion(GyroBridge *bridge) {
    if (bridge->uinput_fd < 0) return;

    /*
     * DualSense evdev sensor resolution:
     * Accel: 8192 units per 1G
     * Gyro: 16 units per deg/s
     */
    struct input_event ev[7];
    memset(ev, 0, sizeof(ev));

    float g_x = bridge->cur_accel_x / 9.80665f;
    float g_y = bridge->cur_accel_y / 9.80665f;
    float g_z = bridge->cur_accel_z / 9.80665f;

    float deg_x = bridge->cur_gyro_x * (180.0f / (float)G_PI);
    float deg_y = bridge->cur_gyro_y * (180.0f / (float)G_PI);
    float deg_z = bridge->cur_gyro_z * (180.0f / (float)G_PI);

    ev[0].type = EV_ABS; ev[0].code = ABS_X; ev[0].value = (int32_t)(g_x * 8192.0f);
    ev[1].type = EV_ABS; ev[1].code = ABS_Y; ev[1].value = (int32_t)(g_y * 8192.0f);
    ev[2].type = EV_ABS; ev[2].code = ABS_Z; ev[2].value = (int32_t)(g_z * 8192.0f);

    ev[3].type = EV_ABS; ev[3].code = ABS_RX; ev[3].value = (int32_t)(deg_x * 16.0f);
    ev[4].type = EV_ABS; ev[4].code = ABS_RY; ev[4].value = (int32_t)(deg_y * 16.0f);
    ev[5].type = EV_ABS; ev[5].code = ABS_RZ; ev[5].value = (int32_t)(deg_z * 16.0f);

    ev[6].type = EV_SYN; ev[6].code = SYN_REPORT; ev[6].value = 0;

    if (write(bridge->uinput_fd, ev, sizeof(ev)) < 0) {
        /* Ignore non-blocking write errors */
    }
}

static void on_gyro_measurement(SSCSensorGyroscope *s, gfloat x, gfloat y, gfloat z, gpointer data) {
    (void)s;
    GyroBridge *b = (GyroBridge *)data;
    b->cur_gyro_x = x;
    b->cur_gyro_y = y;
    b->cur_gyro_z = z;
    send_dsu_data_to_clients(b);
    emit_uinput_motion(b);
}

static void on_accel_measurement(SSCSensorAccelerometer *s, gfloat x, gfloat y, gfloat z, gpointer data) {
    (void)s;
    GyroBridge *b = (GyroBridge *)data;
    b->cur_accel_x = x;
    b->cur_accel_y = y;
    b->cur_accel_z = z;
}

static gboolean on_udp_readable(GIOChannel *source, GIOCondition cond, gpointer data) {
    (void)source;
    (void)cond;
    GyroBridge *b = (GyroBridge *)data;
    uint8_t buf[512];
    struct sockaddr_in client_addr;
    socklen_t addr_len = sizeof(client_addr);

    ssize_t n = recvfrom(b->udp_fd, buf, sizeof(buf), 0, (struct sockaddr *)&client_addr, &addr_len);
    if (n < 20) return TRUE;

    DSUHeader *hdr = (DSUHeader *)buf;
    if (memcmp(hdr->magic, DSU_MAGIC_CLIENT, 4) != 0) return TRUE;

    uint32_t msg_type = *(uint32_t *)(buf + sizeof(DSUHeader));

    if (msg_type == MSG_TYPE_VERSION) {
        DSUVersionResponse resp;
        memset(&resp, 0, sizeof(resp));
        dsu_header_init(&resp.header, sizeof(resp) - sizeof(DSUHeader));
        resp.msg_type = MSG_TYPE_VERSION;
        resp.version = DSU_PROTOCOL_VERSION;
        dsu_packet_finalize(&resp.header, sizeof(resp));
        sendto(b->udp_fd, &resp, sizeof(resp), 0, (struct sockaddr *)&client_addr, addr_len);
    } else if (msg_type == MSG_TYPE_CONTROLLER_INFO) {
        DSUControllerInfoResponse resp;
        memset(&resp, 0, sizeof(resp));
        dsu_header_init(&resp.header, sizeof(resp) - sizeof(DSUHeader));
        resp.msg_type = MSG_TYPE_CONTROLLER_INFO;
        resp.slot = 0;
        resp.slot_state = 2;
        resp.device_model = 2;
        resp.connection_type = 2;
        resp.mac[5] = 0x01;
        resp.battery = 0x05;
        dsu_packet_finalize(&resp.header, sizeof(resp));
        sendto(b->udp_fd, &resp, sizeof(resp), 0, (struct sockaddr *)&client_addr, addr_len);
    } else if (msg_type == MSG_TYPE_DATA) {
        update_client_subscription(b, &client_addr);
    }
    return TRUE;
}

static int init_uinput(void) {
    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) return -1;

    ioctl(fd, UI_SET_EVBIT, EV_ABS);
    ioctl(fd, UI_SET_EVBIT, EV_MSC);
    ioctl(fd, UI_SET_MSCBIT, MSC_TIMESTAMP);
    ioctl(fd, UI_SET_PROPBIT, INPUT_PROP_ACCELEROMETER);

    struct uinput_user_dev dev;
    memset(&dev, 0, sizeof(dev));
    strncpy(dev.name, "Lenovo Legion Y700 Motion Sensors", UINPUT_MAX_NAME_SIZE - 1);
    dev.id.bustype = BUS_USB;
    dev.id.vendor = 0x054c;   /* Sony */
    dev.id.product = 0x0ce6;  /* DualSense */
    dev.id.version = 1;

    int axes[] = { ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ };
    for (int i = 0; i < 6; i++) {
        ioctl(fd, UI_SET_ABSBIT, axes[i]);
        dev.absmin[axes[i]] = -32768;
        dev.absmax[axes[i]] = 32767;
        dev.absfuzz[axes[i]] = 16;
        dev.absflat[axes[i]] = 0;
    }

    if (write(fd, &dev, sizeof(dev)) < 0 || ioctl(fd, UI_DEV_CREATE) < 0) {
        close(fd);
        return -1;
    }
    return fd;
}

int main(int argc, char **argv) {
    int port = DSU_DEFAULT_PORT;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
            port = atoi(argv[++i]);
        }
    }

    GyroBridge bridge;
    memset(&bridge, 0, sizeof(bridge));
    g_bridge = &bridge;

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);

    bridge.udp_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (bridge.udp_fd < 0) {
        g_printerr("Failed to create UDP socket: %s\n", strerror(errno));
        return 1;
    }

    int opt = 1;
    setsockopt(bridge.udp_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in saddr;
    memset(&saddr, 0, sizeof(saddr));
    saddr.sin_family = AF_INET;
    saddr.sin_addr.s_addr = htonl(INADDR_ANY);
    saddr.sin_port = htons(port);

    if (bind(bridge.udp_fd, (struct sockaddr *)&saddr, sizeof(saddr)) < 0) {
        g_printerr("Failed to bind DSU UDP port %d: %s\n", port, strerror(errno));
        close(bridge.udp_fd);
        return 1;
    }

    bridge.uinput_fd = init_uinput();
    g_print("DSU server listening on 0.0.0.0:%d (uinput: %s)\n",
            port, bridge.uinput_fd >= 0 ? "enabled" : "disabled");

    bridge.gyro = ssc_sensor_gyroscope_new_sync(NULL, NULL);
    bridge.accel = ssc_sensor_accelerometer_new_sync(NULL, NULL);

    if (!bridge.gyro || !bridge.accel) {
        g_printerr("Failed to initialize SSC gyro/accel sensors\n");
        return 1;
    }

    g_signal_connect(bridge.gyro, "measurement", G_CALLBACK(on_gyro_measurement), &bridge);
    g_signal_connect(bridge.accel, "measurement", G_CALLBACK(on_accel_measurement), &bridge);

    ssc_sensor_gyroscope_open_sync(bridge.gyro, NULL, NULL);
    ssc_sensor_accelerometer_open_sync(bridge.accel, NULL, NULL);

    bridge.loop = g_main_loop_new(NULL, FALSE);
    bridge.udp_channel = g_io_channel_unix_new(bridge.udp_fd);
    bridge.udp_watch_id = g_io_add_watch(bridge.udp_channel, G_IO_IN, on_udp_readable, &bridge);

    g_print("Gyro bridge active.\n");
    g_main_loop_run(bridge.loop);

    if (bridge.udp_watch_id) {
        g_source_remove(bridge.udp_watch_id);
    }
    if (bridge.udp_channel) {
        g_io_channel_unref(bridge.udp_channel);
    }
    if (bridge.udp_fd >= 0) {
        close(bridge.udp_fd);
    }
    if (bridge.gyro) {
        ssc_sensor_gyroscope_close_sync(bridge.gyro, NULL, NULL);
        g_object_unref(bridge.gyro);
    }
    if (bridge.accel) {
        ssc_sensor_accelerometer_close_sync(bridge.accel, NULL, NULL);
        g_object_unref(bridge.accel);
    }
    if (bridge.uinput_fd >= 0) {
        ioctl(bridge.uinput_fd, UI_DEV_DESTROY);
        close(bridge.uinput_fd);
    }
    g_main_loop_unref(bridge.loop);
    return 0;
}
