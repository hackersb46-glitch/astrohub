/**
 * WASM 播放器模块 - v1.1
 * 海康 WebSDK_noPlugin V3.4.0 + 媒体信息日志
 * 
 * 功能：
 * - 初始化 WebVideoCtrl SDK
 * - 与 ISAPI 登录同步
 * - 16:9 播放器容器
 * - 日志输出到主控台 mediaLogBox
 */

// ================================================================
// 全局状态
// ================================================================

const WasmPlayer = {
    // SDK 状态
    sdkReady: false,
    loggedIn: false,
    playing: false,
    
    // 设备信息
    deviceIdentify: '',  // IP_Port 格式
    deviceIp: '',
    devicePort: 80,
    rtspPort: 554,
    channel: 1,
    
    // 窗口索引
    wndIndex: 0,
    
    // 容器 ID
    containerId: 'divPlugin',
    
    // 日志输出目标
    logBoxId: 'mediaLogBox',
    
    // 日志缓冲区（最多保留 100 条）
    _logBuffer: [],
    _logMaxEntries: 100,
};

// ================================================================
// 日志功能
// wasmLog: 控制台日志（完整，不显示在 UI）
// mediaInfoLog: 媒体信息框日志（精简，只显示关键事件）
// ================================================================

// 需要显示在媒体信息框的关键消息关键词
const MEDIA_INFO_FILTERS = [
    /Initializing WASM SDK/i,
    /SDK initialized/i,
    /Browser supports no-plugin/i,
    /Login success/i,
    /Login failed/i,
    /Logout/i,
    /Preview started/i,
    /Preview stopped/i,
    /Starting preview/i,
    /Capture/i,
    /Recording started/i,
    /Recording stopped/i,
    /Starting recording/i,
];

function _isMediaInfo(msg) {
    for (let i = 0; i < MEDIA_INFO_FILTERS.length; i++) {
        if (MEDIA_INFO_FILTERS[i].test(msg)) return true;
    }
    // 所有 ERROR 级别都显示
    return false;
}

function _getMediaColor(level) {
    if (level === 'ERROR') return '#f85149';
    if (level === 'SUCCESS') return '#3fb950';
    return '#8b949e';
}

function wasmLog(level, message, data) {
    const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });
    const prefix = `[WASM ${timestamp}]`;
    
    const colors = {
        INFO: '#8b949e',
        WARN: '#d29922',
        ERROR: '#f85149',
        SUCCESS: '#3fb950',
        EVENT: '#58a6ff',
    };
    const color = colors[level] || '#8b949e';
    
    let text = `${prefix} [${level}] ${message}`;
    if (data) {
        try {
            text += ` | ${JSON.stringify(data)}`;
        } catch(e) {
            text += ` | ${String(data)}`;
        }
    }
    
    if (level === 'ERROR') console.error(text);
    else if (level === 'WARN') console.warn(text);
    else console.log(text);
    
    WasmPlayer._logBuffer.push({ level, message, data, timestamp: new Date().toISOString() });
    if (WasmPlayer._logBuffer.length > WasmPlayer._logMaxEntries) {
        WasmPlayer._logBuffer.shift();
    }
    
    // 媒体信息框：只显示关键事件
    if (_isMediaInfo(message) || level === 'ERROR') {
        const box = document.getElementById(WasmPlayer.logBoxId);
        if (box) {
            const timeStr = new Date().toLocaleTimeString('en-US', { hour12: false });
            const entry = document.createElement('div');
            entry.style.color = _getMediaColor(level);
            entry.style.fontSize = '11px';
            entry.style.fontFamily = 'monospace';
            entry.style.lineHeight = '1.4';
            entry.style.marginBottom = '2px';
            entry.textContent = timeStr + ' ' + message;
            box.appendChild(entry);
            
            while (box.children.length > WasmPlayer._logMaxEntries) {
                box.removeChild(box.firstChild);
            }
            
            box.scrollTop = box.scrollHeight;
        }
    }
}

function wasmClearLog() {
    const box = document.getElementById(WasmPlayer.logBoxId);
    if (box) {
        box.innerHTML = '';
        WasmPlayer._logBuffer = [];
        wasmLog('INFO', 'Log cleared');
    }
}

function wasmDumpStatus() {
    wasmLog('INFO', '===== Status Dump =====', {
        sdkReady: WasmPlayer.sdkReady,
        loggedIn: WasmPlayer.loggedIn,
        playing: WasmPlayer.playing,
        deviceIdentify: WasmPlayer.deviceIdentify,
        deviceIp: WasmPlayer.deviceIp,
        devicePort: WasmPlayer.devicePort,
        rtspPort: WasmPlayer.rtspPort,
        channel: WasmPlayer.channel,
        wndIndex: WasmPlayer.wndIndex,
    });
}

// ================================================================
// 初始化
// ================================================================

function wasmInit() {
    wasmLog('INFO', 'Initializing WASM SDK...');
    
    if (!window.WebVideoCtrl) {
        wasmLog('ERROR', 'WebVideoCtrl SDK not loaded');
        return false;
    }
    
    // JSPlugin openStream URL 解析不支持 localhost，hook WebSocket 替换
    if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
        var _origWS = window.WebSocket;
        window.WebSocket = function(url, protocols) {
            url = url.replace('localhost:', '127.0.0.1:');
            return protocols ? new _origWS(url, protocols) : new _origWS(url);
        };
        window.WebSocket.prototype = _origWS.prototype;
        Object.assign(window.WebSocket, _origWS);
        wasmLog('INFO', 'WebSocket hook: localhost -> 127.0.0.1');
    }
    
    const supported = WebVideoCtrl.I_SupportNoPlugin();
    if (!supported) {
        wasmLog('ERROR', 'Browser does not support no-plugin mode');
        return false;
    }
    wasmLog('SUCCESS', 'Browser supports no-plugin mode');
    
    WebVideoCtrl.I_InitPlugin('100%', '100%', {
        bWndFull: true,
        iPackageType: 2,
        iWndowType: 1,
        bNoPlugin: true,
        
        cbSelWnd: function(xmlDoc) {
            WasmPlayer.wndIndex = parseInt($(xmlDoc).find('SelectWnd').eq(0).text(), 10);
            wasmLog('EVENT', 'Window selected: ' + WasmPlayer.wndIndex);
        },
        
        cbDoubleClickWnd: function(iWndIndex, bFullScreen) {
            wasmLog('EVENT', 'Double click window ' + iWndIndex + (bFullScreen ? ' → fullscreen' : ' → normal'));
        },
        
        cbEvent: function(iEventType, iParam1, iParam2) {
            if (iEventType === 2) {
                wasmLog('EVENT', 'Playback ended, window ' + iParam1);
                WasmPlayer.playing = false;
            } else if (iEventType === -1) {
                wasmLog('WARN', 'Device disconnected: ' + iParam1);
                WasmPlayer.loggedIn = false;
            } else if (iEventType === 3001) {
                wasmLog('EVENT', 'Record stop event, window ' + iParam1);
            } else {
                wasmLog('EVENT', 'SDK event type=' + iEventType + ', param1=' + iParam1 + ', param2=' + iParam2);
            }
        },
        
        cbRemoteConfig: function() {
            wasmLog('INFO', 'Remote config closed');
        },
        
        cbInitPluginComplete: function() {
            WebVideoCtrl.I_InsertOBJECTPlugin(WasmPlayer.containerId);
            WasmPlayer.sdkReady = true;
            wasmLog('SUCCESS', 'SDK initialized, plugin inserted into: ' + WasmPlayer.containerId);
            
            window.dispatchEvent(new CustomEvent('wasm:ready'));
            wasmDumpStatus();
        },
        
        cbPluginErrorHandler: function(iWndIndex, iErrorCode, oError) {
            wasmLog('ERROR', 'Plugin error: window=' + iWndIndex + ', errorCode=' + iErrorCode, { errorCode: iErrorCode });
            
            const oWndInfo = WebVideoCtrl.I_GetWindowStatus(iWndIndex);
            if (oWndInfo != null) {
                WebVideoCtrl.I_Stop({
                    success: function() { wasmLog('INFO', 'Stopped after error'); },
                    error: function() { wasmLog('WARN', 'Stop failed after error'); }
                });
            }
        },
        
        cbPerformanceLack: function() {
            wasmLog('WARN', 'Performance lack warning');
        },
    });
    
    wasmLog('INFO', 'I_InitPlugin called, waiting for cbInitPluginComplete...');
    return true;
}

// ================================================================
// 登录/登出
// ================================================================

function wasmLogin(ip, port, username, password, protocol) {
    if (!WasmPlayer.sdkReady) {
        wasmLog('ERROR', 'SDK not ready, cannot login');
        return Promise.reject('SDK not ready');
    }
    
    port = port || 80;
    protocol = protocol || 1;
    const szDeviceIdentify = `${ip}_${port}`;
    
    WasmPlayer.deviceIp = ip;
    WasmPlayer.devicePort = port;
    
    wasmLog('INFO', `Attempting login: ${username}@${ip}:${port} (protocol=${protocol})`);
    
    return new Promise((resolve, reject) => {
        const iRet = WebVideoCtrl.I_Login(ip, protocol, port, username, password, {
            success: function(xmlDoc) {
                WasmPlayer.loggedIn = true;
                WasmPlayer.deviceIdentify = szDeviceIdentify;
                wasmLog('SUCCESS', 'Login success: ' + szDeviceIdentify);
                
                wasmGetChannelInfo();
                wasmGetDevicePort();
                
                window.dispatchEvent(new CustomEvent('wasm:login', { detail: { ip, port } }));
                wasmDumpStatus();
                resolve({ success: true, deviceIdentify: szDeviceIdentify });
            },
            error: function(status, xmlDoc) {
                WasmPlayer.loggedIn = false;
                wasmLog('ERROR', 'Login failed: status=' + status, { status });
                
                try {
                    const subStatusCode = $(xmlDoc).find('subStatusCode').eq(0).text();
                    const statusString = $(xmlDoc).find('statusString').eq(0).text();
                    if (subStatusCode || statusString) {
                        wasmLog('ERROR', `Login error detail: ${statusString} (${subStatusCode})`);
                    }
                } catch(e) {}
                
                reject({ success: false, status });
            }
        });
        
        if (iRet === -1) {
            wasmLog('INFO', 'Already logged in: ' + szDeviceIdentify);
            resolve({ success: true, deviceIdentify: szDeviceIdentify, already: true });
        }
    });
}

function wasmLogout() {
    if (!WasmPlayer.loggedIn || !WasmPlayer.deviceIdentify) {
        wasmLog('INFO', 'Not logged in, skip logout');
        return Promise.resolve({ success: true });
    }
    
    wasmLog('INFO', 'Logging out: ' + WasmPlayer.deviceIdentify);
    
    return new Promise((resolve) => {
        const wndSet = WebVideoCtrl.I_GetWndSet();
        wndSet.forEach(function(element) {
            if (element.szDeviceIdentify === WasmPlayer.deviceIdentify) {
                WebVideoCtrl.I_Stop({
                    iIndex: element.iIndex,
                    success: function() { wasmLog('INFO', 'Stopped window ' + element.iIndex); },
                    error: function() { wasmLog('WARN', 'Stop window ' + element.iIndex + ' failed'); }
                });
            }
        });
        
        const iRet = WebVideoCtrl.I_Logout(WasmPlayer.deviceIdentify);
        if (iRet === 0) {
            wasmLog('SUCCESS', 'Logout success');
            WasmPlayer.loggedIn = false;
            WasmPlayer.playing = false;
            WasmPlayer.deviceIdentify = '';
            WasmPlayer.deviceIp = '';
            
            window.dispatchEvent(new CustomEvent('wasm:logout'));
            wasmDumpStatus();
            resolve({ success: true });
        } else {
            wasmLog('ERROR', 'Logout failed, ret=' + iRet);
            resolve({ success: false });
        }
    });
}

// ================================================================
// 通道/端口信息
// ================================================================

function wasmGetChannelInfo() {
    if (!WasmPlayer.deviceIdentify) return;
    
    wasmLog('INFO', 'Getting channel info...');
    
    WebVideoCtrl.I_GetAnalogChannelInfo(WasmPlayer.deviceIdentify, {
        async: false,
        success: function(xmlDoc) {
            const channels = $(xmlDoc).find('VideoInputChannel');
            wasmLog('SUCCESS', 'Analog channels: ' + channels.length);
            
            channels.each(function(i) {
                const id = $(this).find('id').eq(0).text();
                const name = $(this).find('name').eq(0).text() || ('Camera ' + (i < 9 ? '0' + (i + 1) : (i + 1)));
                wasmLog('INFO', `Channel ${id}: ${name}`);
            });
            
            if (channels.length > 0) {
                WasmPlayer.channel = parseInt($(channels[0]).find('id').eq(0).text(), 10) || 1;
            }
        },
        error: function(status) {
            wasmLog('ERROR', 'Get analog channel info failed: status=' + status, { status });
        }
    });
}

function wasmGetDevicePort() {
    if (!WasmPlayer.deviceIdentify) return;
    
    const oPort = WebVideoCtrl.I_GetDevicePort(WasmPlayer.deviceIdentify);
    if (oPort != null) {
        WasmPlayer.devicePort = oPort.iDevicePort;
        WasmPlayer.rtspPort = oPort.iRtspPort;
        wasmLog('SUCCESS', `Device port: ${WasmPlayer.devicePort}, RTSP port: ${WasmPlayer.rtspPort}`);
    } else {
        wasmLog('WARN', 'Cannot get device port info');
    }
}

// ================================================================
// 预览控制
// ================================================================

function wasmStartRealPlay(channel, streamType, useProxy) {
    if (!WasmPlayer.loggedIn || !WasmPlayer.deviceIdentify) {
        wasmLog('ERROR', 'Not logged in, cannot start preview');
        return Promise.reject('Not logged in');
    }
    
    channel = channel || WasmPlayer.channel || 1;
    streamType = streamType || 2;
    useProxy = useProxy !== undefined ? useProxy : true;
    
    wasmLog('INFO', `Starting preview: channel=${channel}, streamType=${streamType}, proxy=${useProxy}`);
    
    return new Promise((resolve, reject) => {
        const oWndInfo = WebVideoCtrl.I_GetWindowStatus(WasmPlayer.wndIndex);
        
        const startPlay = () => {
            WebVideoCtrl.I_StartRealPlay(WasmPlayer.deviceIdentify, {
                iRtspPort: WasmPlayer.rtspPort,
                iStreamType: streamType,
                iChannelID: channel,
                bZeroChannel: false,
                bProxy: useProxy,
                
                success: function() {
                    WasmPlayer.playing = true;
                    wasmLog('SUCCESS', `Preview started: channel=${channel}, streamType=${streamType}`);
                    window.dispatchEvent(new CustomEvent('wasm:playing', { detail: { channel, streamType } }));
                    wasmDumpStatus();
                    resolve({ success: true });
                },
                error: function() {
                    const args = Array.from(arguments);
                    wasmLog('ERROR', `Preview failed: args=${JSON.stringify(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)))}`, { args });
                    
                    try {
                        const subStatusCode = $(xmlDoc).find('subStatusCode').eq(0).text();
                        wasmLog('ERROR', `Error detail: ${subStatusCode}`);
                    } catch(e) {}
                    
                    reject({ success: false, message: 'Preview failed' });
                }
            });
        };
        
        if (oWndInfo != null) {
            wasmLog('INFO', 'Already playing, stopping first...');
            WebVideoCtrl.I_Stop({
                success: startPlay,
                error: function() {
                    wasmLog('WARN', 'Stop failed before start, retrying...');
                    startPlay();
                }
            });
        } else {
            startPlay();
        }
    });
}

function wasmStopRealPlay() {
    if (!WasmPlayer.playing) {
        wasmLog('INFO', 'Not playing, skip stop');
        return Promise.resolve({ success: true, already: true });
    }
    
    wasmLog('INFO', 'Stopping preview...');
    
    return new Promise((resolve) => {
        const oWndInfo = WebVideoCtrl.I_GetWindowStatus(WasmPlayer.wndIndex);
        if (oWndInfo != null) {
            WebVideoCtrl.I_Stop({
                success: function() {
                    WasmPlayer.playing = false;
                    wasmLog('SUCCESS', 'Preview stopped');
                    wasmDumpStatus();
                    resolve({ success: true });
                },
                error: function() {
                    wasmLog('ERROR', 'Stop failed');
                    resolve({ success: false });
                }
            });
        } else {
            wasmLog('INFO', 'No active preview to stop');
            resolve({ success: true, already: true });
        }
    });
}

// ================================================================
// 截图/录像 (v7.110: 恢复WASM录制)
// ================================================================

function wasmCapturePic(filename) {
    if (!WasmPlayer.playing) {
        wasmLog('ERROR', 'Not playing, cannot capture');
        return Promise.reject('Not playing');
    }
    const szPicName = filename || `capture_${Date.now()}`;
    wasmLog('INFO', 'Capturing: ' + szPicName);
    return WebVideoCtrl.I2_CapturePic(szPicName, {})
        .then(() => {
            wasmLog('SUCCESS', 'Capture success: ' + szPicName);
            return { success: true, filename: szPicName };
        })
        .catch((e) => {
            wasmLog('ERROR', 'Capture failed: ' + e);
            return { success: false, error: e };
        });
}

function wasmStartRecord(filename) {
    if (!WasmPlayer.playing) {
        wasmLog('ERROR', 'Not playing, cannot record');
        return Promise.reject('Not playing');
    }
    const szFileName = filename || `record_${Date.now()}`;
    wasmLog('INFO', 'Starting recording: ' + szFileName);
    return new Promise((resolve, reject) => {
        WebVideoCtrl.I_StartRecord(szFileName, {
            bDateDir: true,
            success: function() {
                wasmLog('SUCCESS', 'Recording started: ' + szFileName);
                resolve({ success: true, filename: szFileName });
            },
            error: function() {
                wasmLog('ERROR', 'Start record failed');
                reject({ success: false });
            }
        });
    });
}

function wasmStopRecord() {
    wasmLog('INFO', 'Stopping recording...');
    return new Promise((resolve) => {
        WebVideoCtrl.I_StopRecord({
            success: function() {
                wasmLog('SUCCESS', 'Recording stopped');
                resolve({ success: true });
            },
            error: function() {
                wasmLog('ERROR', 'Stop record failed');
                resolve({ success: false });
            }
        });
    });
}

// ================================================================
// 尺寸调整
// ================================================================

function wasmResize(width, height) {
    if (WasmPlayer.sdkReady) {
        WebVideoCtrl.I_Resize(width, height);
        wasmLog('INFO', `Resized: ${Math.round(width)}×${Math.round(height)}`);
    }
}

function wasmObserveResize(containerId) {
    const container = document.getElementById(containerId || WasmPlayer.containerId);
    if (!container) {
        wasmLog('ERROR', 'Container not found: ' + containerId);
        return;
    }
    
    const resizeObserver = new ResizeObserver(entries => {
        for (const entry of entries) {
            const { width, height } = entry.contentRect;
            if (width > 0 && height > 0) {
                wasmResize(width, height);
            }
        }
    });
    
    resizeObserver.observe(container);
    wasmLog('INFO', 'ResizeObserver attached to: ' + containerId);
}

// ================================================================
// 导出
// ================================================================

window.WasmPlayer = WasmPlayer;
window.wasmInit = wasmInit;
window.wasmLogin = wasmLogin;
window.wasmLogout = wasmLogout;
window.wasmStartRealPlay = wasmStartRealPlay;
window.wasmStopRealPlay = wasmStopRealPlay;
window.wasmCapturePic = wasmCapturePic;
window.wasmStartRecord = wasmStartRecord;
window.wasmStopRecord = wasmStopRecord;
window.wasmResize = wasmResize;
window.wasmObserveResize = wasmObserveResize;
window.wasmLog = wasmLog;
window.wasmClearLog = wasmClearLog;
window.wasmDumpStatus = wasmDumpStatus;

wasmLog('INFO', 'WASM Player module loaded (v1.1)');
