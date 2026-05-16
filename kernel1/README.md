# Kernel1 MVP

Socionics 单次判型 prototype。

> **版本:v0.10**(2026-05-16) — `confidence` 重定义为「系统对最终 type 的可信度」;arbitration 降级为建议层;多 4D 元素自动截断。详见 [`docs/kernel1/v0.10-confidence-semantics.md`](../docs/kernel1/v0.10-confidence-semantics.md)

## 主要特性

- **多档参考字典**:`prompts/reference_cards*.md` 多文件可选,GUI 下拉切换(默认 `reference_cards_socionics.md`,32 张 Function×Position 卡片)
- **三层精化**:L1 定向重提取 / L2 综合仲裁 / L3 用户追问
- **撞顶检测**:Top-2/Top-3 score 同时贴近 1.0 时强降 confidence 到 0.4,避免"分不开但显示满分"
- **稳定性灯**:`stability_hint` 报告算法 Top-1 与综合层是否一致,不一致强制 uncertain
- **回归 fixture**:`tests/test_confidence_calibration.py` 锁住两个离谱 case 的修复

## 图形界面

在项目根目录运行：

```powershell
cd D:\guCodex\shiroProject
python -m uvicorn kernel1.app:app --host 127.0.0.1 --port 8787
```

然后浏览器打开：

```text
http://127.0.0.1:8787/
```

页面可以填写：

- 是否使用本地 LLM
- OpenAI-compatible 监听地址，例如 `http://127.0.0.1:8000/v1/chat/completions`
- 模型名，例如 `qwen3.6-27b`
- API Key，vLLM 本地服务一般可填 `EMPTY`
- **参考字典下拉**(`reference_cards.md` / `reference_cards_socionics.md` / 其他自定义 `reference_cards*.md`)
- 待分析文章 / 自述文本

如果不勾选"使用本地 LLM"，系统会使用内置启发式 fallback 跑通流程。

### GUI 徽标语义(v0.10)

| 徽标 | 含义 | 颜色规则 |
|---|---|---|
| 系统可信度 | `result.confidence`(v0.10 已重定义,不再 = raw score) | 绿:status=certain && conf≥0.80;黄:status=certain && conf<0.80;红:status≠certain |
| IND 命中率 | 合法 IND 代码占所有 quote 的比例 | 绿 ≥70%;黄 ≥40%;红 <40% |
| 算法 Top-1 | `algorithm_top.{type, score}` — 算法层 Top-1,arbitration 无法覆盖 | — |
| 稳定性 | `stability_hint.consistent`(算法与综合层是否一致) | 绿:一致;红:不一致;灰:未仲裁 |

confidence 徽标 hover 可看 `raw_score` 和 `reason`(为啥被降)。

## 启动脚本

也可以直接运行根目录脚本：

```powershell
cd D:\guCodex\shiroProject
.\start_kernel1_api.ps1
```

如果 `8787` 被占用：

```powershell
.\start_kernel1_api.ps1 -Port 8789
```

## 命令行运行

```powershell
cd D:\guCodex\shiroProject
python -m kernel1.cli --text-file .\kernel1\samples\sample_input.txt --case-id sample-001 --report-only
```

## API 调用

```powershell
$body = @{
  case_id = "api-test-001"
  text = Get-Content -Raw .\kernel1\samples\sample_input.txt
  llm_enabled = $false
  ref_cards = "reference_cards_socionics.md"   # 可选,默认即此
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/kernel1/analyze -ContentType "application/json; charset=utf-8" -Body $body
```

使用本地 LLM：

```powershell
$body = @{
  case_id = "qwen-test-001"
  text = Get-Content -Raw .\kernel1\samples\sample_input.txt
  llm_enabled = $true
  llm_base_url = "http://127.0.0.1:8000/v1/chat/completions"
  llm_model = "qwen3.6-27b"
  llm_api_key = "EMPTY"
  llm_timeout = 90
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/kernel1/analyze -ContentType "application/json; charset=utf-8" -Body $body
```

列出可用参考字典:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8787/kernel1/list-refcards
```

## 测试

```powershell
cd D:\guCodex\shiroProject
python -m pytest kernel1/tests -v
```

当前覆盖 42 个测试,含:

- `test_confidence_calibration.py` — v0.10 confidence/arbitration/stability 回归(13 个)
- `test_indicator_normalize.py` / `test_indicator_hit_rate.py` — IND 代码反推 + 命中率
- `test_ref_cards.py` — 参考字典选择 + 路径穿越防护(9 个)
- `test_score_threshold.py` — 打分参数 + 饱和分母

同输入稳定性(连跑 N 次断言 verdict 一致率):

```powershell
python -m kernel1.eval.run_synthetic_repeated --sample ile_alpha_001 --runs 3
# 接本地 LLM:设 KERNEL1_LLM_ENDPOINT / KERNEL1_LLM_MODEL 环境变量
```

## 输出位置

- `kernel1/outputs/*.json`
- `kernel1/logs/kernel1.log`

## 关键新字段(v0.10)

```jsonc
{
  "confidence": 0.4,                          // 系统对 type 的可信度,非 raw score
  "confidence_breakdown": {
    "raw_score": 1.0,
    "reason": "status_uncertain+saturation_top_band_collision",
    "saturation_event": { "event": "top_band_collision", ... }
  },
  "algorithm_top": { "type": "IEI", "score": 1.0 },   // 算法 Top-1 不变事实
  "arbitration": {
    "suggested_type": "ILE",                  // 综合层建议,不覆盖 result.type
    "decision": "disagree_unsupported",
    "agrees_with_algorithm": false
  },
  "stability_hint": {
    "algorithm_top": "IEI",
    "synthesis_verdict": "ILE",
    "coherence": 0.85,
    "consistent": false                       // false → 强制 uncertain
  }
}
```
