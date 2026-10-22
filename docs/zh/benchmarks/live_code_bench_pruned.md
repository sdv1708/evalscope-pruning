# LiveCodeBench (Reference Pruned)

## 概述

在本地评估流程中，历史参考分层的 LiveCodeBench 选择。默认情况下为全保留：参考分析未在其保守决策策略下验证更小的操作点。

## 任务描述

- **任务类型**：竞赛编程 / 代码生成
- **输入**：原始 LiveCodeBench 题目及起始代码
- **输出**：使用标准 LiveCodeBench 格式的 Python 解决方案
- **领域**：编码能力筛选

## 主要特点

- 可配置的 difficulty_stratified 或 response_stratified 历史选择
- prune_ratio 是保留比例，取值范围为 (0, 1]，向上取整
- 冻结的问题指纹将分析索引绑定到源问题
- 排除已评估模型成绩；选择发生在推理之前且可重复

## 评估说明

- 继承 LiveCodeBench 的提示词、日期过滤、提取和代码执行评分器
- 需要本地 reference_path 面板；基准测试下载使用标准加载器
- 标准子集 pass@k 依然可用，同时支持基于总体加权的准确率
- 生成代码使用沙箱执行，与完整基准一致
- 较小的比例为实验性质；不保证新的通过/不通过结果
- **配置要求：** 下方生成的通用 Usage 模板不可直接运行本基准。需提供 `extra_params.reference_path` 并移除 `--limit` / `limit=10`；使用 `prune_ratio` 控制保留大小。要运行离线示例，请在仓库根目录执行：

```python
from evalscope import run_task
run_task('examples/live_code_bench_pruned/task.json')
```

详见 `LIVE_CODE_BENCH_PRUNED.md`，了解完整参考面板架构及实时命令。

## 属性

| 属性 | 值 |
|----------|-------|
| **基准测试名称** | `live_code_bench_pruned` |
| **数据集ID** | [evalscope/livecodebench_code_generation_lite_parquet](https://modelscope.cn/datasets/evalscope/livecodebench_code_generation_lite_parquet/summary) |
| **论文** | 不适用 |
| **标签** | `Coding` |
| **指标** | `accuracy` |
| **默认示例数** | 0-shot |
| **评估划分** | `test` |
| **汇总方式** | `mean_and_pass_at_k` |

## 数据统计

*统计信息不可用。*

## 样例示例

*样例示例不可用。*

## 提示模板

**系统提示：**
```text
You are an expert Python programmer. You will be given a question (problem specification) and will generate a correct Python program that matches the specification and passes all tests. You will NOT return anything except for the program.
```

**提示模板：**
```text
### Question:
{question_content}

{format_prompt} ### Answer: (use the provided format with backticks)


```

## 额外参数

| 参数 | 类型 | 默认值 | 描述 |
|-----------|------|---------|-------------|
| `start_date` | `str | null` | `None` | 筛选起始日期（格式 YYYY-MM-DD），Null 表示全部保留。 |
| `end_date` | `str | null` | `None` | 筛选截止日期（格式 YYYY-MM-DD），Null 表示全部保留。 |
| `debug` | `bool` | `False` | 启用详细调试日志并跳过部分安全检查。 |
| `pruning_strategy` | `str` | `difficulty_stratified` | 历史分层策略；比较基线被拒绝。 |
| `prune_ratio` | `float` | `1.0` | 保留比例，范围 (0, 1]；1.0 为默认保底。 |
| `reference_path` | `str` | `` | 本地冻结参考面板 JSON，架构版本1。 |
| `excluded_reference_models` | `list[str]` | `[]` | 额外排除的参考模型名称（用于成对保留）。 |

## 沙箱配置

本基准测试需要沙箱环境执行代码。

```json
{
  "image": "python:3.11-slim",
  "tools_config": {
    "shell_executor": {},
    "python_executor": {}
  }
}
```

## 使用方法

### 使用命令行

```bash
evalscope eval \
    --model YOUR_MODEL \
    --api-url OPENAI_API_COMPAT_URL \
    --api-key EMPTY_TOKEN \
    --datasets live_code_bench_pruned \
    --sandbox '{"enabled": true}' \
    --limit 10  # Remove this line for formal evaluation
```

### 使用 Python

```python
from evalscope import run_task
from evalscope.config import TaskConfig

task_cfg = TaskConfig(
    model='YOUR_MODEL',
    api_url='OPENAI_API_COMPAT_URL',
    api_key='EMPTY_TOKEN',
    datasets=['live_code_bench_pruned'],
    sandbox={'enabled': True},
    dataset_args={
        'live_code_bench_pruned': {
            # extra_params: {}  # uses default extra parameters
        }
    },
    limit=10,  # Remove this line for formal evaluation
)

run_task(task_cfg=task_cfg)
```
