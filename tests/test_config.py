import tempfile
import unittest
from pathlib import Path

from it_ops_toolkit.config import ConfigError, create_default_config_file, load_config


class ConfigTests(unittest.TestCase):
    def test_create_and_load_default_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ops.yaml"

            create_default_config_file(path)
            config = load_config(path)

            self.assertIn("office_lan", config.scan_profiles)
            self.assertIn("daily_basic", config.health_profiles)

    def test_refuses_to_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ops.yaml"

            create_default_config_file(path)

            with self.assertRaises(ConfigError):
                create_default_config_file(path)


if __name__ == "__main__":
    unittest.main()

