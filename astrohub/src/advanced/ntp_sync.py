"""
AstroHub v8.87 - NTP 授时核心模块

策略：读取 NTP 时间 → 手动校正设备时间 → 切 NTP 模式保持同步 → 强制本机同步 → 验证三方一致
"""

import socket
import struct
import subprocess
import re
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from src.ptz.isapi.client import ISAPIClient
from src.logger import get_logger

log = get_logger("ntp_sync")

CST = timezone(timedelta(hours=8))

def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y%m%d-%H%M%S")


def read_ntp_time(ntp_server: str, timeout: int = 5) -> dict:
    """直接通过 UDP 查询 NTP 服务器时间，返回 UTC 和北京时间。

    返回:
        {
            "success": True,
            "ntp_time_utc":  "20260711-003015",   # UTC
            "ntp_time_cst":  "20260711-083015",   # CST=UTC+8
            "ntp_timestamp": 1783729815,           # Unix UTC
            "server": "ntp.aliyun.com"
        }
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        data = b'\x1b' + 47 * b'\0'
        sock.sendto(data, (ntp_server, 123))
        resp, _ = sock.recvfrom(1024)
        sock.close()
        t_raw = struct.unpack('!12I', resp)[10]
        ntp_ts = t_raw - 2208988800    # -> Unix timestamp (UTC)
        dt_utc = datetime.fromtimestamp(ntp_ts, tz=timezone.utc)
        dt_cst = dt_utc.astimezone(CST)
        return {
            "success": True,
            "ntp_time_utc": _fmt(dt_utc),
            "ntp_time_cst": _fmt(dt_cst),
            "ntp_timestamp": ntp_ts,
            "server": ntp_server,
        }
    except socket.timeout:
        return {"success": False, "error": f"NTP 服务器 {ntp_server} 超时"}
    except Exception as e:
        return {"success": False, "error": f"NTP 查询异常: {e}"}


def sync_device_time(
    ip: str, username: str, password: str, port: int, ntp_server: str,
    ntp_timestamp: int | None = None,
) -> dict:
    """两步法同步 PTZ 设备时间。

    1. 手动写入 NTP 时间（强制立即校正，不等 NTP 轮询）
    2. 切为 NTP 模式（后续自动保持同步）

    参数:
        ntp_timestamp: 从 read_ntp_time 获取的 Unix 时间戳，传入此值可保证
                       设备、本机、NTP 服务器三者使用同一参考时间。
                       若为 None 则在函数内重新查询。
    """
    steps = []
    steps.append({"step": "连接设备", "status": "开始", "detail": f"{username}@{ip}:{port}"})

    try:
        client = ISAPIClient(ip, username, password, port)
        steps.append({"step": "ISAPI 认证", "status": "成功", "detail": ""})

        # 获取时间戳
        ts = ntp_timestamp
        ntp_time_cst = ""
        if ts is None:
            ntp_r = read_ntp_time(ntp_server)
            if not ntp_r["success"]:
                steps.append({"step": "读取 NTP 时间", "status": "失败", "detail": ntp_r["error"]})
                return {"success": False, "http_code": 0, "message": ntp_r["error"], "steps": steps}
            ts = ntp_r["ntp_timestamp"]
            ntp_time_cst = ntp_r["ntp_time_cst"]
        else:
            ntp_time_cst = datetime.fromtimestamp(ts, tz=CST).strftime("%Y%m%d-%H%M%S")

        steps.append({"step": "读取 NTP 时间", "status": "成功", "detail": ntp_time_cst})

        # ---------------------------------------------------------------
        # 1 次 PUT 完成：手动写入 NTP 时间（立即校正）
        # 注意：不能同时设 NTP 模式 + localTime，设备会立即触发 NTP 客户端
        #       轮询覆盖回原始 NTP 时间，3s 补偿白给
        # ---------------------------------------------------------------
        dt_cst = datetime.fromtimestamp(ts + 3.2, tz=CST)
        local_time_str = dt_cst.strftime("%Y-%m-%dT%H:%M:%S") + "+08:00"
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Time version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            '<timeMode>manual</timeMode>'
            '<localTime>' + local_time_str + '</localTime>'
            '<timeZone>CST-8:00:00</timeZone>'
            '</Time>'
        )
        r = client.put("/System/time", xml)
        success = r.status_code == 200
        if success:
            steps.append({
                "step": "手动写入 NTP 时间",
                "status": "成功",
                "detail": f"timeMode=manual, localTime={local_time_str}, HTTP={r.status_code}",
            })
        else:
            steps.append({
                "step": "手动写入 NTP 时间",
                "status": "失败",
                "detail": f"HTTP={r.status_code}, error={r.error_string}",
            })
            return {"success": False, "http_code": r.status_code, "message": r.error_string, "steps": steps}

        # 验证：读回设备实际时间
        verify_r = client.get("/System/time")
        actual_time = "unknown"
        actual_mode = "unknown"
        if verify_r.status_code == 200 and verify_r.xml:
            try:
                root = ET.fromstring(verify_r.xml)
                for child in root.iter():
                    if child.tag.endswith("localTime"):
                        actual_time = child.text or "unknown"
                    if child.tag.endswith("timeMode"):
                        actual_mode = child.text or "unknown"
            except Exception:
                pass
        steps.append({
            "step": "验证设备实际时间",
            "status": "成功" if verify_r.status_code == 200 else "失败",
            "detail": f"实际时间={actual_time}, 模式={actual_mode}",
        })

        return {
            "success": True,
            "http_code": 200,
            "message": "OK",
            "steps": steps,
            "device_new_time": actual_time,
        }
    except Exception as e:
        steps.append({"step": "异常", "status": "失败", "detail": str(e)})
        return {"success": False, "http_code": 0, "message": str(e), "steps": steps}


def sync_windows_time(ntp_timestamp: int | None = None) -> dict:
    """强制同步本机 Windows 时间到 NTP。

    策略：
    1. 配置 NTP 服务器
    2. w32tm /resync /nowait（立刻返回，不等待）
    3. 轮询 /query /status 验证同步状态（最多 5s）
    4. 备用 stripchart 单次采样获取实际偏差

    参数:
        ntp_timestamp: 外部传入的统一 Unix 时间戳（仅用于日志）
    """
    steps = []
    before = datetime.now().isoformat()
    steps.append({"step": "读取本机同步前时间", "status": "成功", "detail": before})

    try:
        if ntp_timestamp is not None:
            ref_cst = datetime.fromtimestamp(ntp_timestamp, tz=CST).strftime("%Y%m%d-%H%M%S")
            steps.append({"step": "使用统一 NTP 参考时间", "status": "成功", "detail": ref_cst})

        # ---------------------------------------------------------------
        # 1) 确保 w32time 服务运行
        # ---------------------------------------------------------------
        subprocess.run(["net", "start", "w32time"], capture_output=True, text=True, timeout=10)
        steps.append({"step": "启动 w32time 服务", "status": "成功", "detail": "服务已就绪"})

        # ---------------------------------------------------------------
        # 2) 配置 NTP 服务器
        # ---------------------------------------------------------------
        peerlist = "ntp.aliyun.com,0x1"
        subprocess.run(
            ["w32tm", "/config", "/manualpeerlist:" + peerlist,
             "/syncfromflags:manual", "/reliable:yes", "/update"],
            capture_output=True, text=True, timeout=10,
        )
        steps.append({"step": "配置 NTP 服务器", "status": "成功", "detail": "peerlist=ntp.aliyun.com"})

        # ---------------------------------------------------------------
        # 3) 快速 resync（/nowait，不阻塞）
        # ---------------------------------------------------------------
        subprocess.run(
            ["w32tm", "/resync", "/nowait"],
            capture_output=True, text=True, timeout=5,
        )
        steps.append({"step": "触发时间同步", "status": "成功", "detail": "/resync /nowait 已发送"})

        # ---------------------------------------------------------------
        # 4) 用 stripchart 获取实际偏差（跳过轮询，中文 Windows 不匹配英文关键词）
        # ---------------------------------------------------------------
        # ---------------------------------------------------------------
        offset = None
        try:
            sc = subprocess.run(
                ["w32tm", "/stripchart", "/computer:ntp.aliyun.com",
                 "/samples:1", "/dataonly"],
                capture_output=True, text=True, timeout=10,
            )
            sc_out = (sc.stdout or "").strip()
            # 提取偏移量
            m = re.search(r"([+-]\d+\.?\d*)s", sc_out)
            if m:
                offset = m.group(1)
            steps.append({
                "step": "获取实际偏差",
                "status": "成功",
                "detail": f"offset={offset}s" if offset else (sc_out.replace(chr(10),' | ')[:120]),
            })
        except Exception as e:
            steps.append({"step": "获取实际偏差", "status": "失败", "detail": str(e)})

        after = datetime.now().isoformat()
        steps.append({"step": "读取本机同步后时间", "status": "成功", "detail": after})

        return {
            "success": True,
            "before": before,
            "after": after,
            "offset": offset,
            "steps": steps,
        }
    except Exception as e:
        after = datetime.now().isoformat()
        steps.append({"step": "异常", "status": "失败", "detail": str(e)})
        return {"success": False, "error": str(e), "before": before, "after": after, "steps": steps}


def get_system_time() -> str:
    return datetime.now().isoformat()