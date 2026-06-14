# 心跳与任务状态

**最后更新**: 2026-06-15 07:21
**状态**: v7.30 开发中
**工作空间**: C:\Users\admin\.openclaw\agents\dev-factory\astrohub

---

## v7.30 当前任务

| 序号 | 问题 | 状态 |
|------|------|------|
| 1 | 视频窗体宽度限定1280 max，16:9横版 | ✅ 已修复 |
| 2 | 刷新后ISAPI连接正常但显示"请连接设备" | ✅ 已修复 |
| 3 | 增益/OSD/PTZ开关未禁用 | ✅ 已修复 |
| 4 | 主控台模块级别禁用灰色 | 待确认 |

---

## v7.30 修复详情

### 问题2修复
- 移除 WASM `cbInitPluginComplete` 中创建覆盖层的逻辑
- 覆盖层由 `restoreConnectionState` 和 disconnect 事件管理

### 问题3修复
- 修改 `loadDeviceImageParams` 函数
- 不因缺少 function.json 而禁用画面控制
- 设备已连接时显示 toast 提示，不调用 `disableImageControls`

---

## v7.12 更新总结

| 版本 | 问题 | 修复 |
|------|------|------|
| v7.07 | 快门设置时光圈也被修改 | 快门/光圈使用独立 ISAPI 端点 |
| v7.08 | 快门下拉列表硬编码 | 从 capabilities 获取 opt_values |
| v7.10 | 断开后状态显示错误 | 区分 active_device 和 last_connected |
| v7.11 | 断开后增益控件仍可操作 | 禁用列表添加 gainLevel |
| v7.12 | 刷新页面提示无设备 | 自动连接上次设备 |

---

## 项目结构

```
astrohub/
├── src/main/              # 主模块入口
│   ├── main.py            # 程序入口
│   └── constants.py       # 版本号
├── src/api/router.py      # API 路由
├── src/core/ptz_manager.py # PTZ 管理器
├── src/web/               # 前端
│   ├── index.html         # 主页面
│   └── includes/          # 页面组件
└── doc/                   # 文档
```

---

## 启动命令

```bash
cd astrohub
python -m src.main.main --headless
```

---

## Git 仓库

- **地址**: https://github.com/hackersb46-glitch/astrohub
- **最后提交**: v7.30
