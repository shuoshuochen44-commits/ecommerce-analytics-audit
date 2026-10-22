# 首次 GitHub 发布准备

目标账号：shuoshuochen44-commits。目标仓库：ecommerce-data-audit，公开可见，项目代码采用 MIT 许可。

本轮只整理发布文档、许可、忽略规则和自动测试，不改变桌面功能与用户已有工作区。

## 本地验收（2026-10-22）

在独立的 Python 3.11 虚拟环境中，按 README 从头安装 requirements-lock.txt，并进行 editable 安装；pip check 无依赖冲突。

- Python 完整回归：362 passed in 112.26s。
- Node.js 界面逻辑测试：15 项通过。
- 固定问题工程验收：30 项通过，0 项失败；21 项计算核验、4 项口径说明、5 项正确拒答。
- 三张界面截图使用独立生成的测试订单和单独工作区，未读取用户已导入的业务工作区。
- Windows 下载包只包含已验证 exe、五份新生成的独立订单文件、使用说明、许可与校验清单，不包含用户的 workspace 或虚拟环境。

本地记录位于忽略的 work/ 目录：publish-clean-tests.log、publish-clean-tests.xml、publish-ui-tests.log、publish-question-acceptance/template-acceptance.json。GitHub Actions 将在上传后独立重跑同类检查，其结果以实际运行状态为准。

历史 Git 对象约 1.1 MB，检查中未发现已配置的常见私钥或令牌格式匹配。该扫描只是发布检查的一部分，不构成对所有形式敏感内容的保证。

## 公开发布核验（2026-10-22）

- [公开仓库](https://github.com/shuoshuochen44-commits/ecommerce-data-audit)已创建，默认分支为 main，GitHub 识别许可为 MIT。
- [首次 Windows 云端测试](https://github.com/shuoshuochen44-commits/ecommerce-data-audit/actions/runs/39712338276)成功：362 项 Python 测试、15 项界面逻辑测试和 30 条固定问题验收均通过。
- [v0.1.0 正式版](https://github.com/shuoshuochen44-commits/ecommerce-data-audit/releases/tag/v0.1.0)已发布，版本标签对应本次测试的源码提交 `84c2d8bb1468334dc645ae5262a12a0335c6031a`。
- Windows 包大小为 46,285,019 字节，GitHub 上传文件的 SHA-256 与本地一致：`c812b8a065a9c4f30053df69925a07e87ad5fcfd47cbc42e990bdb70d29ab115`。
- 仓库与版本页面均已在无需登录的请求中返回 HTTP 200。

原有本地 origin 保留，GitHub 使用单独的 github 远程。用户业务 workspace 未加入公开源码或发布包。
