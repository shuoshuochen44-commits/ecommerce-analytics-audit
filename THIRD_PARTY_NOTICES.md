# 第三方文件与依赖

项目自己的代码使用根目录 MIT 许可证。第三方代码和数据继续适用各自的许可，根目录许可不替代它们的声明。

- `tests/fixtures/file_formats/calamine_issue_419.xlsb` 来自 Calamine 测试资料，来源记录及上游 MIT 许可位于同目录。
- `tests/fixtures/olist_mini/` 是工程验收使用的手工小样本，不是完整 Olist 数据集。
- Olist 原始数据不随本仓库和 Windows 下载包分发；来源记录见 `data/README.md` 与 `docs/week-01-data-discovery.md`。
- Python、DuckDB、SQLGlot、SQLAlchemy、pywebview、数据库驱动等依赖适用其发行包中附带的许可。

Windows 下载包的 `third-party-licenses/` 目录收录构建环境发行元数据中可取得的依赖许可与 Python 运行时许可，便于随软件一同查阅；各依赖的项目和包元数据是具体版本的来源依据。
