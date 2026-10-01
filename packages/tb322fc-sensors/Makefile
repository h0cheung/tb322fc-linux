CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra
PKG_CONFIG ?= pkg-config

LIBSSC_CFLAGS := $(shell $(PKG_CONFIG) --cflags libssc gio-2.0 glib-2.0)
LIBSSC_LIBS := $(shell $(PKG_CONFIG) --libs libssc gio-2.0 glib-2.0)

all: tb322fc-hall-lid tb322fc-gyro-bridge

tb322fc-hall-lid: tb322fc-hall-lid.c
	$(CC) $(CFLAGS) $(LIBSSC_CFLAGS) -o $@ $< $(LIBSSC_LIBS)

tb322fc-gyro-bridge: tb322fc-gyro-bridge.c
	$(CC) $(CFLAGS) $(LIBSSC_CFLAGS) -o $@ $< $(LIBSSC_LIBS) -lm

clean:
	rm -f tb322fc-hall-lid tb322fc-gyro-bridge

install: all
	install -Dm755 tb322fc-hall-lid $(DESTDIR)/usr/bin/tb322fc-hall-lid
	install -Dm755 tb322fc-gyro-bridge $(DESTDIR)/usr/bin/tb322fc-gyro-bridge
	install -Dm644 tb322fc-hall-lid.service $(DESTDIR)/usr/lib/systemd/system/tb322fc-hall-lid.service
	install -Dm644 tb322fc-gyro-bridge.service $(DESTDIR)/usr/lib/systemd/system/tb322fc-gyro-bridge.service

.PHONY: all clean install
