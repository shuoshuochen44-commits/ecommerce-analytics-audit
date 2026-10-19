# 独立桌面窗口

用户已选择沿用现有界面、改为独立桌面窗口。双击 exe 打开带标准标题栏、最小化/最大化/关闭的 Windows 窗口，不启动外部浏览器。继续保留空工作区、外部五格式文件、导入、数据库接入、刷新、快照与报告。

采用 pywebview 6.2.1 与系统 Edge WebView2：复用现有 HTML/CSS/JS 和 Python 处理层。相比 Electron 无需另带完整 Node/Chromium；相比重写原生控件无需重做现有图表与业务流程。本机注册表已确认 WebView2 Runtime 155.0.4283.62；其他电脑需要安装该系统运行时。

桌面宿主独占自己的本机随机端口。启动后台线程后加载应用窗口；关闭窗口停止调度、HTTP 与工作线程，界面退出按钮同时关闭窗口。同工作区重复启动恢复已有窗口，不产生第二份服务；浏览器版服务与桌面窗口互不复用。以工作区哈希命名的 Windows mutex 提供实例互斥。运行时文件仍存放 exe 同目录 workspace，不覆盖业务文件。

窗口内选择文件使用系统文件对话框，保存报告/导出启用 WebView2 下载。默认不展示开发工具和地址栏。保留 --headless（兼容 --no-browser）供已有 HTTP 验收脚本使用，不改变默认桌面体验。

验收：宿主生命周期和实例互斥自动化测试；冻结 exe 五格式导入回归；实际原生窗口中选择文件、导入、图表、报告下载、关闭退出、重开与重复启动；提供原生窗口截图。桌面替换前校验现有 exe 哈希，保留现有 workspace 与五份数据文件。

官方依据：https://pywebview.flowrl.com/guide/installation 、https://pywebview.flowrl.com/guide/freezing 、https://pywebview.flowrl.com/api/ 、https://pywebview.flowrl.com/examples/downloads 。
