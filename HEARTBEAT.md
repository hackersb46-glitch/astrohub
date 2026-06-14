# 心跳与任务状态

**最后更新**: 2026-06-14 22:17
**状态**: v7.12 已推送到 GitHub
**工作空间**: C:\Users\admin\.openclaw\agents\dev-factory\astrohub

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

## 关键修复

### 设备状态字段
```
active_device  = "当前在用"  → 断开就清空
last_connected = "上次用过" → 断开不清空，保留记忆
```

### ISAPI 端点分离
- 曝光模式: `/exposure` + `<ExposureType>`
- 快门: `/Shutter` + `<ShutterLevel>` (独立端点)
- 光圈: `/Iris` + `<IrisLevel>` (独立端点)

---

## 项目结构

```
astrohub/
├── src/main/              # 主模块入口
│   ├── main.py            # 程序入口
│   └── constants.py       # 版本号 v7.12
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
- **文件数**: 315 个
- **最后提交**: v7.12
