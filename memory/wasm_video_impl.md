# 海康 WASM SDK 视频流实现方式

**日期**: 2026-05-20
**设备**: iDS-2DF8C832IXS-A (192.168.5.72)
**SDK版本**: websdk3.220200429

---

## 一、整体架构

```
浏览器 ←── WebSocket (7681) ──→ 海康设备
   │                              │
   ↓                              ↓
WASM SDK                    ISAPI 接口
   │                              │
   ↓                              ↓
Canvas 渲染                 视频流数据
```

**关键点**：
- 视频通过 **WebSocket** 传输，不是 RTSP
- SDK 自动获取 WebSocket 端口（ISAPI `/ISAPI/System/deviceInfo`)
- 播放器用 **Canvas** 渲染，不需要浏览器插件

---

## 二、SDK 文件结构

```
src/web/static/websdk/wasm/
├── webVideoCtrl.js          # 主 SDK 文件
├── jsPlugin/
│   ├── jsPlugin-3.0.0.min.js    # 播放器核心
│   └── playctrl/
│       └── PlayCtrlWasm/
│           ├── playctrlV3/
│           │   ├── Decoder.js
│           │   ├── Decoder.wasm   # WASM 解码器
│           │   └── Decoder.worker.js
│           └── wasmplayer.min.js
├── jquery.min.js
├── encryption/              # 加密模块
├── transform/               # 转换模块
```

---

## 三、初始化流程（官方方式）

### Step 1: 加载 SDK

```html
<!-- HTML 头部引入 -->
<script src="/static/websdk/wasm/jquery.min.js"></script>
<script src="/static/websdk/wasm/webVideoCtrl.js"></script>

<!-- 视频容器 -->
<div id="divPlugin" style="width:100%;height:250px"></div>
```

### Step 2: 初始化播放器

```javascript
function initWasm() {
    // 检查浏览器支持
    if (!WebVideoCtrl.I_SupportNoPlugin()) {
        console.error('浏览器不支持 WASM 模式');
        return;
    }
    
    // 初始化 SDK
    WebVideoCtrl.I_InitPlugin("100%", "100%", {
        bWndFull: true,           // 允许全屏
        iPackageType: 2,          // 包类型
        iWndowType: 1,            // 单窗口
        bNoPlugin: true,          // 无插件模式（WASM）
        
        // 事件回调
        cbEvent: function(iEventType, iParam1, iParam2) {
            console.log('[WASM] Event:', iEventType, iParam1, iParam2);
        },
        
        // 初始化完成回调
        cbInitPluginComplete: function() {
            console.log('[WASM] 初始化完成');
            // 插入播放器到容器
            WebVideoCtrl.I_InsertOBJECTPlugin("divPlugin");
        },
        
        // 错误回调
        cbPluginErrorHandler: function(iWndIndex, iErrorCode, oError) {
            console.error('[WASM] 播放器错误:', iErrorCode);
        },
        
        // 性能警告
        cbPerformanceLack: function() {
            console.warn('[WASM] 性能不足');
        }
    });
}

// 页面加载时初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initWasm);
} else {
    initWasm();  // 立即执行
}
```

---

## 四、登录流程

### Step 1: 准备设备信息

```javascript
// 全局变量（必须在 window 上暴露）
window.connectedDevice = {
    ip: '192.168.5.72',
    port: 80,
    username: 'admin',
    password: 'xxx',
    model: 'iDS-2DF8C832IXS-A',
    online: true
};

// SDK 内部变量
var g_szDeviceIdentify2 = '';   // 设备标识 (IP_Port)
var g_bLoggedIn2 = false;       // 登录状态
var g_bPlaying2 = false;        // 播放状态
var g_iRtspPort2 = 554;         // RTSP 端口（备用）
var g_iWndIndex2 = 0;           // 窗口索引
```

### Step 2: 执行登录

```javascript
function clickLogin2() {
    // 检查设备信息
    if (!window.connectedDevice || !window.connectedDevice.ip) {
        console.error('[WASM] 无设备连接');
        return;
    }
    
    var szIP = window.connectedDevice.ip;
    var szPort = window.connectedDevice.port || 80;
    var szUsername = window.connectedDevice.username || 'admin';
    var szPassword = window.connectedDevice.password || '';
    
    // 设备标识
    g_szDeviceIdentify2 = szIP + '_' + szPort;
    
    console.log('[WASM] 登录:', szIP + ':' + szPort);
    
    // 调用 SDK 登录
    WebVideoCtrl.I_Login(szIP, 1, szPort, szUsername, szPassword, {
        timeout: 5000,
        
        // 登录成功
        success: function(xmlDoc) {
            g_bLoggedIn2 = true;
            console.log('[WASM] 登录成功:', g_szDeviceIdentify2);
            
            // ⚠️ 关键：I_GetDevicePort 是同步函数！
            var oPort = WebVideoCtrl.I_GetDevicePort(g_szDeviceIdentify2);
            console.log('[WASM] 端口信息:', oPort);
            
            if (oPort) {
                // WebSocket 端口（视频流用这个）
                console.log('[WASM] WebSocket端口:', oPort.iWebSocketPort);
                console.log('[WASM] RTSP端口:', oPort.iRtspPort);
            }
            
            // 启动视频流
            setTimeout(function() {
                startConsoleStream2('sub');  // 'sub' = 子码流, 'main' = 主码流
            }, 200);
        },
        
        // 登录失败
        error: function(status, xmlDoc) {
            console.error('[WASM] 登录失败:', status);
            g_bLoggedIn2 = false;
        }
    });
}

// 暴露到 window
window.clickLogin2 = clickLogin2;
```

---

## 五、视频流启动

### Step 1: 检查状态

```javascript
function startConsoleStream2(mode) {
    // mode: 'sub' = 子码流(流畅), 'main' = 主码流(高清)
    
    console.log('[STREAM] 启动视频流, mode=', mode);
    
    // 检查设备
    if (!window.connectedDevice || !window.connectedDevice.ip) {
        console.error('[STREAM] 无设备');
        return;
    }
    
    // 检查登录状态
    if (!g_bLoggedIn2) {
        console.warn('[STREAM] 未登录，先登录');
        clickLogin2();
        return;
    }
    
    // 码流类型
    var iStreamType = (mode === 'main') ? 1 : 2;  // 1=主码流, 2=子码流
    
    // 检查当前窗口状态
    var oWndInfo = WebVideoCtrl.I_GetWindowStatus(g_iWndIndex2);
    
    // 启动播放
    var doStart = function() {
        console.log('[WASM] 开始实时播放');
        
        WebVideoCtrl.I_StartRealPlay(g_szDeviceIdentify2, {
            // ⚠️ 不要传 iRtspPort！SDK 自动用 WebSocket
            iStreamType: iStreamType,      // 码流类型
            iChannelID: 1,                 // 通道ID（单摄像头=1）
            bZeroChannel: false,           // 非零通道
            
            success: function() {
                g_bPlaying2 = true;
                console.log('[WASM] 实时播放启动成功');
            },
            
            error: function(status, xmlDoc) {
                console.error('[WASM] 播放失败:', status);
                g_bPlaying2 = false;
            }
        });
    };
    
    // 如果已有播放，先停止
    if (oWndInfo != null) {
        WebVideoCtrl.I_Stop({
            success: function() { doStart(); },
            error: function() { doStart(); }
        });
    } else {
        doStart();
    }
}

// 暴露到 window
window.startConsoleStream2 = startConsoleStream2;
```

### Step 2: 停止播放

```javascript
function stopConsoleStream2() {
    if (!g_bPlaying2) return;
    
    var oWndInfo = WebVideoCtrl.I_GetWindowStatus(g_iWndIndex2);
    if (oWndInfo != null) {
        WebVideoCtrl.I_Stop({
            success: function() {
                g_bPlaying2 = false;
                console.log('[WASM] 播放已停止');
            }
        });
    }
}

window.stopConsoleStream2 = stopConsoleStream2;
```

---

## 六、容器尺寸调整

**问题**：播放器在不可见页面初始化时尺寸为 0x0

**解决**：切换到可见页面时调用 `I_Resize`

```javascript
// 切换到主控台页面时
function onSwitchToConsole() {
    // 刷新设备列表
    refreshPtzDeviceList();
    loadWasmDevices();
    
    // 调整播放器尺寸
    setTimeout(function() {
        var container = document.getElementById('divPlugin');
        if (container && window.WebVideoCtrl) {
            WebVideoCtrl.I_Resize(container.offsetWidth, container.offsetHeight);
            console.log('[WASM] 尺寸调整:', container.offsetWidth, container.offsetHeight);
        }
    }, 100);
}
```

---

## 七、关键函数清单

| 函数 | 类型 | 用途 |
|------|------|------|
| `I_SupportNoPlugin()` | 检查 | 检查浏览器支持 |
| `I_InitPlugin()` | 初始化 | 初始化 SDK |
| `I_InsertOBJECTPlugin()` | 初始化 | 插入播放器到容器 |
| `I_Login()` | 异步 | 登录设备 |
| `I_GetDevicePort()` | **同步** | 获取端口信息 |
| `I_StartRealPlay()` | 异步 | 启动实时播放 |
| `I_Stop()` | 异步 | 停止播放 |
| `I_Resize()` | 同步 | 调整播放器尺寸 |
| `I_GetWindowStatus()` | 同步 | 获取窗口状态 |

---

## 八、常见错误及解决

### 错误 1: I_GetDevicePort 返回 undefined

**原因**：错误地用 `.then()` 当 Promise 调用

**错误代码**：
```javascript
WebVideoCtrl.I_GetDevicePort(id).then(function(oPort) { ... });
```

**正确代码**：
```javascript
var oPort = WebVideoCtrl.I_GetDevicePort(id);  // 同步调用
```

---

### 错误 2: 播放器尺寸 0x0

**原因**：容器在不可见页面初始化

**解决**：切换页面时调用 `I_Resize()`

---

### 错误 3: g_bLoggedIn2 = false 但登录成功

**原因**：变量作用域问题

**解决**：
- `connectedDevice` 和 `window.connectedDevice` 是两个不同变量
- SDK 函数需要在第二个 `<script>` block 手动暴露到 window

---

### 错误 4: 点击连接后无画面

**原因**：`clickLogin2` 检查 `window.connectedDevice` 但 `connectDevice` 只设置局部变量

**解决**：`connectDevice` 成功后同时设置：
```javascript
connectedDevice = window.connectedDevice = { ... };
```

---

## 九、端口说明

| 端口 | 用途 | 说明 |
|------|------|------|
| 80 | HTTP/ISAPI | 设备管理、API 调用 |
| 554 | RTSP | ⚠️ WASM 模式不用这个 |
| 7681 | WebSocket | **视频流传输端口** |
| 7682 | WebSockets | WebSocket SSL（HTTPS 时用） |
| 8000 | Device Port | 设备管理端口 |

---

## 十、完整调用顺序

```
1. 加载 SDK (webVideoCtrl.js)
   ↓
2. I_InitPlugin() - 初始化
   ↓
3. I_InsertOBJECTPlugin("divPlugin") - 插入播放器
   ↓
4. I_Login(ip, port, username, password) - 登录设备
   ↓
5. I_GetDevicePort(deviceId) - 获取端口（同步）
   ↓
6. I_StartRealPlay(deviceId, {iStreamType: 2}) - 启动子码流
   ↓
7. Canvas 渲染实时画面
```

---

## 十一、禁止的方案

| 方案 | 原因 |
|------|------|
| ❌ ffmpeg 转码 | 非官方方式，绕弯路 |
| ❌ HLS 推流 | 非官方方式，绕弯路 |
| ❌ RTSP 直接播放 | WASM SDK 用 WebSocket，不是 RTSP |
| ❌ 自建视频服务器 | 官方 SDK 已提供完整方案 |

---

## 十二、验证方法

```javascript
// 检查 SDK 加载
console.log('WebVideoCtrl:', typeof WebVideoCtrl);

// 检查登录状态
console.log('g_bLoggedIn2:', g_bLoggedIn2);

// 检查播放状态
console.log('g_bPlaying2:', g_bPlaying2);

// 检查设备信息
console.log('connectedDevice:', window.connectedDevice);

// 检查端口信息
var oPort = WebVideoCtrl.I_GetDevicePort(g_szDeviceIdentify2);
console.log('WebSocket端口:', oPort.iWebSocketPort);
```

---

**最后更新**: 2026-05-20 19:12