// SPDX-License-Identifier: GPL-2.0
/*
 * als-bridge - minimal IIO light sensor backed by a value published from
 * userspace.
 *
 * The Y700 Gen4's ambient light sensor is wired to the ADSP sensor PD and is
 * only reachable through the SSC (iio-sensor-proxy/libssc over QRTR), which
 * serves D-Bus clients fine. Steam, however, reads
 * /sys/bus/iio/devices/iio:deviceN/in_illuminance_raw directly and greys out
 * its adaptive-brightness switch when nothing is there. This bridge exposes
 * exactly that interface; the als-bridge daemon writes lux values read from
 * net.hadess.SensorProxy into the module parameter.
 */

#include <linux/iio/iio.h>
#include <linux/module.h>
#include <linux/platform_device.h>

static unsigned int lux;
module_param(lux, uint, 0644);
MODULE_PARM_DESC(lux, "ambient light level in lux, published by the als-bridge daemon");

/*
 * Emulated ACPI firmware-node path. Tunable so the exact format Steam
 * expects can be iterated on without a rebuild.
 */
static char *fw_path = "\\_SB_.PCI0.I2C1.OPT3";
module_param(fw_path, charp, 0644);
MODULE_PARM_DESC(fw_path, "contents of the emulated firmware_node/path attribute");

static int alsbridge_read_raw(struct iio_dev *indio_dev,
			      struct iio_chan_spec const *chan,
			      int *val, int *val2, long mask)
{
	switch (mask) {
	case IIO_CHAN_INFO_RAW:
		*val = READ_ONCE(lux);
		return IIO_VAL_INT;
	default:
		return -EINVAL;
	}
}

static const struct iio_chan_spec alsbridge_channels[] = {
	{
		.type = IIO_LIGHT,
		.info_mask_separate = BIT(IIO_CHAN_INFO_RAW),
	},
};

static const struct iio_info alsbridge_info = {
	.read_raw = alsbridge_read_raw,
};

/*
 * Steam's ALS scan (BHasAmbientLightSensor) accepts three device names:
 * "ltrf216a" (model 1, needs firmware_node/path + in_illuminance_raw),
 * "opt3001" (model 2, needs firmware_node/path whose parsed content must
 * yield gain > 0) and "als" (model 3, gain hardcoded to 1.0, nothing else
 * read). Reverse-engineering steamclient.so showed model 3 is trivially
 * accepted, so we simply register the IIO device under that name; the
 * daemon keeps feeding live lux into the module parameter and the IIO
 * in_illuminance_raw channel stays available for other consumers.
 */
static ssize_t fw_path_show(struct kobject *kobj, struct kobj_attribute *attr,
			    char *buf)
{
	return sysfs_emit(buf, "%s\n", fw_path);
}

static struct kobj_attribute fw_path_attr = __ATTR(path, 0444, fw_path_show, NULL);
static struct kobject *fw_node_kobj;

static void alsbridge_fwnode_cleanup(void *data)
{
	kobject_put(fw_node_kobj);
}

static int alsbridge_probe(struct platform_device *pdev)
{
	struct iio_dev *indio_dev;
	int ret;

	indio_dev = devm_iio_device_alloc(&pdev->dev, 0);
	if (!indio_dev)
		return -ENOMEM;

	indio_dev->name = "als";
	indio_dev->modes = INDIO_DIRECT_MODE;
	indio_dev->channels = alsbridge_channels;
	indio_dev->num_channels = ARRAY_SIZE(alsbridge_channels);
	indio_dev->info = &alsbridge_info;

	ret = devm_iio_device_register(&pdev->dev, indio_dev);
	if (ret)
		return ret;

	/* Hang the emulated ACPI firmware node off the IIO device itself
	 * (/sys/bus/iio/devices/iio:deviceN/firmware_node/path), which is what
	 * Steam inspects - not the platform device. */
	fw_node_kobj = kobject_create_and_add("firmware_node", &indio_dev->dev.kobj);
	if (!fw_node_kobj)
		return -ENOMEM;

	ret = sysfs_create_file(fw_node_kobj, &fw_path_attr.attr);
	if (ret) {
		kobject_put(fw_node_kobj);
		return ret;
	}

	ret = devm_add_action_or_reset(&pdev->dev, alsbridge_fwnode_cleanup, NULL);
	if (ret)
		return ret;

	return 0;
}

static const struct platform_device_id alsbridge_id[] = {
	{ .name = "als-bridge" },
	{ }
};

static struct platform_driver alsbridge_driver = {
	.driver = { .name = "als-bridge" },
	.probe = alsbridge_probe,
	.id_table = alsbridge_id,
};

static struct platform_device *alsbridge_pdev;

static int __init alsbridge_init(void)
{
	int ret;

	ret = platform_driver_register(&alsbridge_driver);
	if (ret)
		return ret;

	alsbridge_pdev = platform_device_register_simple("als-bridge", -1, NULL, 0);
	if (IS_ERR(alsbridge_pdev)) {
		platform_driver_unregister(&alsbridge_driver);
		return PTR_ERR(alsbridge_pdev);
	}

	return 0;
}

static void __exit alsbridge_exit(void)
{
	platform_device_unregister(alsbridge_pdev);
	platform_driver_unregister(&alsbridge_driver);
}

module_init(alsbridge_init);
module_exit(alsbridge_exit);

MODULE_DESCRIPTION("IIO illuminance bridge fed by the als-bridge userspace daemon");
MODULE_LICENSE("GPL");
