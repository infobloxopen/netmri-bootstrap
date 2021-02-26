import os
from unittest import TestCase
from netmri_bootstrap import config


class TestConfig(TestCase):
    @classmethod
    def setUpClass(cls):
        from importlib import reload
        reload(config)
        config.config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                          "test_config.json")

    def test_get_config(self):
        conf = config.get_config()
        self.assertEqual(conf.host, "localhost")
        self.assertEqual(conf.username, "admin")
        self.assertEqual(conf.password, "unittest")
        self.assertEqual(conf.proto, "https")
        self.assertEqual(conf.ssl_verify, True)
        self.assertEqual(conf.scripts_root, "/tmp/netmri/")
        self.assertEqual(conf.bootstrap_branch, "master")
        self.assertEqual(conf.skip_readonly_objects, True)
        expected_class_paths = {
            'Script': 'scripts',
            'Policy': 'policy',
            'PolicyRule': 'policy/rules'
        }
        self.assertEqual(conf.class_paths, expected_class_paths)

    def test_get_api_client(self):
        client = config.get_api_client()
        self.assertEqual(client.host, 'localhost')
        self.assertEqual(client.username, 'admin')
        self.assertEqual(client.password, 'unittest')
        self.assertEqual(client.protocol, "https")
        self.assertEqual(client.ssl_verify, True)
