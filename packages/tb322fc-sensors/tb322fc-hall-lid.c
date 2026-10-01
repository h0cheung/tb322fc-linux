/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Lenovo Legion Y700 Gen 4 (TB322FC) Folio Hall Sensor Lid Switch Bridge
 *
 * Reads ROHM BU52053NVX magnetic Hall effect sensor events from Qualcomm
 * Snapdragon Sensor Core (SSC) and forwards them as Linux input SW_LID
 * switch events via /dev/uinput.
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
#include <linux/uinput.h>

#define SSC_MSG_HALL_EVENT 770

typedef struct {
    int uinput_fd;
    GMainLoop *loop;
    SSCSensor *sensor;
    SSCClient *client;
    gulong report_id;
    int last_state;
} HallLidBridge;

static HallLidBridge *g_bridge = NULL;

static void on_signal(int sig) {
    (void)sig;
    if (g_bridge && g_bridge->loop && g_main_loop_is_running(g_bridge->loop)) {
        g_main_loop_quit(g_bridge->loop);
    }
}

static int uinput_init(void) {
    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) {
        g_printerr("Failed to open /dev/uinput: %s\n", strerror(errno));
        return -1;
    }

    if (ioctl(fd, UI_SET_EVBIT, EV_SW) < 0 ||
        ioctl(fd, UI_SET_SWBIT, SW_LID) < 0) {
        g_printerr("Failed to setup uinput EV_SW/SW_LID: %s\n", strerror(errno));
        close(fd);
        return -1;
    }

    struct uinput_setup usetup;
    memset(&usetup, 0, sizeof(usetup));
    usetup.id.bustype = BUS_HOST;
    usetup.id.vendor = 0x17aa;  /* Lenovo */
    usetup.id.product = 0x0002;
    strncpy(usetup.name, "Lenovo Legion Y700 Folio Hall Sensor", UINPUT_MAX_NAME_SIZE - 1);

    if (ioctl(fd, UI_DEV_SETUP, &usetup) < 0 ||
        ioctl(fd, UI_DEV_CREATE) < 0) {
        g_printerr("Failed to create uinput device: %s\n", strerror(errno));
        close(fd);
        return -1;
    }

    g_print("Created uinput SW_LID device: %s\n", usetup.name);
    return fd;
}

static void emit_lid_switch(int fd, int closed) {
    struct input_event ev[2];
    memset(ev, 0, sizeof(ev));

    ev[0].type = EV_SW;
    ev[0].code = SW_LID;
    ev[0].value = closed ? 1 : 0;

    ev[1].type = EV_SYN;
    ev[1].code = SYN_REPORT;
    ev[1].value = 0;

    if (write(fd, ev, sizeof(ev)) < 0) {
        g_printerr("Failed to write uinput event: %s\n", strerror(errno));
    } else {
        g_print("Lid event emitted: %s (SW_LID=%d)\n", closed ? "CLOSED" : "OPEN", closed ? 1 : 0);
    }
}

static void on_report(SSCClient *client, guint32 msg_id, guint64 uid_high, guint64 uid_low, GArray *buf, gpointer user_data) {
    (void)client;
    (void)uid_high;
    (void)uid_low;
    HallLidBridge *bridge = (HallLidBridge *)user_data;

    if (msg_id == SSC_MSG_HALL_EVENT && buf && buf->len >= 2) {
        /*
         * Protobuf parsing of sns_hall_event:
         * Tag 1 (event_type varint): 0x08 followed by value:
         * 0 = SNS_HALL_EVENT_TYPE_FAR (cover open)
         * 1 = SNS_HALL_EVENT_TYPE_NEAR (cover closed)
         */
        const guint8 *data = (const guint8 *)buf->data;
        int state = -1;

        for (guint i = 0; i + 1 < buf->len; i++) {
            if (data[i] == 0x08) {
                state = data[i + 1] != 0 ? 1 : 0;
                break;
            }
        }

        if (state >= 0 && state != bridge->last_state) {
            bridge->last_state = state;
            emit_lid_switch(bridge->uinput_fd, state);
        }
    }
}

static void on_sensor_opened(SSCSensor *sensor, GAsyncResult *res, gpointer user_data) {
    HallLidBridge *bridge = (HallLidBridge *)user_data;
    GError *error = NULL;

    if (!ssc_sensor_open_finish(sensor, res, &error)) {
        g_printerr("Failed to open hall sensor: %s\n", error ? error->message : "unknown");
        g_main_loop_quit(bridge->loop);
        return;
    }
    g_print("Hall sensor opened successfully. Monitoring cover state.\n");
}

static void on_sensor_created(GObject *source, GAsyncResult *res, gpointer user_data) {
    (void)source;
    HallLidBridge *bridge = (HallLidBridge *)user_data;
    GError *error = NULL;

    bridge->sensor = ssc_sensor_new_finish(res, &error);
    if (!bridge->sensor) {
        g_printerr("Failed to create hall sensor: %s\n", error ? error->message : "unknown");
        g_main_loop_quit(bridge->loop);
        return;
    }

    g_object_get(bridge->sensor, SSC_SENSOR_CLIENT, &bridge->client, NULL);
    bridge->report_id = g_signal_connect(bridge->client, "report", G_CALLBACK(on_report), bridge);

    ssc_sensor_open(bridge->sensor, NULL, (GAsyncReadyCallback)on_sensor_opened, bridge);
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    HallLidBridge bridge;
    memset(&bridge, 0, sizeof(bridge));
    bridge.last_state = -1;
    g_bridge = &bridge;

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);

    bridge.uinput_fd = uinput_init();
    if (bridge.uinput_fd < 0) {
        return 1;
    }

    bridge.loop = g_main_loop_new(NULL, FALSE);

    g_print("Connecting to Qualcomm SSC hall sensor...\n");
    ssc_sensor_new("hall", NULL, on_sensor_created, &bridge);

    g_main_loop_run(bridge.loop);

    if (bridge.sensor) {
        if (bridge.report_id && bridge.client) {
            g_signal_handler_disconnect(bridge.client, bridge.report_id);
        }
        g_object_unref(bridge.sensor);
    }
    if (bridge.client) {
        g_object_unref(bridge.client);
    }
    if (bridge.uinput_fd >= 0) {
        ioctl(bridge.uinput_fd, UI_DEV_DESTROY);
        close(bridge.uinput_fd);
    }
    g_main_loop_unref(bridge.loop);
    return 0;
}
