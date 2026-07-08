# AstroHub 待修复任务

**创建时间**: 2026-06-16 08:38
**更新时间**: 2026-06-16 08:51

---

## 时间逻辑问题修复

### 🔴 高优先级

#### 问题1: PTZManager 录像状态依赖内存
- **文件**: `src/core/ptz_manager.py:~L690` (`_recording_state`)
- **问题**: FFmpeg 进程 PID、文件路径存内存，刷新后变孤儿进程
- **建议**: 启动录制时写入 `data/devices/{mac}/recording.json`

#### 问题9: StreamManager 流状态依赖内存
- **文件**: `src/core/stream_manager.py:~L47` (`_streams`)
- **问题**: FFmpeg PID、RTSP URL 存内存，刷新后变孤儿进程
- **建议**: 启动流时写入 `data/streams/{device_id}.json`

### 🟡 中优先级

#### 问题3: FTP 配置仅存内存
- **文件**: `src/core/ptz_manager.py:~L694` (`_ftp_config`)
- **问题**: 刷新后 FTP 配置丢失
- **建议**: 持久化到 `data/config.json`

#### 问题14: Orchestrator 任务队列纯内存
- **文件**: `src/core/orchestrator.py:~L35-38`
- **问题**: 刷新后排队任务丢失
- **建议**: 写入 `data/tasks/pending.json`

### 🔵 重构任务

#### 问题7: 删除过期脚本
- **文件**: `src/ptz/ptz/limits.py`（旧版本，2026/5/23）
- **操作**: 删除，保留 `src/advanced/limit.py`（新版本，2026/6/13）
- **影响**: 无外部引用，安全删除

#### 问题11: PTZManager 改名为 PTZController
- **文件**: `src/core/ptz_manager.py` → `src/core/ptz_controller.py`
- **类名**: `PTZManager` → `PTZController`
- **操作**: 修改文件名、类名、所有导入语句
- **影响**: router.py, main.py, 其他模块

#### 问题12: connected 状态判断逻辑
- **文件**: `src/api/router.py:~L792-797`
- **问题**: 只检查 `active_device`，未检查实际连接状态
- **修复**: 同时检查 `active_device` 非空 AND `ip in mgr._controllers`

---

## 已完成

#### ✅ 问题6: 操作日志持久化
- 写入 `logs/operations.json`

---

## 修复原则

1. 拆分步骤，逐一修复
2. 禁止打补丁，必须精确修复
3. 禁止过度开发
4. 修复后更新 documents/file_structure.md
5. 修复后更新记忆，复盘错误开发
