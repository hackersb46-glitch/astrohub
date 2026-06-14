# AstroHub 数据存储规范

**版本**: v7.17  
**更新时间**: 2026-06-15

---

## 一、核心原则

### 1. 设备标识统一使用 MAC 地址

- **唯一标识**：所有设备数据以 MAC 地址为唯一标识
- **MAC 格式**：统一使用无分隔符小写格式（如 `240f9b764193`）
- **禁止**：使用 IP 地址作为设备标识

### 2. 目录结构

```
data/
├── devices/                    # 设备数据（按 MAC 组织）
│   └── {mac_clean}/           # MAC 地址（无分隔符小写）
│       ├── info.json          # 设备基础信息
│       ├── function.json      # 功能测试结果
│       ├── limit.json         # 限位测试结果
│       ├── speed.json         # 速度测试结果
│       ├── function.csv       # 功能测试原始数据
│       ├── limit.csv          # 限位测试原始数据
│       └── speed.csv          # 速度测试原始数据
│
├── reports/                    # 报告文件
│   └── localhost.json         # 本机信息（非设备数据）
│
├── config/                     # 配置文件
│   └── local.json             # 本地配置
│
├── registry.json              # 设备注册表
│
├── records/                    # 录像文件
├── downloads/                  # 下载文件
├── hls/                       # HLS 流
├── db/                        # 数据库
└── calibration/               # 校准数据
```

---

## 二、设备数据存储

### 1. 设备信息 (info.json)

**路径**: `data/devices/{mac_clean}/info.json`

```json
{
  "mac": "240f9b764193",
  "ip": "192.168.5.72",
  "name": "4k 32X DC",
  "model": "iDS-2DF8C832IXS-A",
  "serial_number": "iDS-2DF8C832IXS-A20211211CCCHJ22538548",
  "firmware_version": "V5.8.0build 230208",
  "gateway": "192.168.5.1",
  "subnet_mask": "255.255.255.0",
  "username": "admin",
  "password": "xxx",
  "port": 80,
  "connected": true,
  "last_updated": "2026-06-15T04:20:00"
}
```

### 2. 功能测试 (function.json)

**路径**: `data/devices/{mac_clean}/function.json`

由 `src/advanced/function.py` 生成，记录功能探测结果。

### 3. 限位测试 (limit.json)

**路径**: `data/devices/{mac_clean}/limit.json`

由 `src/advanced/limit.py` 生成，记录限位测试结果。

### 4. 速度测试 (speed.json)

**路径**: `data/devices/{mac_clean}/speed.json`

由 `src/advanced/speed.py` 生成，记录速度测试结果。

---

## 三、MAC 地址格式规范

### 1. 输入格式（接受）

- 带冒号：`24:0f:9b:76:41:93`
- 带连字符：`24-0f-9b-76-41-93`
- 无分隔符：`240f9b764193`

### 2. 存储格式（统一）

- **格式**：无分隔符小写
- **示例**：`240f9b764193`
- **长度**：12 位十六进制字符

### 3. 验证函数

```python
def normalize_mac(mac: str) -> str:
    """统一 MAC 格式为无分隔符小写"""
    clean = mac.replace(":", "").replace("-", "").lower()
    if len(clean) != 12 or not all(c in "0123456789abcdef" for c in clean):
        raise ValueError(f"无效 MAC 地址: {mac}")
    return clean
```

---

## 四、禁止行为

### 1. 禁止使用 IP 作为标识

```python
# ❌ 错误
mac = req.mac or req.ip

# ✅ 正确
if not req.mac:
    # 从 SADP 发现中查找
    return {"error": "未发现设备 MAC"}
```

### 2. 禁止创建无效 MAC

```python
# ❌ 错误
"mac": mac or ip

# ✅ 正确
if not mac or mac == ip:
    return  # 拒绝保存
```

### 3. 禁止重复存储

- 同一设备只能有一个存储目录（按 MAC）
- 不允许按 IP 创建额外目录

---

## 五、相关脚本

| 脚本 | 存储路径 | 说明 |
|------|----------|------|
| `device_path.py` | `data/devices/{mac}/` | 路径管理 |
| `function.py` | `data/devices/{mac}/function.json` | 功能测试 |
| `limit.py` | `data/devices/{mac}/limit.json` | 限位测试 |
| `speed.py` | `data/devices/{mac}/speed.json` | 速度测试 |
| `startup.py` | `data/reports/localhost.json` | 本机信息 |
| `ptz_manager.py` | `data/devices/{mac}/info.json` | 设备信息 |

---

## 六、验证检查

### 1. 检查 MAC 格式

```bash
# 查找无效 MAC
find data/devices -name "*.json" -exec grep -l '"mac": ".*\..*"' {} \;
```

### 2. 检查重复存储

```bash
# 列出所有设备目录
ls data/devices/
# 应该只有 MAC 格式的目录，不应有 IP 格式
```

---

**作者**: 雅痞张@南方天文  
**生成时间**: 2026-06-15
