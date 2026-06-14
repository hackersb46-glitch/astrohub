# livecam_hik.md - 海康摄像头实时预览

## 概述

海康威视 WASM SDK 实时视频流集成方法，使用官方 WebSocket 方式，无需 ffmpeg/HLS。

---

## 核心架构

```
浏览器 ←─ WebSocket(7681) ─→ 海康设备
  │                            │
  WASM SDK                 ISAPI接口
  │                            │
  Canvas渲染               视频流数据
```

---

## 文件依赖

```
/static/websdk/wasm/
├── webVideoCtrl.js          # 主SDK
├── jsPlugin/jsPlugin-3.0.0.min.js
├── jsPlugin/playctrl/PlayCtrlWasm/playctrlV3/
│   ├── Decoder.wasm         # 解码器
│   ├── Decoder.js
│   └── Decoder.worker.js
```

---

## 调用顺序

```
I_InitPlugin() → I_InsertOBJECTPlugin() → I_Login() → I_GetDevicePort() → I_StartRealPlay()
```

---

## 代码实现

### 1. 初始化

```html
<script src="/static/websdk/wasm/jquery.min.js"></script>
<script src="/static/websdk/wasm/webVideoCtrl.js"></script>
<div id="divPlugin" style="width:100%;height:250px"></div>
```

```javascript
function initWasm() {
    if (!WebVideoCtrl.I_SupportNoPlugin()) return;
    
    WebVideoCtrl.I_InitPlugin("100%", "100%", {
        bNoPlugin: true,
        iWndowType: 1,
        cbInitPluginComplete: function() {
            WebVideoCtrl.I_InsertOBJECTPlugin("divPlugin");
        }
    });
}
```

### 2. 登录

```javascript
var g_szDeviceIdentify2 = '';
var g_bLoggedIn2 = false;
var g_bPlaying2 = false;

function login(ip, port, username, password) {
    g_szDeviceIdentify2 = ip + '_' + port;
    
    WebVideoCtrl.I_Login(ip, 1, port, username, password, {
        timeout: 5000,
        success: function(xmlDoc) {
            g_bLoggedIn2 = true;
            
            // ⚠️ 同步调用，不是Promise
            var oPort = WebVideoCtrl.I_GetDevicePort(g_szDeviceIdentify2);
            console.log('WebSocket端口:', oPort.iWebSocketPort);  // 7681
            
            setTimeout(() => startPlay('sub'), 200);
        },
        error: function(status) {
            console.error('登录失败:', status);
        }
    });
}
```

### 3. 播放

```javascript
function startPlay(mode) {
    if (!g_bLoggedIn2) return;
    
    var iStreamType = (mode === 'main') ? 1 : 2;  // 1=主码流, 2=子码流
    
    WebVideoCtrl.I_StartRealPlay(g_szDeviceIdentify2, {
        iStreamType: iStreamType,
        iChannelID: 1,
        success: function() {
            g_bPlaying2 = true;
            console.log('播放成功');
        },
        error: function(status) {
            console.error('播放失败:', status);
        }
    });
}
```

### 4. 停止

```javascript
function stopPlay() {
    WebVideoCtrl.I_Stop({ success: () => g_bPlaying2 = false });
}
```

### 5. 尺寸调整

```javascript
function resize() {
    var el = document.getElementById('divPlugin');
    WebVideoCtrl.I_Resize(el.offsetWidth, el.offsetHeight);
}
```

---

## 关键点

| 项目 | 说明 |
|------|------|
| 传输方式 | WebSocket (端口7681)，非RTSP |
| 码流选择 | `sub`=子码流(流畅)，`main`=主码流(高清) |
| I_GetDevicePort | **同步函数**，不能`.then()` |
| 容器尺寸 | 不可见时为0x0，需调用`I_Resize()` |
| 变量暴露 | SDK函数需手动`window.xxx = xxx` |

---

## 端口

| 端口 | 用途 |
|------|------|
| 80 | HTTP/ISAPI |
| 554 | RTSP (WASM不用) |
| 7681 | WebSocket **视频流** |
| 8000 | 设备管理 |

---

## 禁止方案

- ❌ ffmpeg转码
- ❌ HLS推流
- ❌ RTSP直连

---

## 验证

```javascript
console.log('登录:', g_bLoggedIn2);
console.log('播放:', g_bPlaying2);
var oPort = WebVideoCtrl.I_GetDevicePort(g_szDeviceIdentify2);
console.log('WS端口:', oPort.iWebSocketPort);
```

---

**更新**: 2026-05-20