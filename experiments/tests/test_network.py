"""自动局域网寻址：优先物理网卡，兼顾离线局域网与系统回退。"""

import unittest
from unittest.mock import patch

from light_sign import network


class NetworkTests(unittest.TestCase):
    def test_address_filters(self):
        for address in ["127.0.0.1", "0.0.0.0", "169.254.1.2", "198.18.0.1", "224.0.0.1", "::1", ""]:
            with self.subTest(address=address):
                self.assertFalse(network.usable_ipv4(address))
        for address in ["10.10.133.142", "172.16.1.2", "192.168.1.2", "100.64.1.2"]:
            with self.subTest(address=address):
                self.assertTrue(network.usable_ipv4(address))

    @patch.object(network.platform, "system", return_value="Windows")
    def test_physical_wifi_preferred_to_proxy_and_vmware(self, _system):
        interfaces = [
            {"address": "192.168.19.1", "physical": False, "gateway": False, "metric": 1},
            {"address": "198.18.0.1", "physical": False, "gateway": True, "metric": 1},
            {"address": "10.8.0.1", "physical": False, "gateway": True, "metric": 1},
            {"address": "10.10.133.142", "physical": True, "gateway": True, "metric": 50},
        ]
        with patch.object(network, "_windows_interfaces", return_value=interfaces):
            self.assertEqual(network.discover_lan_ipv4(), "10.10.133.142")

    @patch.object(network.platform, "system", return_value="Windows")
    def test_gateway_and_metric_select_active_lan(self, _system):
        interfaces = [
            {"address": "192.168.5.2", "physical": True, "gateway": False, "metric": 5},
            {"address": "192.168.1.2", "physical": True, "gateway": True, "metric": 20},
            {"address": "192.168.2.2", "physical": True, "gateway": True, "metric": 10},
        ]
        with patch.object(network, "_windows_interfaces", return_value=interfaces):
            self.assertEqual(network.discover_lan_ipv4(), "192.168.2.2")

    @patch.object(network.platform, "system", return_value="Windows")
    def test_offline_physical_lan_without_gateway(self, _system):
        interfaces = [{"address": "192.168.1.2", "physical": True, "gateway": False, "metric": 10}]
        with patch.object(network, "_windows_interfaces", return_value=interfaces):
            self.assertEqual(network.discover_lan_ipv4(), "192.168.1.2")

    @patch.object(network.platform, "system", return_value="Windows")
    def test_vmware_only_does_not_generate_misleading_qr(self, _system):
        interfaces = [{"address": "192.168.19.1", "physical": False, "gateway": False, "metric": 1}]
        with patch.object(network, "_windows_interfaces", return_value=interfaces):
            with self.assertRaisesRegex(ValueError, "连接 Wi-Fi"):
                network.discover_lan_ipv4()

    @patch.object(network.platform, "system", return_value="Windows")
    def test_system_inspection_failure_falls_back_to_sockets(self, _system):
        with patch.object(network, "_windows_interfaces", side_effect=OSError), \
             patch.object(network, "_socket_addresses", return_value=["127.0.0.1", "198.18.0.1", "192.168.1.2"]):
            self.assertEqual(network.discover_lan_ipv4(), "192.168.1.2")

    @patch.object(network.platform, "system", return_value="Linux")
    def test_socket_discovery_and_no_network_error(self, _system):
        with patch.object(network, "_socket_addresses", return_value=["10.10.1.2"]):
            self.assertEqual(network.discover_lan_ipv4(), "10.10.1.2")
        with patch.object(network, "_socket_addresses", return_value=[]):
            with self.assertRaises(ValueError):
                network.discover_lan_ipv4()

    def test_scheme_port_and_explicit_binding(self):
        with patch.object(network, "discover_lan_ipv4", return_value="10.10.133.142"):
            self.assertEqual(network.participant_base_url(), "https://10.10.133.142:8504/")
            self.assertEqual(network.participant_base_url("http", 9000), "http://10.10.133.142:9000/")
        self.assertEqual(network.participant_base_url(host="192.168.1.2"), "https://192.168.1.2:8504/")
        with self.assertRaises(ValueError):
            network.participant_base_url(host="127.0.0.1")

    def test_advanced_override_remains_compatible(self):
        with patch.object(network, "discover_lan_ipv4") as discover:
            self.assertEqual(network.participant_base_url(override="https://custom.example:9000/"),
                             "https://custom.example:9000/")
            discover.assert_not_called()
        with self.assertRaises(ValueError):
            network.participant_base_url(override="javascript:alert(1)")


if __name__ == "__main__":
    unittest.main()
