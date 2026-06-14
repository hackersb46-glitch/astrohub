function clickLogin2() {
    if (!window.connectedDevice || !window.connectedDevice.ip) {
        console.log('[WASM SDK] No device connected');
        if (typeof ptzLog === 'function') ptzLog('未连接设备，无法登录', 'warning');
        return;
    }
    console.log('[CLICKLOGIN2] Device IP: ' + window.connectedDevice.ip);
    if (typeof ptzLog === 'function') ptzLog('连接设备: ' + window.connectedDevice.ip, 'info');
    var szIP = window.connectedDevice.ip;
    var szPort = window.connectedDevice.port || 80;
    var szUsername = window.connectedDevice.username || 'admin';
    var szPassword = window.connectedDevice.password || '';
    g_szDeviceIdentify2 = szIP + '_' + szPort;
    console.log('[WASM SDK] Login: ' + szIP + ':' + szPort);
    
    // 博客方案：I_Login
    WebVideoCtrl.I_Login(szIP, 1, szPort, szUsername, szPassword, {
        timeout: 5000,
        success: function(xmlDoc) {
            g_bLoggedIn2 = true;
            g_szDeviceIdentify2 = szIP + '_' + szPort;
            console.log('[WASM SDK] Login success: ' + g_szDeviceIdentify2);
            if (typeof ptzLog === 'function') ptzLog('登录成功', 'success');
            
            // 博客方案：延迟500ms后执行 getDevicePort + getChannelInfo
            setTimeout(() => {
                // Step 1: getDevicePort
                var oPort = WebVideoCtrl.I_GetDevicePort(g_szDeviceIdentify2);
                console.log('[WASM SDK] GetDevicePort:', oPort);
                if (oPort) {
                    g_iRtspPort2 = oPort.iRtspPort || 554;
                    g_iWebSocketPort = oPort.iWebSocketPort || 7681;
                    if (typeof ptzLog === 'function') ptzLog('WebSocket端口: ' + g_iWebSocketPort, 'info');
                    document.cookie = 'webVideoCtrlProxyWs=' + szIP + ':' + g_iWebSocketPort + '; path=/';
                }
                
                // Step 2: getChannelInfo (返回 Promise)
                getChannelInfo().then(() => {
                    console.log('[WASM SDK] 获取通道结束');
                    // Step 3: clickStartRealPlay
                    clickStartRealPlay({ iStreamType: 2 });
                }).catch(err => {
                    console.log('[WASM SDK] 获取通道失败', err);
                    // 失败也尝试播放
                    g_iChannelID = 1;
                    clickStartRealPlay({ iStreamType: 2 });
                });
            }, 500);
        },
        error: function(status, xmlDoc) {
            console.error('[WASM SDK] Login failed:', status);
            g_bLoggedIn2 = false;
            if (typeof ptzLog === 'function') ptzLog('登录失败: ' + status, 'error');
        }
    });
}

// 博客方案：getChannelInfo 返回 Promise
function getChannelInfo() {
    var szDeviceIdentify = g_szDeviceIdentify2;
    console.log('[WASM SDK] getChannelInfo', szDeviceIdentify);
    
    return new Promise((resolve, reject) => {
        WebVideoCtrl.I_GetAnalogChannelInfo(szDeviceIdentify, {
            async: true,
            success: function(xmlDoc) {
                console.log('[WASM SDK] 获取模拟通道成功');
                var channels = [];
                var nodeList = xmlDoc.getElementsByTagName('VideoInputChannel');
                for (var i = 0; i < nodeList.length; i++) {
                    var id = nodeList[i].getElementsByTagName('id')[0]?.textContent || (i + 1);
                    var name = nodeList[i].getElementsByTagName('name')[0]?.textContent || ('通道' + id);
                    channels.push({ id: parseInt(id), name: name });
                }
                g_iChannelList = channels;
                g_iChannelID = channels.length > 0 ? channels[0].id : 1;
                console.log('[WASM SDK] Channels:', channels, 'Using ID:', g_iChannelID);
                if (typeof ptzLog === 'function') ptzLog('通道: ' + channels.length + '个', 'info');
                resolve();
            },
            error: function(status, xmlDoc) {
                console.log('[WASM SDK] 获取模拟通道失败:', status);
                g_iChannelID = 1;
                reject(status);
            }
        });
    });
}

// 博客方案：clickStartRealPlay
function clickStartRealPlay(options) {
    console.log('[WASM SDK] clickStartRealPlay', options);
    var iStreamType = options.iStreamType || 2;
    var iChannelID = g_iChannelID || 1;
    
    if (typeof ptzLog === 'function') ptzLog('开始播放: 码流=' + iStreamType + ', 通道=' + iChannelID, 'info');
    
    WebVideoCtrl.I_StartRealPlay(g_szDeviceIdentify2, {
        iStreamType: iStreamType,
        iChannelID: iChannelID,
        bZeroChannel: false,
        success: function() {
            g_bPlaying2 = true;
            console.log('[WASM SDK] 播放成功');
            if (typeof ptzLog === 'function') ptzLog('视频播放中', 'success');
        },
        error: function(status, xmlDoc) {
            console.error('[WASM SDK] 播放失败:', status);
            if (typeof ptzLog === 'function') ptzLog('播放失败: ' + status, 'error');
        }
    });
}

window.clickLogin2 = clickLogin2;
window.getChannelInfo = getChannelInfo;
window.clickStartRealPlay = clickStartRealPlay;