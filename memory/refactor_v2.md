# AstroHub 重构文档

**日期**: 2026-05-21
**版本**: v2.0

---

## 一、完成的改动

### 1. 模板拆分（Jinja2）

**目的**: 减少 index.html 代码量，便于维护

**改动**:
```
src/web/
├── base.html           # 基础模板（CSS、导航、JS）
├── index.html          # 入口（{% extends "base.html" %}）
├── includes/
│   ├── dashboard.html  # 仪表盘模块
│   ├── devices.html    # 设备管理模块
│   ├── console.html    # 主控台模块
│   ├── observation.html# 观察计划模块
│   ├── advanced.html   # 高级功能模块
│   └── replay.html     # 回放模块
```

**配置**: `m12_integration/main.py` 添加 Jinja2Templates

---

### 2. 统一启动入口

**目的**: 跨平台启动脚本

**新增文件**:
- `start.py` - Python 跨平台启动脚本
- `start.sh` - Shell 脚本（macOS/Linux）

**用法**:
```bash
# 启动服务
python start.py --port 10280

# 无头模式
python start.py --port 10280 --headless

# 停止服务
python start.py --stop

# 查看状态
python start.py --status
```

---

### 3. 清理冗余文件

**备份位置**: `D:\PY BACK\astro_hub_backup\20260521_001037\`

**清理内容**:
- `fix_*.py` - 临时修复脚本
- `add_*.py` - 临时添加脚本
- `check*.py` - 临时检查脚本
- `test*.py` - 临时测试脚本
- `analyze*.py` - 临时分析脚本
- `create*.py` - 临时创建脚本
- `split*.py` - 临时拆分脚本
- `disable*.py` - 临时禁用脚本

**保留**:
- `src/m12_integration/main.py` - 主入口
- `src/main.py` - 模块路由定义
- 各模块目录内的 main.py

---

## 二、文件结构

```
项目目录/
├── start.py            # 统一启动入口
├── start.sh            # Shell 启动脚本
├── start.bat           # Windows 批处理（保留）
├── stop.bat            # Windows 停止脚本
├── src/
│   ├── main.py         # 路由定义
│   ├── config_paths.py # 配置路径
│   ├── m12_integration/
│   │   └── main.py     # 服务入口（uvicorn）
│   └── web/
│       ├── base.html   # Jinja2 基础模板
│       ├── index.html  # Jinja2 入口
│       ├── includes/   # HTML 模块
│       └── static/
│           ├── js/
│           └── websdk/
```

---

## 三、验证结果

| 项目 | 状态 |
|------|------|
| 服务启动 | ✅ 端口 10280 正常 |
| 页面渲染 | ✅ nav-btn 存在 |
| 模块加载 | ✅ page-dashboard 存在 |
| Jinja2 模板 | ✅ 正常组装 |

---

## 四、后续维护

### 添加新页面模块

1. 创建 `src/web/includes/new_module.html`
2. 在 `base.html` 添加 `{% include "includes/new_module.html" %}`
3. 在导航添加按钮

### 修改页面内容

直接编辑对应的 `includes/*.html` 文件

---

**更新时间**: 2026-05-21 00:25