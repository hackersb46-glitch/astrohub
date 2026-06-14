# AstroHub 项目路径与结构文档

**最后更新**: 2026-06-14

## 正确的项目结构

```
C:\Users\admin\.openclaw\agents\dev-factory\astrohub\
│
├── src\                          # 源代码目录
│   ├── main\                     # 主模块目录（正确）
│   │   ├── __init__.py           # 模块初始化
│   │   ├── main.py               # 入口文件（正确）
│   │   └── constants.py          # 全局常量（版本号在这里！）
│   │
│   ├── api\                      # API 路由
│   │   ├── __init__.py
│   │   └── router.py             # API 端点定义
│   │
│   ├── core\                     # 核心模块
│   │   ├── ptz_manager.py        # PTZ 管理
│   │   ├── device_manager.py     # 设备管理
│   │   └── ...
│   │
│   ├── web\                      # Web 前端
│   │   ├── index.html            # 主页面
│   │   └── includes\
│   │       └── console.html      # 主控台页面
│   │
│   └── config.py                 # 配置文件
│
├── data\                         # 数据目录
│   └── devices\                  # 设备凭据
│
├── tests\                        # 测试文件
│
└── backup_*                      # 备份目录
```

## 关键文件位置

| 内容 | 正确路径 | 错误路径（已删除） |
|------|----------|-------------------|
| 入口文件 | `src/main/main.py` | ~~`src/main.py`~~ |
| 版本号 | `src/main/constants.py` | ~~`index.html`~~ |
| API 路由 | `src/api/router.py` | - |
| 主控台前端 | `src/web/includes/console.html` | - |

## 正确的启动命令

### 方式 1：命令行启动
```bash
cd C:\Users\admin\.openclaw\agents\dev-factory\astrohub
python -m src.main.main --headless
```

### 方式 2：后台启动
```bash
cd C:\Users\admin\.openclaw\agents\dev-factory\astrohub
Start-Process python -ArgumentList "-m", "src.main.main", "--headless"
```

### 方式 3：带窗口启动
```bash
cd C:\Users\admin\.openclaw\agents\dev-factory\astrohub
python -m src.main.main
```

## 访问地址

- **Web 界面**: http://localhost:10280/
- **API 文档**: http://localhost:10280/docs
- **设备 ISAPI**: http://192.168.5.72/ISAPI/

## 版本号管理

**版本号定义位置**: `src/main/constants.py`

```python
VERSION = "v6.56"
VERSION_NUM = "6.56"
```

**注意**: 修改版本号时，需要同时更新：
1. `src/main/constants.py` - 代码读取的版本号
2. `src/web/index.html` - 页面显示的版本号（可选）

## 常见问题

### 问题 1: 启动失败 "No module named 'src'"
**原因**: 不在正确目录下运行
**解决**: `cd astrohub` 后再运行

### 问题 2: 版本号不更新
**原因**: 只修改了 `index.html`，没有修改 `constants.py`
**解决**: 修改 `src/main/constants.py`

### 问题 3: 导入错误 "cannot import name 'create_app'"
**原因**: 命名冲突，`src/main/` 目录和 `src/main.py` 文件冲突
**解决**: 已删除错误的 `src/main.py`

## 开发规范

1. **备份**: 修改前创建备份 `backup_YYYYMMDD_HHMMSS/`
2. **版本号**: 同时更新 `constants.py` 和 `index.html`
3. **测试**: 修改后运行 E2E 测试验证
4. **路径**: 所有路径相对于 `astrohub/` 目录