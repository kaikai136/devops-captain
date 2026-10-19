from django.test import SimpleTestCase

from .. import services


class MonitoringParserCharacterizationTests(SimpleTestCase):
    monitor_output = """SECTION:system
hostname=node-1
arch=x86_64
kernel=Linux 6.8
os=Ubuntu 24.04
uptime=120.5
SECTION:cpu1
cpu 100 0 50 850 0 0 0 0 0 0
cpu0 100 0 50 850 0 0 0 0 0 0
SECTION:load
0.10 0.20 0.30 1/100 1
SECTION:cpu2
cpu 120 0 60 920 0 0 0 0 0 0
cpu0 120 0 60 920 0 0 0 0 0 0
SECTION:mem
MemTotal: 1000 kB
MemAvailable: 250 kB
Cached: 100 kB
SReclaimable: 10 kB
SECTION:net1
eth0: 1000 0 0 0 0 0 0 0 2000 0 0 0 0 0 0 0
SECTION:net2
eth0: 4072 0 0 0 0 0 0 0 6096 0 0 0 0 0 0 0
SECTION:df
Filesystem Type 1B-blocks Used Available Use% Mounted on
/dev/vda1 ext4 2048 1024 1024 50% /
tmpfs tmpfs 1024 0 1024 0% /run
"""

    def test_monitor_output_maps_to_exact_payload(self):
        self.assertEqual(
            services.parse_remote_resource_monitor_output(self.monitor_output),
            {
                "system": {
                    "hostname": "node-1", "arch": "x86_64", "os": "Ubuntu 24.04",
                    "kernel": "Linux 6.8", "uptimeSeconds": 120.5,
                },
                "cpu": {
                    "usagePercent": 30.0, "cores": 1, "load1": 0.1,
                    "perCore": [{"name": "cpu0", "usagePercent": 30.0}],
                    "load5": 0.2, "load15": 0.3,
                },
                "memory": {
                    "totalBytes": 1024000, "usedBytes": 768000,
                    "availableBytes": 256000, "cacheBytes": 112640,
                    "usagePercent": 75.0,
                },
                "network": [
                    {"name": "eth0", "rxBytesPerSecond": 3072.0, "txBytesPerSecond": 4096.0}
                ],
                "disks": [
                    {
                        "filesystem": "/dev/vda1", "type": "ext4", "mountpoint": "/",
                        "totalBytes": 2048, "usedBytes": 1024,
                        "availableBytes": 1024, "usagePercent": 50.0,
                    }
                ],
            },
        )

    def test_empty_and_malformed_sections_keep_current_behavior(self):
        with self.assertRaisesMessage(services.TerminalConnectionError, "\u5f53\u524d\u4e3b\u673a\u4e0d\u652f\u6301\u8d44\u6e90\u76d1\u63a7"):
            services.parse_remote_resource_monitor_output("")
        with self.assertRaisesMessage(services.TerminalConnectionError, "\u5185\u5b58\u6570\u636e\u89e3\u6790\u5931\u8d25"):
            services.parse_monitor_memory("malformed")
        self.assertEqual(services.parse_monitor_network("malformed"), {})
        self.assertEqual(services.parse_monitor_disks("malformed"), [])
