# 心跳与任务状态

**最后更新**: 2026-07-08 19:30
**状态**: v8.73 基线管理系统完成
**当前版本**: v8.73

---

## v8.73 基线管理系统（2026-07-08）

### 完成的任务

#### 1. 基线管理基础设施
- ✅ region_base.py: 新增 `read_search_baseline()` / `write_search_baseline()` 函数
- ✅ region_base.py: 新增 `calc_wb_delta()` 白平衡差异计算
- ✅ region_base.py: 新增 `check_baseline()` 基线检查函数
- ✅ region_base.py: 新增阈值定义 `BASELINE_THRESHOLDS`
  - 对焦（反差）：15%
  - 白平衡（delta）：10%
  - 亮度（亮度值）：5%
- ✅ 存储文件：`data/search_baseline.json`

#### 2. API 端点
- ✅ router.py: 新增 `POST /api/v1/vision/check-baseline` 端点
  - 用于手动框选前的基线检查
  - 返回 `{should_search: bool, diff_percent: float, message: str}`

#### 3. 互锁竞态条件修复
- ✅ router.py: `_guarded_search()` 使用 `asyncio.Lock()` 保护 `_search_state['active']`
  - 修复了多个搜索请求同时到达时的竞态条件

#### 4. 基线自动存储
- ✅ whitebalance.py: 在 `done` 事件中存储基线（red, blue, delta）
- ✅ autofocus.py: 在 `done` 事件中存储基线（contrast, best_contrast）
- ✅ brightness.py: 在 `done` 事件中存储基线（brightness, shutter, iris, gain）

### 修改文件
- `src/controlpanel/region_base.py` — 基线管理函数
- `src/controlpanel/autofocus.py` — 基线存储
- `src/controlpanel/whitebalance.py` — 基线存储
- `src/controlpanel/brightness.py` — 基线存储
- `src/api/router.py` — 互锁修复 + check-baseline 端点
- `src/main/constants.py` — v8.72 → v8.73

### 备份
`backup_20260708_v872/`

---

## v8.72 三模块互锁+基类重构（2026-07-08）

### 完成的任务

#### 需求1：停止按钮在运行中可用
- ✅ console.html: `executeScheduledSearch()` 开头启用对应停止按钮
- ✅ console.html: SSE pump 中处理 `queued` 事件（等待其他搜索完成）
- ✅ index.html: `_finishRegion()` 已有停止按钮启用逻辑（v8.41）

#### 需求2：三模块互锁
- ✅ router.py: 新增 `_search_state` 字典追踪活跃搜索器
- ✅ router.py: 新增 `_guarded_search()` 异步生成器包装器
- ✅ router.py: 新增 `GET /api/v1/vision/search-status` 端点
- ✅ router.py: 三个 search 端点改用 `_guarded_search('wb'/'focus'/'brightness', ...)` 包装
- ✅ index.html: `toggleRegionMode()` 入口检查 search-status，活跃时拒绝框选

#### 需求3：基类提取
- ✅ region_base.py: 新增 `SearcherBase` 基类
  - `_interrupt()` 方法（三个子类完全相同）
  - `_capture()` 方法（三个子类完全相同）
  - `_setup_stable_delay()` 方法
  - `search_type` 属性
- ✅ autofocus.py: FocusSearcher 继承 SearcherBase，删除重复方法
- ✅ whitebalance.py: WhiteBalanceSearcher 继承 SearcherBase，删除重复方法
- ✅ brightness.py: BrightnessSearcher 继承 SearcherBase，删除重复方法

### 修改文件
- `src/controlpanel/region_base.py` — 新增 SearcherBase 基类
- `src/controlpanel/autofocus.py` — 继承基类
- `src/controlpanel/whitebalance.py` — 继承基类
- `src/controlpanel/brightness.py` — 继承基类
- `src/api/router.py` — 互锁机制 + 状态端点
- `src/web/includes/console.html` — 停止按钮启用 + queued 事件
- `src/web/index.html` — 框选互锁检查
- `src/main/constants.py` — v8.71 → v8.72

### 备份
`backup_20260708_v869/`

---

## v8.69 主控台模式记忆功能（2026-07-08）

### 完成的任务
1. ✅ router.py 新增 GET/POST /api/v1/console/state 端点（读/写 registry.json 的 console_state）
2. ✅ console.html 新增 loadConsoleState() / saveConsoleState() 函数
3. ✅ onWbModeChange / onFocusModeChange / setExposureMode 添加 saveConsoleState() 调用
4. ✅ loadAllImageParams() 末尾调用 loadConsoleState() 恢复上次状态
5. ✅ 曝光模式 label font-size: 10px→11px（与对焦一致）
6. ✅ flex 容器加 align-items: center（居中对齐）
7. ✅ 版本号: v8.68→v8.69
8. ✅ 备份: backup_20260708_console_state/

### 存储设计
```
registry.json
└── console_state: { wb_mode, focus_mode, exposure_mode }
```

### 错误记录
- ERR-20260708-002: router.py 中 json 模块未导入，导致 API 返回 500
- ERR-20260708-003: 端口占用导致服务启动失败

---

## v8.68 光圈值格式修改（2026-07-08）

### 完成的任务
1. ✅ brightness.py iris 值从原始数字（如 160）显示为 F 样式（如 F1.6）
2. ✅ step() 消息字符串 `/10` → `/100`
3. ✅ SSE 事件 iris 字段格式化
4. ✅ ISAPI 调用保持原始值不变

### 备份
`backup_20260708_gain_osc/`

---

## v8.67 局部亮度控制（2026-07-08）

### 完成的任务
1. ✅ 新增 `calc_brightness()` 亮度计算（region_base.py）
2. ✅ 创建亮度迭代搜索器 `IterativeBrightness`（三阶优先级：快门→光圈→增益）
3. ✅ 创建 `BrightnessSearcher`（SSE流式，复用WB模式）
4. ✅ 曝光模式下拉新增"局部"选项，亮度滑块双模式切换
5. ✅ 局部亮度面板（框选+定时+停止），复用WB/对焦UI风格
6. ✅ `toggleRegionMode('brightness')` 框选分析，独立 localStorage key
7. ✅ 轮询暂停 `pausePtzPolling()` / `resumePtzPolling()` 复用
8. ✅ 定时搜索 `executeScheduledSearch('brightness')` 完整支持
9. ✅ API端点 `POST /vision/brightness-search`（SSE）+ `POST /vision/brightness-stop`
10. ✅ 版本号: v8.66 → v8.67
11. ✅ 备份: backup_20260708_brightness/

### 亮度计算算法
```
Y = 0.299R + 0.587G + 0.114B（标准亮度）
排除死黑死白 → 取有效像素Y均值 → 映射0-100
```

### 控制算法
```
优先快门（每次±1步opt_values档位）
  → 快门到极限 → 调光圈（每次±1步）
    → 光圈到极限 → 调增益（±5粗调→±1精调）
      → 全部到极限 → "亮度不足"或"亮度超出"
```

### 复用清单
```
后端:
├── _valid_pixels() / calc_stable_delay()  → region_base.py
├── WhiteBalanceSearcher 结构模板          → brightness.py
├── ISAPI PUT 设备控制                    → router.py
└── SSE 流式响应                          → router.py

前端:
├── toggleRegionMode() / _finishRegion()    → index.html
├── pausePtzPolling() / resumePtzPolling()  → console.html
├── wbTimerInput/wbTimerToggle 定时器UI      → console.html
├── localStorage key: 'region_brightness'    → index.html
└── deviceFunctionData.functions.{shutter,iris}.opt_values → console.html
```

### 修改文件
- `src/controlpanel/region_base.py` — +calc_brightness()
- `src/controlpanel/brightness.py` — 新增（128行）
- `src/web/includes/console.html` — UI+JS（~150行）
- `src/web/index.html` — region模式+SSE（~80行）
- `src/api/router.py` — API端点（~80行）
- `src/main/constants.py` — VERSION v8.66→v8.67

### 技术细节
- **1读+2写/步**: 截图(1读) → 设置参数(1写) → 手动曝光模式(1写)
- **增益2阶段**: 粗调±5 → 精调±1（过冲检测自动切换）
- **无步数限制**: 全部到极限时终止，返回"亮度不足"/"亮度超出"
- **目标亮度**: 亮度slider在局部模式下变为"目标亮度"（0-100）

---

## v8.66 主控台轮询暂停机制（2026-07-08）

### 完成的任务
1. ✅ 创建 `pausePtzPolling()`/`resumePtzPolling()` 统一封装器（计数器保护）
2. ✅ 同时暂停 `ptzImagePoll`（5 GET/s）和 `ptzPositionPoll`（1 GET/s）
3. ✅ `index.html::_finishRegion()` 框选搜索：pause + .finally(resume)
4. ✅ `console.html::executeScheduledSearch()` 定时搜索：pause + resume
5. ✅ `advanced.html` function/limit/speed测试：pause + 4处resume
6. ✅ 局部搜索4个恢复分支集中到 `.finally()`
7. ✅ 版本号: v8.64 → v8.66
8. ✅ 备份: backup_20260708_poll-pause/

### 修改的文件
- `astrohub/src/web/includes/console.html` — 新增pausePtzPolling/resumePtzPolling + executeScheduledSearch替换
- `astrohub/src/web/index.html` — _finishRegion替换为pause+finally
- `astrohub/src/web/includes/advanced.html` — runAdvTest/stopAdvTest/pollAdvProgress添加pause/resume
- `astrohub/src/main/constants.py` — VERSION v8.64→v8.66

### 技术细节

**封装器设计**：
```javascript
var _pollPauseCount = 0;
function pausePtzPolling()  { if (++_pollPauseCount === 1) { stopPtzImagePoll(); stopPtzPositionPoll(); } }
function resumePtzPolling() { if (_pollPauseCount > 0 && --_pollPauseCount === 0) { startPtzImagePoll(); startPtzPositionPoll(); } }
```

**调用点分布**：
```
pausePtzPolling:
├── index.html::_finishRegion()       ← 框选手动搜索
└── advanced.html::runAdvTest()       ← function/limit/speed测试

resumePtzPolling:
├── index.html::_finishRegion()       ← .finally()统一恢复
├── console.html::executeScheduledSearch()  ← 定时搜索
└── advanced.html (4处)              ← completed/failed/cancelled/stopAdvTest
```

### 错误记录
- ERR-20260708-001: 修改共享机制前未全量搜索调用点，漏掉console.html的executeScheduledSearch

---

## 启动命令
```bash
cd astrohub
python -m src.main.main --headless
```
