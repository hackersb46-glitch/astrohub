"""修复曝光模式 - 从 function.json 动态加载"""
import re

with open('src/web/includes/console.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 修改 HTML：删除硬编码选项，改为动态加载
old_html = '''                                        <select id="exposureMode" style="width:100%;padding:4px;background:#0d1117;border:1px solid #30363d;border-radius:4px;color:#e0e6f0;font-size:12px" onchange="setExposureMode(this.value);updateShutterIrisState()">
                                            <option value="auto">自动</option>
                                            <option value="manual">手动</option>
                                        </select>'''

new_html = '''                                        <select id="exposureMode" style="width:100%;padding:4px;background:#0d1117;border:1px solid #30363d;border-radius:4px;color:#e0e6f0;font-size:12px" onchange="setExposureMode(this.value);updateShutterIrisState()">
                                            <!-- v7.35: 从 function.json 动态加载 -->
                                        </select>'''

content = content.replace(old_html, new_html)

# 2. 添加 loadExposureMode 函数（在 loadExposure 之后）
old_load = '''// 加载曝光模式
function loadExposure(deviceIp) {
    apiGet('/api/v1/ptz/' + deviceIp + '/image/exposure').then(function(r) {
        if (r && r.success && r.data) {
            var select = document.getElementById('exposureMode');
            if (select && r.data.mode) {
                // v5.47: 只支持 auto/manual，其他模式统一为 manual
                select.value = (r.data.mode === 'auto') ? 'auto' : 'manual';
                // 更新快门光圈控件状态
                updateShutterIrisState();
            }
        }
    }).catch(function(e) {
        console.warn('[Exposure] Load failed:', e);
    });
}'''

new_load = '''// 加载曝光模式
function loadExposure(deviceIp) {
    // v7.35: 先从 function.json 获取 opt_values
    var select = document.getElementById('exposureMode');
    if (!select) return;
    
    select.innerHTML = '';
    
    // 检查 function.json
    if (!deviceFunctionData || !deviceFunctionData.functions || !deviceFunctionData.functions.exposure_mode) {
        console.warn('[Exposure] No function.json data');
        select.innerHTML = '<option value="">-- 不支持 --</option>';
        select.disabled = true;
        return;
    }
    
    var exposureData = deviceFunctionData.functions.exposure_mode;
    var optValues = exposureData.opt_values || [];
    
    if (!optValues || optValues.length === 0) {
        select.innerHTML = '<option value="">-- 不支持 --</option>';
        select.disabled = true;
        return;
    }
    
    select.disabled = false;
    
    // 映射显示名称
    var labels = {
        'manual': '手动',
        'auto': '自动',
        'IrisFirst': '光圈优先',
        'ShutterFirst': '快门优先'
    };
    
    optValues.forEach(function(val) {
        var opt = document.createElement('option');
        opt.value = val;
        opt.textContent = labels[val] || val;
        select.appendChild(opt);
    });
    
    // 获取当前值
    apiGet('/api/v1/ptz/' + deviceIp + '/image/exposure').then(function(r) {
        if (r && r.success && r.data && r.data.mode) {
            select.value = r.data.mode;
            updateShutterIrisState();
        }
    }).catch(function(e) {
        console.warn('[Exposure] Load current failed:', e);
    });
}'''

content = content.replace(old_load, new_load)

with open('src/web/includes/console.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('曝光模式动态加载修复完成')