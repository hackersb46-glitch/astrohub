"""修复码流切换问题 - 使用全局变量"""
import re

with open('src/web/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 添加全局变量 g_iStreamType
old_var = 'var g_iWebSocketPort = 7681;'
new_var = '''var g_iWebSocketPort = 7681;
var g_iStreamType = 3;  // v7.34: 用户选择的码流类型，默认第三码流'''

# 只替换第一个匹配
content = content.replace(old_var, new_var, 1)

# 2. 修改 clickLogin2 中的硬编码 3 为 g_iStreamType
# 第 2724 行
old_play1 = 'clickStartRealPlay({ iStreamType: 3 });'
new_play1 = 'clickStartRealPlay({ iStreamType: g_iStreamType });'
content = content.replace(old_play1, new_play1)

# 3. 修改 changeStreamType 保存用户选择
old_change = '''function changeStreamType(streamType) {
    console.log('[changeStreamType] streamType=' + streamType);
    var parsedType = parseInt(streamType, 10);'''

new_change = '''function changeStreamType(streamType) {
    console.log('[changeStreamType] streamType=' + streamType);
    var parsedType = parseInt(streamType, 10);
    g_iStreamType = parsedType;  // v7.34: 保存用户选择的码流'''

content = content.replace(old_change, new_change)

with open('src/web/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('码流切换修复完成')