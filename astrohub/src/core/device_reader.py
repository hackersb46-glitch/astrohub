"""
AstroHub v8.83 - 统一设备参数读取层

通过后台单线程轮询，一次性读取所有参数到内存缓存，
所有API端点从缓存读取，大幅降低设备IO。

Author: 雅痞张@南方天文
"""

import threading
import time
from typing import Any, Optional
from datetime import datetime


class DeviceReader:
    """
    统一设备参数读取器
    
    功能：
    - 后台单线程轮询，批量读取所有参数
    - 内存缓存，API端点直接读取
    - 线程安全，支持并发访问
    """
    
    def __init__(self, ptz_controller):
        """
        初始化 DeviceReader
        
        Args:
            ptz_controller: PTZController 实例
        """
        self.ptz = ptz_controller
        self._cache = {}
        self._cache_lock = threading.RLock()
        self._last_update = 0
        self._running = False
        self._poll_thread = None
        self._poll_interval = 1.0  # 轮询间隔（秒）
        self._config_loaded = False  # 是否已加载本地设备配置
        self._counters = {
            "isapi_reads": 0,     # ISAPI 读取次数
            "isapi_writes": 0,    # ISAPI 写入次数
            "cache_hits": 0,      # 缓存命中次数
            "cache_misses": 0,    # 缓存未命中次数
        }
    
    def start(self, interval: float = 1.0):
        """
        启动后台轮询线程
        
        Args:
            interval: 轮询间隔（秒），默认1秒
        """
        if self._running:
            return
        
        self._poll_interval = interval
        self._running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="DeviceReader-Poll"
        )
        self._poll_thread.start()
    
    def stop(self):
        """停止后台轮询"""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=2.0)
            self._poll_thread = None
    
    def _poll_loop(self):
        """后台轮询循环"""
        while self._running:
            try:
                self._poll_all()
            except Exception as e:
                # 记录错误但不中断轮询
                from src.ptz.core.logger import LOG
                LOG.log("warning", f"DeviceReader 轮询失败: {e}")
            
            time.sleep(self._poll_interval)
    
    def _poll_all(self):
        """
        一次性读取所有参数，写入缓存
        
        读取内容：
        1. PTZ position (pan, tilt, zoom)
        2. Image settings (whitebalance, noisereduce, exposure, shutter, iris, gain, sharpness, color, filter, slow_shutter)
        3. OSD info
        4. 设备配置（启动时一次性读取）
        5. Device info (可选，低频)
        """
        if not self.ptz:
            return
        
        # 获取当前连接的设备控制器
        try:
            dev_info = self.ptz.get_connected_device()
            if not dev_info:
                return
            
            ip = dev_info.get('ip')
            if not ip:
                return
            
            ctrl, err = self.ptz._get_controller(ip)
            if err or not ctrl:
                return
            
            # 成功获取控制器，标记一次ISAPI读取
            self._counters["isapi_reads"] += 1
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"获取设备控制器失败: {e}")
            return
        
        # 1. PTZ Position
        try:
            pos = ctrl.get_position()
            if pos:
                self._set_cache("position", {
                    "pan": pos.get("pan", 0),
                    "tilt": pos.get("tilt", 0),
                    "zoom": pos.get("zoom", 0),
                })
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取 PTZ 位置失败: {e}")
        
        # 2. Image Settings
        image_data = {}
        try:
            # White Balance
            wb = ctrl.client.get("/Image/channels/1/whiteBalance")
            if wb.status_code == 200:
                image_data["whitebalance"] = self._parse_whitebalance(wb.xml)
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取白平衡失败: {e}")
        
        try:
            # Noise Reduction
            nr = ctrl.client.get("/Image/channels/1/noiseReduce")
            if nr.status_code == 200:
                image_data["noisereduce"] = self._parse_noisereduce(nr.xml)
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取降噪失败: {e}")
        
        try:
            # Exposure
            exp = ctrl.client.get("/Image/channels/1/exposure")
            if exp.status_code == 200:
                image_data["exposure"] = self._parse_exposure(exp.xml)
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取曝光失败: {e}")
        
        try:
            # Shutter
            shut = ctrl.client.get("/Image/channels/1/Shutter")
            if shut.status_code == 200:
                image_data["shutter"] = self._parse_shutter(shut.xml)
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取快门失败: {e}")
        
        try:
            # Iris
            iris = ctrl.client.get("/Image/channels/1/Iris")
            if iris.status_code == 200:
                image_data["iris"] = self._parse_iris(iris.xml)
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取光圈失败: {e}")
        
        try:
            # Gain
            gain = ctrl.client.get("/Image/channels/1/gain")
            if gain.status_code == 200:
                image_data["gain"] = self._parse_gain(gain.xml)
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取增益失败: {e}")
        
        try:
            # Sharpness
            sharp = ctrl.client.get("/Image/channels/1/sharpness")
            if sharp.status_code == 200:
                image_data["sharpness"] = self._parse_sharpness(sharp.xml)
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取锐化失败: {e}")
        
        try:
            # Color
            color = ctrl.client.get("/Image/channels/1/color")
            if color.status_code == 200:
                image_data["color"] = self._parse_color(color.xml)
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取颜色失败: {e}")
        
        try:
            # Filter / DayNight
            filt = ctrl.client.get("/Image/channels/1/IrcutFilter")
            if filt.status_code == 200:
                image_data["filter"] = self._parse_filter(filt.xml)
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取滤波失败: {e}")
        
        try:
            # Slow Shutter
            slow = ctrl.client.get("/Image/channels/1/DSS")
            if slow.status_code == 200:
                image_data["slow_shutter"] = self._parse_slow_shutter(slow.xml)
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取慢快门失败: {e}")
        
        if image_data:
            self._set_cache("image", image_data)
        
        # 3. OSD Info (可选)
        try:
            osd = ctrl.client.get("/ISAPI/System/Video/inputs/channels/1/osd")
            if osd.status_code == 200:
                self._set_cache("osd", self._parse_osd(osd.xml))
        except Exception as e:
            from src.ptz.core.logger import LOG
            LOG.log("warning", f"读取 OSD 失败: {e}")
        
        # 4. 设备配置（从本地 function.json 读取，启动时一次性加载）
        if not self._config_loaded:
            try:
                self._load_device_config(ctrl)
                self._config_loaded = True
            except Exception as e:
                from src.ptz.core.logger import LOG
                LOG.log("warning", f"读取设备配置失败: {e}")
        
        # 更新时间戳
        self._last_update = time.time()
    
    def _set_cache(self, key: str, value: Any):
        """设置缓存（线程安全）"""
        with self._cache_lock:
            self._cache[key] = value
            self._cache["_last_update"] = time.time()
    
    def _get_cache(self, key: str) -> Optional[Any]:
        """获取缓存（线程安全）"""
        with self._cache_lock:
            if key in self._cache:
                self._counters["cache_hits"] += 1
                return self._cache[key]
            self._counters["cache_misses"] += 1
            return None
    
    def get_position(self) -> Optional[dict]:
        """返回缓存的PTZ位置"""
        return self._get_cache("position")
    
    def get_image_settings(self) -> Optional[dict]:
        """返回缓存的图像设置（含 function.json 中的光圈/快门档位）"""
        return self._get_image_params()
    
    def get_osd_info(self) -> Optional[dict]:
        """返回缓存的OSD信息"""
        return self._get_cache("osd")
    
    def get_counters(self) -> dict:
        """返回计数器统计"""
        with self._cache_lock:
            return self._counters.copy()
    
    def get(self, key: str) -> Optional[Any]:
        """通用读取接口"""
        return self._get_cache(key)
    
    def get_all(self) -> dict:
        """返回所有缓存数据"""
        with self._cache_lock:
            return self._cache.copy()
    
    def get_last_update(self) -> float:
        """返回上次更新时间戳"""
        return self._last_update
    
    def is_fresh(self, max_age: float = 2.0) -> bool:
        """
        检查缓存是否新鲜
        
        Args:
            max_age: 最大允许年龄（秒）
        
        Returns:
            True 如果缓存年龄 < max_age
        """
        age = time.time() - self._last_update
        return age < max_age
    
    # ============ XML 解析方法 ============
    
    def _get_image_params(self) -> dict:
        """
        获取图像参数（包含从 function.json 读取的光圈/快门档位）
        
        如果设备配置已加载，将 iris_levels 和 shutter_levels 合并到图像数据中
        
        返回:
            dict: 图像参数字典
        """
        # 从缓存读取已有的图像设置
        image_data = self._get_cache("image") or {}
        
        # 从设备配置缓存读取光圈/快门档位
        device_config = self._get_cache("device_config") or {}
        
        # 合并光圈/快门档位到图像数据
        if "iris_levels" in device_config:
            image_data["iris_levels"] = device_config["iris_levels"]
        if "shutter_levels" in device_config:
            image_data["shutter_levels"] = device_config["shutter_levels"]
        
        return image_data
    
    def _load_device_config(self, ctrl):
        """
        从本地 function.json 读取设备配置（启动时一次性读取）
        
        Args:
            ctrl: PTZController 实例
        
        读取内容：
        1. iris_levels → 光圈档位列表
        2. shutter_levels → 快门档位列表
        
        路径: {devices_dir}/{mac_clean}/function.json
        """
        import json as _json
        from src.advanced.device_path import get_devices_dir, get_device_info
        from src.ptz.core.logger import LOG
        
        # 通过 ISAPI 获取设备 MAC（一次性操作）
        try:
            dev_info = get_device_info(ctrl)
            self._counters["isapi_reads"] += 1
        except Exception as e:
            LOG.log("warning", f"通过 ISAPI 获取设备信息失败: {e}")
            return
        
        mac_clean = dev_info.get("mac_clean", "")
        if not mac_clean:
            LOG.log("warning", "无法获取设备 MAC，跳过 function.json 读取")
            return
        
        # 构建 function.json 路径
        func_path = get_devices_dir() / mac_clean / "function.json"
        if not func_path.exists():
            LOG.log("info", f"function.json 不存在，跳过: {func_path}")
            return
        
        # 读取 JSON 文件
        try:
            with open(str(func_path), "r", encoding="utf-8") as f:
                data = _json.load(f)
        except Exception as e:
            LOG.log("warning", f"解析 function.json 失败: {e}")
            return
        
        config_data = {}
        
        # 读取光圈档位
        iris_levels = data.get("iris_levels")
        if iris_levels is not None:
            config_data["iris_levels"] = iris_levels
            LOG.log("info", f"从 function.json 读取 iris_levels，共 {len(iris_levels)} 档")
        else:
            LOG.log("info", "function.json 中未找到 iris_levels")
        
        # 读取快门档位
        shutter_levels = data.get("shutter_levels")
        if shutter_levels is not None:
            config_data["shutter_levels"] = shutter_levels
            LOG.log("info", f"从 function.json 读取 shutter_levels，共 {len(shutter_levels)} 档")
        else:
            LOG.log("info", "function.json 中未找到 shutter_levels")
        
        if config_data:
            self._set_cache("device_config", config_data)
            LOG.log("info", f"设备配置加载完成: {list(config_data.keys())}")
        else:
            LOG.log("info", "function.json 中无有效配置数据")
    
    # ============ v8.93: 修复所有XML解析（正确标签名+命名空间处理） ============
    
    @staticmethod
    def _get_xml_text(root, tag: str) -> str:
        """从XML元素中安全提取文本（忽略命名空间）。"""
        for elem in root.iter():
            t = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if t == tag:
                return (elem.text or "").strip()
        return ""
    
    def _parse_whitebalance(self, xml_str: str) -> dict:
        """解析白平衡XML: WhiteBalanceStyle, WhiteBalanceRed, WhiteBalanceBlue"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_str)
            mode = self._get_xml_text(root, "WhiteBalanceStyle")
            red = int(self._get_xml_text(root, "WhiteBalanceRed") or 100)
            blue = int(self._get_xml_text(root, "WhiteBalanceBlue") or 80)
            return {"mode": mode or "auto", "red_gain": red, "blue_gain": blue}
        except:
            return {"mode": "auto", "red_gain": 100, "blue_gain": 80}
    
    def _parse_noisereduce(self, xml_str: str) -> dict:
        """解析降噪XML: FrameNoiseReduceLevel(空域), InterFrameNoiseReduceLevel(时域)"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_str)
            spatial = int(self._get_xml_text(root, "FrameNoiseReduceLevel") or 50)
            temporal = int(self._get_xml_text(root, "InterFrameNoiseReduceLevel") or 50)
            return {"spatial_level": spatial, "temporal_level": temporal}
        except:
            return {"spatial_level": 50, "temporal_level": 50}
    
    def _parse_exposure(self, xml_str: str) -> dict:
        """解析曝光XML: ExposureType"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_str)
            mode = self._get_xml_text(root, "ExposureType")
            return {"mode": mode or "auto"}
        except:
            return {"mode": "auto"}
    
    def _parse_shutter(self, xml_str: str) -> dict:
        """解析快门XML: ShutterLevel"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_str)
            level = self._get_xml_text(root, "ShutterLevel")
            return {"current_level": level or "auto"}
        except:
            return {"current_level": "auto"}
    
    def _parse_iris(self, xml_str: str) -> dict:
        """解析光圈XML: IrisLevel"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_str)
            level = self._get_xml_text(root, "IrisLevel")
            return {"current_level": int(level) if level else 0}
        except:
            return {"current_level": 0}
    
    def _parse_gain(self, xml_str: str) -> dict:
        """解析增益XML: GainLevel"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_str)
            level = self._get_xml_text(root, "GainLevel")
            return {"current_level": int(level) if level else 0}
        except:
            return {"current_level": 0}
    
    def _parse_sharpness(self, xml_str: str) -> dict:
        """解析锐化XML: SharpnessLevel"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_str)
            level = self._get_xml_text(root, "SharpnessLevel")
            return {"current_level": int(level) if level else 50}
        except:
            return {"current_level": 50}
    
    def _parse_color(self, xml_str: str) -> dict:
        """解析颜色XML: brightnessLevel, contrastLevel, saturationLevel"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_str)
            brightness = self._get_xml_text(root, "brightnessLevel")
            contrast = self._get_xml_text(root, "contrastLevel")
            saturation = self._get_xml_text(root, "saturationLevel")
            return {
                "brightness": int(brightness) if brightness else 50,
                "contrast": int(contrast) if contrast else 50,
                "saturation": int(saturation) if saturation else 50,
            }
        except:
            return {"brightness": 50, "contrast": 50, "saturation": 50}
    
    def _parse_filter(self, xml_str: str) -> dict:
        """解析日夜模式XML: IrcutFilterType"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_str)
            mode = self._get_xml_text(root, "IrcutFilterType")
            return {"dayNightMode": mode or "auto"}
        except:
            return {"dayNightMode": "auto"}
    
    def _parse_slow_shutter(self, xml_str: str) -> dict:
        """解析慢快门XML: DSSLevel"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_str)
            level = self._get_xml_text(root, "DSSLevel") or "off"
            return {"enabled": level != "off", "dss_level": level}
        except:
            return {"enabled": False, "dss_level": "off"}
    
    def _parse_osd(self, xml_str: str) -> dict:
        """解析OSD XML"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_str)
            return {"osd": "parsed"}
        except:
            return {"osd": "unparsed"}


# 全局实例（在应用中共享）
_device_reader: Optional[DeviceReader] = None


def get_device_reader() -> Optional[DeviceReader]:
    """获取全局 DeviceReader 实例"""
    return _device_reader


def init_device_reader(ptz_controller) -> DeviceReader:
    """初始化全局 DeviceReader 实例"""
    global _device_reader
    _device_reader = DeviceReader(ptz_controller)
    return _device_reader
