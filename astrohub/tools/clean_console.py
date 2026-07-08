"""Clean up console.html - remove IR filter switch, rename label"""

with open('src/web/includes/console.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Rename dayNightMode label
content = content.replace(
    '<label style="font-size:10px;color:#8b949e;margin-bottom:1px;display:block">日夜模式</label>',
    '<label style="font-size:10px;color:#8b949e;margin-bottom:1px;display:block">日夜转换/IR滤镜</label>'
)

# 2. Remove IR filter switch block
old_ir_tag = '''                                    <div style="display:flex;gap:3px;margin-bottom:2px">
                                        <div style="flex:1;min-width:0">
                                            <label style="font-size:10px;color:#8b949e;margin-bottom:1px;display:block">日夜转换/IR滤镜</label>
                                            <div class="triple-switch" id="dayNightSwitch" style="display:flex;width:100%">
                                                <button class="ts-btn" data-value="day" onclick="setDayNightMode(\'day\')">日</button>
                                                <button class="ts-btn" data-value="night" onclick="setDayNightMode(\'night\')">夜</button>
                                                <button class="ts-btn" data-value="auto" onclick="setDayNightMode(\'auto\')">自动</button>
                                            </div>
                                        </div>
                                        <div style="flex:1;min-width:0">
                                            <label style="font-size:10px;color:#8b949e;margin-bottom:1px;display:block">IR 滤镜</label>
                                            <div class="triple-switch" id="irCutSwitch" style="display:flex;width:100%">
                                                <button class="ts-btn" data-value="on" onclick="setIRCutFilter(\'on\')">开</button>
                                                <button class="ts-btn" data-value="off" onclick="setIRCutFilter(\'off\')">关</button>
                                                <button class="ts-btn" data-value="auto" onclick="setIRCutFilter(\'auto\')">自动</button>
                                            </div>
                                        </div>
                                    </div>'''

new_ir_tag = '''                                    <div style="display:flex;gap:3px;margin-bottom:2px">
                                        <div style="flex:1;min-width:0">
                                            <label style="font-size:10px;color:#8b949e;margin-bottom:1px;display:block">日夜转换/IR滤镜</label>
                                            <div class="triple-switch" id="dayNightSwitch" style="display:flex;width:100%">
                                                <button class="ts-btn" data-value="day" onclick="setDayNightMode(\'day\')">日</button>
                                                <button class="ts-btn" data-value="night" onclick="setDayNightMode(\'night\')">夜</button>
                                                <button class="ts-btn" data-value="auto" onclick="setDayNightMode(\'auto\')">自动</button>
                                            </div>
                                        </div>
                                    </div>'''

if old_ir_tag in content:
    content = content.replace(old_ir_tag, new_ir_tag)
    print("[OK] IR filter switch removed")
else:
    print("[FAIL] IR filter switch block not found")

# Write back
print(f"\nOriginal length: {len(open('src/web/includes/console.html', encoding='utf-8').read())}")
with open('src/web/includes/console.html', 'w', encoding='utf-8') as f:
    f.write(content)
print(f"New length: {len(content)}")
print(f"Saved {len(open('src/web/includes/console.html', encoding='utf-8').read())} - {len(content)}")
