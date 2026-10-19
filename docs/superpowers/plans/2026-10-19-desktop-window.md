# 独立桌面窗口 Implementation Plan

**Goal:** 用户双击 exe 直接打开桌面窗口，保留现有界面和数据。

**Architecture:** desktop.py 管理本机服务和原生窗口生命周期；desktop_instance.py 管理 Windows 工作区实例锁与恢复窗口；desktop_entry.py 默认选择窗口，--headless 保持验收入口。复用现有 server 与所有 UI。

**Tech Stack:** Python、pywebview 6.2.1、Edge WebView2、Windows named mutex、PyInstaller。

- [x] 编写 tests/test_desktop.py：真实服务窗口关闭后端口关闭、源管理器停止；GUI 启动失败清理；服务退出触发窗口销毁；原生默认入口不调用浏览器。先运行 pytest 确认缺少模块失败。
- [x] 编写 tests/test_desktop_instance.py：同工作区互斥、不同工作区独立、释放后重新获得。使用实际 Windows mutex，不操作用户窗口。
- [x] 实现桌面宿主和入口；原生窗口宽 1280、高 860、最小 900×640，开启文件下载；默认以 edgechromium 启动；关闭窗口终止自身服务。--headless / --no-browser 转交既有 launcher 的无浏览器模式。
- [x] 添加依赖与冻结所需的 webview、pythonnet、CLR DLL；重新构建无控制台 exe。执行现有 scripts/verify_desktop.py 对五个 12,000 行文件实际导入。
- [x] 通过 Computer Use 查看实际窗口、选择文件并导入、保存报告、关闭及重开，保存原生窗口截图。检查重复启动复用同一窗口。
- [x] 更新使用说明，运行完整 pytest 与 git diff --check。校验后替换桌面 exe，保持数据文件和 workspace 原样；最终从桌面运行空启动并交付截图。

执行在现有 codex/auditable-analysis 隔离分支内完成，不创建其他用户任务或修改原项目。

## 验收记录

2026-10-19：6 项新增宿主/Windows mutex 测试先失败后通过；全套 331 项通过（95.59 秒）。冻结 exe 的五种 12,000 行导入一致性检查通过。实际 Windows 窗口完成系统文件选择、预览映射、导入、经营图表与另存为 HTML 报告（4532 字节）；标题栏关闭后 HTTP 端口不再响应。冻结程序的重复启动恢复同一窗口，并以默认无命令参数方式在桌面启动成功。

桌面程序已替换并核对哈希，大小 44,125,863 字节。升级前已有 1 份业务快照，升级后其 latest 指针哈希保持一致，五份独立订单文件未改动。旧 exe 仅备份在开发工作区 `work/previous-browser-desktop-2026-10-19.exe`。真实桌面窗口截图保存为 `work/desktop-native-final.jpg`。
