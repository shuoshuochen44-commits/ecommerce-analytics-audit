# 独立桌面窗口 Implementation Plan

**Goal:** 用户双击 exe 直接打开桌面窗口，保留现有界面和数据。

**Architecture:** desktop.py 管理本机服务和原生窗口生命周期；desktop_instance.py 管理 Windows 工作区实例锁与恢复窗口；desktop_entry.py 默认选择窗口，--headless 保持验收入口。复用现有 server 与所有 UI。

**Tech Stack:** Python、pywebview 6.2.1、Edge WebView2、Windows named mutex、PyInstaller。

- [ ] 编写 tests/test_desktop.py：真实服务窗口关闭后端口关闭、源管理器停止；GUI 启动失败清理；服务退出触发窗口销毁；原生默认入口不调用浏览器。先运行 pytest 确认缺少模块失败。
- [ ] 编写 tests/test_desktop_instance.py：同工作区互斥、不同工作区独立、释放后重新获得。使用实际 Windows mutex，不操作用户窗口。
- [ ] 实现桌面宿主和入口；原生窗口宽 1280、高 860、最小 900×640，开启文件下载；默认以 edgechromium 启动；关闭窗口终止自身服务。--headless / --no-browser 转交既有 launcher 的无浏览器模式。
- [ ] 添加依赖与冻结所需的 webview、pythonnet、CLR DLL；重新构建无控制台 exe。执行现有 scripts/verify_desktop.py 对五个 12,000 行文件实际导入。
- [ ] 通过 Computer Use 查看实际窗口、选择文件并导入、保存报告、关闭及重开，保存原生窗口截图。检查重复启动复用同一窗口。
- [ ] 更新使用说明，运行完整 pytest 与 git diff --check。校验后替换桌面 exe，保持数据文件和 workspace 原样；最终从桌面运行空启动并交付截图。

执行在现有 codex/auditable-analysis 隔离分支内完成，不创建其他用户任务或修改原项目。
