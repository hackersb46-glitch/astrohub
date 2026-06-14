# AstroHub 三档速度 + 一键检测 设计文档

**日期**: 2026-05-08
**版本**: v1.0

---

## 1. 三档速度档位定义

三档是**速度档位**，不是 Zoom 档位。

| 档位 | 速度值列表 | 数量 | 说明 |
|------|-----------|------|------|
| **Lite** | [1, 50, 100] | 3 档 | 默认档位，快速检测 |
| **Medium** | [1, 20, 40, 60, 80, 100] | 6 档 | 中等精度 |
| **Full** | [1, 5, 10, 15, 20, ..., 95, 100] | 21 档 | 全精度，差值5等差数列 |

**默认/自动化**: Lite 档
**用户可选**: Web UI 提供下拉选择 Lite / Medium / Full

---

## 2. 三大检测

初次连接设备时，必须执行三大检测：

| 检测模块 | 对应 CSV | 说明 |
|---------|---------|------|
| **Function 探测** | P4.1-P4.21 | 20项设备能力探测，GET→PUT→GET验证→PUT恢复 |
| **Limit 限位** | P6.0-P6.6 | P/T/Z 限位检测，翻转检测 |
| **Speed 速度** | P5-P8 | Lite 档速度测试 (3档速度 × 2轴 × 2方向 × 3档Zoom = 36次测量) |

---

## 3. 一键检测按钮设计

### 3.1 位置
**高级功能 → A 检测模块** 页面

### 3.2 UI 元素

```
┌─────────────────────────────────────────────┐
│           一键检测                           │
├─────────────────────────────────────────────┤
│ 速度档位: [▼ Lite]  [Medium]  [Full]         │
│                                             │
│ 检测项目:                                    │
│ ☑ Function 探测 (20项)                      │
│ ☑ Limit 限位 (P/T/Z)                        │
│ ☑ Speed 速度 (Lite档)                       │
│                                             │
│              [▶ 开始检测]                    │
│                                             │
│ 进度: [████████████░░░░] 60%                │
│ 当前: Speed 速度测试 - Pan 正向 speed=50    │
│ 日志: [info] 2026-05-08 21:00:01 Speed测试中 │
└─────────────────────────────────────────────┘
```

### 3.3 按钮行为

**默认行为** (用户点击 [▶ 开始检测]，未改选项):
1. 执行 Function 探测 (20项)
2. 执行 Limit 限位 (P/T/Z)
3. 执行 Speed 速度测试 (Lite档: 1, 50, 100)

**用户选择 Medium/Full**:
- Speed 速度测试使用对应档位的速度列表
- Function 和 Limit 不变

### 3.4 执行流程

```
用户点击 [▶ 开始检测]
    ↓
1. 检查设备是否已连接 → 未连接则提示
    ↓
2. Function 探测
   - 20项端点探测
   - GET → PUT → GET验证 → PUT恢复
   - 每完成一项更新进度条
    ↓
3. Limit 限位
   - goto_home 验证
   - P轴限位 (连续移动，20点同值判限位)
   - T轴限位/翻转
   - Z轴限位
    ↓
4. Speed 速度测试 (默认Lite)
   - 3档Zoom × 2轴 × 2方向 × N档速度
   - Lite: 36次测量
   - Medium: 72次测量
   - Full: 252次测量
    ↓
5. 生成检测报告
   - Function: 通过/失败列表
   - Limit: P/T/Z 限位值
   - Speed: 各档位速度值 (deg/s)
    ↓
6. 保存结果到 config.json + 报告文件
```

### 3.5 进度反馈

- 进度条实时更新 (0% → 100%)
- 当前执行步骤显示
- 日志窗口实时输出 [info]/[done]/[warning]/[error]

---

## 4. 修改清单

### 4.1 speed.py 修改

| 修改点 | 说明 |
|--------|------|
| `SPEED_PROFILES` | 新增三档定义: `{"lite": [1,50,100], "medium": [1,20,40,60,80,100], "full": [1,5,10,...,100]}` |
| `run_all_tests` 参数 | 新增 `speed_profile: str = "lite"` 参数 |
| `speed_levels` | 从 `SPEED_PROFILES[speed_profile]` 动态获取 |

### 4.2 Web UI 修改

| 文件 | 修改 |
|------|------|
| `src/web/index.html` | 高级功能页面添加检测模块 UI |
| | 一键检测按钮 + 档位选择 + 进度条 + 日志窗口 |
| `src/api/router.py` | 新增 `/api/v1/advanced/detect` 端点 (WebSocket 或 SSE 推送进度) |

### 4.3 API 设计

```
POST /api/v1/advanced/detect/start
Body: {"speed_profile": "lite", "modules": ["function", "limit", "speed"]}
Response: {"task_id": "xxx", "status": "started"}

GET /api/v1/advanced/detect/status/{task_id}
Response: {"progress": 60, "current_step": "Speed测试", "log": "..."}

GET /api/v1/advanced/detect/result/{task_id}
Response: {"function": {...}, "limit": {...}, "speed": {...}}
```

---

## 5. 约束

- 最小修改，不破坏已有功能
- 每个 Python 改完 py_compile 验证
- 完成后汇报修改清单
