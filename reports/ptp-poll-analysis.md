# 主控台轮询暂停机制 - 分析报告

**时间**: 2026-07-08
**任务**: 为主控台轮询添加暂停/恢复机制

---

## 一、现有机制盘点

### 1. 存在两个轮询系统

```
┌─────────────────────────────────────────────────────┐
│  system1: ptzImagePoll (console.html, 1990行)       │
│    - 频率: 1次/秒                                     │
│    - 内容: 5个并行GET                                 │
│      • position    → /PTZCtrl/channels/1/position   │
│      • whitebalance → /Image/channels/1/whiteBalance │
│      • noisereduce  → /Image/channels/1/noiseReduce  │
│      • iris        → /Image/channels/1/iris          │
│      • shutter     → /Image/channels/1/shutter       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  system2: ptzPositionPoll (index.html, 2381行)      │
│    - 频率: 1次/秒                                     │
│    - 内容: 1个GET                                     │
│      • position → /PTZCtrl/channels/1/position       │
│    - 用途: 顶部状态栏显示P/T/Z坐标                    │
└─────────────────────────────────────────────────────┘
```

### 2. 现有调用链

**主控台轮询 (ptzImagePoll)**

| 触发点 | 文件 | 行号 | 动作 |
|--------|------|------|------|
| 设备断开 | console.html | 676 | `stopPtzImagePoll()` |
| 设备连接 | console.html | 747 | `startPtzImagePoll()` |
| 框选搜索开始 | index.html | 2926 | `stopPtzImagePoll()` |
| done事件 | index.html | 2986 | `startPtzImagePoll()` |
| error事件 | index.html | 3011 | `startPtzImagePoll()` |
| interrupt事件 | index.html | 3027 | `startPtzImagePoll()` |

**位置轮询 (ptzPositionPoll)**

| 触发点 | 文件 | 行号 | 动作 |
|--------|------|------|------|
| 设备断开 | index.html | 1498 | `stopPtzPositionPoll()` |
| 设备连接 | *(未完整搜索)* | - | `startPtzPositionPoll()` |

---

## 二、问题定位

### ❌ 缺失：function/limit/speed 测试暂停轮询

当前 `advanced.html` 的测试流程：

```
用户点击"Run"
  ↓
POST /api/v1/advanced/detect/start
  ↓
轮询 /api/v1/advanced/detect/status/{taskId}
  ↓
[测试期间: backend 大量 ISAPI 操作]
  ↓
completed/failed/cancelled
```

**问题**: 测试全程没有调用 `stopPtzImagePoll()`，主控台5次GET/秒持续运行，与测试并发抢占设备。

### ✅ 已有：局部对焦/白平衡暂停轮询

当前 `index.html` 的框选搜索流程：

```
_finishRegion()
  ↓
stopPtzImagePoll()       ← 搜索开始前暂停 ✓
  ↓
fetch POST /vision/focus-search (SSE)
  ↓
... 搜索进行中 ...
  ↓
event === 'cleanup' → startPtzImagePoll()  ← 搜索结束后恢复 ✓
event === 'done'    → startPtzImagePoll()  ← 恢复 ✓
event === 'error'   → startPtzImagePoll()  ← 恢复 ✓
event === 'interrupt'→ startPtzImagePoll()  ← 恢复 ✓
```

**结论**: 局部搜索的暂停/恢复已经正确实现。但恢复点分散在4个事件分支中。

---

## 三、建议方案

### 方案A: 直接添加（最小改动）

在 `advanced.html` 的 `runAdvTest()` 和 `pollAdvProgress()` 中添加 `stopPtzImagePoll`/`startPtzImagePoll`:

```javascript
// runAdvTest() 中, fetch之前添加:
stopPtzImagePoll();

// pollAdvProgress() 中, 3个完成状态分支各添加:
startPtzImagePoll();

// stopAdvTest() 中添加:
startPtzImagePoll();
```

**优点**: 改动最小, 直接复用现有函数
**缺点**: 恢复点分散, 如果有更多场景需要类似处理会重复代码

### 方案B: 统一封装器（推荐）

创建计数器保护机制:

```javascript
// 统一轮询暂停器
var _pollPauseCount = 0;

function pausePtzPolling() {
    _pollPauseCount++;
    if (_pollPauseCount === 1) {
        stopPtzImagePoll();
        // stopPtzPositionPoll(); // 如需同时暂停
    }
}

function resumePtzPolling() {
    if (_pollPauseCount <= 0) return;
    _pollPauseCount--;
    if (_pollPauseCount === 0) {
        startPtzImagePoll();
        // startPtzPositionPoll(); // 如需同时恢复
    }
}
```

**优点**: 
- 计数器保护, 多个并发暂停需求可叠加
- 集中管理, 恢复点统一
- 未来新增暂停场景只需加一对 pause/resume

**缺点**: 改动量比方案A稍大

---

## 四、具体改动点清单

### 如果采用方案A（直接添加）

**文件**: `src/web/includes/advanced.html`

| 函数 | 行号 | 添加代码 |
|------|------|----------|
| `runAdvTest()` | fetch前 | `stopPtzImagePoll();` |
| `pollAdvProgress()` | completed分支 | `startPtzImagePoll();` |
| `pollAdvProgress()` | failed分支 | `startPtzImagePoll();` |
| `pollAdvProgress()` | cancelled分支 | `startPtzImagePoll();` |
| `stopAdvTest()` | 末尾 | `startPtzImagePoll();` |

### 如果采用方案B（统一封装器）

**新增位置**: `index.html` 或 `console.html`（全局可用）

```javascript
// 在 startPtzImagePoll/stopPtzImagePoll 定义后添加
var _pollPauseCount = 0;
function pausePtzPolling() {
    _pollPauseCount++;
    if (_pollPauseCount === 1) stopPtzImagePoll();
}
function resumePtzPolling() {
    if (_pollPauseCount <= 0) return;
    _pollPauseCount--;
    if (_pollPauseCount === 0) startPtzImagePoll();
}
```

**替换位置**:

| 文件 | 函数 | 原代码 | 替换为 |
|------|------|--------|--------|
| index.html | `_finishRegion()` | `stopPtzImagePoll()` | `pausePtzPolling()` |
| index.html | 4个event分支 | `startPtzImagePoll()` | `resumePtzPolling()` |
| advanced.html | `runAdvTest()` | *(无)* | `pausePtzPolling()` |
| advanced.html | 4个完成分支 | *(无)* | `resumePtzPolling()` |

---

## 五、关于局部对焦/白平衡的补充说明

现有代码已正确实现:
- 暂停时机: `_finishRegion()` 中, 发送SSE请求前 → 早于"获取第一帧" ✓
- 恢复时机: 收到 `cleanup`/`done`/`error`/`interrupt` 事件后 → 晚于"获取最后一帧" ✓

但恢复逻辑分散在4个分支, 可优化为统一 `finally`-style:

```javascript
// 建议在 fetch().then().catch() 的 .finally() 中统一恢复
// 或使用 try/finally 包装
```

---

## 六、待审批问题

1. **是否采用方案B（统一封装器）？**
2. **是否同时暂停 ptzPositionPoll（顶部状态栏轮询）？**
3. **局部搜索的恢复逻辑是否需要统一集中到 finally？**

请审批后执行。
