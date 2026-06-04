# DeepInvestigate Evaluation

自动化评估系统，量化 v2.0 Agent 的能力。

## 数据集

`dataset/attack_logs_eval.jsonl` —— 15 条精选任务，覆盖：

- SSH 暴力破解 / 密码喷洒
- Log4Shell / XZ 后门 / BlueKeep 等高危 CVE
- 横向移动 / 凭据导出 / 勒索 / C2 通信
- 数据分析 / 闲聊 / 复合任务

每条数据：
```json
{
  "task_id": "T001",
  "category": "ssh_bruteforce",
  "input": "...",
  "expected_keywords": ["1.2.3.4", "暴力破解", "封禁"],
  "expected_tools": ["query_logs", "run_python"],
  "difficulty": "easy"
}
```

## 评估指标

| 指标 | 含义 |
|---|---|
| Task Success Rate | 关键词覆盖 ≥60% 且无错误无幻觉 |
| Keyword Coverage | 期望关键词命中率 |
| Tool Call Accuracy | 期望工具被调用比例 |
| Avg Iterations | 平均推理轮数 |
| Avg Latency | 平均完成耗时（秒） |
| Hallucination Rate | 出现"我不知道/无法回答"等拒答信号的比例 |

## 用法

```bash
# 跑全部
python -m eval.run_eval

# 只跑前 3 条（快速冒烟）
python -m eval.run_eval --limit 3

# 并发 3
python -m eval.run_eval --concurrency 3

# 指定数据集
python -m eval.run_eval --dataset eval/dataset/attack_logs_eval.jsonl
```

报告输出：`eval/reports/report_<timestamp>.json`

## 期望产出

跑完后会在 `reports/` 下产生 JSON 报告，含：
- summary：聚合指标
- results：每条任务的明细（含关键词命中、调用工具、耗时、final answer 摘要）

可用于：
- 简历用的"成功率提升"数据
- baseline vs v2 对比
- 回归测试
