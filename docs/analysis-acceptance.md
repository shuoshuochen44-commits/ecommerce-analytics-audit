# 离线问答内核验收记录

验收日期：2026-10-18（Asia/Shanghai）。本分支从主项目已提交状态 `3a68ede` 开发；使用独立源码与独立虚拟环境，没有合并主项目中尚未完成的表格接入等开发。

## 实际检查结果

- 干净虚拟环境按 requirements-lock.txt 安装，editable 安装当前项目成功。
- 全量 pytest：**127 passed in 28.04s**，其中原有基线为 68 项。
- git diff --check：通过。
- 代码复核发现的空日期、恒真 JOIN、CTE 遮蔽、并发连接配置、源日期格式、地区标签、缺明细覆盖、孤儿支付和地区筛选依赖问题均已补回归测试并修复。

| 输入 | 目录问题验收 | SQL/质量计算 | 口径说明 | 明确拒答 | 重放 |
|---|---:|---:|---:|---:|---|
| 三笔手工订单样本 | 30/30 | 21 | 4 | 5 | 一致 |
| 12,000 笔国内模拟订单 | 30/30 | 21 | 4 | 5 | 一致 |

这里的“通过”是目录工程验收：计算问题与独立原始层复算一致，口径问题有来源，拒答问题按设计阻止。手工小样本的 21 条计算/质量结果另与提交的人工金标准逐项核对。不能将 30/30 写成模型准确率、自然语言泛化率或论文实验指标。

## 输入与证据

两套验收数据的运行清单均明确 simulated=true；小样本包含独立 dataset.json，进入输入哈希。

| 输入 | 输入指纹 SHA256 | A01 商品金额结果 |
|---|---|---:|
| olist_mini（手工模拟） | 917c40320366c0fea997335195c803cde3d46556981ce4ffe2d96ccc2d64a722 | 230.00 BRL |
| china_demo（程序模拟） | 60eb7ffbdd197bff851a3c163aa84a9bc822d5a04a9347b669ea180544675015 | 7,972,223.95 CNY |

完整逐题结果保存在本地 `artifacts/analysis-acceptance/template-acceptance.json` 和 `artifacts/analysis-china-demo/template-acceptance.json`；各目录的 analysis_runs/ 包含逐运行清单。产物未提交版本库，可由以下命令重建。

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts/verify_analysis.py --fixture-gold
.\.venv\Scripts\python.exe -m zhishu_inspection.china_demo data/raw/analysis-china-demo
.\.venv\Scripts\python.exe scripts/verify_analysis.py --raw-dir data/raw/analysis-china-demo --output-root artifacts/analysis-china-demo
```

国内模拟数据生成器拒绝覆盖已有目录；数据已生成时，跳过生成命令。复用既有成功快照可执行 `scripts/verify_analysis.py --existing --output-root artifacts/analysis-china-demo`。

## 本次未交付

LLM 接入、HTTP 问答接口、问答页面、20 条规则补齐、Docker 和模型对照评测仍是后续里程碑。当前没有模型调用或模型费用；也没有录制演示视频。运行记录具有文件完整性检查，不具备签名或防管理员篡改能力。
