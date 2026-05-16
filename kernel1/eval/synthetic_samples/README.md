# Kernel1 合成评测样本

## 来源与用途

每个样本是基于《工具社会人格学》(戈利霍夫·德米特里 著，章鱼 译) 中 8 元素 × 4 重视位置的描述合成的「模拟用户自述」，配套一份 `*.gt.json` 标注 ground truth。

四象限各 1 例（Alpha/Beta/Gamma/Delta）作为最小回归集，用于：
- 验证 `reference_cards_socionics.md` 字典加载后判型准确率
- 跑 confidence 阈值回归（目标 ≥ 0.80）
- 调整打分参数前后做 A/B 对比

**不是真实用户文本，不能当训练集；只用来做回归和 sanity check。**

## 文件

| 文件 | Ground Truth | 象限 | 关键功能位 |
|---|---|---|---|
| `ile_alpha_001.txt` + `.gt.json` | ILE / ENTp | Alpha | Ne(1) + Ti(2) + Fe(3) + Si(4) |
| `lsi_beta_001.txt` + `.gt.json` | LSI / ISTj | Beta | Ti(1) + Se(2) + Ni(3) + Fe(4) |
| `lie_gamma_001.txt` + `.gt.json` | LIE / ENTj | Gamma | Te(1) + Ni(2) + Se(3) + Fi(4) |
| `eii_delta_001.txt` + `.gt.json` | EII / INFj | Delta | Fi(1) + Ne(2) + Si(3) + Te(4) |

每个 `.gt.json` 含：
- `ground_truth.type` / `alias` / `quadra` / `model_a` —— 期望的判型
- `source.sections` —— 该样本各功能位措辞所对应的 docx 段落号
- `expected_signals` —— 验收下限：
  - `top_candidate_must_include`：Top-1 候选必须包含的类型
  - `min_confidence_target`：confidence 目标（0.80）
  - `evidence_must_cover_elements`：1st/2nd 元素必须出现在证据链
  - `evidence_should_cover_elements`：3rd/4th 元素至少应该被采集

## 跑评测

```powershell
cd D:\guCodex\shiroProject
python -m kernel1.eval.run_synthetic           # heuristic 模式
python -m kernel1.eval.run_synthetic --llm     # 启用本地 LLM
```

结果落在 `kernel1/eval/results/synthetic_<timestamp>.json`。

## 编号体系注意

docx 用 Kalinauskas 编号（1=主导、2=创造、3=MSP/激活、4=暗示），kernel1 内部一律用 Bukalov 8 位排布：

| docx 标号 | Bukalov 位置 | 维度 | 重视 | 环路 |
|---|---|---|---|---|
| 1号 | 1 | 4D | valued | mental |
| 2号 | 2 | 3D | valued | mental |
| **3号** | **6** | **2D** | **valued** | **vital** |
| **4号** | **5** | **1D** | **valued** | **vital** |

`gt.json` 里的 `model_a` 数组按 Bukalov 8 位顺序写（1主导→2创造→3角色→4脆弱→5暗示→6激活→7忽略→8演示）。
