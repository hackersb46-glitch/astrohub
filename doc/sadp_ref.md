# SADP SDK 开发参考文档

> 来源: M1_method.csv P2 方法技术总结 + 官方 SDK 文档
> 目标: 通过 SADP SDK 实现设备发现 + IP 修改

---

## P2 总体概览

**目标**: 通过 SADP 广播发现设备，以 MAC 为唯一标识，支持多台设备 IP 修改。
**实现方式**: 使用 DLL（Sadp.dll）实现，禁止使用官方示例 exe。

---

## P2.1 SADP 设备扫描

**功能**: SADP 广播扫描，10 秒内发现设备列表（MAC/IP/型号/SN）

**SDK 调用流程**:
```
SADP_Start_V40 → 注册回调 → 等待设备列表 → SADP_SendInquiry() → SADP_Stop()
```

**关键 API**:
- `SADP_Start_V40(callback, bInstallNPF, pUser)` — 启动发现服务
- `SADP_SendInquiry()` — 发送广播探测报文
- `SADP_Stop()` — 停止发现服务
- 回调类型: `DEVICE_FIND_CALLBACK_V40` 接收 `SADP_DEVICE_INFO_V40` 结构体

**Python 示例**:
```python
import ctypes
SDK_DIR = r'D:\astro_py\astro_hub\src\core'
sadp = ctypes.WinDLL(os.path.join(SDK_DIR, 'Sadp.dll'))

# V40 callback
CB_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)
dev_list = []

def dev_cb(lpDi, userData):
    addr = int(lpDi)
    pV40 = ctypes.cast(addr, ctypes.POINTER(V40))
    d = pV40.contents
    dev_list.append({...})

sadp.SADP_Start_V40(CB_TYPE(dev_cb), 0, None)
# 等待设备发现，定期 SADP_SendInquiry()
sadp.SADP_Stop()
```

---

## P2.2 设备型号识别

**功能**: 以 MAC+型号匹配设备，判断是否已记录

**逻辑**:
- MAC 相同 + 型号匹配 = 已记录设备
- MAC 不同 = 新设备

```python
recorded = json.load(open('config.json'))
new_devices = [d for d in dev_list if d['mac'] not in [r['mac'] for r in recorded]]
```

---

## P2.3 激活状态判断

**功能**: 通过 SADP API 查询设备状态，判断是否已激活

**关键字段**: `SADP_DEVICE_INFO_V40.struSadpDeviceInfo.byActivated`
- `1` = 已激活
- `0` = 未激活

```python
is_active = pV40.contents.struSadpDeviceInfo.byActivated == 1
```

---

## P2.4 IP 可达性判断

**功能**: PING 目标设备判断是否可达

```python
import subprocess
r = subprocess.run(['ping', '-n', '1', '-w', '500', ip], capture_output=True)
reachable = r.returncode == 0
```

**逻辑**:
- `reachable=True` → 跳过 P2.5（不需要修改 IP）
- `reachable=False` → 执行 P2.5（修改 IP）

---

## P2.5 修改设备 IP ⭐ 核心

**功能**: 使用 SADP SDK 修改设备 IP/网关，目标 IP 默认同网段.64（支持手动输入）

**SDK 调用流程**:
1. 检查目标 IP 是否被占用: `p2_check_reachable(new_ip)`
2. 构造 `SADP_DEV_NET_PARAM`（IP/子网掩码/网关/端口）
3. 调用 `SADP_ModifyDeviceNetParam_V40(mac, password, net_param, ret_param, sizeof(ret_param))`
4. 修改成功后 `time.sleep(10)` → 返回 P2.1 重新扫描

**关键 API**:
```c
int SADP_ModifyDeviceNetParam_V40(
    const char* sMAC,                        // MAC 地址（大写+横杠，如 "24-0F-9B-76-41-93"）
    const char* sPassword,                   // 设备密码
    const SADP_DEV_NET_PARAM* lpNetParam,    // 网络参数结构体
    SADP_DEV_RET_NET_PARAM* lpRetNetParam,   // 返回参数结构体
    int nSize                                // sizeof(SADP_DEV_RET_NET_PARAM)
);
```

**结构体定义**:
```c
// SADP_DEV_NET_PARAM
typedef struct {
    char szIPv4Address[16];      // 目标 IPv4 地址
    char szIPv4SubNetMask[16];   // 子网掩码
    char szIPv4Gateway[16];      // 网关
    char szIPv6Address[128];     // IPv6 地址（通常为全 0）
    char szIPv6Gateway[128];     // IPv6 网关（通常为全 0）
    unsigned short wPort;        // 设备端口（从发现信息获取）
    unsigned char byIPv6MaskLen; // IPv6 掩码长度（0 表示未使用）
    unsigned char byDhcpEnable;  // DHCP 开关（0=禁用，1=启用）
    unsigned short wHttpPort;    // HTTP 端口
    unsigned int dwSDKOverTLSPort; // TLS 端口
    char byRes[120];             // 保留字段
} SADP_DEV_NET_PARAM;

// SADP_DEV_RET_NET_PARAM
typedef struct {
    unsigned char byRetryModifyTime;    // 重试修改次数
    unsigned char bySurplusLockTime;    // 剩余锁定时间
    char byRes[126];                    // 保留字段
} SADP_DEV_RET_NET_PARAM;
```

**错误码定义**（来自 Sadp.h）:
| 错误码 | 常量 | 含义 |
|--------|------|------|
| 2005 | `SADP_PARAMETER_ERROR` | 参数错误 |
| 2006 | `SADP_OPEN_ADAPTER_FAIL_ERROR` | 打开适配器失败 |
| 2010 | `SADP_NPF_INSTALL_ERROR` | NPF 驱动安装失败 |
| 2024 | `SADP_PASSWORD_ERROR` | 密码错误 |
| 2045 | `SADP_AES_ENCRYPT_ERROR` | AES 加密失败 |

**Python 实现要点**:
```python
# 构造网络参数
net_param = SADP_DEV_NET_PARAM()
ctypes.memset(ctypes.byref(net_param), 0, ctypes.sizeof(net_param))
net_param.szIPv4Address = new_ip.encode("utf-8")
net_param.szIPv4SubNetMask = subnet_mask.encode("utf-8")
net_param.szIPv4Gateway = gateway.encode("utf-8")
net_param.szIPv6Address = b"\x00" * 128
net_param.szIPv6Gateway = b"\x00" * 128
net_param.byIPv6MaskLen = 0
net_param.byDhcpEnable = 0
net_param.wHttpPort = 80
net_param.wPort = device_sdk_port  # 从发现信息获取
net_param.dwSDKOverTLSPort = 0

# 返回参数
ret_param = SADP_DEV_RET_NET_PARAM()
ctypes.memset(ctypes.byref(ret_param), 0, ctypes.sizeof(ret_param))

# 调用
result = sadp.SADP_ModifyDeviceNetParam_V40(
    mac.encode("utf-8"),
    password.encode("utf-8"),
    ctypes.byref(net_param),
    ctypes.byref(ret_param),
    ctypes.sizeof(ret_param)
)
```

**MAC 格式关键发现**:
- SDK 回调返回的 MAC 格式为 **大写+横杠**（如 `24-0F-9B-76-41-93`）
- 官方 C demo 中 `m_smac` 直接从 SDK 回调取值，**不做任何转换**
- DLL 调用时必须使用 **大写+横杠** 格式

**重要注意事项**:
- `SADP_ModifyDeviceNetParam_V40` 必须在 `SADP_Start_V40` 之后调用
- 目标 IP 已被占用时，提示用户更换
- 修改成功后必须等待 10 秒再重新扫描
- IP 不可达时循环: P2.5 修改 → 等待 10s → 返回 P2.1 重新扫描，实现自动循环

---

## P2.6 保存设备凭证到 config

**功能**: 以 MAC 为唯一标识，保存设备信息到 device_config.json

**保存内容**: 型号、MAC、账号、密码（掩码）、激活状态、IP、子网掩码、网关

```python
device_entry = {
    'mac': mac, 'ip': ip, 'model': model,
    'username': 'admin', 'password': pwd
}
json.dump(device_entry, open('device_config.json','w'), indent=2, ensure_ascii=False)
```

---

## P2.7 已记录设备自动配置

**功能**: MAC 匹配 + Ping 验证可达 + SADP 修改 IP，临时自动配置

```python
for dev in devices:
    if dev['mac'] == target_mac and ping(dev['ip']):
        sadp.modify_ip(dev['mac'], new_ip)
```

---

## 约束规则

1. **禁止修改本机网络配置**
2. **禁止全网段 IP 扫描**
3. **纯 DLL 方案，不调用 exe**
4. **必须读取官方文档，不要猜测**
5. **每次尝试失败后，必须杀进程释放 DLL 等资源**
6. **设备与主机在同一网段，直接可达，不需要排查网络连通性**
