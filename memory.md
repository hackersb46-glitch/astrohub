# AstroHub 开发关键规则

## 项目结构

### 模块命名
- 小写+下划线：`stream_wasm.py`、`device_manager.py`
- 不用驼峰、不用大写
- 新模块放对应目录：stream→`src/stream/`，core→`src/core/`

### 文件路径
- 主程序：`src/main/main.py`
- WebSocket代理：`src/stream/stream_wasm.py`（v7.60从main.py剥离）
- 前端页面：`src/web/index.html`
- 前端组件：`src/web/includes/console.html`
- 版本号：`src/main/constants.py`（唯一定义）
- 数据存储：`data/devices/{mac_clean}/`

## UI调整规则

### 尺寸用像素值
- 老板要求精确控制，不用百分比
- 例：信息窗体固定110px，不用70%

## 执行纪律

### 禁止大量调用进程
- 不要反复调用Python/PS进程
- 卡死系统=严重错误
- 专注完成任务，不盲目试错

### 需求理解规则（v7.102教训）

**遇到模糊需求时，必须立即停下来确认**

1. **信息框/面板职责划分**
   - 多个信息框时，必须明确每个的具体职责
   - 问清楚：哪个显示关键事件？哪个显示详细日志？
   - 不要混淆职责

2. **路径/目录结构设计**
   - 问清楚：这个目录未来会扩展吗？
   - 设置页面应该显示哪个层级？
   - 父级目录 = 通用类别，子级目录 = 具体类型/品牌
   - 例：SDK/（父级）→ HIK/大华/宇视/（子级品牌）

3. **状态指示器设计**
   - 必须反映实际状态，不要硬编码
   - 问清楚：什么条件下显示什么状态？
   - 已连接时不显示"等待连接"
   - 已登录时不显示"登录"按钮

4. **按钮/控件显示逻辑**
   - 根据实际状态动态显示/隐藏
   - 问清楚：什么条件下显示？什么条件下隐藏？

**检查清单**（开发前必须确认）：
- [ ] 每个信息框的具体职责是什么？
- [ ] 路径/目录结构的设计意图是什么？
- [ ] 状态指示器应该显示哪些状态？
- [ ] 按钮应该如何根据状态显示/隐藏？
- [ ] 是否需要支持未来扩展？

## ISAPI 接口规则

### 1. XML 格式必须与 GET 响应一致
- GET 响应就是 PUT 应用的正确格式模板
- 大小写敏感：`manual`/`auto`（小写），不是 `Manual`/`Auto`
- 完整结构：降噪需要 `<mode>general</mode><GeneralMode><generalLevel>`

### 2. 白平衡端点
- GET: `/ISAPI/Image/channels/1/whiteBalance`
- 返回字段：`WhiteBalanceStyle`, `WhiteBalanceRed`, `WhiteBalanceBlue`
- PUT 格式必须与 GET 一致

### 3. 降噪端点
- GET: `/ISAPI/Image/channels/1/noiseReduce`
- 返回字段：`mode`, `GeneralMode/generalLevel`
- PUT 需要完整 `<mode>general</mode><GeneralMode>` 结构

---

## 测试验证标准

### 连续5次测试
- 每次设置不同值
- 每次等待1秒
- ISAPI PUT 返回 200
- GET 验证值正确

### SDK 集成验证标准（v7.98 确立）
- **浏览器验证 > Python 脚本验证**：SDK 集成必须用 Playwright 在浏览器中验证
- **错误码第一时间查定义**：在 minified 源码中搜索错误码
- **localhost ≠ 127.0.0.1**：JSPlugin URL 解析只认 IP 和带点号的域名

---

## 图片识别（2026-06-21 确认）

### 唯一可用方法
- **端点**: `coding.dashscope.aliyuncs.com/apps/anthropic/v1/messages`
- **格式**: Anthropic Messages API
- **模型**: `qwen3.7-plus`
- **API Key**: 见 TOOLS.md

### 不可用方法
- OpenClaw `image` 工具：provider 大小写 bug
- MiniMax `mmx vision`：配额用完
- 标准 DashScope 端点：拒绝 Coding Plan API key

---

## WASM 视频播放架构（v7.98）

### 调用链
```
wasmStartRealPlay(channel, streamType, useProxy)
  → WebVideoCtrl.I_StartRealPlay(deviceIdentify, {bProxy: true, ...})
    → oProtocolInc.startRealPlay(device, options)
      → k(url)  // URL 转换：设备IP → location.hostname，设置 cookie
      → JS_Play(url, {sessionID, token}, wndIndex)
        → _openStream(url, opts, wndIndex)
          → oStreamClient.openStream(url, opts, callback)
            → new WebSocket(url)  // URL 已被重建
```

### k() 函数逻辑
- 输入：`ws://设备IP:端口/通道号`（如 `ws://192.168.5.72:7681/102`）
- 替换 IP 为 `location.hostname`
- 设置 `webVideoCtrlProxyWs` cookie = `设备IP:端口`
- 返回：`ws://hostname:port/通道号/webSocketVideoCtrlProxy`

### openStream URL 重建
- 解析 k() 返回的 URL，提取 hostname/port/通道号
- **重建 URL**：`ws://hostname:port?version=...&sessionID=...&token=...`
- 检查原 URL 含 `webSocketVideoCtrlProxy` → 插入 `/webSocketVideoCtrlProxy/?`
- **localhost 不被识别** → 当 IPv6 处理 → URL 崩溃

### 代理配置（官方 Nginx 方式）
- ISAPI：`/ISAPI|SDK/` → 从 `webVideoCtrlProxy` cookie 读取设备地址
- WebSocket：`/webSocketVideoCtrlProxy` → 从 `webVideoCtrlProxyWs` cookie 读取设备地址
- 查询字符串：`?$args`（含 token）

### 本机 IP 获取
- `/api/v1/localhost` → `data/reports/localhost.json` → `local_ip` 字段
- index.html 检测 `localhost` → 同步请求本机 IP → 重定向

---

## 备份规范（v7.122 确认）

### D盘备份路径格式
- `D:\astrohub_backup_YYYYMMDD`

### 备份流程
1. 复制项目到 `D:\astrohub_backup_YYYYMMDD`
2. 清理临时文件（__pycache__, backup_*, data/records, test_*.py等）
3. 初始化 git 并推送到 https://github.com/hackersb46-glitch/astrohub

### 本地备份路径
- `astrohub/backup_YYYYMMDD_HHMMSS/`

---

## 代码架构重构（v8.01 重大重构）

### 模块重命名
- `Logger` → `PTZLogger`（src/ptz/core/logger.py）- 避免与全局 Logger 混淆
- `Orchestrator` → `TaskScheduler`（src/core/orchestrator.py）- 明确职责

### 代码瘦身
- ptz_controller.py 减少约 20KB 重复代码
  - 删除内嵌 `Logger` 类，复用 `src/ptz/core/logger.py`
  - 删除内嵌 `ISAPIResponse` + `ISAPIClient`，复用 `src/ptz/isapi/client.py`
- 删除未使用的 `src/ptz/sadp/` 目录

### 版本号
- v8.01: VERSION = "8.01", VERSION_NUM = "8.01"

---

## E2E 测试经验（v8.01）

### 测试结果
- API 测试: 6/6 全部通过（100%）
- 总体测试: 16/22 通过（73%）
- UI 定位失败主要是选择器匹配问题，不影响功能验证

### 选择器优化建议
- Playwright 的 `text="xxx"` 选择器在复杂 UI 中容易超时
- **建议**: 优先使用更稳定的选择器（data-testid、role、name）
- **教训**: UI 自动化测试需要稳定的元素定位策略

### 测试脚本位置
- E2E 脚本: `astrohub/tools/e2e_v801_simple.py`
- 截图: `astrohub/e2e_screenshots/`
- 结果: `astrohub/e2e_screenshots/results.json`

---

## 前端开发教训（v7.122）

### 1. 多入口UI操作只改一处
- **错误**: 只修改 `switchPage()`，遗漏 `initNav` click handler
- **教训**: 修改按钮行为 → 搜索所有触发路径（onclick/onchange/handler）
- **检查清单**: 按钮 onclick、页面导航 handler、全局函数、键盘快捷键

### 2. 异步竞态覆盖
- **错误**: `loadDevicesQuick()`(GET,无status) 和 `refreshDevices()`(POST,有status) 同时触发，无status的GET后返回覆盖了有status的POST结果
- **教训**: 两个async写同一个UI → 合并为一个请求，或用标志位阻止覆盖
- **解决方案**: 改用 `refreshDevices()` 替代 `loadDevicesQuick()`

### 3. 多分支函数遗漏分支
- **错误**: `connectDevice()` 有3个成功路径，主路径缺 `showToast('success')`
- **教训**: 列出所有 if/else/catch 分支 → 逐一检查用户反馈
- **检查清单**: 每个分支是否都有用户反馈（toast/log/alert）

---

## 设备管理架构（v7.122）

### 设备发现
- SADP: 即时返回（后台服务持续运行）
- 手动添加: IP + 凭证

### 状态刷新
- 切换设备页面时自动触发 `refreshDevices()`（POST /devices/refresh）
- 不再依赖 `loadDevicesQuick()` 的定时轮询

### 列顺序
序号 | 设备型号 | 设备名称 | MAC | IP地址 | 网关地址 | 状态 | 操作