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

### IND VT-B(自动化习惯)

- 原话：「下意识就把房间收拾好了」
  → indicator="IND VT-B", element_hint="Si", dimension_hint="3D",
    strength_signal="strong", valued_signal="unvalued", mental_signal="vital",
    accepting_signal="accepting", contact_signal="inert", guide_signal="guide",
    evidence_type="comfort"

### IND VT-F(只关心对自己的影响)

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
