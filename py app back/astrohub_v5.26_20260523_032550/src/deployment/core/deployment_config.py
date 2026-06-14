"""
M11 Deployment v1.0 - 部署配置管理

环境配置加载、敏感配置加密、配置校验、多环境切换。

P1: 环境配置 (P1.1-P1.4)
P1.1: 环境文件管理
P1.2: 环境变量注入
P1.3: 配置校验
P1.4: 敏感配置加密

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from deployment.constants import (
    CONFIG_DIR,
    ENV_DEVELOPMENT,
    ENV_FILE_DEVELOPMENT,
    ENV_FILE_PRODUCTION,
    ENV_FILE_TEST,
    ENV_PRODUCTION,
    ENV_TEST,
    ERROR_CODE_DESCRIPTION,
    ErrorCode,
    REQUIRED_CONFIG_KEYS,
    VALID_ENVIRONMENTS,
)


# ------------------------------------------------------------------ #
#  简单加密 (P1.4 - Base64 混淆, 生产环境应使用 Fernet)
# ------------------------------------------------------------------ #

def _encode(value: str) -> str:
    """Base64 编码敏感值。生产环境替换为 Fernet 加密。"""
    import base64
    return base64.b64encode(value.encode()).decode()


def _decode(value: str) -> str:
    """Base64 解码。"""
    import base64
    return base64.b64decode(value.encode()).decode()


class ConfigValidationError(Exception):
    """配置校验异常。"""

    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code.value}] {message}")


# ------------------------------------------------------------------ #
#  环境配置文件加载 (P1.1, P1.2)
# ------------------------------------------------------------------ #

class EnvironmentConfig:
    """环境配置加载器。

    管理 .env.{environment} 文件的加载与合并。
    优先级: 系统环境变量 > 环境文件 > 默认值。
    """

    ENV_FILE_MAP = {
        ENV_DEVELOPMENT: ENV_FILE_DEVELOPMENT,
        ENV_TEST: ENV_FILE_TEST,
        ENV_PRODUCTION: ENV_FILE_PRODUCTION,
    }

    def __init__(self, env_name: str | None = None, config_dir: Path | None = None):
        """Initialize."""
        self._env = env_name or os.environ.get("DEPLOY_ENV", ENV_DEVELOPMENT)
        self._config_dir = config_dir or CONFIG_DIR
        self._loaded: dict[str, str] = {}

    @property
    def environment(self) -> str:
        """当前环境名。"""
        return self._env

    def load(self) -> dict[str, str]:
        """加载环境变量。

        Returns:
            环境变量字典 {KEY: VALUE}
        """
        if self._env not in VALID_ENVIRONMENTS:
            raise ConfigValidationError(
                ErrorCode.CONFIG_NOT_FOUND,
                f"未知环境: {self._env}, 有效环境: {VALID_ENVIRONMENTS}"
            )

        env_file = self._config_dir / self.ENV_FILE_MAP[self._env]
        if env_file.exists():
            self._loaded = self._parse_env_file(env_file)

        # 系统环境变量优先级更高
        for key in self._loaded:
            if key in os.environ:
                self._loaded[key] = os.environ[key]

        return self._loaded

    def get(self, key: str, default: str | None = None) -> str | None:
        """获取环境变量值。"""
        if not self._loaded:
            self.load()
        return self._loaded.get(key, os.environ.get(key, default))

    def _parse_env_file(self, path: Path) -> dict[str, str]:
        """解析 .env 文件。

        格式: KEY=VALUE, 支持 # 注释。
        """
        result = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip()
        return result


# ------------------------------------------------------------------ #
#  敏感配置加密 (P1.4)
# ------------------------------------------------------------------ #

class SecretManager:
    """敏感信息管理。

    支持加密存储和解密读取 (密码、密钥、Token 等)。
    P1.4: 加密配置可正确解密; 解密失败时启动失败。
    """

    def __init__(self, config_dir: Path | None = None):
        """Initialize."""
        self._secrets_file = (config_dir or CONFIG_DIR) / "secrets.json"

    def store(self, key: str, value: str) -> None:
        """加密存储敏感信息。"""
        secrets = self._load_secrets()
        secrets[key] = _encode(value)
        self._save_secrets(secrets)

    def get(self, key: str) -> str:
        """解密获取敏感信息。

        Raises:
            ConfigValidationError: 解密失败或 key 不存在。
        """
        secrets = self._load_secrets()
        if key not in secrets:
            raise ConfigValidationError(
                ErrorCode.CONFIG_NOT_FOUND,
                f"敏感配置不存在: {key}"
            )
        try:
            return _decode(secrets[key])
        except Exception as e:
            raise ConfigValidationError(
                ErrorCode.CONFIG_VALIDATION_FAILED,
                f"敏感配置解密失败: {key}, 错误: {e}"
            )

    def _load_secrets(self) -> dict[str, str]:
        """加载 secrets 文件。"""
        if not self._secrets_file.exists():
            return {}
        with open(self._secrets_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_secrets(self, secrets: dict[str, str]) -> None:
        """保存 secrets 文件。"""
        (self._secrets_file.parent).mkdir(parents=True, exist_ok=True)
        with open(self._secrets_file, "w", encoding="utf-8") as f:
            json.dump(secrets, f, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------ #
#  配置校验 (P1.3)
# ------------------------------------------------------------------ #

class ConfigValidator:
    """配置完整性校验。

    P1.3: 启动时检查所有必需配置是否存在。
    缺失配置时启动失败并输出明确错误。
    """

    def __init__(self, required_keys: list[str] | None = None):
        """Initialize."""
        self._required_keys = required_keys or REQUIRED_CONFIG_KEYS

    def validate(self, config: dict[str, Any]) -> tuple[bool, list[str]]:
        """校验配置完整性。

        Args:
            config: 配置字典
        Returns:
            (是否通过, 缺失键列表)
        """
        missing = [k for k in self._required_keys if k not in config or not config[k]]
        return len(missing) == 0, missing

    def validate_or_raise(self, config: dict[str, Any]) -> None:
        """校验配置，失败抛出异常。

        Raises:
            ConfigValidationError: 配置缺失。
        """
        ok, missing = self.validate(config)
        if not ok:
            raise ConfigValidationError(
                ErrorCode.CONFIG_VALIDATION_FAILED,
                f"缺失必需配置: {', '.join(missing)}"
            )
