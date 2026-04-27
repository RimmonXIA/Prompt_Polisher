# Prompt Polisher — 架构白皮书

**阅读说明：** 所有详尽的底层理论推导、严格的证据等级划分以及完整的文献引用地图，均收录于 **[THEORY.zh.md](THEORY.zh.md)**。本文档作为架构层面的“过渡桥梁”，旨在帮助开发者快速理解系统设计的核心哲学与严格的边界。

---

## 1. 核心哲学与严格边界

我们不将提示词工程视为简单的“单次文本重写”。相反，Prompt Polisher 旨在对大模型的**注意力分配**、**测试时算力 (Test-time compute，如思维链架构)**、**输出分布/解码**以及**安全边界**进行**结构化干预**。

### 我们的系统架构
本代码库实现了一条**多节点 LangGraph 协作管线**：意图嗅探雷达 (Intent Sniffer) → 可选的安全中止闸门 (Safety Gate) → 算力感知路由 (Compute-Aware Router) → 结构化编译器 (Structured Compiler) → 红队审查员 (Red-Team Critic，含可选的标量打分机制) → 产物分发器 (Artifact Dispatcher)。

### 局限性与非承诺 (Non-claims)
- **没有绝对的安全保证：** 任何模板、XML 沙盒或基于启发式规则的 Critic 机制，都**无法**替代专业的威胁建模、风控监控与组织级安全策略。
- **不提供形式化验证：** 在金融、医疗、法律等需要强形式化、可审计正确性保证的高危领域，切勿将本工具作为*唯一*的防线。
- **不内置约束解码：** 如果您需要严格的语法/Logit 掩码控制，请在下游的解码器栈中实现。本项目**仅产出文本层面的制品**，未内置类似 Outlines 的推理引擎。
- **表现因模型而异：** 标签、工具与格式约束的具体表现，天然受限于不同的模型供应商、底层模型版本及您下游的 API 配置。

---

## 2. 架构体系与角色纪律 (Persona Discipline)

在编写复杂提示词时，最致命的失败模式是“身份环路 (Identity Loops)”——即大模型混淆了用户的意图、系统的指令以及它自身的角色设定。为杜绝此问题，本系统严格划分了以下 5 大实体：

1. **调用方/发起者 (Invoker)**: 触发 CLI 或 API 的人类用户或自动化代理。
2. **作者 (Author)**: 原始意图 `raw_prompt` 的提出者（用于信任策略追踪）。
3. **编排器 (Orchestrator, 即 Prompt Polisher 本身)**: 运行 LangGraph 编译管线的核心。它严格扮演**架构分析师**的角色，仅以中立的“第三人称”视角审视当前任务，**绝不**在此阶段进行最终助手的角色扮演 (role-play)。
4. **推理引擎 (Inference Engine)**: 通过 LiteLLM 驱动内部推理节点（雷达、编译器等）的算力源。
5. **执行目标 (Target / Executor)**: 最终接收并运行 `final_prompt` 的下游大模型。

### 角色纪律 (The Persona Discipline)
编译器在生成的草稿中强制执行极为严苛的人称代词管控，以保持绝对隔离：
- **客观简报 (Task Context)**: 必须使用**中立的第三人称分析**（例如：“此任务要求……”）向目标模型进行简报，严防编排器的内部主观声音泄露。
- **指令集 (Direct Instructions)**: 必须使用**第二人称祈使句**对执行目标下达指令（例如：“你是……”、“你必须……”）。
- **编排器隐身 (Orchestrator Invisibility)**: 编排器（流水线本身）的私有推理过程严禁出现在最终制品中。如果编排器的第一人称视角泄露（例如：“作为编译器，我认为……”），将被视为严重的系统性错误。

---

## 3. 编译管线 (The Compilation Pipeline)

编排器驱动的多 Agent 工作流遵循以下 6 步离散路径：

1. **意图嗅探雷达 (Intent Sniffer)** — 执行意图解构，评估对齐/注入风险，并将 JSON 格式的分析结果合并至全局图状态中。
2. **安全中止闸门 (Safety Gate)** — 配置驱动的提前阻断机制。如果雷达探测到严重威胁，编译将立即中止。
3. **算力感知路由 (Compute-Aware Router)** — 推荐适用的多节点结构，评估任务复杂度，并提供角色与风格锚定建议。
4. **结构化编译器 (Structured Compiler)** — 组装 `compiler_draft`，实施 XML 沙盒隔离、空间位置强化（首尾强调），并注入 `<task_context>` 简报。
5. **红队审查员 (Red-Team Critic)** — 根据角色纪律和安全约束对草稿进行多轮审查。*（例如：一旦审查员发现草稿中混入了编排器的第一人称声音，将立即拦截并打回重置）。*
6. **产物分发器 (Artifact Dispatcher)** — 格式化最终交付物，支持文本、LangGraph 工作流蓝图及 DSPy 代码草图。

### 雷达内部视角 (JSON 解析)
雷达生成的关键元数据将直接指导后续的编译走向：

| 字段 | 含义简述 |
| --- | --- |
| `negations_flipped` | 将用户的负向约束强制转化为正向动作的重述表达。 |
| `threats` | 启发式的威胁标签列表（如探测到的注入信号），为闸门策略提供依据。 |
| `alignment_risk` | 粗粒度的安全风险评级（`low`/`medium`/`high`），决定结构防范的严厉程度。 |
| `summary` | 自然语言的意图摘要；触发阻断时会附加至 `abort_detail`。 |

---

## 4. 理论范围与代码实现映射

Prompt Polisher 将业界成熟的 LLM 实证研究转化为代码库中可落地的干预手段。

| 理论关注点 | 本项目实现路径 | 超出本项目范围 (常在下游或学术界) |
| --- | --- | --- |
| **输入 / 注意力层** (否定失效、U型注意力衰减) | 雷达执行正向化改写；编译环节通过条件提示实施首尾位置强化。 | RULER 级别的超长上下文完整复现评测。 |
| **测试时算力 / TTS** (单次调用算力不足) | 注入 `<task_context>` 结构扩展推理空间；在草稿中写入 ICL (少样本学习) 格式示范。 | 完整的多轨迹采样执行器；ICL 原理的普适性定论。 |
| **采样与格式** (解析故障) | 在路由/编译内部调用原生的 `response_format={"type": "json_schema"}`。 | 类似 Outlines 的有限状态机 (FSM) 约束解码。 |
| **闭环搜索** (自回归误差放大) | 红队审查员的 FAIL→重试 回路 (`MAX_CRITIC_ITERATIONS`)；可选的标量打分闸门。 | 完整的基于验证器引导的树搜索 (Tree Search) 栈。 |
| **隐流形 / 风格** (输出空洞平庸) | 注入 `anchor_persona`；实施启发式的词汇升维干预。 | 可进行几何测量的流形“投影”。 |
| **对齐与对抗** (过度拒绝、越狱攻击) | 雷达输出 `alignment_risk` 标签；执行 XML 沙盒隔离；配置闸门阻断策略。 | CaMeL 式的物理架构隔离；自适应攻击基准测试。 |
| **自动化与优化** (手工调参成本高) | 提供工作流蓝图分发；输出 DSPy 纯文本草图。 | 可训练的连续软提示；运行完整的 DSPy 离散优化循环。 |

---

## 5. 生态上下文与参考文献

### 相关工作 (Related Work)
- **[DSPy](https://github.com/stanfordnlp/dspy)** — 声明式的语言模型流水线优化器。Prompt Polisher 会产出与之方向契合的**文本草图**，但自身不执行 DSPy 的循环训练。
- **过程奖励模型 (PRM)** — 可选的 `CRITIC_USE_PRM` 路径是对过程级打分的轻量级、启发式尝试，而非正式训练的 PRM 模型。
- **红队审查循环 (Red-Teaming Loops)** — 在精神上类似于 Reflexion 模式，但受限于离散文本空间的重写与严格的迭代次数上限。
- **[LangGraph](https://github.com/langchain-ai/langgraph)** — 为我们的状态机提供底层驱动的编排框架。

### 核心参考文献

| 主题 | 文献出处 |
| --- | --- |
| 长上下文 U 型位置效应 | Liu et al., [Lost in the Middle](https://aclanthology.org/2024.tacl-1.9/) |
| 风格镜像 / Mimesis 效应 | Jain et al., [arXiv:2509.12517](https://arxiv.org/abs/2509.12517) |
| 下一个 Token 预测机制 (TPG) | Li et al., [PMLR v238](https://proceedings.mlr.press/v238/li24f/li24f.pdf) |
| RULER 系列长度评测 | Hsieh et al., [arXiv:2404.06654](https://arxiv.org/abs/2404.06654) |
| RAG 位置偏见再评估 | Cuconasu et al., [arXiv:2505.15561](https://arxiv.org/abs/2505.15561) |
| 思维链 (Chain-of-thought) | Wei et al., [arXiv:2201.11903](https://arxiv.org/abs/2201.11903) |
| 自洽性 (Self-consistency) | Wang et al., [arXiv:2203.11171](https://arxiv.org/abs/2203.11171) |
| 测试时算力 (Test-time compute) | Snell et al., [arXiv:2408.03314](https://arxiv.org/abs/2408.03314); Agarwal et al., [arXiv:2512.02008](https://arxiv.org/abs/2512.02008) |
| 隐式上下文学习与线性模型 | Akyürek et al., [arXiv:2211.15661](https://arxiv.org/abs/2211.15661) |
| DSPy | Khattab et al., [arXiv:2310.03714](https://arxiv.org/abs/2310.03714) |
| 约束解码机制 | [Outlines](https://github.com/dottxt-ai/outlines) |
| 提示词注入风险分类 | [OWASP LLM01:2025](https://genai.owasp.org/llmrisk/llm01/) |
| 对防御机制的自适应攻击 | Nasr et al., [arXiv:2510.09023](https://arxiv.org/abs/2510.09023) |

---

**一句收束:** Prompt Polisher 是一条**分阶段、可审计的类编译器工作流**，旨在驾驭黑盒大模型。它具备明确的**边界定义**与对前沿技术的**敬畏之心 (Epistemic Humility)**。如需探究更深层的底层机制推导，请阅读 **[THEORY.zh.md](THEORY.zh.md)**。
