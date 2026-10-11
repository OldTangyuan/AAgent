# ADAS（Automated Design of Agentic Systems）论文列表

> 类型:调研笔记。
> 性质:现行文档。
> 归属:—（不描述代码）。
> 适用版本:—。

本列表整合了“ADAS 研究范式分类”与“六种搜索算子家族”两份材料，去重后按 **搜索空间 → 搜索算子 → 应用与评估 → 开放问题** 的逻辑重新组织。每篇论文只在首次出现时给出完整信息，算子家族部分对已出现论文做交叉引用。


## 一、综述与基础框架

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **Automated Design of Agentic Systems: A Survey** | 未完整列出 | Preprints.org 2026.06 | 系统综述 2022–2026 年 ADAS 文献，四轴分类框架，覆盖 33 种方法 |
| **Automated Design of Agentic Systems (ADAS)** | Shengran Hu, Cong Lu, Jeff Clune (UBC) | NeurIPS 2024 Workshop / ICLR 2025 | 领域奠基性论文，首次形式化定义 ADAS，提出 Meta Agent Search 算法 |
| **AI-Generating Algorithms** | Jeff Clune | 2019 | ADAS 思想源头之一，提出元学习应学习“产生智能的机制本身” |


## 二、按搜索空间分类

### 2.1 代码空间搜索

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **Meta Agent Search / ADAS** | Shengran Hu et al. | ICLR 2025 | 元 Agent 在代码空间中迭代编程新 Agent，基于不断增长的发现档案。跨领域、跨模型迁移保持优越性能 |
| **Gödel Agent** | 未完整列出 | 2024 | 自引用自改进 Agent，在代码空间中搜索新脚手架 |
| **ADIAS: Automated Design of Interactive Agentic Systems** | Lekang Jiang et al. | arXiv 2026.08 | 全代码 Agent 设计的自动化框架，专注于交互式 Agent 系统 |
| **Self-Referential Self-Improving Systems** | 未完整列出 | arXiv 2025 | 覆盖 ADAS、ComfyAgent、Gödel Agent 等自引用系统的综合研究 |

> 代码空间搜索的图灵完备性允许发现任意 Agent 系统，但搜索空间极大，且存在执行不可信模型生成代码的安全隐患。

### 2.2 工作流拓扑搜索

#### MCTS 与树搜索

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **AFlow: Automating Agentic Workflow Generation** | Jiayi Zhang et al. (DeepWisdom) | ICLR 2025 | 工作流表示为图（节点=LLM调用，边=代码逻辑），MCTS 迭代精炼 |
| **A²Flow** | Zhao et al. | AAAI 2026 | 自适应抽象算子，从专家演示中自动抽取可复用执行算子，资源消耗降低 37% |
| **AgentSwift** | 清华/华为 | AAAI 2026 | 联合优化工作流与可组合功能组件，不确定性引导 MCTS 导航分层搜索空间 |
| **FlowMAS** | 未完整列出 | arXiv 2026 | 信息引导生成流网络学习多 Agent 工作流拓扑 |

#### 耦合拓扑与执行搜索

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **HierFlow** | 未完整列出 | arXiv 2026 | 拓扑层与执行层耦合搜索：拓扑决定子任务边界，执行结果反过来重塑拓扑，无训练分层搜索 |
| **FlowXpert** | 南开/华为云 | KDD 2026 | 以事件感知节点为中心的知识库 + RL 精炼工作流生成器/评估器，华为云 10 周真实部署 |
| **EvoAgentX** | Yingxu Wang et al. | ACL 2026 | 开源平台，五层模块化架构，自动化生成与进化优化工作流 |

#### 图优化框架

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **GPTSwarm** | Mingchen Zhuge et al. | ICML 2024 | Agent 作为可优化图：节点级（提示词）和边级（图连接）优化，REINFORCE 梯度优化 |
| **DynamicGPTSwarm** | Lukas Vierling et al. | 2024 | 在 GPTSwarm 基础上学习输入条件图生成，为每个输入动态生成边 |
| **RUMAD** | Chao Wang et al. (清华/浙大) | AAMAS 2026 | MAD 动态通信拓扑控制形式化为 RL，PPO 训练控制器动态调整边权，token 成本降低超 80% |

### 2.3 模块化设计空间搜索

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **AgentSquare** | Yu Shang et al. (清华) | ICLR 2025 | 提出 MoLAS 问题，将 Agent 抽象为 Planning/Reasoning/Tool Use/Memory 四模块，LLM 作为模块程序员通过进化元提示搜索新模块 |
| **AgentOptimizer** | Zhang et al. | 2024 | 学习 Agent 中使用的工具，扩展模块化搜索到工具维度 |
| **DYLAN** | Liu et al. | arXiv 2026.09 | 主动子结构感知策略优化，搜索整个 Agent 系统（Python 代码形式） |

### 2.4 提示级优化

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **TextGrad** | 未完整列出 | Nature 2025.03 | 文本计算图，将优化信号表示为自然语言批评 |
| **OPRO** | Yang et al. | ICLR 2024 | LLM 作为优化器，根据优化历史评分搜索自然语言指令 |
| **GEPA** | 未完整列出 | ICLR 2026 | 遗传-帕累托提示优化 |
| **PromptRL** | 未完整列出 | ICML 2026 | 联合 RL 循环优化提示词 |


## 三、六种搜索算子家族

> 以下六类算子与第二节的搜索空间正交：同一篇论文可能同时出现在“工作流拓扑搜索”和“MCTS”中。此处只列代表论文，完整信息见第二节对应条目。

### 3.1 LLM-as-Optimizer

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **OPRO** | Yang et al. | ICLR 2024 | 见 2.4，LLM 根据优化历史迭代生成新指令 |
| **APE** | Zhou et al. | 2022 | 用 LLM 生成候选指令并评分筛选，早期范式 |
| **The Optimizer Is the Agent** | Junbo Li et al. | arXiv 2026.08 | 将优化搜索内化为 Agent 自主推理，提出 ReASearch 统一框架 |
| **Naive Prompt Optimization (NPO)** | Yuan Chang et al. | arXiv 2026.08 | 简单 LLM-as-optimizer 迭代修订即可达到竞争性效果 |
| **Meta Agent Search** | Shengran Hu et al. | ICLR 2025 | 见 2.1，元 Agent 根据发现档案迭代生成新 Agent 代码 |

### 3.2 文本梯度（Textual Gradients）

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **TextGrad** | Yuksekgonul et al. | Nature 2025.03 | 见 2.4，文本计算图，LLM 生成“文本梯度”作为自然语言批评 |
| **Inducing LLM Workflows with Bilevel Optimization and Textual Gradients** | 未完整列出 | ICML 2026 | 工作流归纳形式化为双层优化，内层逐层反向传播文本梯度 |
| **Textual Stochastic Gradient Descent (TSGD)** | 未完整列出 | ICML 2026 | 外部记忆库离散优化，失败驱动增删改估计文本梯度，双验证防过拟合 |
| **Textual Equilibrium Propagation** | 未完整列出 | ICLR 2026 | 解决深层工作流文本梯度爆炸/消失，两阶段设计（Free Phase + Nudged Phase） |
| **MemGrad** | 未完整列出 | ICLR 2026 | 用文本梯度将行为反馈转化为可解释改进方向，支持回顾-前瞻记忆 |
| **TextResNet** | 未完整列出 | arXiv 2026 | 解耦和路由文本梯度信号，性能超越 TextGrad，基线崩溃场景下仍能工作 |

### 3.3 进化与质量-多样性搜索

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **AgentSquare** | Yu Shang et al. | ICLR 2025 | 见 2.3，模块进化 + 重组，程序级模块创新 |
| **SwarmAgentic** | Shijie Zhou et al. | 2025 | 群体智能驱动的全自动 Agent 系统生成，TravelPlanner 相比 ADAS 相对提升 +261.8% |
| **CB-Orchestrator** | 未完整列出 | ICML 2026 | 两阶段：进化搜索构建候选池，上下文 Bandit 做样本高效选择 |
| **EvoAgentX** | Yingxu Wang et al. | ACL 2026 | 见 2.2，开源平台，支持自动化生成与进化优化 |
| **DEI: Diversity in Evolutionary Inference** | 未完整列出 | arXiv 2026 | 分布式质量-多样性搜索，异构 LLM 作为变异算子 |
| **IDEAgent** | 未完整列出 | arXiv 2026 | 研究创意生成形式化为 QD 搜索，多目标反馈驱动质量 |
| **Loreley** | 未完整列出 | arXiv 2026 | 仓库级 QD 搜索，MAP-Elites 存档保留完整 git 仓库状态 |
| **Gödel Agent** | 未完整列出 | 2024 | 见 2.1，自引用自改进 Agent |

### 3.4 MCTS

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **AFlow** | Jiayi Zhang et al. | ICLR 2025 | 见 2.2，MCTS 工作流搜索标杆 |
| **AgentSwift** | 清华/华为 | AAAI 2026 | 见 2.2，分层搜索空间 + 不确定性引导 MCTS |
| **SCULPT** | 未完整列出 | arXiv 2026 | 约束引导剪枝 MCTS，避免遍历不合理分支 |
| **Agentic Workflows Generation Based on Meta-Cognitive CoT Guided MCTS** | 未完整列出 | IEEE 2025 | 元认知 CoT 引导 MCTS，动态调整工作流 |
| **Cost-Constrained Automatic Workflow Search for Small LLM Agents** | 未完整列出 | IEEE 2026 | 成本感知奖励函数集成到 MCTS，联合优化性能、token、延迟、失败风险 |
| **I-MCTS** | 未完整列出 | 2026 | 内省式 MCTS，应用于 Agentic AutoML |

### 3.5 贝叶斯/代理方法

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **AgentSquare 性能预测器** | Yu Shang et al. | ICLR 2025 | 见 2.3，上下文代理模型跳过无望设计，加速搜索 |
| **Balanced-Extreme Bayesian Optimization for AgentSwift** | 未完整列出 | AAAI 2026 | 见 2.2，平衡-极端贝叶斯优化增强初始数据集 |
| **Agentic Bayesian Optimization through Surrogate-Augmented Autoresearch** | 未完整列出 | arXiv 2026 | LLM Agent 成为贝叶斯优化循环中央决策者，动态调整优化策略 |
| **OPTIMA** | 未完整列出 | 2026 | 数值搜索委托给验证过的集成优化工具，保持确定性和可复现性 |
| **LLMs for Bayesian Optimization in Scientific Domains: Are We There Yet?** | 未完整列出 | ACL 2026 | 系统评估 LLM 在科学贝叶斯优化中的适用性，提出混合方法 LLMNN |

### 3.6 RL/DPO

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **GPTSwarm** | Mingchen Zhuge et al. | ICML 2024 | 见 2.2，节点级和边级优化，REINFORCE |
| **EvoRL** | 未完整列出 | IEEE BigData 2025 | 分层 RL：高层 Evolver 选择模块化组件定义工作流结构，低层 LLM Selector 选择模型，准确率 87.99% |
| **FlowSteer** | 未完整列出 | arXiv 2026 | 端到端 RL 框架，轻量级策略模型作为 Agent，可执行画布环境中多轮交互自动化工作流编排 |
| **Conductor** | Sakana AI | ICLR 2026 | 7B Qwen2.5 用 GRPO 训练为“Conductor”，输出完整 Agent 工作流，协调 GPT-5/Claude，7 个推理基准平均 77.27% |
| **iStar** | 未完整列出 | ICLR 2026 | 通用信用分配策略，交替优化隐式过程奖励模型和策略模型，多轮 DPO 学习密集奖励 |
| **UnityMAS-O** | 未完整列出 | arXiv 2026 | 可复用基底，将多样多 Agent 工作流转为可训练多 Agent RL 系统 |
| **RUMAD** | Chao Wang et al. | AAMAS 2026 | 见 2.2，PPO 训练控制器动态调整通信图边权 |


## 四、多智能体协作与自组织

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **Flow: Modularized Agentic Workflow Automation** | 未完整列出 | ICLR 2025 | 模块化 Agent 工作流自动化框架 |
| **Multi-Agent System Search** | 未完整列出 | 2026 | 多 Agent 系统搜索 |
| **MADA (Multi-Agent Design Assistant)** | Menon et al. | arXiv 2026.03 | 多 Agent 协作自动化设计探索 |


## 五、元优化与自我改进

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **Meta-Agent-Workflow** | Xiaoyu Tan et al. | WWW 2025 | 构建-检索-精炼闭环：将 LLM 工具推理过程转化为任务特定工作流，遵循 Dify 等开源 Agent 平台架构 |
| **BayesFlow** | 未完整列出 | arXiv 2026 | 概率推理框架下的元 Agent 辅助工作流生成，平均提升 4.6%，最高 9% |
| **Meta-Moderator** | 未完整列出 | arXiv 2026 | 辩论中的可学习元认知调节器，跨任务和跨系统配置迁移 |
| **STOP (Self-Taught Optimizer)** | Zelikman et al. | 2023 | 递归式脚手架改进的早期工作，基础模型需足够强才能从递归结构中获益 |


## 六、领域专用工作流自动化

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **VFlow** | 未完整列出 | ASP-DAC 2026 | 硬件设计（Verilog 生成）的 Agent 工作流自动发现 |
| **SurgRAW** | 未完整列出 | 2026 | 机器人手术视频分析的多 Agent 工作流 |
| **RFChipAgent** | 未完整列出 | arXiv 2026.10 | 模拟/RF 芯片设计的多 Agent 端到端设计自动化流程 |
| **RocketAgent** | 未完整列出 | arXiv 2026.10 | 液体火箭推力室多学科初步设计的长期工程 Agent |


## 七、基准与评估

| 论文 | 作者/团队 | Venue | 核心贡献 |
|---|---|---|---|
| **GitTaskBench** | 未完整列出 | AAAI 2026 | 代码 Agent 通过代码仓库解决真实任务的基准 |
| **OpsFlowBench** | FlowXpert 团队 | KDD 2026 | 运维工作流基准 |
| **CoMemBench** | 未完整列出 | 2026 | 多 Agent 工作流拓扑下的协作记忆边界基准，包含 ADAS 基线 |
| **AIRA-Compose / AIRA-Design** | Pepe et al. | arXiv 2026.05 | 神经架构的 Agent 发现，匹配或超越手工设计基线 |


## 八、开放问题与关键洞察

根据 ADAS 综述，当前领域存在两个核心结构性张力：

1. **表达能力 vs. 可搜索性**  
   代码空间表达能力最强，但搜索难度最高；模块化 DSL 和自然语言字符串表达受限但更易搜索。

2. **反馈丰富度 vs. 信用分配**  
   大多数方法只使用结果级奖励，无法知道工作流中**哪个节点或哪条边**导致了性能变化。将学习到的过程奖励模型与方差缩减的策略梯度结合，是最清晰的开放方向。

此外，**安全性问题**值得持续关注：递归自我改进使 ADAS 可以改进自己（元 Agent 本身也是 Agent），带来对齐和可控性新挑战；代码空间搜索中执行不可信模型生成代码的风险也需警惕。


## 九、推荐阅读路径

| 阶段 | 论文 | 理由 |
|---|---|---|
| **入门** | ADAS (Hu et al., ICLR 2025) | 领域奠基，理解核心范式 |
| **精读** | AFlow (ICLR 2025) | MCTS 工作流搜索标杆 |
| **精读** | AgentSquare (ICLR 2025) | 模块化设计空间代表性工作 |
| **扩展** | AgentSwift / A²Flow (AAAI 2026) | 2026 最新进展，算子自学习与分层搜索 |
| **前沿** | SwarmAgentic / ReCreate | 群体智能与经验驱动新范式 |
| **算子专项** | OPRO → TextGrad → iStar | 分别对应 LLM-as-optimizer、文本梯度、RL 信用分配 |
| **综述** | ADAS Survey (Preprints 2026.06) | 系统性俯瞰全领域 33 种方法 |


**统计说明**：本列表整合后共收录 **70+ 篇** ADAS 相关论文，覆盖综述、搜索空间、六类算子、应用、基准与开放问题。与原始两份列表相比，去除了重复条目（如 AgentSquare、AFlow、GPTSwarm、EvoRL、RUMAD 等），并补充了交叉引用关系。