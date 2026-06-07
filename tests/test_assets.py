import unittest

from it_ops_toolkit.assets import AssetScanError, expand_scan_hosts
from it_ops_toolkit.config import ScanProfile


class AssetScanTests(unittest.TestCase):
    def test_expand_scan_hosts(self) -> None:
        profile = ScanProfile(subnets=["192.168.1.0/30"])

        hosts = expand_scan_hosts(profile)

        self.assertEqual(hosts, ["192.168.1.1", "192.168.1.2"])

    def test_invalid_subnet_raises(self) -> None:
        profile = ScanProfile(subnets=["not-a-subnet"])

        with self.assertRaises(AssetScanError):
            expand_scan_hosts(profile)


if __name__ == "__main__":
    unittest.main()

