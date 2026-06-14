"""
Database Service v1.0 - 操作日志

操作日志记录、查询、过期清理。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.database.core.db_manager import OperationLog


class OperationLogRepo:
    """操作日志仓库：日志记录/查询/清理。"""

    def __init__(self, session: AsyncSession) -> None:
        """初始化操作日志仓库。

        Args:
            session: SQLAlchemy 异步会话
        """
        self._session = session

    async def log_operation(
        self,
        operation: str,
        status: str,
        target_type: str | None = None,
        target_id: str | None = None,
        details: str | None = None,
        operator: str | None = None,
    ) -> OperationLog:
        """记录操作日志。

        Args:
            operation: 操作名称(如 "create_device")
            status: 操作状态("success"/"failed"/"partial")
            target_type: 目标类型(如 "device", "group")
            target_id: 目标标识(如 MAC 或 ID)
            details: 详细信息
            operator: 操作人

        Returns:
            创建的 OperationLog 实例
        """
        log_entry = OperationLog(
            operation=operation,
            status=status,
            target_type=target_type,
            target_id=target_id,
            details=details,
            operator=operator,
        )
        self._session.add(log_entry)
        await self._session.flush()
        return log_entry

    async def query_logs(
        self,
        operation: str | None = None,
        target_type: str | None = None,
        status: str | None = None,
        operator: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[Sequence[OperationLog], int]:
        """分页查询操作日志。

        Args:
            operation: 按操作名称筛选
            target_type: 按目标类型筛选
            status: 按状态筛选
            operator: 按操作人筛选
            start_time: 起始时间
            end_time: 结束时间
            page: 页码(从1开始)
            page_size: 每页条数

        Returns:
            (日志列表, 总数)
        """
        filters: list = []
        if operation:
            filters.append(OperationLog.operation == operation)
        if target_type:
            filters.append(OperationLog.target_type == target_type)
        if status:
            filters.append(OperationLog.status == status)
        if operator:
            filters.append(OperationLog.operator == operator)
        if start_time:
            filters.append(OperationLog.created_at >= start_time)
        if end_time:
            filters.append(OperationLog.created_at <= end_time)

        # 计数
        count_stmt = select(func.count(OperationLog.id))
        if filters:
            count_stmt = count_stmt.where(*filters)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        # 分页
        size = min(max(page_size, 1), MAX_PAGE_SIZE)
        offset = (max(page, 1) - 1) * size
        stmt = select(OperationLog)
        if filters:
            stmt = stmt.where(*filters)
        stmt = stmt.order_by(OperationLog.created_at.desc()).offset(offset).limit(size)
        result = await self._session.execute(stmt)
        logs = result.scalars().all()
        return logs, total

    async def get_log_by_id(self, log_id: int) -> OperationLog | None:
        """按 ID 获取单条日志。

        Args:
            log_id: 日志 ID

        Returns:
            OperationLog 实例或 None
        """
        return await self._session.get(OperationLog, log_id)

    async def cleanup_old_logs(self, retention_days: int = 30) -> int:
        """清理过期日志。

        Args:
            retention_days: 保留天数

        Returns:
            删除的记录数
        """
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        stmt = delete(OperationLog).where(OperationLog.created_at < cutoff)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[return-value]
