"""
M2 Device Manager v1.0 - ISAPI HTTP 客户端

Hikvision ISAPI Digest Auth HTTP客户端，支持GET/PUT请求、XML解析、错误码处理。
参考 M1: src/ptz/isapi/client.py 的 ISAPIClient 模式。
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

try:
    import requests
    from requests.auth import HTTPDigestAuth
except ImportError:
    raise ImportError("需要安装 requests 库: pip install requests")

from device.core.logger import LOG


@dataclass
class ISAPIResponse:
    """ISAPI 响应封装。

    Attributes:
        status_code: HTTP状态码，0=超时/连接失败
        xml: XML响应体(200时有效)
        error_code: 设备错误码
        error_string: 设备错误描述
        sub_status_code: 子状态码
    """
    status_code: int
    xml: str = ""
    error_code: int = 0
    error_string: str = ""
    sub_status_code: str = ""
    response_time_ms: float = 0.0


class ISAPIClient:
    """ISAPI HTTP 客户端，使用 Digest Auth。

    Args:
        ip: 设备IP地址
        username: 登录用户名
        password: 登录密码
        port: HTTP端口，默认80
        timeout: 请求超时(秒)，默认5
    """

    def __init__(self, ip: str, username: str, password: str, port: int = 80, timeout: int = 5) -> None:
        self.ip = ip
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{ip}:{port}/ISAPI"
        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(username, password)
        self.session.headers.update({
            "Content-Type": "application/xml; charset=UTF-8",
        })
        self.authenticated = False

    def _log_response(self, method: str, endpoint: str, response, response_time_ms: float) -> None:
        """记录响应详情。"""
        if response.status_code == 200:
            LOG.info(f"ISAPI {method} {endpoint} → {response.status_code} ({response_time_ms:.0f}ms)")
        elif response.status_code == 401:
            LOG.error(f"ISAPI {method} {endpoint} → {response.status_code} (认证失败)")
        else:
            LOG.warning(f"ISAPI {method} {endpoint} → {response.status_code}")

    def _parse_error_response(self, response_text: str) -> tuple[int, str, str]:
        """从XML响应中解析错误码。

        Returns:
            (status_code, status_string, sub_status_code)
        """
        try:
            root = ET.fromstring(response_text)

            def find_text(tag: str) -> str:
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
        """发送GET请求。

        Args:
            endpoint: ISAPI端点路径，如 "/System/deviceInfo"

        Returns:
            ISAPIResponse 对象
        """
        url = f"{self.base_url}{endpoint}"
        LOG.info(f"ISAPI GET: {endpoint}")

        import time
        start = time.time()
        try:
            response = self.session.get(url, timeout=self.timeout)
            response_time_ms = (time.time() - start) * 1000
            self._log_response("GET", endpoint, response, response_time_ms)

            result = ISAPIResponse(status_code=response.status_code, response_time_ms=response_time_ms)

            if response.status_code == 200:
                result.xml = response.text
            else:
                result.error_code, result.error_string, result.sub_status_code = (
                    self._parse_error_response(response.text)
                )

            return result

        except requests.exceptions.Timeout:
            response_time_ms = (time.time() - start) * 1000
            LOG.error(f"ISAPI GET 超时: {endpoint}")
            return ISAPIResponse(status_code=0, error_string="Timeout", response_time_ms=response_time_ms)
        except requests.exceptions.ConnectionError as e:
            response_time_ms = (time.time() - start) * 1000
            LOG.error(f"ISAPI GET 连接失败: {endpoint} - {e}")
            return ISAPIResponse(status_code=0, error_string=str(e), response_time_ms=response_time_ms)
        except Exception as e:
            response_time_ms = (time.time() - start) * 1000
            LOG.error(f"ISAPI GET 异常: {endpoint} - {e}")
            return ISAPIResponse(status_code=0, error_string=str(e), response_time_ms=response_time_ms)

    def put(self, endpoint: str, xml_body: str) -> ISAPIResponse:
        """发送PUT请求。

        Args:
            endpoint: ISAPI端点路径
            xml_body: XML请求体

        Returns:
            ISAPIResponse 对象
        """
        url = f"{self.base_url}{endpoint}"
        LOG.info(f"ISAPI PUT: {endpoint}")

        import time
        start = time.time()
        try:
            response = self.session.put(
                url,
                data=xml_body.encode("utf-8"),
                headers={"Content-Type": "application/xml; charset=UTF-8"},
                timeout=self.timeout,
            )
            response_time_ms = (time.time() - start) * 1000
            self._log_response("PUT", endpoint, response, response_time_ms)

            result = ISAPIResponse(status_code=response.status_code, response_time_ms=response_time_ms)

            if response.status_code == 200:
                result.xml = response.text
            else:
                result.error_code, result.error_string, result.sub_status_code = (
                    self._parse_error_response(response.text)
                )

            return result

        except requests.exceptions.Timeout:
            response_time_ms = (time.time() - start) * 1000
            LOG.error(f"ISAPI PUT 超时: {endpoint}")
            return ISAPIResponse(status_code=0, error_string="Timeout", response_time_ms=response_time_ms)
        except requests.exceptions.ConnectionError as e:
            response_time_ms = (time.time() - start) * 1000
            LOG.error(f"ISAPI PUT 连接失败: {endpoint} - {e}")
            return ISAPIResponse(status_code=0, error_string=str(e), response_time_ms=response_time_ms)
        except Exception as e:
            response_time_ms = (time.time() - start) * 1000
            LOG.error(f"ISAPI PUT 异常: {endpoint} - {e}")
            return ISAPIResponse(status_code=0, error_string=str(e), response_time_ms=response_time_ms)

    def verify_credentials(self) -> bool:
        """验证账号密码是否正确。

        通过GET /ISAPI/System/deviceInfo测试认证。

        Returns:
            True=认证成功, False=认证失败
        """
        LOG.info(f"验证ISAPI凭证: {self.username}@{self.ip}")

        self.session.auth = HTTPDigestAuth(self.username, self.password)

        result = self.get("/System/deviceInfo")

        if result.status_code == 200:
            self.authenticated = True
            LOG.done("ISAPI认证成功")
            return True

        if result.status_code == 401:
            LOG.failed("ISAPI认证失败 (401 Unauthorized) - 请检查用户名/密码")
            return False

        if result.status_code == 0:
            LOG.failed(f"ISAPI连接失败: {result.error_string}")
            return False

        LOG.warning(f"ISAPI认证状态码: {result.status_code}")
        return False

    # ------------------------------------------------------------------ #
    #  XML 解析辅助方法
    # ------------------------------------------------------------------ #
    def get_xml_text(self, root: ET.Element, tag: str, default: str = "") -> str:
        """从XML元素中安全提取文本（忽略命名空间）。"""
        for child in root.iter():
            if child.tag.endswith(tag):
                return (child.text or default).strip()
        return default

    def get_xml_int(self, root: ET.Element, tag: str, default: int = 0) -> int:
        """从XML元素中安全提取整数。"""
        text = self.get_xml_text(root, tag, str(default))
        try:
            return int(text)
        except (ValueError, TypeError):
            return default

    def get_xml_float(self, root: ET.Element, tag: str, default: float = 0.0) -> float:
        """从XML元素中安全提取浮点数。"""
        text = self.get_xml_text(root, tag, str(default))
        try:
            return float(text)
        except (ValueError, TypeError):
            return default
