# Prompt Polisher: 大模型提示词编译器

[![CI](https://github.com/RimmonXIA/Prompt_Polisher/actions/workflows/ci.yml/badge.svg)](https://github.com/RimmonXIA/Prompt_Polisher/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![A2A Compliant](https://img.shields.io/badge/A2A-Compliant-success.svg)](https://github.com/a2aproject/A2A)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

🌐 [English](./README.md) | 简体中文

*就像 GCC 将 C 语言编译为确定的机器码，Prompt Polisher 将人类的模糊意图编译为确定的大模型上下文。*

基于 **LangGraph** 的多节点提示词编译流水线：将原始需求重塑为结构化、安全且具备极致性能的高质量指令。专为提示词工程师与自主 Agent 设计。

---

## 💡 Aha Moment

告别那些总是忽略约束条件、随意格式化输出的大模型。

**Before (模糊原始意图):**
> "总结一下这个仓库，帮我写个发布说明，注意要写得好一点。"

**After (经 Prompt Polisher 编译后):**
```xml
<task_context>
The user requires a release note summary for the current repository...
</task_context>
<primary_directive>
Generate a structured release note summary based on the provided repository context.
</primary_directive>
<constraints>
- Maintain a professional and concise tone.
- Do not invent or hallucinate features not present in the context.
- Format the output using markdown headers and bullet points.
</constraints>
```
*(编译器会自动推断隐藏约束、注入结构化锚点，并进行正向化改写以最大化模型服从度。)*

---

## 🚀 为什么选择 Prompt Polisher？

大多数 Prompt 失败的原因在于：缺乏结构、误触负向约束，或者透支了模型单次思考的逻辑极限。Prompt Polisher 从三大支柱切入进行结构化干预：

### ⚡️ 效能跃升 (High-Performance)
- **注意力管理**：通过**首尾强化**对抗大模型的 "Lost in the Middle" 效应，并引入**锚点角色**稳定输出风格与详略。
- **算力优化**：自动注入 `<task_context>` 标签与 ICL (少样本示范)，通过延长上下文序列来换取更高的推理质量。
- **风格增强**：主动检测低熵输入，通过词量提升与结构启动干预，确保目标模型能够镜像出专家级的认知标准。

### 🛡️ 原生安全 (Built-in Safety)
- **威胁雷达**：内置启发式预扫描与模型驱动的意图嗅探器，在执行前精准拦截 Prompt 注入与越狱攻击。
- **沙箱隔离**：使用 **XML 沙盒 (XML Sandboxing)** 确保用户指令与系统指令安全隔离。
- **质量门控**：支持可选的自动化质量打分体系，在劣质结果到达最终用户前进行拦截。

### 🔌 极客体验 (Developer & Agent Native)
- **多轨输出**：除最终 Prompt 外，同时生成供下游自动化使用的 **LangGraph 蓝图** 与 **DSPy 代码草图**。
- **A2A 原生支持**：作为全合规的 **A2A 参与者**，原生支持 JSON-RPC 与 SSE 实时任务委托。
- **多模型兼容**：图内调用经 **LiteLLM** 统一路由，一套代码无缝对接 OpenAI、Anthropic、Gemini、DeepSeek 等所有主流后端。

---

## ⚡ 快速开始

### 1. 安装配置 (Setup)
```bash
# 同步依赖
uv sync --all-groups

# 配置环境变量
cp .env.example .env   # 填写 API Keys (OpenAI, DeepSeek, Claude, Gemini 等)
```

### 2. 使用方法 (Usage)
```bash
# 基础模式: 直接获取编译后的 prompt
uv run prompt-polisher "Summarize this repo for a release note"

# 专业模式: 获取包含完整审计轨迹的 Markdown 报告
uv run prompt-polisher -m "你的原始需求"

# Agent 模式: 输出版本化的 JSON 信封，供自动化脚本解析
uv run prompt-polisher --envelope "你的原始需求"

# 服务模式: 启动 A2A HTTP 服务器
uv run prompt-polisher --serve --port 8000
```

### 3. 示例报告与库内调用
- **样例输出**：[examples/](examples/README.md) 涵盖正常完成、**威胁闸门中止**与**多节点路由**提示。
- **Python 嵌入**：使用 [`run_compiler_async`](src/prompt_polisher/graph.py)，详见 **[docs/CLI_INVOCATION_FLOW.md](docs/CLI_INVOCATION_FLOW.md)**。

---

## 🗺️ 内部工作流 (Workflow Architecture)

在底层，Prompt Polisher 运行着一个多 Agent 的 LangGraph 协作流。它严格扮演**架构分析师**的角色，与最终执行 Prompt 的下游大模型物理隔离，以防止身份混淆。

```mermaid
graph LR
    classDef node fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef critic fill:#fff9c4,stroke:#fbc02d,stroke-width:2px;
    classDef gate fill:#ffebee,stroke:#c62828,stroke-width:2px;
    classDef output fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;

    subgraph A2A_Interface [A2A Protocol 接口层]
        direction LR
        Discovery([/.well-known/agent-card.json])
        JSONRPC[POST /a2a/v1 JSON-RPC]
    end

    Raw([原始输入]) --> JSONRPC
    JSONRPC --> Intent Sniffer[Node 1: 雷达]
    Intent Sniffer --> Gate{威胁闸门}
    Gate -->|中止| Stop([提前终止])
    Gate -->|通过| Route[Node 2: 路由]
    Route --> Compile[Node 3: 编译]
    Compile --> Critic[Node 4: 审查]
    Critic -->|重试| Compile
    Critic -->|通过| Final([最终产物])

    class Intent Sniffer,Route,Compile node;
    class Critic critic;
    class Gate gate;
    class Stop,Final output;
    class Discovery,JSONRPC output;
```

---

## 🛠️ 开发者与自动化指南

### 将 CLI 作为工具协议
对于编码 Agent (如 Cursor) 而言，应将 CLI 视为一个协议：
- **stdout**: 承载主要返回体（文本、Markdown 或 JSON）。
- **stderr**: 承载日志与诊断信息（使用 `--quiet` 减少噪音）。

#### 自动化退出码 (Exit Codes)
| 状态码 | 含义 |
| --- | --- |
| `0` | **成功**: 编译成功结束，且未被威胁闸门中止。 |
| `2` | **中止**: 执行结束，但由于检测到威胁，编译被闸门中止。 |
| `1` | **错误**: 配置有误、I/O 失败或无效的 CLI 调用。 |

#### 数据信封结构 (`--envelope`)
标准 JSON 信封包含：
- `compiled`: 当且仅当未被威胁闸门中止时为 `true`。
- `version`: 当前版本为 `1`。
- `report`: 包含雷达、路由、审查和交付物等完整编译报告。
- `abort_reason`: 成功时为 `null`；被闸门中止时返回错误详情对象。

### 评测基线
`evalsets/bundled/` 提供版本化评测任务。
```bash
uv run prompt-polisher-eval --help
uv run prompt-polisher-eval --structural-only --fail-on-structural
uv run prompt-polisher-eval --output eval-report.json
```

> [!TIP]
> 环境变量设置 `PROMPT_POLISHER_AGENT=1`，可使所有调用默认输出 `--envelope` 格式。

### 核心配置 (Configuration)
位于 `.env` 中的关键设置：
- `LLM_PROVIDER`: `deepseek`（默认）、`openai`、`anthropic` 等。
- `LLM_MODEL`: 目标模型名称（如 `deepseek-v4-pro`）。
- `LLM_API_KEY`: 通用 API 秘钥。
- `AUTHOR_TRUST_MODE`: 设置为 `true` 可针对可信作者禁用严格的安全闸门。
- `CRITIC_USE_PRM`: 启用可选的过程奖励评分门控。
- **Langfuse**: 设置 `LANGFUSE_TRACING=true` 并配置密钥开启链路追踪。

> [!IMPORTANT]
> Prompt Polisher **仅产出文本制品**。它不直接在工具内部执行约束解码 (logits masking) 或采样控制；这些应在您的下游解码器或 API 客户端中配置。

---

## 🤝 A2A 集成

Prompt Polisher 是一个 [全合规 A2A 参与者](https://github.com/a2aproject/A2A) (Agent-to-Agent Protocol)。

- **服务发现**: `uv run prompt-polisher --agent-card` 或访问 `GET /.well-known/agent-card.json`
- **A2A 服务器**: `uv run prompt-polisher --serve --port 8000`
- **服务接口**: 支持 `SendMessage`, `GetTask`, `ListTasks` 以及 `SendStreamingMessage` (SSE)。

---

## 📖 深度理论与长文指南

关于 5 大实体角色划分、详细架构理论及证据声明，请移步专用文档阅读：

| 语言 | 产物 | 适用范围 |
| --- | --- | --- |
| **中文** | [docs/ARCHITECTURE.zh.md](docs/ARCHITECTURE.zh.md) | **架构白皮书**：核心架构哲学、严格的系统边界与编译管线说明。 |
| **中文** | [docs/THEORY.zh.md](docs/THEORY.zh.md) | **学术深潜**：完整的机制推导、证据等级声明及流形/注意力探讨。 |
| **英文 (Only)** | [docs/CLI_INVOCATION_FLOW.md](docs/CLI_INVOCATION_FLOW.md) | **实现对照**：CLI→图→API 输出与状态字段的 Mermaid 说明。 |

---

**开源贡献:** 参阅 [CONTRIBUTING.md](CONTRIBUTING.md).  
**安全政策:** 参阅 [SECURITY.md](SECURITY.md).  
**行为准则:** [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
