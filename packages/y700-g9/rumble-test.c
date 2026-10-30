// SPDX-License-Identifier: GPL-2.0-or-later
// One bounded evdev FF_RUMBLE effect, sent through an explicitly selected node.
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <signal.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t interrupted;
static void stop(int signal_number) { (void)signal_number; interrupted = 1; }

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "Usage: %s /dev/input/eventN\n", argv[0]);
        return 2;
    }
    int fd = open(argv[1], O_RDWR | O_CLOEXEC);
    if (fd < 0) { perror("open"); return 1; }
    char name[256] = {0};
    if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) < 0) { perror("EVIOCGNAME"); close(fd); return 1; }
    printf("FF_RUMBLE through %s: %s\n", argv[1], name);
    struct ff_effect effect = { .type = FF_RUMBLE, .id = -1,
        .replay = { .length = 300 },
        .u.rumble = { .strong_magnitude = 0x6000, .weak_magnitude = 0x6000 } };
    if (ioctl(fd, EVIOCSFF, &effect) < 0) { perror("EVIOCSFF"); close(fd); return 1; }
    signal(SIGINT, stop); signal(SIGTERM, stop);
    struct input_event event = { .type = EV_FF, .code = effect.id, .value = 1 };
    int result = 0;
    if (write(fd, &event, sizeof(event)) != sizeof(event)) { perror("start"); result = 1; }
    else {
        struct timespec left = { .tv_nsec = 350000000 };
        while (!interrupted && nanosleep(&left, &left) < 0 && errno == EINTR) { }
    }
    event.value = 0;
    if (write(fd, &event, sizeof(event)) != sizeof(event)) { perror("stop"); result = 1; }
    if (ioctl(fd, EVIOCRMFF, effect.id) < 0) { perror("EVIOCRMFF"); result = 1; }
    close(fd);
    return result;
}
