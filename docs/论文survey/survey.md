> 类型:调研笔记。
> 性质:现行文档。
> 归属:—（不描述代码）。
> 适用版本:—。

## 一、Agent 组件选择与组合优化

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| Automated Composition of Agents: A Knapsack Approach | Michelle Yuan 等 | NeurIPS 2025 | 将组件选择形式化为在线背包问题，成功率提升最高31.6% | 1-1 |
| PARCO: Parallel AutoRegressive Models for Multi-Agent CO | Federico Berto 等 | NeurIPS 2025 | 并行自回归多Agent组合优化，可泛化到50倍规模 | 1-2 |
| GOAL: A Generalist Combinatorial Optimization Agent Learner | Darko Drakulić 等 | ICLR 2025 Poster | 单模型求解多种组合优化问题 | 1-3 |


## 二、形式化验证与全路径评估

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| CORE: Full-Path Evaluation of LLM Agents Beyond Final State | Panagiotis Michelakis 等 | NeurIPS 2025 Workshop | 用DFA编码合法工具调用路径，全路径评估Agent | 2-1 |
| Proof-Gated Skill Compilation | Bren Worth | NeurIPS 2026 Workshop | 程序验证门控技能持久化，拒绝89%虚假声明 | 2-2 |
| ShieldAgent | 未完整列出 | ICML 2025 | 逻辑推理强制执行安全策略的guardrail agent | 2-3 |
| G-Safeguard | Shilong Wang 等 | ACL 2025 Long | GNN检测话语图异常，拓扑干预修复攻击 | 2-4 |
| STRATUS | IBM Research | NeurIPS 2025 | 状态机组织Agent，定义Transactional No-Regression安全规约 | 2-5 |
| Agentproof | Melwin Xavier 等 | arXiv 2026 | DFA+图验证，27%工作流有结构缺陷 | 2-6 |
| FormalJudge | Jiayi Zhou 等 | ICML 2026 | 神经符号监督，相比LLM-as-Judge提升16.6% | 2-7 |
| Formal Runtime Verification for Tool-Using LLM Agents | 未完整列出 | ACM 2026 | MFOTL运行时验证工具使用型Agent | 2-8 |
| RefineAct | 未完整列出 | 2026 | 自动推导任务规约，失败率从77%降至39% | 2-9 |


## 三、神经符号与规约

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| Ground-Compose-Reinforce | Andrew Li 等 | NeurIPS 2025 Poster | 350条轨迹学习原子命题接地，Reward Machine组合规约 | 3-1 |
| Aria | Wang Hanyu 等 | ICLR 2026 | 两阶段Graph-of-Thought，Lean定理自动形式化 | 3-2 |
| ProofOfThought | Debargha Ganguly 等 | NeurIPS 2024 Workshop | 基于Z3定理证明器的agentic SMT-LIB scratchpad | 3-3 |


## 四、多智能体通信的形式化

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| ThoughtComm | Yujia Zheng 等 | NeurIPS 2025 Spotlight | 潜变量生成模型，证明thought可辨识，数学推理提升19.06% | 4-1 |
| HyperAgent | Heng Zhang 等 | AAMAS 2026 | 超图优化通信拓扑，GSM8K 95.07% | 4-2 |
| Guided Topology Diffusion (GTD) | Eric Hanchen Jiang 等 | ACL 2026 | 图扩散模型动态生成通信拓扑 | 4-3 |


## 五、联邦/去中心化 LLM 智能体

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| DAWN | Guancheng Wan 等 | AAAI 2026 | 联邦图学习，Parametric Resonance + Structural Gravity | 5-1 |
| KNEXA-FL | Inderjeet Singh 等 | AAAI 2026 | 上下文Bandit + LinUCB配对，安全蒸馏 | 5-2 |
| FedWave | Jiaxing Zhao 等 | ICML 2026 | Value Chain + MoE路由，工作流感知联邦 | 5-3 |
| Fed-SE | 未完整列出 | arXiv 2025.12 | 低秩子空间聚合，本地进化-全局聚合 | 5-4 |
| Helmsman | 未完整列出 | ICLR 2026 | 多智能体工作流，AgentFL-Bench基准 | 5-5 |
| Advancing Agentic AI | Arpita Sarker 等 | ICML 2025 | DAG账本+共识，去中心化可验证训练 | 5-6 |
| Personalized FL for Sovereign Personal AI Agents | 未完整列出 | IEEE 2026 | PFL+LLM+隐私保护综述 | 5-7 |
| LLM-Flex | Shuai Huang 等 | CSCWD 2026 | LLM Agent自动化配置异构联邦学习系统 | 5-8 |
| Starfish-FL | 未完整列出 | ACM Transactions 2026 | 三层Agent架构，LLM仅作顾问 | 5-9 |


## 六、分布式训练优化

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| OptiCo | Sheng Chen 等 | ACL 2026 | 多智能体CoT推理，25+配置平均提升1.84% | 6-1 |
| ASAP | 未完整列出 | NeurIPS 2025 | 自动分片配置，28%训练步时间减少 | 6-2 |
| MARTI | 未完整列出 | ICLR 2026 | 分布式RL+轨迹派发 | 6-3 |


## 七、去中心化 MARL

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| Blockchain-Enhanced MARL | 未完整列出 | Scientific Reports 2025.11 | 智能合约+激励相容 | 7-1 |
| Self-Regulating FDRL | 未完整列出 | AAAI 2026 | 动态客户端环境，增强六种FDRL方法 | 7-2 |
| Decentralized RL for Multi-Agent Multi-Resource Allocation | Antonio Marino 等 | arXiv 2025.03 | 动态集群协议，无中心协调 | 7-3 |


## 八、联邦图学习 + Agent

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| RAFHGL | 未完整列出 | AAAI 2025 | 主动学习智能体选择高贡献客户端 | 8-1 |
| ActiveTrap | 未完整列出 | IEEE 2025.12 | 溯源超图+FGL，APT诱捕 | 8-2 |
| Decentralized FGL with Zero Trust | 未完整列出 | IEEE/OpenReview 2025 | PPO+零信任，自适应安全策略 | 8-3 |


## 九、离散内容连续化

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| Soft Thinking | Microsoft/Purdue | NeurIPS 2025 | Training-free连续概念推理，token减少22.4% | 9-1 |
| ELF | 何恺明团队 | NeurIPS 2026 | Flow Matching，连续嵌入空间去噪 | 9-2 |
| Cola DLM | 字节跳动Seed | arXiv 2026 | Text VAE + DiT，分层潜在扩散 | 9-3 |
| RDLM | 未完整列出 | NeurIPS 2025 | 统计流形，1.32 BPC | 9-4 |
| CCDD | 未完整列出 | ICML 2026 | 联合扩散过程，连续-离散并集去噪 | 9-5 |
| GradMem | 未完整列出 | ICML 2026 | 前缀记忆token，测试时梯度下降 | 9-6 |
| Soft Tokens, Hard Truths | Natasha Butt 等 | arXiv 2025 | 首次RL可扩展学习连续CoT，pass@32超越离散 | 9-7 |
| DyLaR | 未完整列出 | AAAI 2026 | 动态潜在推理切换 | 9-8 |
| Soft Latent Thinking | 未完整列出 | arXiv 2026 | 替换LM head | 9-9 |
| GFPR | 未完整列出 | arXiv 2026 | 单纯形几何不动点 | 9-10 |
| SoftCoT | Yige Xu 等 | ACL 2025 | 轻量级助手模型生成软思考token | 9-11 |
| COCONUT | Meta FAIR/UC San Diego | NeurIPS 2024 | 无限制潜在空间推理 | 9-12 |
| HRPO | Zhenrui Yue 等 | NeurIPS 2025 | 可学习门控机制混合隐藏状态与token嵌入 | 9-13 |
| ∇-Reasoner | 未完整列出 | ICLR 2026 | token logits上可微优化 | 9-14 |
| LangFlow | 未完整列出 | ICML 2026 | 首个连续DLM匹敌离散模型 | 9-15 |


## 十、RL for Workflow

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| EvoRL | 未完整列出 | IEEE 2025.12 | 分层RL，准确率87.99% | 10-1 |
| FlowSteer | 未完整列出 | arXiv 2026.02 | CWRPO，多样性约束奖励 | 10-2 |
| AgentFlow | 未完整列出 | ICLR 2026 Oral | Flow-GRPO，7B模型10基准提升4-15分 | 10-3 |
| Workflow-R1 | 未完整列出 | ICML 2026 | GSsPO | 10-4 |
| W4S/RLAO | 未完整列出 | ICML 2026 | 7B弱元智能体设计工作流 | 10-5 |
| Conductor | Sakana AI | ICLR 2026 | 7B协调GPT-5/Claude | 10-6 |
| GPTSwarm | 未完整列出 | ICML 2024 | REINFORCE，节点级/边级图优化 | 10-7 |
| AgentConductor | Siyu Wang 等 | ICML 2026 | 分层DAG+GRPO，pass@1提升14.6% | 10-8 |
| UnityMAS-O | 未完整列出 | arXiv 2026 | 工作流图+奖励接口 | 10-9 |
| Agent Lightning | Xufang Luo 等 | arXiv 2025 | 通用框架，任意Agent转RL问题 | 10-10 |
| SWEET-RL | Yifei Zhou 等 | arXiv 2025 | 多轮协作推理 | 10-11 |
| AgentPRM | Zhiheng Xi 等 | arXiv 2025 | 步骤级PRM | 10-12 |
| ParetoPO | 未完整列出 | ICML 2026 | 多目标MDP | 10-13 |
| WebSeer | 未完整列出 | ICLR 2026 | 自反思RL | 10-14 |
| Graph-GRPO | Yueyang Cang 等 | ACL 2026 Findings | 组内相对边级优势 | 10-15 |
| PivotRL | Junkeun Yi 等 | arXiv 2026 | 低计算成本后训练 | 10-16 |
| TCPO | Sicong Liao 等 | arXiv 2026 | 轮次级信用分配 | 10-17 |


## 十一、提示词 / 技能优化

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| TextGrad | 未完整列出 | Nature 2025.03 | 文本计算图 | 11-1 |
| GEPA | 未完整列出 | ICLR 2026 | 遗传-帕累托提示优化 | 11-2 |
| PromptRL | 未完整列出 | ICML 2026 | 联合RL循环 | 11-3 |
| SAGE | Amazon Science | ACL 2026 | Sequential Rollout，AppWorld提升8.9% | 11-4 |
| Graph-of-Skills (GoS) | 未完整列出 | EMNLP 2026 | 技能图，依赖感知检索 | 11-5 |
| SE-GoS | 未完整列出 | arXiv 2026.04 | 执行轨迹演化技能图 | 11-6 |
| SkillBrew | Wentao Hu 等 | arXiv 2026.05 | 帕累托优化技能策展 | 11-7 |
| SkillX | Chenxi Wang 等 | ICML 2026 | 三层技能层级 | 11-8 |
| SKILLFOUNDRY | 未完整列出 | arXiv 2026 | 自进化技能库 | 11-9 |
| Skills on the Fly | 未完整列出 | arXiv 2026 | 测试时技能合成 | 11-10 |
| Dynamic Agent Skills Survey | 未完整列出 | arXiv 2025 | 技能库生态综述 | 11-11 |
| SCRIBE | 未完整列出 | arXiv 2025 | 技能原型库，AIME25 43.3→63.3 | 11-12 |
| PRL | 未完整列出 | arXiv 2025 | RL优化提示词 | 11-13 |


## 十二、Reward 设计

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| ReasonRAG | 未完整列出 | NeurIPS 2025 | 过程级奖励，5k实例超越90k | 12-1 |
| GLARE | Jingyuan Yan 等 | ICML 2026 | LTL+自动机，ALFWorld提升12.1% | 12-2 |
| MASPRM | 未完整列出 | arXiv 2025.10 | MCTS rollout，GSM8K提升30.7 EM点 | 12-3 |
| IGPO | 未完整列出 | ICLR 2026 | 信念更新，密集内在奖励 | 12-4 |
| SPEAR | 未完整列出 | ICLR 2026 | 课程调度，内在奖励塑形 | 12-5 |
| PRA | Jiwoong Sohn 等 | ICML 2026 | 在线步骤级奖励，MedQA 81.9% | 12-6 |
| PRO-CUA | 未完整列出 | arXiv 2026 | PRM引导on-policy RL | 12-7 |
| WebShepherd | Chae 等 | NeurIPS 2025 Spotlight | 首个网页导航PRM | 12-8 |
| WebArbiter | Zhang 等 | 2026 | 原则引导推理 | 12-9 |
| HiPRAG | 未完整列出 | arXiv 2025 | 过度搜索率降至2.3% | 12-10 |
| RLSR | 未完整列出 | arXiv 2025 | LLM自我评判实现自我提升 | 12-11 |
| EVILGENIE | 未完整列出 | 基准 | Reward Hacking基准 | 12-12 |
| FedMOA | 未完整列出 | 联邦多目标对齐 | 异构Reward自适应加权 | 12-13 |
| RLSVR | 未完整列出 | arXiv 2025 | 自可验证Reward | 12-14 |
| OPRL | 未完整列出 | arXiv 2025 | 隐式过程奖励，无需人工标注 | 12-15 |
| PRM-PBE | 未完整列出 | ICML 2026 | PRM应用于编程示例 | 12-16 |
| PPR | 未完整列出 | 2025 | 统一步骤级评估和结果验证 | 12-17 |
| **Debate as Reward** | **Moein Salimi, Babak Hosseini Mohtasham, MohammadHossein Rohban 等** | **arXiv 2026 (arXiv:2604.16723)** | **领域**：科学创意生成与RL后训练。**贡献**：首个多Agent Reward函数作为Judge，将方法论验证与实现细节解耦，提供对Reward Hacking鲁棒的严格二值奖励。用无偏GRPO变体缓解人工长度偏差，基于ICLR-320数据集。 | **12-18** |
| **Debate Helps Weak Judges Reward Stronger Models** | **Ethan Elasky, Frank Nakasako, Naman Goyal（Palaestra Research）** | **arXiv 2026 (arXiv:2605.27483)** | **领域**：可扩展监督与辩论训练协议。**贡献**：研究proposer-critic辩论在强辩手/弱评判者设置下的效果。核心发现：辩论只有在批评者分类能力超过评判者、且评判者将批评视为需验证的主张时才有效。消融反驳轮次无显著变化，单次独立批评即可恢复大部分收益。 | **12-19** |
| **Debate Training Reduces Reward Hacking in RLAIF** | **Zachary Kenton, Lili Janzer, Rory Greig, Tian Huey Teh, Kirill Tyshchuk, Jonah Brown-Cohen, Harri Edwards, Senthooran Rajamanoharan, Noah Y. Siegel, Natasha Jaques, Rohin Shah** | **arXiv 2026 (arXiv:2608.17776)** | **领域**：RLAIF中的Reward Hacking缓解。**贡献**：用生成器-批评者双玩家对抗博弈配合弱LLM裁判，相比RLAIF基线显著降低Reward Hacking，挽回45%性能差距。关键发现：Hacking judge是默认结果，除非加入限制措施（如150词限制）。 | **12-20** |
| **Debate4MATH / FMAD** | **Shaowei Zhang, Deyi Xiong（天津大学TJUNLP Lab）** | **ACL 2025 Findings (pp. 16810–16824)** | **领域**：数学推理的多Agent辩论Reward Model。**贡献**：提出FMAD框架和MMATH-Data数据集（46K推理步骤），训练Multi-Agent Debate Reward Model (MRM)提供鲁棒反馈。MMATH-LLM在GSM8K达83.4%、MATH达45.1%。 | **12-21** |
| **Self-Debate Reinforcement Learning (SDRL)** | **Chenxi Liu, Yanshuo Chen, Ruibo Chen, Tianyi Xiong, Tong Zheng, Heng Huang** | **arXiv 2026 (arXiv:2601.22297)** | **领域**：自辩论RL。**贡献**：训练单个推理模型同时作为独立求解者和辩论参与者，联合优化初始响应和辩论条件响应，用可验证Reward驱动。理论框架解耦辩论驱动的改进与多数投票效应。 | **12-22** |
| **Latent Agents: Internalized Multi-Agent Debate** | **John Seon Keun Yi, Aaron Mueller, Dokyun Lee** | **ACL 2026 Long (pp. 15569–15602)** | **领域**：辩论内化与后训练。**贡献**：将多Agent辩论蒸馏到单个LLM中，通过两阶段微调管道（辩论结构学习+内化），结合动态Reward调度和长度裁剪。内化模型匹配或超越显式多Agent辩论性能，token减少最多93%。 | **12-23** |
| **Epistemic Gain, Aleatoric Cost** | **Dan Qiao, Binbin Chen, Fengyu Cai, Jianlong Chen, Wenhao Li, Fuxin Jiang, Zuzhi Chen, Hongyuan Zha, Tieying Zhang, Baoxiang Wang** | **ICML 2026** | **领域**：辩论中的不确定性分解与Reward塑形。**贡献**：提出贝叶斯不确定性分析框架，将答案级预测不确定性分解为认知不确定性（可被辩论上下文减少）和偶然不确定性（内部模型噪声）。基于此设计不确定性引导的多Agent RL算法。 | **12-24** |


## 十三、Judge Bias

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| CALM | Jiayi Ye 等 | ICLR 2025 | 12种偏差，自动化量化框架 | 13-1 |
| JudgeBiasBench | 未完整列出 | arXiv 2026.03 | 4维度12类型 | 13-2 |
| VERDICT-BENCH / JURY | 未完整列出 | Zenodo 2025.11 | 偏差感知面板 | 13-3 |
| D3: Debate, Deliberate, Decide | 未完整列出 | arXiv 2024/2025 | 对抗性多Agent | 13-4 |
| Judging with Many Minds | 未完整列出 | EMNLP 2025 Findings | 辩论首轮后偏差急剧上升 | 13-5 |
| RBD | 未完整列出 | NeurIPS 2025 | 即插即用偏差检测 | 13-6 |
| FairJudge | Bo Yang 等 | ICML 2026 | SFT-DPO-GRPO课程 | 13-7 |
| AGDe-Judge | 未完整列出 | ACL 2025 Findings | 教师偏好去偏 | 13-8 |
| Genii | Shuliang Liu 等 | ACL 2026 Findings | 分组轮询缓解判断偏好偏差 | 13-9 |
| Translationese Bias (DIBJudge) | Hongbin Zhang 等 | ICML 2026 | 翻译腔偏差缓解 | 13-10 |
| Pairwise-RL | 未完整列出 | arXiv 2025 | 成对比较统一奖励模型与RL | 13-11 |
| Pairwise RM | 未完整列出 | arXiv 2025 | 淘汰赛机制 | 13-12 |
| DEBATE | 未完整列出 | arXiv 2025 | 魔鬼代言人框架 | 13-13 |
| G-DMAD | 未完整列出 | arXiv 2025 | 分组辩论机制 | 13-14 |
| MAPoRL | 未完整列出 | arXiv 2025 | 多智能体辩论+可验证奖励 | 13-15 |
| ECS | 未完整列出 | arXiv 2025 | 冲突门控级联 | 13-16 |
| BT-σ | 未完整列出 | arXiv 2025 | Bradley-Terry判别力加权聚合 | 13-17 |
| InstaJudge | 未完整列出 | arXiv 2025 | 自动prompt优化 | 13-18 |
| BabelJudge | 未完整列出 | arXiv 2025 | 跨语言judge可靠性 | 13-19 |
| SCOPE | 未完整列出 | arXiv 2025 | 双向偏好熵共形优化 | 13-20 |
| EIT | 未完整列出 | arXiv 2025 | 认知独立性训练 | 13-21 |
| AI Debate Aids Assessment | 未完整列出 | NeurIPS 2025 Poster | AI judge 78.5% > 人类70.1% | 13-22 |
| MAD Adaptive Stability Detection | 未完整列出 | NeurIPS 2025 | 自适应稳定性检测 | 13-23 |


## 十四、联邦 Reward 聚合

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| Preference Aggregation in Federated RLHF | 未完整列出 | NeurIPS 2025 | 距离-based聚合优于排序 | 14-1 |
| APPA | 未完整列出 | arXiv 2026 | 自适应组级重加权 | 14-2 |
| PluralLLM | 未完整列出 | arXiv 2025 | FedAvg偏好聚合 | 14-3 |
| Systematic Evaluation of Federated RLHF | 未完整列出 | NeurIPS 2025 | 距离-based显著优于排序 | 14-4 |


## 十五、多智能体通信拓扑

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| LF-Commer | 未完整列出 | Neurocomputing 2026 | 领导者-跟随者图 | 15-1 |
| MACRL-GNN | 未完整列出 | IEEE 2025 | GNN+MARL，应急Mesh网络 | 15-2 |
| EAC | 未完整列出 | Information Sciences 2026 | 实体感知超网络 | 15-3 |
| **RUMAD** | **Chao Wang, Han Lin, Huaze Tang, Huijing Lin, Wenbo Ding（清华大学、浙江大学）** | **AAMAS 2026 (DOI: 10.65109/CBJO8409)** | **领域**：多Agent辩论的动态拓扑控制。**贡献**：将MAD动态通信拓扑控制形式化为RL问题。用多目标Reward建模解质量、凝聚力和效率。PPO训练控制器动态调整通信图边权，token成本降低超80%，同时提升推理准确率。零样本泛化到OOD任务。 | **15-4** |


## 十六、模块化 Agent 与开放协议

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| FinAgent | 未完整列出 | NeurIPS 2025 | MCP+A2A | 16-1 |
| LACP | 未完整列出 | NeurIPS 2025 Position | 三层协议栈 | 16-2 |
| LAP | 未完整列出 | arXiv 2026 | 意图接地+安全协商 | 16-3 |
| STEM Agent | 未完整列出 | arXiv 2026 | 多协议统一网关 | 16-4 |
| Modular Agent Capabilities | 未完整列出 | Zenodo 2025 | 模块化能力封装 | 16-5 |
| MCP in LLM Agent Architectures | 未完整列出 | Tampere Thesis 2025 | MCP模块化可扩展架构 | 16-6 |
| Governing MAS | 未完整列出 | Zenodo 2026 | 企业治理，MCP+A2A | 16-7 |
| DREAMS | 未完整列出 | EBSCO 2026 | MCP智能显微镜 | 16-8 |
| AgentMaster | 未完整列出 | NeurIPS 2025 | 模块化多协议MAS框架 | 16-9 |
| Modular Agents Orchestrated | 未完整列出 | NeurIPS 2025 Talk | 开放Agentic协议 | 16-10 |


## 十七、Agent 安全的形式化与拓扑分析

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| NetSafe | Miao Yu 等 | ACL 2025 Findings | 拓扑安全性，Star Graph性能降29.7% | 17-1 |
| Agentproof | Melwin Xavier 等 | arXiv 2026 | DFA+图验证，27%工作流有缺陷 | 17-2 |
| TraceFix | Shuren Xia 等 | ACM CAIS 2026 Best Paper | TLA+模型检查，死锁/活锁31.1%→14.1% | 17-3 |
| Zero-trust Architecture | 未完整列出 | IEEE 2026 | 拓扑分歧+信任张量 | 17-4 |
| Topology Linearization | Liu 等 | Semantic Scholar 2026 | 路径分解 | 17-5 |
| TOPOSHIELD | 未完整列出 | ACL 2025 | 时空风险拓扑演化 | 17-6 |
| Graph-theoretic Agreement | 未完整列出 | HF Daily Papers 2026 | 签名图共识 | 17-7 |
| AXION | 未完整列出 | Zenodo 2026 | 52个原语约束格 | 17-8 |
| Byzantine-MCP-Router | 未完整列出 | GitHub 2026 | 拜占庭容错 | 17-9 |


## 十八、多环境 POMDP 与鲁棒策略

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| Multi-Environment POMDPs | Eline M. Bovy 等 | NeurIPS 2025 | ME-POMDP，最坏情况鲁棒策略 | 18-1 |
| RFPG | 未完整列出 | IJCAI 2025 | 有限记忆策略梯度 | 18-2 |
| Evaluating Policies for Robust POMDPs | 未完整列出 | NeurIPS 2025 Poster | 最优性差距上界 | 18-3 |
| Pessimistic Iterative Planning | Jansen 等 | ECAI 2025 | RNN+悲观规划 | 18-4 |
| Robust POMDP Lung Cancer | 未完整列出 | arXiv 2026 | 范数模糊集 | 18-5 |
| Finite-State Controllers | 未完整列出 | AAAI 2026 | 深度RL，有限状态控制器 | 18-6 |
| Robustness Analysis POMDP | Kraske 等 | Semantic Scholar 2026 | 观测扰动 | 18-7 |
| Cooperative Protection Multi-Unmanned | 未完整列出 | IEEE 2026 | 扩展Dec-POMDP | 18-8 |
| Entropy-regularized PBVI | 未完整列出 | IEEE 2026 | 熵正则化 | 18-9 |
| Belief-Driven Decentralized RL | 未完整列出 | IEEE 2026 | Dec-POMDP | 18-10 |


## 十九、Agentic RL 训练框架

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| ARLArena / SAMPO | 未完整列出 | ICML 2026 | 稳定训练配方+分析框架 | 19-1 |
| StepPO | 未完整列出 | 2026 | 步骤对齐策略优化 | 19-2 |


## 二十、其他

| 论文 | 作者/团队 | 会议 | 核心贡献 | 索引 |
|---|---|---|---|---|
| TimeAgent | 未完整列出 | IEEE 2026 | Training-free闭环时序Agent | 20-1 |
| CFAgentic Workshop | 未完整列出 | ICML 2025 Workshop | 协作/联邦Agent工作流 | 20-2 |
| REALM-Bench | 未完整列出 | 2026 | 多智能体真实世界规划基准 | 20-3 |
| Agentic RL Survey | Guibin Zhang 等 | arXiv 2025 | Agentic RL综述 | 20-4 |


## 索引汇总

| 编号 | 方向 | 论文数 |
|---|---|---|
| 1 | Agent 组件选择与组合优化 | 3 |
| 2 | 形式化验证与全路径评估 | 9 |
| 3 | 神经符号与规约 | 3 |
| 4 | 多智能体通信的形式化 | 3 |
| 5 | 联邦/去中心化 LLM 智能体 | 9 |
| 6 | 分布式训练优化 | 3 |
| 7 | 去中心化 MARL | 3 |
| 8 | 联邦图学习 + Agent | 3 |
| 9 | 离散内容连续化 | 15 |
| 10 | RL for Workflow | 17 |
| 11 | 提示词 / 技能优化 | 13 |
| 12 | Reward 设计 | 24 |
| 13 | Judge Bias | 23 |
| 14 | 联邦 Reward 聚合 | 4 |
| 15 | 多智能体通信拓扑 | 4 |
| 16 | 模块化 Agent 与开放协议 | 10 |
| 17 | Agent 安全的形式化与拓扑分析 | 9 |
| 18 | 多环境 POMDP 与鲁棒策略 | 10 |
| 19 | Agentic RL 训练框架 | 2 |
| 20 | 其他 | 4 |
| **合计** | | **169** |