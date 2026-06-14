"""
PTZ_ASTRO v1.1 - ISAPI HTTP 客户端
Hikvision ISAPI Digest Auth HTTP 客户端，支持 GET/PUT 请求、XML 解析、错误码处理。

Author: 雅痞张@南方天文
"""

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

try:
    import requests
    from requests.auth import HTTPDigestAuth
except ImportError:
    raise ImportError("需要安装 requests 库: pip install requests")

from ptz.core.logger import LOG


@dataclass
class ISAPIResponse:
    """ISAPI 响应封装。"""
    status_code: int
    xml: str = ""
    error_code: int = 0
    error_string: str = ""
    sub_status_code: str = ""


class ISAPIClient:
    """ISAPI HTTP 客户端，使用 Digest Auth。"""

    def __init__(self, ip: str, username: str, password: str, port: int = 80) -> None:
        self.ip = ip
        self.username = username
        self.password = password
        self.port = port
        self.base_url = f"http://{ip}:{port}/ISAPI"
        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(username, password)
        self.session.headers.update({
            "Content-Type": "application/xml; charset=UTF-8",
        })
        # BUG-014: 全局连接超时 5 秒，避免设备不可达时挂起
        self.session.timeout = 5
        self.authenticated = False

    def _log_response(self, method: str, url: str, response) -> None:
        """记录响应详情。"""
        if response.status_code == 200:
            LOG.log("done", f"ISAPI {method} {url} → {response.status_code}")
        elif response.status_code == 401:
            LOG.log("error", f"ISAPI {method} {url} → {response.status_code} (认证失败)")
        else:
            LOG.log("warning", f"ISAPI {method} {url} → {response.status_code}")

    def _parse_error_response(self, response_text: str) -> tuple[int, str, str]:
        """从 XML 响应中解析错误码。

        返回 (status_code, status_string, sub_status_code)
        """
        try:
            root = ET.fromstring(response_text)
            ns = {"hv": "http://www.hikvision.com/ver20/XMLSchema"}

            def find_text(tag: str) -> str:
                elem = root.find(tag)
                if elem is not None and elem.text:
                    return elem.text.strip()
                elem = root.find(f"hv:{tag}", ns)
                if elem is not None and elem.text:
                    return elem.text.strip()
                # Namespace-free search
                for child in root.iter():
                    if child.tag.endswith(tag):
                        return (child.text or "").strip()
                return ""

            code_str = find_text("statusCode")
            string_val = find_text("statusString")
            sub_code = find_text("subStatusCode")

            try:
                code = int(code_str)
            except (ValueError, TypeError):
                code = 0

            return code, string_val, sub_code
        except ET.ParseError:
            return 0, "", ""

    def get(self, endpoint: str) -> ISAPIResponse:
        """发送 GET 请求。

        参数:
            endpoint: ISAPI 端点路径，如 "/System/deviceInfo"

        返回:
            ISAPIResponse 对象
        """
        url = f"{self.base_url}{endpoint}"
        LOG.log("info", f"ISAPI GET: {endpoint}")

        try:
            response = self.session.get(url, timeout=5)
            self._log_response("GET", endpoint, response)

            result = ISAPIResponse(status_code=response.status_code)

            if response.status_code == 200:
                result.xml = response.text
            else:
                result.error_code, result.error_string, result.sub_status_code = (
                    self._parse_error_response(response.text)
                )

            return result

        except requests.exceptions.Timeout:
            LOG.log("error", f"ISAPI GET 超时: {endpoint}")
            return ISAPIResponse(status_code=0, error_string="Timeout")
        except requests.exceptions.ConnectionError as e:
            LOG.log("error", f"ISAPI GET 连接失败: {endpoint} - {e}")
            return ISAPIResponse(status_code=0, error_string=str(e))
        except Exception as e:
            LOG.log("error", f"ISAPI GET 异常: {endpoint} - {e}")
            return ISAPIResponse(status_code=0, error_string=str(e))

    def put(self, endpoint: str, xml_body: str) -> ISAPIResponse:
        """发送 PUT 请求。

        参数:
            endpoint: ISAPI 端点路径
            xml_body: XML 请求体（原始字符串，非 ElementTree）

        返回:
            ISAPIResponse 对象
        """
        url = f"{self.base_url}{endpoint}"
        LOG.log("info", f"ISAPI PUT: {endpoint}")

        try:
            response = self.session.put(
                url,
                data=xml_body.encode("utf-8"),
                headers={"Content-Type": "application/xml; charset=UTF-8"},
                timeout=5,
            )
            self._log_response("PUT", endpoint, response)

            result = ISAPIResponse(status_code=response.status_code)

            if response.status_code == 200:
                result.xml = response.text
            else:
                result.error_code, result.error_string, result.sub_status_code = (
                    self._parse_error_response(response.text)
                )

            return result

        except requests.exceptions.Timeout:
            LOG.log("error", f"ISAPI PUT 超时: {endpoint}")
            return ISAPIResponse(status_code=0, error_string="Timeout")
        except requests.exceptions.ConnectionError as e:
            LOG.log("error", f"ISAPI PUT 连接失败: {endpoint} - {e}")
            return ISAPIResponse(status_code=0, error_string=str(e))
        except Exception as e:
            LOG.log("error", f"ISAPI PUT 异常: {endpoint} - {e}")
            return ISAPIResponse(status_code=0, error_string=str(e))

    def verify_credentials(self) -> bool:
        """验证账号密码是否正确。

        通过多端点 GET 验证账号密码是否正确 (P3.2)。

        返回:
            True = 认证成功，False = 认证失败
        """
        LOG.log("info", f"验证 ISAPI 凭证: {self.username}@{self.ip}")

        # 清除代理环境变量
        for key in list(os.environ.keys()):
            if "proxy" in key.lower():
                del os.environ[key]

        # 使用独立 Session 用于认证验证
        auth_session = requests.Session()
        auth_session.trust_env = False
        auth_session.auth = HTTPDigestAuth(self.username, self.password)
        auth_session.headers.update({
            "Content-Type": "application/xml; charset=UTF-8",
        })

        # 多端点尝试列表（按顺序）
        endpoints = [
            "/System/deviceInfo",         # 标准路径
            "/System/DeviceInfo",         # PascalCase 变体
            "/System/status/deviceInfo",   # 带 status 前缀（PTZ 球机）
            "/System/capabilities",        # 设备能力端点
            "/DeviceManagement/DeviceInfo", # ISAPI v2.0
            "/System/network/interfaces",   # 网络设备信息端点
        ]

        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            try:
                response = auth_session.get(url, timeout=5)

                if response.status_code == 200:
                    self.authenticated = True
                    LOG.log("done", f"ISAPI 认证成功 (端点: {endpoint})")
                    auth_session.close()
                    return True

                elif response.status_code == 401:
                    LOG.log("failed", "ISAPI 认证失败 (HTTP 401) - 密码错误，端点存在但认证不通过")
                    auth_session.close()
                    return False

                # 404 或其他状态码继续尝试下一个端点
                LOG.log("info", f"端点 {endpoint} 返回 {response.status_code}, 继续尝试...")

            except requests.exceptions.Timeout:
                LOG.log("info", f"端点 {endpoint} 超时, 继续尝试下一个...")
                continue
            except requests.exceptions.ConnectionError as e:
                LOG.log("info", f"端点 {endpoint} 连接失败 ({e}), 继续尝试下一个...")
                continue
            except Exception as e:
                LOG.log("info", f"端点 {endpoint} 异常 ({e}), 继续尝试下一个...")
                continue

        LOG.log("failed", "ISAPI 凭证验证失败: 所有端点均失败")
        auth_session.close()
        return False

    def get_xml_text(self, root: ET.Element, tag: str, default: str = "") -> str:
        """从 XML 元素中安全提取文本（忽略命名空间）。"""
        for child in root.iter():
            if child.tag.endswith(tag):
                return (child.text or default).strip()
        return default

    def get_xml_int(self, root: ET.Element, tag: str, default: int = 0) -> int:
        """从 XML 元素中安全提取整数。"""
        text = self.get_xml_text(root, tag, str(default))
        try:
            return int(text)
        except (ValueError, TypeError):
            return default

    def get_xml_float(self, root: ET.Element, tag: str, default: float = 0.0) -> float:
        """从 XML 元素中安全提取浮点数。"""
        text = self.get_xml_text(root, tag, str(default))
        try:
            return float(text)
        except (ValueError, TypeError):
            return default
