"""
M12 Unified Integration v1.0 - 配置合并器

从 M1-M11 模块读取并合并配置，处理冲突（优先级覆盖策略）。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from src.main.constants import MODULE_ORDER

logger = logging.getLogger("m12.config_merger")


class ConfigMerger:
    """M1-M11 模块配置合并器。

    按 MODULE_ORDER 顺序从各模块读取配置，后加载的模块配置覆盖先加载的。
    """

    def __init__(self) -> None:
        self._merged_config: dict[str, Any] = {}
        self._module_configs: dict[str, dict[str, Any]] = {}

    def merge_all(self) -> dict[str, Any]:
        """从所有 M1-M11 模块读取并合并配置。

        Returns:
            合并后的统一配置字典
        """
        self._merged_config = {}
        self._module_configs = {}

        for module_name in MODULE_ORDER:
            try:
                module_config = self._read_module_config(module_name)
                if module_config:
                    self._module_configs[module_name] = module_config
                    self._merged_config.update(module_config)
                    logger.debug("模块 %s 配置已合并 (%d 项)", module_name, len(module_config))
            except Exception as e:
                logger.warning("模块 %s 配置读取失败: %s", module_name, e)

        logger.info("配置合并完成: %d/%d 模块, 共 %d 配置项",
                     len(self._module_configs), len(MODULE_ORDER), len(self._merged_config))
        return self._merged_config

    def get_module_config(self, module_name: str) -> dict[str, Any]:
        """获取指定模块的原始配置。

        Args:
            module_name: 模块名称（如 m1_ptz_astro）

        Returns:
            模块配置字典，未找到返回空字典
        """
        return self._module_configs.get(module_name, {})

    def get_merged(self) -> dict[str, Any]:
        """返回当前合并后的配置。"""
        return dict(self._merged_config)

    def get(self, key: str, default: Any = None) -> Any:
        """从合并配置中获取指定键。"""
        return self._merged_config.get(key, default)

    # ---- 内部辅助方法 ----

    @staticmethod
    def _read_module_config(module_name: str) -> dict[str, Any]:
        """从单个模块读取配置。

        尝试以下入口（按优先级）:
        1. {module_name}.config.get_config_dict()
        2. 模块级别的 CONFIG 常量
        3. 空字典（模块无配置）
        """
        # 尝试 config 模块
        try:
            mod = importlib.import_module(f"src.{module_name}.config")
            if hasattr(mod, "get_config_dict"):
                result = mod.get_config_dict()
                if isinstance(result, dict):
                    return result
        except (ImportError, ModuleNotFoundError):
            pass

        # 尝试 CONFIG 常量
        try:
            mod = importlib.import_module(f"src.{module_name}")
            if hasattr(mod, "CONFIG"):
                config = getattr(mod, "CONFIG")
                if isinstance(config, dict):
                    return dict(config)
        except (ImportError, ModuleNotFoundError):
            pass

        # 模块无配置
        return {}