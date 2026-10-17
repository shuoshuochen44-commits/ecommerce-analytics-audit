# 离线可审计问答使用说明

这是原项目的下一阶段：在数据快照和既有模型上实现可测试的分析内核。只接受目录内问题 ID 或精确文本（忽略首尾空白及句末问号/句号）。不调用模型，没有泛化自然语言理解，也没有 B1/B2/M1/M2/M3 实验结果。

## 安装与首次运行

在本分支源码根目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe scripts/verify_analysis.py --fixture-gold
```

最后一条命令加工已提交的自造小样本，执行全部 30 条目录问题，核对其中 21 条计算/质量结果的手工金标准，生成 `artifacts/analysis-acceptance/template-acceptance.json` 和 `analysis_runs/` 中的逐运行记录。它是工程验收，不能用于声称模型准确率。

```powershell
.\.venv\Scripts\python.exe -m zhishu_inspection.analysis_cli --list
.\.venv\Scripts\python.exe -m zhishu_inspection.analysis_cli artifacts/analysis-acceptance A01
.\.venv\Scripts\python.exe -m zhishu_inspection.analysis_cli artifacts/analysis-acceptance "唯一购买客户数是多少" --start 2018-02-01 --end 2018-02-28 --state SP
```

记录返回的 `run_id` 后，用其完整值替换以下占位参数：

```powershell
.\.venv\Scripts\python.exe -m zhishu_inspection.analysis_cli artifacts/analysis-acceptance --replay ANALYSIS_RUN_ID
```

重放读取原运行的快照、问题、筛选与版本，生成新运行，保留 `replay_of` 和 `replay_matches`。最新数据指针改变不会改变重放范围。CLI 对被阻止的结果返回退出码 2，包括目录中刻意拒答的问题；验收脚本将这些正确拒答独立检查。

已有国内模拟版或历史版快照也可以直接使用：将上述输出根目录替换为相应 `artifacts/china-demo` 或 `artifacts/analytics`。没有成功快照时，会返回可读错误和 blocked 运行记录。

## Python 接口与组件

```python
from pathlib import Path
from zhishu_inspection.analysis import analyze, get_run, replay

root = Path('artifacts/analysis-acceptance')
answer = analyze(root, 'A01', start='2018-02-01', state='SP')
stored = get_run(root, answer['run_id'])
replayed = replay(root, answer['run_id'])
```

| 文件 | 责任 |
|---|---|
| question_catalog.py | 30 条问题、口径、规则依赖和绑定参数 SQL |
| query_gateway.py | SQLGlot AST/作用域校验和受限只读执行 |
| answer_verifier.py | 从原始表按订单粒度独立 Python/Decimal 复算 |
| analysis.py | 固定快照、状态判定、证据、运行记录和重放 |
| analysis_cli.py | JSON 命令行入口 |
| scripts/verify_analysis.py | 模板工程验收，不是模型评测 |

未来模型应输出目录内问题 ID 和结构化筛选，经相同内核处理；开放 SQL 生成需要单独扩展策略与攻击测试，不能绕过此边界。

## 结果与核验状态

每个结果都有 answer、sql、parameters、result、chart_spec、citations、verification_status、quality_warnings 和独立分析 run_id。snapshot_run_id 标识输入数据批次。实际 SQL 是经解析器资格化并执行的 SQL，参数不拼接进语句。chart_spec 为简单图表描述，不是已绘制的页面图。

| 状态 | 意义 |
|---|---|
| verified | 模型层结果与原始表复算一致，当前问题没有命中的质量风险 |
| needs_review | 数值复算一致，但相应字段/口径受到质量问题影响 |
| blocked | 不支持、明确拒答、执行失败、预算不足或独立核验不一致 |
| not_applicable | 口径说明，仅引用版本化文档/数据来源，没有 SQL 数值核验 |

计算结果逐行比较，原始层独立核验不复用模型层 SQL。Q01 查询整批失败规则数，以规则重执行核对质量报告，记录不同的 verification.method。客户数每个范围独立去重；复购买家指当前范围内至少两笔已交付订单的客户。地区、品类、商品排名只返回前十，金额相同按维度名称排序。月份趋势包含出现过的购买月份，不补造无订单月份。金额与客单价在无可用数据时为空值。

质量警告覆盖整个固定批次，记录 scope=full_snapshot，可能比当前筛选更保守。已交付订单缺商品明细影响金额/客单价与品类订单数；缺稳定客户影响客户指标；地区筛选和地区分组依赖客户映射，映射缺失时提示 Q06；孤儿支付向支付对账附加 Q18 提示。warning 的 failed_count 不可加总为异常订单数。数值一致不等同于业务事实完整。

## 执行与审计边界

安全策略只允许小范围的单条 SELECT/非递归 CTE 和显式授权表列/AST 节点。拒绝写入、多语句、系统表、外部文件/表函数、未知列、星号明细、递归和笛卡尔积；最多一次订单与商品明细按 order_id 的直接等值关联。DuckDB read_only 连接通过固定 SET 关闭外部访问、自动扩展安装及加载，单线程、256 MB 内存；连接参数与已有看板保持兼容，这些设置作用于同进程共享的数据库实例。默认 5 秒、最多 1,000 行返回、1,000,000 参与源行、16,000 字符 SQL 和 500 个 AST 节点。超过结果限制时不返回部分答案。

参与源行数是获准物理表的行数之和，**不是物理扫描量或关联基数的精确估计**；超时/内存限制承担网关查询的运行期保护，不是整个分析任务的总时限。原始层 Python 复算也有总行数预算，面向当前普通电脑上的本地数据规模；原始日期解析使用 DuckDB 的基础 CAST 以遵循接入允许的日期格式，业务聚合和分组使用独立 Python 逻辑。这不是多租户沙箱；不要把它直接暴露为公网任意 SQL 服务。

SQLGlot 的字段校验使用官方 [qualify 源码](https://github.com/tobymao/sqlglot/blob/v28.10.1/sqlglot/optimizer/qualify.py) 的作用域资格化流程；DuckDB 的外部访问和扩展限制见[官方安全说明](https://duckdb.org/docs/stable/operations_manual/securing_duckdb/overview)。本分支固定 SQLGlot 28.10.1，在依赖升级时必须重跑攻击测试。

运行 JSON 独占创建、附内容 SHA256，可检测意外修改，并固定内核、目录、字段策略与引擎版本；没有签名或访问控制，不能抵御拥有文件系统写权限者同时篡改内容与哈希。运行记录不保存自由输入全文、原始身份明细、规则样例主键或任意异常堆栈。CSV 源数据与成功数据库快照的长期保管仍由本地用户负责。

## 回归与范围

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts/verify_analysis.py --fixture-gold
```

本阶段不修改既有网页/服务器、不接入任意表结构上传、不声称完成项目总规格中的模型 Agent、容器、20 条规则、五方法评测或演示视频。原项目当前仍是 18 条质量规则；这些交付继续保留为后续独立里程碑。
