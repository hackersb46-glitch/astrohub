"""修复高级功能复用主控台画面"""
import re

with open('src/web/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到导航切换逻辑
old_switch = """                    if (btn.getAttribute('data-page') === 'advanced') initAdvSidebar();
                    if (btn.getAttribute('data-page')) refreshAdvancedDeviceSelectors();"""

new_switch = """                    // v7.36: 高级功能复用主控台视频容器
                    if (btn.getAttribute('data-page') === 'advanced') {
                        moveVideoToAdvanced();
                        initAdvSidebar();
                    } else if (btn.getAttribute('data-page') === 'console') {
                        moveVideoToConsole();
                    }
                    if (btn.getAttribute('data-page')) refreshAdvancedDeviceSelectors();"""

content = content.replace(old_switch, new_switch)

# 添加视频容器移动函数（在 initAdvSidebar 之前）
old_init = """        // Sidebar click handlers for advanced page sub-items
        function initAdvSidebar() {"""

new_init = """        // v7.36: 视频容器移动函数
        function moveVideoToAdvanced() {
            var videoContainer = document.getElementById('divPlugin');
            var advVideoBox = document.getElementById('advVideoBox');
            if (videoContainer && advVideoBox) {
                // 清空高级功能的占位符
                var placeholder = document.getElementById('advVideoPlaceholder');
                if (placeholder) placeholder.style.display = 'none';
                // 移动视频容器到高级功能
                advVideoBox.appendChild(videoContainer);
                console.log('[ADV] Video container moved to advanced page');
                // Resize WASM
                setTimeout(function() {
                    if (window.WebVideoCtrl) {
                        try { WebVideoCtrl.I_Resize(videoContainer.offsetWidth, videoContainer.offsetHeight); } catch(e) {}
                    }
                }, 100);
            }
        }

        function moveVideoToConsole() {
            var videoContainer = document.getElementById('divPlugin');
            var consoleVideoWrap = document.querySelector('.console-video-wrap');
            if (videoContainer && consoleVideoWrap) {
                // 移动视频容器回主控台
                consoleVideoWrap.appendChild(videoContainer);
                console.log('[CONSOLE] Video container moved back to console');
                // Resize WASM
                setTimeout(function() {
                    if (window.WebVideoCtrl) {
                        try { WebVideoCtrl.I_Resize(videoContainer.offsetWidth, videoContainer.offsetHeight); } catch(e) {}
                    }
                }, 100);
            }
        }

        // Sidebar click handlers for advanced page sub-items
        function initAdvSidebar() {"""

content = content.replace(old_init, new_init)

with open('src/web/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('高级功能复用主控台画面修复完成')