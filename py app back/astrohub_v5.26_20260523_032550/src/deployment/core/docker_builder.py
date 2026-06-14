"""
M11 Deployment v1.0 - Docker 构建配置

Dockerfile 多阶段构建、镜像构建、体积校验、docker-compose 管理。

P0.1: Docker 镜像构建 (多阶段构建减少体积, 大小 <1GB)
P0.2: docker-compose 配置管理

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from deployment.constants import (
    DOCKER_BUILD_TIMEOUT,
    DOCKER_MAX_IMAGE_SIZE_MB,
    ErrorCode,
)


class DockerBuildError(Exception):
    """Docker 构建异常。"""

    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code.value}] {message}")


class DockerBuilder:
    """Docker 构建器。支持多阶段构建、镜像标签管理、体积校验。"""

    def __init__(
        self,
        dockerfile: Path | None = None,
        context: Path | None = None,
    ):
        self._dockerfile = dockerfile or Path("Dockerfile")
        self._context = context or Path(".")
        self._build_history: list[dict[str, Any]] = []

    def build(
        self,
        image_name: str,
        tag: str = "latest",
        target: str | None = None,
    ) -> str:
        """构建 Docker 镜像。

        Args:
            image_name: 镜像名称
            tag: 镜像标签
            target: 多阶段构建的目标阶段
        Returns:
            完整镜像名 (name:tag)
        """
        full_name = f"{image_name}:{tag}"
        cmd = [
            "docker", "build",
            "-f", str(self._dockerfile),
            "-t", full_name,
        ]

        if target:
            cmd.extend(["--target", target])

        cmd.append(str(self._context))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=DOCKER_BUILD_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise DockerBuildError(
                ErrorCode.DOCKER_BUILD_FAILED,
                f"构建超时 ({DOCKER_BUILD_TIMEOUT}s)"
            )

        if result.returncode != 0:
            raise DockerBuildError(
                ErrorCode.DOCKER_BUILD_FAILED,
                f"docker build 失败: {result.stderr.strip()}"
            )

        self._build_history.append({
            "image": full_name,
            "target": target,
            "status": "success",
        })

        return full_name

    def inspect_size(self, image_name_tags: str) -> int:
        """获取镜像大小 (MB)。

        Args:
            image_name_tags: 镜像名:标签
        Returns:
            大小 (MB), 失败返回 -1
        """
        cmd = [
            "docker", "image", "inspect",
            image_name_tags,
            "--format={{.Size}}",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return -1

        size_bytes = int(result.stdout.strip())
        return size_bytes // (1024 * 1024)

    def validate_size(self, image_name_tags: str) -> tuple[bool, int]:
        """校验镜像大小是否超出限制。

        Returns:
            (合法, 大小MB)
        """
        size_mb = self.inspect_size(image_name_tags)
        return size_mb <= DOCKER_MAX_IMAGE_SIZE_MB, size_mb

    def history(self) -> list[dict[str, Any]]:
        """获取构建历史。"""
        return self._build_history.copy()

    def compose_up(self, compose_file: Path) -> str:
        """执行 docker-compose up。

        Args:
            compose_file: compose 文件路径
        Returns:
            启动输出
        """
        cmd = ["docker", "compose", "-f", str(compose_file), "up", "-d"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise DockerBuildError(
                ErrorCode.DOCKER_BUILD_FAILED,
                f"docker-compose up 失败: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def compose_down(self, compose_file: Path) -> str:
        """执行 docker-compose down。"""
        cmd = ["docker", "compose", "-f", str(compose_file), "down"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout.strip()


# ------------------------------------------------------------------ #
#  单例访问
# ------------------------------------------------------------------ #

_default_builder: DockerBuilder | None = None


def get_builder() -> DockerBuilder:
    """获取默认 DockerBuilder 实例。"""
    global _default_builder
    if _default_builder is None:
        _default_builder = DockerBuilder()
    return _default_builder
