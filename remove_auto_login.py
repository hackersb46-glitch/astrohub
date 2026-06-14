import re

html_path = r"D:\astro_py\astro_hub\src\web\index.html"

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and remove the entire auto-login block
# Start: "// Auto-login DISABLED"
# End: "});" before "refreshPtzDeviceList"

old_block = '''// Auto-login DISABLED: Login happens when user clicks Connect button
// console.log('[AUTO-LOGIN] allDevices:', allDevices);
// var autoDev = allDevices.find(function(d) { return d.has_credentials; });
                console.log('[AUTO-LOGIN] autoDev:', autoDev, 'window.connectedDevice:', window.connectedDevice);
                if (autoDev && !window.connectedDevice) {
                    console.log('[AUTO-LOGIN] Fetching credentials for:', autoDev.ip);
                    // Fetch credentials from PTZ manager API
                    apiGet('/api/v1/ptz/devices/' + autoDev.ip + '/credentials').then(function(creds) {
                        console.log('[AUTO-LOGIN] Credentials response:', creds);
                        if (creds && creds.success) {
                            console.log('[AUTO-LOGIN] Setting connectedDevice...');
                            window.connectedDevice = {
                                ip: autoDev.ip,
                                model: autoDev.model || '',
                                name: autoDev.name || autoDev.device_name || '',
                                mac: autoDev.mac || '',
                                username: creds.username || 'admin',
                                password: creds.password || '',
                                port: creds.port || 80,
                                online: true
                            };
                            addLog('info', 'Auto-detected device with credentials: ' + window.connectedDevice.ip);
                            // Only call onPtzDeviceChange if DOM elements exist (PTZ page)
                            if (typeof onPtzDeviceChange === 'function' && document.getElementById('ptzControlArea')) {
                                try { onPtzDeviceChange(); } catch(e) { console.warn('onPtzDeviceChange error:', e); }
                            }
                            // Auto-login to WASM SDK for video streaming (delayed to ensure function defined)
                            console.log('[AUTO-LOGIN] Scheduling setTimeout for WASM login');
                            setTimeout(function() {
                                try {
                                    console.log('[AUTO-LOGIN] setTimeout callback executing');
                                    console.log('[AUTO-LOGIN] window.connectedDevice =', window.connectedDevice);
                                    if (!window.connectedDevice) {
                                        console.log('[AUTO-LOGIN] ERROR: connectedDevice not set');
                                        return;
                                    }
                                    console.log('[AUTO-LOGIN] Direct WASM login');
                                    // Direct WASM SDK login
                                    var szIP = window.connectedDevice.ip;
                                    var szPort = window.connectedDevice.port || 80;
                                    var szUsername = window.connectedDevice.username || 'admin';
                                    var szPassword = window.connectedDevice.password || '';
                                    window.g_szDeviceIdentify2 = szIP + '_' + szPort;
                                    console.log('[AUTO-LOGIN] I_Login params: IP='+szIP+' port='+szPort+' user='+szUsername);
                                    WebVideoCtrl.I_Login(szIP, 1, szPort, szUsername, szPassword, {
                                        timeout: 8000,
                                        success: function(xmlDoc) {
                                            window.g_bLoggedIn2 = true;
                                            console.log('[AUTO-LOGIN] WASM Login SUCCESS');
                                            // Get RTSP port and start playback
                                            var portResult = WebVideoCtrl.I_GetDevicePort(window.g_szDeviceIdentify2);
                                            if (portResult && portResult.then) {
                                                portResult.then(function(oPort) {
                                                    if (oPort) window.g_iRtspPort2 = oPort.iRtspPort || 554;
                                                });
                                            }
                                            // Start video playback immediately after login success
                                            console.log('[AUTO-LOGIN] Starting video playback immediately');
                                            if (typeof startConsoleStream2 === 'function') {
                                                console.log('[AUTO-LOGIN] startConsoleStream2 function exists, calling');
                                                startConsoleStream2('sub');
                                            } else {
                                                console.log('[AUTO-LOGIN] ERROR: startConsoleStream2 not found');
                                                console.log('[AUTO-LOGIN] typeof startConsoleStream2 =', typeof startConsoleStream2);
                                                console.log('[AUTO-LOGIN] window.startConsoleStream2 =', typeof window.startConsoleStream2);
                                            }
                                        },
                                        error: function(status) {
                                            window.g_bLoggedIn2 = false;
                                            console.log('[AUTO-LOGIN] WASM Login FAILED: ' + status);
                                        }
                                    });
                                } catch(e) { console.error('[AUTO-LOGIN] setTimeout error:', e); }
                            }, 1000);
                        }
                    }).catch(function(e) {
                        console.warn('Failed to fetch credentials:', e);
                    });
                }'''

new_block = '''// Auto-login removed - login happens when user clicks Connect button'''

if old_block in content:
    content = content.replace(old_block, new_block)
    print("Removed entire auto-login block")
else:
    print("Auto-login block not found exactly")
    # Try alternative
    if "// Auto-login DISABLED:" in content:
        content = re.sub(
            r'// Auto-login DISABLED: Login happens when user clicks Connect button\n// console\.log\(\[AUTO-LOGIN\] allDevices:[^}]+\}\);',
            '// Auto-login removed - login happens when user clicks Connect button',
            content
        )
        print("Removed via regex")

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")