"""
PTZ_ASTRO v1.1 - 网络接口枚举模块
枚举所有网络接口，分类（有线>无线>虚拟），按优先级排序，提供用户选择 UI。

Author: 雅痞张@南方天文
"""

import subprocess

from .logger import LOG


def _run_cmd(cmd: str) -> str:
    """执行命令行并返回输出。"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except Exception as e:
        LOG.log("warning", f"命令执行失败 {cmd}: {e}")
        return ""


def _classify_interface(if_name: str, if_type_hint: str | None = None) -> str:
    """分类网络接口类型。
    
    返回: 'wired' | 'wireless' | 'virtual'
    """
    lower = if_name.lower()

    # 常见虚拟网卡关键词
    virtual_keywords = [
        "loopback", "lo:", "docker", "veth", "br-", "bridge",
        "vmnet", "virtual", "tap", "tun", "vnic", "hamachi",
        "zero tier", "zerotier", "wg", "wireguard", "wsl",
        "hyper-v", "vpn", "openvpn", "pppoe", "bluetooth",
        "teredo", "isatap", "6to4", "netvsc", "pseudo",
    ]

    # 常见无线网卡关键词
    wireless_keywords = [
        "wi-fi", "wireless", "wifi", "wlan", "wi-fi", "wireless",
        "802.11", "ath", "wl", "ra", "rt", "mt", "bcmwl",
        "intel(r) dual", "intel(r) wi-fi", "killer", "mediatek mt",
    ]

    for kw in virtual_keywords:
        if kw in lower:
            return "virtual"

    for kw in wireless_keywords:
        if kw in lower:
            return "wireless"

    # 默认为有线
    return "wired"


def enumerate_nics_windows() -> list[dict]:
    """Windows 系统：使用 netsh 枚举网络接口。"""
    nics = []

    # 方法 1: netsh interface ip show config (获取 IP/网关)
    output = _run_cmd("netsh interface ip show config")
    if not output:
        LOG.log("warning", "netsh 命令无输出")
        return nics

    current_nic = {}
    for line in output.split("\n"):
        line = line.strip()

        # 检测新的接口配置段
        if line.startswith('配置接口 "') or line.startswith("配置接口 '"):
            # 保存之前的接口
            if current_nic:
                nics.append(current_nic)
            current_nic = {"name": "", "ip": "", "netmask": "", "gateway": "", "has_gateway": False, "if_type": "unknown"}
            # 提取接口名
            start = line.find('"') if '"' in line else line.find("'")
            end = line.rfind('"') if '"' in line else line.rfind("'")
            if start >= 0 and end > start:
                current_nic["name"] = line[start+1:end]

        elif "IP 地址" in line or "IP Address" in line or "IP 地址:" in line:
            # "IP 地址: 192.168.1.100"
            parts = line.split(":", 1)
            if len(parts) == 2:
                ip_part = parts[1].strip()
                current_nic["ip"] = ip_part.split("/")[0].strip()

        elif "子网掩码" in line or "Subnet Prefix" in line or "子网前缀长度" in line:
            # "子网前缀长度: 24" 或 "子网掩码: 255.255.255.0"
            parts = line.split(":", 1)
            if len(parts) == 2:
                val = parts[1].strip()
                if "." in val:
                    current_nic["netmask"] = val
                else:
                    # CIDR → netmask
                    try:
                        prefix = int(val)
                        mask_int = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
                        current_nic["netmask"] = f"{(mask_int>>24)&0xFF}.{(mask_int>>16)&0xFF}.{(mask_int>>8)&0xFF}.{mask_int&0xFF}"
                    except ValueError:
                        pass

        elif "默认网关" in line or "Default Gateway" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                gw = parts[1].strip().split()[0]  # 取第一个网关
                if gw and gw != "0.0.0.0":
                    current_nic["gateway"] = gw
                    current_nic["has_gateway"] = True

    if current_nic and current_nic.get("name"):
        nics.append(current_nic)

    # 方法 2: 用 getmac 或 ipconfig 补充接口名详情
    # 获取接口类型
    for nic in nics:
        if nic.get("name"):
            nic["if_type"] = _classify_interface(nic["name"])

    return nics


def get_all_nics() -> list[dict]:
    """获取所有网络接口列表。"""
    import platform
    system = platform.system()

    if system == "Windows":
        nics = enumerate_nics_windows()
    else:
        # Linux fallback (shouldn't happen but keep it)
        nics = []

    # 过滤掉无 IP 的接口
    nics = [n for n in nics if n.get("ip") and n["ip"] != "0.0.0.0"]

    # 按优先级排序：有线+网关 > 有线 > 无线+网关 > 无线 > 虚拟
    type_priority = {"wired": 0, "wireless": 1, "virtual": 2}

    nics.sort(key=lambda n: (
        type_priority.get(n.get("if_type", "virtual"), 2),
        0 if n.get("has_gateway") else 1,
    ))

    LOG.log("info", f"枚举到 {len(nics)} 个有效网络接口")
    for i, nic in enumerate(nics, 1):
        gw_status = f"网关: {nic.get('gateway', '无')}" if nic.get("has_gateway") else "无网关"
        LOG.log("info", f"  [{i}] {nic['name']} | {nic.get('ip', 'N/A')} | {nic.get('netmask', 'N/A')} | {gw_status} | {nic.get('if_type', 'unknown')}")

    return nics


def select_nic_interactive(nics: list[dict]) -> dict | None:
    """交互式选择网卡。

    返回: 选中的网卡字典，或 None（用户按 Q）
    """
    if not nics:
        LOG.log("error", "没有可用的网络接口")
        return None

    print("\n=== 选择网络接口 ===")
    for i, nic in enumerate(nics, 1):
        gw_status = f"网关: {nic.get('gateway', '无')}" if nic.get("has_gateway") else "无网关"
        type_label = {"wired": "有线", "wireless": "无线", "virtual": "虚拟"}.get(nic.get("if_type", "unknown"), "未知")
        print(f"  {i}. {nic['name']}")
        print(f"     IP: {nic.get('ip', 'N/A')} | 掩码: {nic.get('netmask', 'N/A')} | {gw_status} | 类型: {type_label}")

    print("\n  输入序号选择（默认 1），Q 退出")

    while True:
        choice = input("\n请选择 [1]: ").strip()

        if choice.upper() == "Q":
            LOG.log("info", "用户选择退出网卡选择")
            return None

        if not choice:
            choice = "1"

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(nics):
                selected = nics[idx]
                LOG.log("done", f"用户选择网卡: {selected['name']} ({selected['ip']})")
                return selected
            else:
                print(f"  错误: 序号超出范围，请输入 1-{len(nics)}")
        except ValueError:
            print("  错误: 请输入有效序号或 Q")
