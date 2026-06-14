# AstroHub 待清理清单（技术债务）

## 1. PTZ 模块代码重复

### 问题描述
`src/core/ptz_manager.py` (122KB) 内嵌定义了多个类，与 `src/ptz/` 目录下的独立文件功能重复。

### 重复定义

| 类名 | ptz_manager.py 内嵌 | src/ptz/ 独立文件 | 被导入位置 |
|------|---------------------|-------------------|------------|
| Logger | ✓ | core/logger.py | limit.py, isapi/*.py, ptz/*.py, report/*.py, sadp/*.py |
| ConfigManager | ✓ | core/config.py | ptz/limits.py |
| ISAPIClient | ✓ | isapi/client.py | router.py, advanced/*.py, ptz/limits.py |
| PTZController | ✓ | isapi/ptz.py | router.py, advanced/*.py, ptz/*.py |
| CSVRecorder | ✓ | core/recorder.py | 未检查 |
| MotionTester | ✓ | ptz/motion.py | 未检查 |

### 导入冲突

```python
# router.py 同时导入两处：
from src.core.ptz_manager import PTZManager        # 管理器
from src.ptz.isapi.client import ISAPIClient       # 独立文件
from src.ptz.isapi.ptz import PTZController        # 独立文件
```

### 清理方案（待执行）

**方案 B（推荐）：保留 src/ptz/，清理 ptz_manager.py 内嵌类**

1. 分析 ptz_manager.py 中 PTZManager 类的实际依赖
2. 将内嵌的类改为导入 src/ptz/ 下的独立实现
3. 测试确保功能正常
4. 删除 ptz_manager.py 中的重复类定义

**风险等级**：中
**工作量**：需要仔细重构，确保不破坏 PTZManager 功能

---

## 2. Stream 模块潜在冗余

### 检查项
- [ ] stream/core/logger.py 与 src/logger.py 是否重复
- [ ] stream/core/stream_manager.py 与 src/core/stream_manager.py 是否重复

---

## 3. 待检查模块

| 模块 | 检查项 | 状态 |
|------|--------|------|
| src/stream | Logger 重复检查 | 待检查 |
| src/websocket | 常量/管理器重复检查 | 待检查 |
| src/ascom | 常量重复检查 | 待检查 |

---

## 4. 已清理项目

| 项目 | 文件数 | 清理日期 |
|------|--------|----------|
| 备份目录 (backup_20260529) | 3 | 2026-06-15 |
| scripts 目录 | 3 | 2026-06-15 |
| 重复 WASM SDK (jsPlugin/) | 15 | 2026-06-15 |
| __pycache__ 目录 | 17 | 2026-06-15 |
| 空目录 | 9 | 2026-06-15 |
| 备份文件 (*.bak, *backup*) | 11 | 2026-06-15 |
| 模块内日志 (src/*/log/) | 48 | 2026-06-15 |
| 无用模块 (calibration, database) | 28 | 2026-06-15 |

---

## 5. WSManager 双重定义

### 问题描述
存在两个 WSManager 文件，大小不同：
- `src/core/ws_manager.py` (4200 bytes)
- `src/websocket/core/ws_manager.py` (11150 bytes)

### 导入情况

```python
# router.py 同时导入两处：
from src.core.ws_manager import WebSocketManager  # 用于类型声明
from src.websocket.core.ws_manager import get_ws_manager  # 实际调用

# websocket 模块只用大版本：
handlers.py, server.py, api/router.py → src.websocket.core.ws_manager
```

### 分析结果

两个文件功能不同：
- `src/core/ws_manager.py` (4200 bytes) - `WebSocketManager` 类
- `src/websocket/core/ws_manager.py` (11150 bytes) - `WSManager` 类 + `get_ws_manager()` 函数

**router.py 使用了 WebSocketManager 作为类型声明，不能删除！**

### 清理方案

暂不清理，两者都在使用中。建议未来统一命名和实现。

**风险等级**：暂不处理

---

## 6. 常量重复定义

### 问题描述
`ErrorCode` 和 `ConnectionStatus` 在多处定义：
- `src/ascom/constants.py`
- `src/websocket/constants.py`

### 清理方案（待执行）
1. 创建 `src/constants.py` 统一常量
2. 更新所有导入位置

**风险等级**：低

---

**更新时间**: 2026-06-15 02:53
