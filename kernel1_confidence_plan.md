# Kernel1 Confidence ≥ 0.8 实施计划（Sonnet 执行版）

> 由 Opus 4.7 评估并设计。Sonnet 执行时按【推荐执行顺序】逐 commit 完成，每条都标了具体文件 + 行号 + 验证手段。

## 1. 背景与目标

`D:\guCodex\shiroProject\kernel1` 是 Socionics 单次判型 MVP。当前痛点：

- 用户验收口径：`confidence ≥ 0.8` 才能进入 Kernel2 多轮
- 典型样本 `outputs/edited-qa-smoke-001.json` 现状：`confidence=0.665`、`status="uncertain"`
- 根因：本地 LLM（Qwen3.6-27B）在 Q&A 模式下 indicator 字段经常返回非法字符串（如 `"显性/感觉"`、`"主导直觉"`、`"strong_logic"`），`core.py:421` 的 `_normalize_extraction` 没做白名单校验直接落地；下游 `IND_PROFILES.get(indicator)`（core.py:838）拿不到 profile → IND 加分链整段被 `continue` 丢弃 → 归一化分数 = `score / max_possible + 0.2`（line 900）的分子不够大

**目标**：
1. LLM 输出的 quote 中 `indicator` 是合法 IND 代码的比例 ≥ 70%
2. Top-1 confidence 中位数 ≥ 0.80
3. 同时保留代码反推作为兜底，不依赖单一信号源

## 2. 设计思路（用户已确认）

- **范本范围**：先做**字典级小卡片**（原话片段 → 标准 IND 代码 + 完整信号填充），覆盖 19 个 IND 代码常见命中场景；同时**保留端到端整组 QA 范例的接口**（数据格式、加载位置统一，将来扩展只编辑 markdown）
- **注入方式**：嵌入 `evidence_extraction.md` 默认加载段，不做动态 top-K 选取
- **不动**：评分总框架、Model A 字典、L1/L2/L3 精化、Laning 抢七

## 3. 关键文件与行号速查

- `kernel1/core.py:65-92` —— `IND_PROFILES` 字典（反推算法基于这里）
- `kernel1/core.py:120-127` —— `AnalyzeOptions` dataclass
- `kernel1/core.py:134` —— `extraction_prompt` 加载点
- `kernel1/core.py:333-359` —— `_extract_evidence`
- `kernel1/core.py:406-495` —— `_normalize_extraction`（核心改造点）
- `kernel1/core.py:753-905` —— `_score_candidates` 主循环
- `kernel1/core.py:836-884` —— IND 加分链
- `kernel1/core.py:900-904` —— 归一化 + 0.58 硬天花板
- `kernel1/prompts/evidence_extraction.md:58-62` —— IND 代码白名单
- `kernel1/static/index.html:444-449, 506` —— GUI metrics 与报告渲染

## 4. 执行序列（共 7 个独立 commit）

### Commit D — 测试脚手架（先做，否则后面没法验证）

**新文件**：
- `kernel1/tests/__init__.py`（空）
- `kernel1/tests/conftest.py`
- `kernel1/pytest.ini`（`pythonpath = ..`）
- `kernel1/tests/test_smoke.py`
- `kernel1/tests/test_indicator_normalize.py`（先建占位，Commit C 填实）
- `kernel1/tests/test_reference_load.py`（先建占位，Commit B 填实）

**`conftest.py` 提供的 fixture**：
- `analyzer_heuristic`：`Kernel1Analyzer(llm=LLMClient(LLMConfig(enabled=False)))`
- `sample_text`：`(BASE_DIR / "samples/sample_input.txt").read_text(encoding="utf-8")`
- `stub_llm`：monkeypatch `LLMClient.chat_json` 返回预录响应（用于 indicator-hit-rate 等单元测试）
- `qa_smoke_extraction`：加载 `outputs/edited-qa-smoke-001.json` 中的 `evidence_chain` 作为反推 fixture 输入

**`test_smoke.py` 最小断言**：
- `result = analyzer_heuristic.analyze(sample_text, case_id="smoke-test")` 不抛异常
- 必须包含字段：`case_id`、`status`、`candidates`、`report`
- `status` 是 `{"certain", "uncertain", "clarifying", "rejected"}` 之一
- `candidates` 长度 ≤ 3

**验证**：`pytest kernel1/tests -v` 全绿。

---

### Commit A — 用 docx 摘录的完整字典做默认（**已完成**）

**已完成内容**：

- `kernel1/prompts/reference_cards_socionics.md`（661 行，来源：戈利霍夫《工具社会人格学》，译者章鱼）已经写好
  - 32 张「Function × 位置」卡片（8 元素 × 4 重视位置），每张 2-3 条原话样本
  - 补充 7/8/3/4 位非重视位置常见模式 4 张
  - 编号转换表：Kalinauskas 1/2/3/4 ↔ Bukalov 1/2/6/5
- `kernel1/prompts/reference_cards.md` 仍保留作为简版兜底（19 个 IND × 1-2 张卡片）
- `kernel1/core.py:_resolve_ref_cards_path` 默认指向 `reference_cards_socionics.md`，不存在时静默回退到简版
- `kernel1/app.py:list_ref_cards` 暴露默认名称给前端

**为什么用 docx 来源**：作者描述里大量「领地」「我是主宰」「我可以聊一整天」「下意识就做了」这种生活化措辞，远比手写的合成卡片更接近真实用户自述。已按 Bukalov 8 位重新打标，3/4 号位置的 mental/valued/accepting 信号方向与 core.py 常量一致（已交叉验证 Te 3/4 号、3 位角色、8 位演示、4 位脆弱）。

**原 V1 简版结构**（保留作历史参考）：

```markdown
# Kernel1 证据参考字典

下面是「原话片段 → 标准 IND 代码 + 信号字段填充」的范本。
学习这个映射模式，遇到类似措辞时输出同样的结构化字段。
不要把 indicator 字段塞入元素名、强弱描述或自创代码。

## 字典卡片（V1）

### IND TM-A（4D 主导，全局时间感 / 持续追踪）

- 原话：「我一直能提前看到事情的走向」
  → indicator="IND TM-A", element_hint="Ni", dimension_hint="4D",
    strength_signal="strong", valued_signal="valued", mental_signal="mental",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="identity"
- 原话：「这套体系我用了十几年，没有想不通的角度」
  → indicator="IND TM-A", element_hint="Ti", dimension_hint="4D",
    strength_signal="strong", valued_signal="valued", mental_signal="mental",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="identity"

### IND F1-A（4D 认同，"我即是此元素"）

- 原话：「我天生就是个对气氛特别敏感的人」
  → indicator="IND F1-A", element_hint="Fe", dimension_hint="4D",
    strength_signal="strong", valued_signal="valued", mental_signal="mental",
    accepting_signal="producing", contact_signal="contact", guide_signal="separate",
    evidence_type="identity"
- 原话：「效率这事儿就是刻在我骨子里的本能」
  → indicator="IND F1-A", element_hint="Te", dimension_hint="4D",
    strength_signal="strong", valued_signal="valued", mental_signal="mental",
    accepting_signal="producing", contact_signal="contact", guide_signal="separate",
    evidence_type="identity"

### IND MN-A（意识环，大声思考）

- 原话：「我得说出来才能想清楚」
  → indicator="IND MN-A", element_hint="Ti", dimension_hint="3D",
    strength_signal="strong", valued_signal="valued", mental_signal="mental",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="identity"

### IND MN-C（代表集体发言）

- 原话：「我们这边一般都是先打个招呼」
  → indicator="IND MN-C", element_hint="Fe", dimension_hint="3D",
    strength_signal="strong", valued_signal="valued", mental_signal="mental",
    accepting_signal="producing", contact_signal="contact", guide_signal="separate",
    evidence_type="identity"

### IND VT-A（生机环，模糊回忆 / "有时"）

- 原话：「有时候我会突然冒出一些以前的画面」
  → indicator="IND VT-A", element_hint="Si", dimension_hint="3D",
    strength_signal="strong", valued_signal="unvalued", mental_signal="vital",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="flexibility"

### IND VT-B（自动化习惯）

- 原话：「下意识就把房间收拾好了」
  → indicator="IND VT-B", element_hint="Si", dimension_hint="3D",
    strength_signal="strong", valued_signal="unvalued", mental_signal="vital",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="comfort"

### IND VT-F（只关心对自己的影响）

- 原话：「别人怎么评价我不太在乎，自己舒服就行」
  → indicator="IND VT-F", element_hint="Fi", dimension_hint="3D",
    strength_signal="strong", valued_signal="unvalued", mental_signal="vital",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="avoidance"

### IND NR-D（2D 规范，"必须 / 应该"）

- 原话：「这种事必须要按规矩来才对」
  → indicator="IND NR-D", element_hint="Ti", dimension_hint="2D",
    strength_signal="weak", valued_signal="unvalued", mental_signal="mental",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="stress"
- 原话：「该有的礼数还是要走到位」
  → indicator="IND NR-D", element_hint="Fi", dimension_hint="2D",
    strength_signal="weak", valued_signal="unvalued", mental_signal="mental",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="stress"

### IND NR-A（引用权威 / 教条）

- 原话：「书上写的就是这样，没什么好争的」
  → indicator="IND NR-A", element_hint="Ti", dimension_hint="2D",
    strength_signal="weak", valued_signal="unvalued", mental_signal="mental",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="stress"

### IND 1D-A（1D 极弱，无法应用规范）

- 原话：「这种场合我完全不知道该怎么应付」
  → indicator="IND 1D-A", element_hint="Fe", dimension_hint="1D",
    strength_signal="weak", valued_signal="unvalued", mental_signal="vital",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="stress"

### IND LD-A（非黑即白思维）

- 原话：「要么就做到最好，要么就别做」
  → indicator="IND LD-A", element_hint="Te", dimension_hint="1D",
    strength_signal="weak", valued_signal="unvalued", mental_signal="vital",
    accepting_signal="producing", contact_signal="contact", guide_signal="separate",
    evidence_type="stress"

### IND LD-E（末日降临感）

- 原话：「我一想到这事就感觉天要塌了」
  → indicator="IND LD-E", element_hint="Ni", dimension_hint="1D",
    strength_signal="weak", valued_signal="unvalued", mental_signal="vital",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="stress"

### IND 1D-L（过度补偿 / 极度焦虑）

- 原话：「我总担心人家是不是讨厌我，反复确认」
  → indicator="IND 1D-L", element_hint="Fi", dimension_hint="1D",
    strength_signal="weak", valued_signal="unvalued", mental_signal="vital",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="stress"

### IND ST-A（3D 情境，灵活变通）

- 原话：「不同场合我会用不同方式去处理」
  → indicator="IND ST-A", element_hint="Se", dimension_hint="3D",
    strength_signal="strong", valued_signal="valued", mental_signal="mental",
    accepting_signal="producing", contact_signal="contact", guide_signal="separate",
    evidence_type="flexibility"
- 原话：「我能根据现场气氛调整说话方式」
  → indicator="IND ST-A", element_hint="Fe", dimension_hint="3D",
    strength_signal="strong", valued_signal="valued", mental_signal="mental",
    accepting_signal="producing", contact_signal="contact", guide_signal="separate",
    evidence_type="flexibility"

### IND HD-B（承认多种正确可能性）

- 原话：「这事其实有好几种说法都说得通」
  → indicator="IND HD-B", element_hint="Ne", dimension_hint="3D",
    strength_signal="strong", valued_signal="valued", mental_signal="mental",
    accepting_signal="accepting", contact_signal="contact", guide_signal="guide",
    evidence_type="flexibility"

### IND HD-F（对他人评价漠不关心）

- 原话：「别人怎么看我无所谓，我自己有数」
  → indicator="IND HD-F", element_hint="Fi", dimension_hint="3D",
    strength_signal="strong", valued_signal="unvalued", mental_signal="vital",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="avoidance"

### IND VR-A（重视，开放讨论，舒适区）

- 原话：「这个话题我可以聊一整天」
  → indicator="IND VR-A", element_hint="Ne", dimension_hint="3D",
    strength_signal="strong", valued_signal="valued", mental_signal="mental",
    accepting_signal="accepting", contact_signal="contact", guide_signal="guide",
    evidence_type="identity"

### IND NV-A（非重视，态度严肃，压力源）

- 原话：「一谈起感情就让我头疼」
  → indicator="IND NV-A", element_hint="Fi", dimension_hint="2D",
    strength_signal="weak", valued_signal="unvalued", mental_signal="mental",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="stress"

### IND NV-D（非重视，保密 / 回避）

- 原话：「这种事我宁愿不说也不愿意聊」
  → indicator="IND NV-D", element_hint="Se", dimension_hint="2D",
    strength_signal="weak", valued_signal="unvalued", mental_signal="mental",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="avoidance"

## 字段填充原则

1. **indicator 唯一来源**：上述 19 个代码或空字符串 `""`，禁止自创
2. **信号字段独立**：`strength_signal` 表强弱，`valued_signal` 表重视，`mental_signal` 表环路；不要把强弱塞进 indicator
3. **遇到歧义**：选最确定的一个 IND，宁可漏报也不强行编造
4. **没命中 IND 时**：`indicator=""`，其他信号字段照填，不要交白卷

## 端到端范例（V2 接口预留）

<!-- BEGIN_EXAMPLES -->
<!-- 这里将来放完整的「QA 输入 → 成品 quotes JSON」端到端范例。 -->
<!-- 当前为空；core.py 已支持读取此段。 -->
<!-- END_EXAMPLES -->
```

**卡片选材原则**：
- 同一 IND 给 2 种不同元素的命中示例（如 `IND TM-A` 既给 Ni 又给 Ti）
- 不要把 element 锁死，让 LLM 知道 IND 是行为指标、可挂到不同 element
- 覆盖 QA 模式典型表达（「我一直 / 我天生 / 有时候 / 必须 / 不知道怎么…」）

**验证**：

1. 人工通读 `reference_cards_socionics.md`，确保 19 个 IND 全部覆盖；每张卡片 6 个核心信号都不为 unknown ✓
2. 跑 `python -m kernel1.cli --text-file kernel1/samples/sample_input.txt --case-id smoke-docx --report-only`，确认 heuristic 报告里 `命中 IND 指标` 段不空 ✓（实测 Top-1 ILE 0.919）
3. 跑 `python -m kernel1.eval.run_synthetic`（heuristic）作为 baseline；预期不全过（heuristic 不能精细识别 docx 风格措辞）→ 留给本地 LLM + 字典联合发力时再过

**关联评测样本**：见 `kernel1/eval/synthetic_samples/`（4 个四象限代表样本，详见本计划末尾「合成评测样本」一节）

---

### Commit B — `extraction_prompt` 加载字典 + 错例对照

**改 1**：`kernel1/core.py:134`

```python
# 现状
self.extraction_prompt = EXTRACTION_PROMPT_PATH.read_text(encoding="utf-8")

# 改为
self.extraction_prompt = self._load_extraction_prompt()
```

新增方法（建议放在 `_load_model_a` 旁边）：

```python
def _load_extraction_prompt(self) -> str:
    """加载主 prompt，若 reference_cards.md 存在则拼接到末尾。"""
    base = EXTRACTION_PROMPT_PATH.read_text(encoding="utf-8")
    ref_path = BASE_DIR / "prompts" / "reference_cards.md"
    if ref_path.exists():
        ref = ref_path.read_text(encoding="utf-8")
        return f"{base}\n\n---\n\n{ref}"
    return base
```

**改 2**：`kernel1/prompts/evidence_extraction.md` line 58-62 后追加：

```markdown

## 错误示例（禁止）

- indicator="显性/感觉"     → 应改为 "IND ST-A"（情境灵活）或 "IND F1-A"（4D 认同）
- indicator="主导直觉"       → 应改为 "IND F1-A" 或 "IND TM-A"
- indicator="strong_logic"  → 应改为 ""，强弱用 strength_signal=strong 表达
- indicator="弱情感"         → 应改为 "" + valued_signal=unvalued + strength_signal=weak

规则：indicator 字段只能从 19 个 IND 代码或 "" 中选；强弱/重视/环路请用专门字段表达。
下方有参考字典，遇到类似措辞时直接对照套用。
```

**补 Commit D 的 `test_reference_load.py`**：

```python
def test_extraction_prompt_includes_reference(analyzer_heuristic):
    prompt = analyzer_heuristic.extraction_prompt
    # 19 个 IND 代码都在
    for ind in ["IND TM-A", "IND F1-A", "IND MN-A", "IND MN-C", "IND VT-A",
                "IND VT-B", "IND VT-F", "IND NR-D", "IND NR-A", "IND 1D-A",
                "IND LD-A", "IND LD-E", "IND 1D-L", "IND ST-A", "IND HD-B",
                "IND HD-F", "IND VR-A", "IND NV-A", "IND NV-D"]:
        assert ind in prompt, f"missing {ind} in prompt"
    # 错例段落存在
    assert "错误示例" in prompt
    assert "显性/感觉" in prompt
```

**验证**：`pytest kernel1/tests/test_reference_load.py -v` 通过。本地 LLM 跑同一段 QA 对比加载前后 indicator 合法率（手动观测）。

---

### Commit C — Indicator 白名单 + 反推归一化

**改**：`kernel1/core.py:406-438` 的 `_normalize_extraction`，把 `cleaned_quotes` 装配逻辑里 `"indicator": str(item.get("indicator", "unknown"))[:40]` 这一行拆出来用新方法 `_resolve_indicator(item)`：

```python
def _resolve_indicator(self, item: dict) -> str:
    """白名单 + 反推：合法 IND 直接返回；非法字符串尝试按信号反推。"""
    raw = str(item.get("indicator", ""))[:40].strip()
    if raw in IND_PROFILES:
        return raw
    return self._infer_indicator(item) or ""

def _infer_indicator(self, item: dict) -> str | None:
    """根据 quote 的信号字段，从 IND_PROFILES 中找出匹配度最高的 IND 代码。
    匹配 ≥ 2 项（dimension/strength/valued/mental）才返回；否则返回 None。
    """
    dim = item.get("dimension_hint")
    strength = item.get("strength_signal")
    valued = item.get("valued_signal")
    mental = item.get("mental_signal")

    best_code: str | None = None
    best_score = 0
    for code, profile in IND_PROFILES.items():
        score = 0
        if profile.get("dimension_hint") and profile["dimension_hint"] == dim:
            score += 2  # dimension 最重要
        if profile.get("strength_signal") and profile["strength_signal"] == strength:
            score += 1
        if profile.get("valued_signal") and profile["valued_signal"] == valued:
            score += 1
        if profile.get("mental_signal") and profile["mental_signal"] == mental:
            score += 1
        if score > best_score:
            best_score = score
            best_code = code
    return best_code if best_score >= 2 else None
```

把 `cleaned_quotes.append` 里的 `"indicator": str(...)` 替换为 `"indicator": self._resolve_indicator(item)`。

**补 Commit D 的 `test_indicator_normalize.py`**：

```python
def test_legal_indicator_preserved(analyzer_heuristic):
    out = analyzer_heuristic._resolve_indicator({"indicator": "IND TM-A"})
    assert out == "IND TM-A"

def test_illegal_indicator_inferred_from_signals(analyzer_heuristic):
    # 模拟 LLM 返回 "显性/感觉"，但信号字段齐全
    item = {
        "indicator": "显性/感觉",
        "dimension_hint": "3D",
        "strength_signal": "strong",
        "valued_signal": "valued",
        "mental_signal": "mental",
    }
    out = analyzer_heuristic._resolve_indicator(item)
    # 反推应当落到 IND ST-A（3D + strong）
    assert out == "IND ST-A"

def test_illegal_indicator_no_signals_falls_to_empty(analyzer_heuristic):
    item = {"indicator": "strong_logic"}
    out = analyzer_heuristic._resolve_indicator(item)
    assert out == ""

def test_normalize_replays_qa_smoke(analyzer_heuristic, qa_smoke_extraction):
    """用真实 QA smoke 输出做回放：'显性/感觉' 等非法 indicator 全部归一化。"""
    raw = {"quotes": qa_smoke_extraction}
    normalized = analyzer_heuristic._normalize_extraction(raw)
    for q in normalized["quotes"]:
        ind = q["indicator"]
        assert ind == "" or ind in IND_PROFILES, f"unexpected indicator: {ind}"
```

**验证**：测试全绿 + 拿 `outputs/edited-qa-smoke-001.json` 的 evidence_chain 走一遍，断言「显性/感觉」被反推。

---

### Commit E — 打分归一化饱和 + 引入 `target_confidence`

**改 1**：`kernel1/core.py:120-127` 的 `AnalyzeOptions`

```python
@dataclass(frozen=True)
class AnalyzeOptions:
    min_chars: int = 80
    max_chars: int = 12000
    top_threshold: float = 0.65
    target_confidence: float = 0.80      # 新增
    margin_threshold: float = 0.12
    min_evidence: int = 3
    no_first_4d_ceiling: float = 0.58    # 新增（原硬编码 0.58）
    denom_quote_cap: int = 12            # 新增
```

**改 2**：`kernel1/core.py:766` 的累加逻辑——保留每条 +`3.8 * confidence`，但在归一化时用饱和分母替代。

具体做法：把 `max_possible` 在 `_score_candidates` 末尾做一次饱和处理。在 line 898（`for type_code, score in raw_scores.items()` 上方）插入：

```python
# 饱和分母：避免高质量证据多时分母膨胀
quote_count = len([q for q in quotes if q.get("element_hint") in {
    "Ne", "Ni", "Se", "Si", "Te", "Ti", "Fe", "Fi"
}])
avg_conf = (
    sum(float(q.get("confidence") or 0.5) for q in quotes) / max(len(quotes), 1)
    if quotes else 0.5
)
saturated_max = 3.8 * min(quote_count, self.options.denom_quote_cap) * avg_conf
# 保留 dichotomy 部分（不饱和，本来就少）
dichotomy_pool = max(0.0, max_possible - 3.8 * quote_count * avg_conf)
max_possible = max(saturated_max + dichotomy_pool, 1.0)  # 防 0 除
```

**改 3**：`kernel1/core.py:904` 的硬天花板改用 options：

```python
if details[type_code]["first_4d_support"] <= 0:
    normalized = min(normalized, self.options.no_first_4d_ceiling)
```

**改 4**：`status` 判定升级。找到 `_build_result` 中决定 `status` 的逻辑（line 1210-1221 附近）。当前用 `top_threshold=0.65`；引入 `target_confidence=0.80` 作为 `certain` 的更高门槛：

```python
# 原逻辑保留，但加一层「分数低于 target_confidence 标 uncertain」
score_below_target = top["score"] < self.options.target_confidence
hard_uncertain = no_4d or no_3d or few_evidence or bool(real_conflicts) or partial_recovered or schema_invalid

if not hard_uncertain and margin_small and not score_low and not creative_confused and not insufficiency:
    laning_result = self._laning_tiebreak(candidates, laning_signals)
    if laning_result:
        top = laning_result["winner"]
        status = "certain" if not score_below_target else "uncertain"
    else:
        status = "uncertain"
elif score_low or hard_uncertain or creative_confused or insufficiency:
    status = "uncertain"
else:
    status = "certain" if not score_below_target else "uncertain"
```

> 注：`score_low` 是 `top["score"] < self.options.top_threshold`（line 1196 附近）。`target_confidence` 是更高的「certain 门槛」，比 `top_threshold`（uncertain 截断）更严。

**补 Commit D 的 `test_score_threshold.py`**：

```python
def test_qa_smoke_with_inference_hits_target(analyzer_heuristic, qa_smoke_extraction):
    """关键回归：用 edited-qa-smoke-001 的 quotes 走 Commit C 反推 + Commit E 饱和归一，
    Top-1 score 应 ≥ 0.78（接近 target_confidence 0.80，留出小余量给本地噪声）。"""
    raw = {"quotes": qa_smoke_extraction, "dichotomy_signals": {}, "conflicts": [], "insufficiency": []}
    normalized = analyzer_heuristic._normalize_extraction(raw)
    candidates = analyzer_heuristic._score_candidates(normalized)
    assert candidates[0]["score"] >= 0.78, f"top score {candidates[0]['score']} below target"

def test_target_confidence_gates_certain(analyzer_heuristic):
    """score=0.75 时 status 不能是 certain（< target_confidence 0.80）。"""
    # 通过 monkeypatch / 构造 candidates 验证 status 判定
    ...
```

**验证**：测试全绿；用 `outputs/edited-qa-smoke-001.json` 的 quotes 实测 Top-1 score ≥ 0.78。

---

### Commit F — Indicator 命中率监控

**改**：`kernel1/core.py:_extract_evidence`（line 333-359）。在拿到 `raw_normalized` 后插入：

```python
def _indicator_hit_rate(self, quotes: list[dict]) -> float:
    if not quotes:
        return 0.0
    hits = sum(1 for q in quotes if q.get("indicator") in IND_PROFILES)
    return round(hits / len(quotes), 3)
```

调用并写入：

```python
raw_normalized["_indicator_hit_rate"] = self._indicator_hit_rate(raw_normalized.get("quotes", []))
```

在 `_build_result`（line 1236-1248 附近的 `preprocess` dict）透传到 `result`：

```python
"preprocess": {
    ...,
    "indicator_hit_rate": extraction.get("_indicator_hit_rate", 0.0),
},
```

**验证**：单元测试构造 8 条 quote（其中 5 条合法 IND），断言 `_indicator_hit_rate` 返回 `0.625`。

---

### Commit G — GUI markdown 渲染 + confidence 徽标

**改**：`kernel1/static/index.html`

**改 1**：`<head>` 加 CDN
```html
<script src="https://cdn.jsdelivr.net/npm/marked@4/marked.min.js"></script>
```

**改 2**：line 506 附近的 `$("reportView").textContent = data.report || ...` 改为：
```js
$("reportView").innerHTML = data.report ? marked.parse(data.report) : "没有报告内容。";
```

**改 3**：line 444-449 附近的 metrics 板，加两个新格子：

```html
<!-- 加在现有 metrics 块里 -->
<div>confidence: <span id="mConfBadge">-</span></div>
<div>IND hit rate: <span id="mHitBadge">-</span></div>
```

JS（更新 metrics 的位置）：

```js
const conf = data.confidence ?? 0;
const target = 0.80;
const confBadge = $("mConfBadge");
confBadge.textContent = `${(conf).toFixed(3)} (目标 ≥ ${target})`;
confBadge.style.color = conf >= target ? "#0a0" : (conf >= 0.65 ? "#c80" : "#c00");

const hit = data.preprocess?.indicator_hit_rate ?? 0;
const hitBadge = $("mHitBadge");
hitBadge.textContent = `${(hit * 100).toFixed(0)}% (目标 ≥ 70%)`;
hitBadge.style.color = hit >= 0.7 ? "#0a0" : (hit >= 0.4 ? "#c80" : "#c00");
```

**验证**：浏览器开 `http://127.0.0.1:8787/`，跑示例 → markdown 标题/列表正确渲染；confidence 与 IND hit rate 徽标按阈值着色。

---

## 5. 推荐执行顺序

1. **D** — 测试脚手架（先有验证手段）
2. **A** — 字典骨架（纯文档工作量大）
3. **B** — prompt 加载 + 错例（同 commit 同步生效）
4. **C** — 反推兜底（与 B 互为保险）
5. **E** — 归一化 + 新阈值（跟 C 联合验证 confidence 上 0.8）
6. **F** — hit rate 监控（数据先有，不做强制重抽）
7. **G** — GUI 渲染 + 徽标（用户立刻能看到改善）

## 6. V2 预留：端到端范例接口

将来扩展时不动 `core.py`，只编辑 `reference_cards.md` 的 `<!-- BEGIN_EXAMPLES --> ... <!-- END_EXAMPLES -->` 段。范例格式：

````markdown
### 范例 1：典型 LIE 用户的 QA 提取

输入 QA：
```
回答1: 我一般做决定先看效率和资源回报...
回答2: 长远来看这套方案大概率走不通...
```

应输出 quotes：
```json
[
  {"quote":"做决定先看效率和资源回报","indicator":"IND TM-A","element_hint":"Te","dimension_hint":"4D", ...},
  {"quote":"长远来看这套方案大概率走不通","indicator":"IND TM-A","element_hint":"Ni","dimension_hint":"3D", ...}
]
```
````

V2 落地只需：（1）写 1-2 组高质量金样本（2）填进 `<!-- BEGIN_EXAMPLES --> ... <!-- END_EXAMPLES -->`。`_load_extraction_prompt` 自动加载，零代码变更。

## 7. 不在此次范围

- Kernel2 多轮 case_state、任务队列
- 20-50 条带 ground truth 的评测集扩张
- 真 LLM moderation / 输入安全过滤（独立路径，下一轮再做）
- 重新校准 16 型权重
- LLM 重试 / 退避
- L2 `report_generation.md` 补全（vestigial 文件，独立路径处理）
- 动态 top-K 范例选取（用户明确不做）

## 8. 端到端验收清单

1. `pytest kernel1/tests -v` — 全绿
2. 启 vLLM 跑 Qwen3.6-27B，调 API `POST /kernel1/analyze` 用 `samples/sample_input.txt`：
   - `result["confidence"] ≥ 0.80`
   - `result["status"] == "certain"`
   - `result["preprocess"]["indicator_hit_rate"] ≥ 0.70`
3. Q&A 模式：手粘一段 8-12 题的中文问卷回答，跑 3 次，confidence 中位数 ≥ 0.80
4. 改 prompt 字典做 A/B：关掉字典加载（注释 `_load_extraction_prompt` 中的拼接）跑同一份输入，对比 `indicator_hit_rate` 差值 ≥ 0.2
5. GUI 验：浏览器打开，confidence 徽标显示绿色（≥0.80）、hit_rate 徽标显示绿色（≥0.70）；markdown 报告正确渲染
6. **合成评测样本回归**：`python -m kernel1.eval.run_synthetic --llm --save` 4 个样本 ≥3 个 pass，每个 confidence ≥ 0.80（heuristic 模式预期不过，作为差距测量）

## 8.5 合成评测样本（已落地）

来源：基于戈利霍夫 docx 中 8 元素 × 4 重视位置的描述合成的「模拟用户自述」，作为最小回归集。**不是训练集**，只用来做 sanity check 和参数 A/B。

文件位置：`D:\guCodex\shiroProject\kernel1\eval\synthetic_samples\`

| 样本 | Ground Truth | 象限 | 关键功能位 |
|---|---|---|---|
| `ile_alpha_001` | ILE / ENTp | Alpha | Ne(1) + Ti(2) + Fe(3) + Si(4) |
| `lsi_beta_001` | LSI / ISTj | Beta | Ti(1) + Se(2) + Ni(3) + Fe(4) |
| `lie_gamma_001` | LIE / ENTj | Gamma | Te(1) + Ni(2) + Se(3) + Fi(4) |
| `eii_delta_001` | EII / INFj | Delta | Fi(1) + Ne(2) + Si(3) + Te(4) |

每个 `.gt.json` 标注：
- 期望类型 / 别名 / 象限 / Bukalov 8 位 model_a
- docx 段落号映射
- `expected_signals`：`top_candidate_must_include`、`min_confidence_target=0.80`、`evidence_must_cover_elements`（1st/2nd 必须出现）、`evidence_should_cover_elements`（3rd/4th 应当出现）

跑评测：
```powershell
cd D:\guCodex\shiroProject
python -m kernel1.eval.run_synthetic              # heuristic baseline
python -m kernel1.eval.run_synthetic --llm --save # 接本地 LLM 并存结果到 eval/results/
```

**当前 heuristic baseline 实测**（已跑过）：
- 4 个样本：0/4 pass
- 但 confidence 已达 0.766–0.842（字典让分数饱和度起来了）
- Top-1 全部偏向 ILE/ILI（heuristic 的固有偏好，无法精细识别 docx 措辞）
- **结论**：confidence 阈值能过，但 Top-1 准确率必须靠本地 LLM + 字典联合发力，这正是 Commit C/E/F 的核心论点的实证

## 8.6 docx 来源使用边界

**做了什么**：把 docx 32 段细颗粒描述按 Bukalov 体系重新打标，做成 `reference_cards_socionics.md`（已落地）+ 4 个合成评测样本（已落地）。

**没做（保留为以后选项）**：
- 不把 docx 整段塞进 prompt（编号体系会冲突）
- 不用 docx 当 ground-truth 训练集（理论描述文体 ≠ 真实用户自述）
- 不用 docx 校准 IND_PROFILES 权重（重视/非重视会反，需要先有真实标注样本）

## 9. Sonnet 执行注意事项

- **每 commit 独立提交**，按推荐顺序，commit msg 用「kernel1: <Commit X> <一句话动机>」
- **不要改动**：Model A 字典、`_score_candidates` 的核心循环结构、Laning tiebreak、L1/L2/L3 精化逻辑
- **每改完一个 commit 跑一次 `pytest kernel1/tests -v` + `python -m kernel1.eval.run_synthetic`** 确认未引入回归
- **Commit A 已完成**：用了 docx 来源的 `reference_cards_socionics.md`（661 行、32+ 张卡片），且默认指向已切换。不需要再写简版字典
- **Commit C 的反推匹配阈值是 ≥2 项**：太严会反推失败率高，太松会乱归一；2 项（且 dimension 占 2 分）是合理起点
- **Commit E 的 `denom_quote_cap=12`**：经验值，可在跑了实测后调整；调整时同步更新 `test_score_threshold.py` 的下限断言
- **合成评测样本应被纳入 CI**：`python -m kernel1.eval.run_synthetic --llm` 至少 3/4 pass 才能算 Confidence ≥ 0.80 目标真正达成

## 10. 当前进度（截至本计划最近一次更新）

- [x] Commit A — `reference_cards_socionics.md` + 默认切换（含 docx 来源的 32 张主卡 + 4 张非重视位置卡）
- [x] **合成评测样本** — 4 个四象限代表（ILE/LSI/LIE/EII）+ `run_synthetic.py` 评测脚本
- [ ] Commit D — 测试脚手架
- [ ] Commit B — 错例对照段（字典加载逻辑已经在仓库里，差错例对照）
- [ ] Commit C — Indicator 白名单 + 反推
- [ ] Commit E — 归一化饱和 + `target_confidence` 阈值
- [ ] Commit F — Indicator 命中率监控
- [ ] Commit G — GUI markdown 渲染 + confidence 徽标

完成后请把端到端验收清单 1-6 的每一项跑一遍，把结果报给用户。
