"""自动选择参与者可通过局域网访问的本机 IPv4 地址。"""

from ipaddress import IPv4Address, IPv4Network
import json
import platform
import socket
import subprocess

from light_sign.links import participant_link

_LOCAL_NETWORKS = tuple(IPv4Network(network) for network in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10",
))


def usable_ipv4(value):
    try:
        address = IPv4Address(value)
    except ValueError:
        return False
    # 排除回环、自动分配地址，以及代理常用的 198.18/15 测试地址。
    if address.is_loopback or address.is_unspecified or address.is_link_local or address.is_multicast or address.is_reserved:
        return False
    return address.is_global or any(address in network for network in _LOCAL_NETWORKS)


def _windows_interfaces():
    script = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$ErrorActionPreference = 'Stop'
$items = @([System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | ForEach-Object {
    $adapter = $_
    if ($adapter.OperationalStatus -ne 'Up') { return }
    $properties = $adapter.GetIPProperties()
    $type = $adapter.NetworkInterfaceType.ToString()
    $virtual = ($adapter.Name + ' ' + $adapter.Description) -match 'VMware|Virtual|VPN|TAP|TUN|Hyper-V|WSL|Loopback|Docker|Proxy'
    $physical = ($type -eq 'Wireless80211' -or $type -eq 'Ethernet') -and -not $virtual
    $gateways = @($properties.GatewayAddresses | Where-Object { $_.Address.AddressFamily -eq 'InterNetwork' -and $_.Address.ToString() -ne '0.0.0.0' })
    foreach ($ip in $properties.UnicastAddresses) {
        if ($ip.Address.AddressFamily -ne 'InterNetwork') { continue }
        [PSCustomObject]@{
            address = $ip.Address.ToString()
            physical = [bool]$physical
            gateway = [bool]($gateways.Count -gt 0)
            metric = 0
        }
    }
})
ConvertTo-Json -InputObject $items -Compress
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", timeout=5, check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return json.loads(result.stdout.lstrip("\ufeff"))


def _socket_addresses():
    candidates = []
    try:
        # UDP connect 只查询路由选择的源地址，不发送数据，也不要求公网可达。
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 80))
            candidates.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        candidates.extend(info[4][0] for info in socket.getaddrinfo(
            socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM,
        ))
    except OSError:
        pass
    return candidates


def discover_lan_ipv4():
    if platform.system() == "Windows":
        try:
            interfaces = _windows_interfaces()
        except (OSError, subprocess.SubprocessError, ValueError):
            interfaces = None
        if interfaces is not None:
            candidates = [item for item in interfaces
                          if usable_ipv4(item.get("address", ""))
                          and (item.get("physical") or item.get("gateway"))]
            candidates.sort(key=lambda item: (
                not item.get("physical"), not item.get("gateway"),
                item.get("metric", 0), int(IPv4Address(item["address"])),
            ))
            if candidates:
                return candidates[0]["address"]
            raise ValueError("未检测到可用局域网，请连接 Wi-Fi 或网线后重新生成二维码。")
    for address in _socket_addresses():
        if usable_ipv4(address):
            return address
    raise ValueError("未检测到可用局域网，请连接 Wi-Fi 或网线后重新生成二维码。")


def participant_base_url(scheme="https", port=8504, host="0.0.0.0", override=None):
    if override:
        participant_link(override, "validate-address")
        return override.strip()
    if scheme not in {"http", "https"} or not 1 <= int(port) <= 65535:
        raise ValueError("参与者入口协议或端口配置无效")
    address = discover_lan_ipv4() if host in {"0.0.0.0", "::", ""} else host
    if not usable_ipv4(address):
        raise ValueError("参与者服务需监听局域网地址，才能生成手机可访问的二维码。")
    return f"{scheme}://{address}:{int(port)}/"
