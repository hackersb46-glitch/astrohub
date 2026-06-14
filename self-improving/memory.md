# self-improving memory

## HOT Layer

### 核心行为规则
1. **所有代码修改直接执行** — 发现问题 → 用 edit/write 工具直接修改 → 验证
2. **任何测试逻辑必须先完整读取CSV原文** — 列D方法+列E标准，不得自己推断或创造。
3. **E2E测试失败时先截图+分析HTML结构** — 确认选择器正确性后再重试，不要盲目试错。
4. **禁止 HLS 方案** — HLS 是错误方向，视频流必须用 WASM SDK 直连设备 RTSP。所有 HLS 相关模块、代码、路由、前端播放器必须彻底删除，不允许再使用。

### 工作流
- 发现问题 → 直接修复 → 验证 → 汇报结果
- 被老板纠正 → 立即写入 `~/self-improving/corrections.md`
- 任务完成 → 验证修改 → 汇报结果

### 已知问题模式
- 前端检测函数必须使用 `allDevices.find()` 获取凭据，不是 `connectedDevice`
- P轴限位跳变判断：`abs(delta) > 1800`
- 预置点10 在 function.py 的 run_all() 开头设置
