# MPAC v0.1.3 严苛审计报告

**审计日期**: 2026-04-02
**审计对象**: SPEC.md (MPAC v0.1.3 — Interoperability Hardening)
**审计者角色**: 资深分布式系统架构师 / 多智能体系统专家
**审计范围**: 效率性、鲁棒性、扩展性、语义对齐、状态机交叉安全性五个维度

---

## 总体评价

MPAC v0.1.3 是一份**设计意图清晰、层次划分合理、迭代方向正确**的多主体协调协议草案。经过三轮迭代（v0.1 → v0.1.1 → v0.1.2 → v0.1.3），协议已从"概念验证"成长为"可实现的工程草案"。五层抽象模型（Session → Intent → Operation → Conflict → Governance）对多主体协调的核心痛点——意图冲突预检、跨主体治理、因果可追溯——提出了有针对性的解决方案。

然而，从严苛的工程落地视角审视，协议在**消息效率、大规模扩展、故障恢复完备性、语义协商**四个方面仍存在需要正视的结构性问题。以下逐一展开。

---

## 一、效率性审计

### 1.1 消息信封开销偏重

每条 MPAC 消息都必须携带完整信封（Section 11.2）：`protocol`、`version`、`message_type`、`message_id`、`session_id`、`sender`（含嵌套对象）、`ts`、`payload`，加上推荐的 `watermark` 对象。以一条简单的 HEARTBEAT 消息为例，payload 仅有 `status: "idle"` 一个字段，但信封本身的 JSON 序列化大约 300-500 字节，payload 不到 30 字节——**信封开销是有效载荷的 10-15 倍**。

对于 HEARTBEAT 这种每 30 秒发送一次的高频消息，这个比例是不合理的。在 100 个参与者的 session 中，仅心跳消息的网络开销就达到 ~50KB/30秒（100 × 500B），年化约 52GB 的纯心跳流量。

**问题严重度**: 中等
**建议**:
- 定义一种轻量级的 "compact envelope" 模式，允许 HEARTBEAT 等高频低价值消息省略 `protocol`、`version`、完整 `sender` 对象（用 `sender_id` 短标识替代）
- 或者允许 session 级别的信封字段缓存——首次 HELLO 后，后续消息可省略不变字段
- 考虑引入二进制序列化选项（如 CBOR/MessagePack），而非强制 JSON

### 1.2 Intent-Before-Action 引入的两阶段开销

在 Governance Profile 下，一次完整的操作流程需要：`INTENT_ANNOUNCE` → (等待冲突检测) → `OP_PROPOSE` → (等待审批) → `OP_COMMIT`。这是一个**三消息 + 两次等待**的流程。如果检测到冲突，还要加上 `CONFLICT_REPORT` → `CONFLICT_ACK` → `RESOLUTION`，总计六条消息才能完成一次操作。

与直接操作相比，这引入了至少 2 个 RTT 的延迟。对于高频协作场景（如实时文档编辑），这个延迟可能无法接受。

**问题严重度**: 中等
**建议**:
- 引入 `INTENT_ANNOUNCE_AND_PROPOSE` 合并消息类型，允许在无冲突预期时将意图声明和操作提案合并为一条消息（乐观路径优化）
- 定义 "fast-path" 策略：对 `low` severity 级别的 scope overlap，允许操作先行、冲突后检

### 1.3 缺少消息批处理（Batching）机制

当一个 Agent 需要对多个资源执行相关操作时（如重构涉及 10 个文件），当前协议要求为每个文件单独发送 `OP_COMMIT`。没有标准的批处理信封来将多个操作原子化打包。

**问题严重度**: 中等
**建议**: 定义 `OP_BATCH` 消息类型，允许将多个 `OP_COMMIT` 打包为一个原子操作组，共享一个信封和 watermark

### 1.4 冗余握手评估

协议本身没有严格的"握手"——`HELLO` 是单向声明而非请求/响应。这是好的设计。但由于**缺少 Session Negotiation**（见 v0.1.3 重评报告 Section 1），参与者在 `HELLO` 之后可能发现自己与 session 不兼容，被迫立即发 `GOODBYE`，导致一次"加入-发现不兼容-离开"的无效交互。这不是冗余握手，但它是**缺少必要握手**导致的隐性浪费。

**问题严重度**: 中低

**效率性总评**: 协议在设计上选择了"语义完整性优先于传输效率"的路线，这对于 v0.1 草案是合理的。但如果不在 v0.2 中引入压缩信封、快速路径和批处理机制，该协议在高频协作场景下的实际吞吐量会成为瓶颈。

---

## 二、鲁棒性审计

### 2.1 参与者离线恢复：已有良好基础，但存在盲区

v0.1.1 引入的不可用检测和恢复机制（Section 14.4）是协议的一大亮点。`SUSPENDED` / `ABANDONED` 状态、`INTENT_CLAIM` 消息、first-claim-wins 竞态解决——这些都是经过思考的设计。

**但以下盲区仍然存在**：

**a) Session Coordinator 单点故障**
Section 8.1 定义了 coordinator 为 session 的唯一逻辑中心，但 coordinator 自身崩溃的恢复完全未定义。心跳检测、冻结作用域执行、身份绑定——所有关键运行时功能都依赖 coordinator。一旦 coordinator 不可用，整个 session 的协调能力归零。

Spec 仅说"分布式部署 MUST 提供等价机制"，但对于最常见的单 coordinator 部署，没有任何恢复指引。没有状态持久化要求，没有重启后状态重建的建议，没有 coordinator 故障转移的最低框架。

**问题严重度**: 高
**建议**:
- Section 8.1 增加 SHOULD 级要求：coordinator SHOULD 支持状态持久化（participant roster、intent registry、conflict state），以便从审计日志重建状态
- 定义 coordinator 不可用时参与者的行为：SHOULD 暂停所有冲突敏感操作，MAY 继续只读活动
- 建议（不强制）coordinator 心跳机制——参与者也应能检测 coordinator 的活性

**b) 网络分区下的脑裂风险**
如果网络分区导致部分参与者与 coordinator 断联但彼此可达，当前协议没有任何机制防止分区两侧的参与者同时对同一资源执行操作。这不是 MPAC 必须解决的问题（Section 4 明确了不替代 CRDT/OT），但协议应该**承认并声明**这个边界，而不是沉默。

**问题严重度**: 中等
**建议**: 在 Section 8.1 或 Non-Goals (Section 4) 中明确声明：MPAC 不保证网络分区下的一致性，分区场景下的冲突应在分区愈合后通过标准冲突报告机制追溯解决

**c) TTL 过期与操作提交的竞态**
Intent 的 TTL（`ttl_sec`）是墙钟秒数，但 spec 从未定义谁负责执行过期检查、检查的精度要求、以及过期瞬间提交的操作如何处理。如果 coordinator 使用本地墙钟检查 TTL，参与者的时钟偏差可能导致：Agent A 认为 intent 仍然有效并提交 OP_COMMIT，但 coordinator 判定 intent 已过期而拒绝该操作。

**问题严重度**: 中等
**建议**: 明确 TTL 由 coordinator 本地墙钟判定，`INTENT_ANNOUNCE` 中的 `ts` 仅用于审计。coordinator 在收到 `INTENT_ANNOUNCE` 时记录 `received_at` 时间戳，TTL 基于 `received_at + ttl_sec` 计算。

### 2.2 死锁风险分析

**a) 冻结作用域死锁——已基本解决**
v0.1.3 的 `frozen_scope_timeout_sec`（Section 18.6.2.1）提供了超时释放机制，这是对死锁的有效防护。设计允许禁用（设为 0），但默认启用（1800 秒）是合理的。

**b) 治理仲裁死锁——残留风险**
如果 session 中唯一的 arbiter 离线且无替代者，冲突会先升级、再冻结作用域、最后超时释放。但超时释放的结果是**全部拒绝**——这意味着双方的工作都被丢弃。对于长时间运行的协作 session，这是一个高代价的降级路径。

**问题严重度**: 中低
**建议**: 在超时释放时，增加一种 `deferred` 决策选项——将冲突暂挂而非全部拒绝，允许参与者继续其他不冲突的工作，待 arbiter 恢复后再处理积压冲突

**c) 循环冲突风险**
当前协议没有防止以下循环：A 的操作触发冲突 → 解决后 B 重新提交 → 再次触发冲突 → 解决后 A 又重新提交... 没有限制单个 scope 上的冲突轮次。

**问题严重度**: 低
**建议**: 增加 SHOULD 级建议——session 策略 MAY 定义同一 scope 上的最大冲突轮次（如 3），超过后要求人工介入

### 2.3 错误处理的完备性

`PROTOCOL_ERROR`（Section 22）提供了 10 种错误码，覆盖了常见的协议违规场景。这是合理的。但 `PROTOCOL_ERROR` 被定义为"informational"——不强制任何恢复行为。这意味着一个收到 `MALFORMED_MESSAGE` 错误的实现可以选择完全忽略它，继续发送畸形消息。

**问题严重度**: 低
**建议**: 对于安全关键错误（`AUTHORIZATION_FAILED`、`VERSION_MISMATCH`），增加 SHOULD 级后果——如收到 N 次 `AUTHORIZATION_FAILED` 后 coordinator SHOULD 暂停该参与者

**鲁棒性总评**: 参与者级故障恢复设计出色（SUSPENDED/ABANDONED/INTENT_CLAIM 是亮点），但 coordinator 单点故障、网络分区、TTL 竞态三个系统级故障场景缺乏覆盖。

---

## 三、扩展性审计

### 3.1 从 3 个 Agent 到 100 个：消息扇出问题

当前协议的消息模型是**广播式**的——每条消息对 session 中的所有参与者可见。在 3 个 Agent 的 session 中，这完全合理。但在 100 个 Agent 的 session 中：

- 每个 `INTENT_ANNOUNCE` 需要被 99 个其他参与者处理和冲突检测
- 每 30 秒的 HEARTBEAT 产生 100 条消息，所有参与者都需要接收
- 冲突检测的复杂度从 O(n) 变为 O(n²)——每个新 intent 需要与所有现有 intent 做 scope overlap 检查

**在 100 个 Agent 场景下的估算**：
- 心跳流量：~100 × 500B × 2/min = ~100KB/min = ~6MB/hour（仅心跳）
- Intent 冲突检测：如果每个 Agent 平均有 2 个活跃 intent，每个新 intent 需要 198 次 scope overlap 检查
- 消息总吞吐：假设每个 Agent 平均每分钟产生 5 条消息，总计 500 msg/min，每个参与者需要处理 500 msg/min 的入站消息流

**这不会让协议"崩溃"，但会导致显著的性能降级。**

**问题严重度**: 高
**建议**:
- 引入 **scope-based subscription**：参与者可以声明自己关注的 scope 范围，coordinator 只转发相关消息
- 引入 **intent registry 摘要推送**：不为每个 `INTENT_ANNOUNCE` 做全量广播，而是 coordinator 维护 intent 注册表的摘要（如布隆过滤器），定期推送给参与者，参与者在本地做初筛后再拉取详情
- 心跳消息考虑 coordinator 聚合——参与者向 coordinator 发心跳，coordinator 维护在线状态表，其他参与者按需查询而非被动接收全量心跳

### 3.2 Session Coordinator 的可扩展性

Section 8.1 要求每个 session 有且只有一个逻辑 coordinator。在大规模 session 中，coordinator 需要：
- 维护 100 个参与者的活性状态
- 处理所有消息的排序和转发
- 执行冻结作用域检查
- 验证身份绑定（Authenticated Profile）
- 维护审计日志

这是一个单点性能瓶颈。Spec 允许 coordinator 由分布式共识机制实现，但这句话更像是免责声明而非可操作的指引。

**问题严重度**: 中高
**建议**:
- 定义 coordinator 的最低性能要求建议（如：SHOULD 能处理 N 条消息/秒，N 由 session 规模决定）
- 考虑引入 **session 分片**（sharding）机制：大规模协作可以拆分为多个 sub-session，每个有独立 coordinator，通过 cross-session intent 引用实现协调
- 在 Section 9 中增加 session 规模的推荐上限（如：Core Profile 推荐 ≤ 20 参与者，Governance Profile 推荐 ≤ 50）

### 3.3 Scope Overlap 检测的计算复杂度

对于 `file_set` scope（Section 15.2.1.1），overlap 判定是集合交集，复杂度为 O(|A| × |B|)（朴素实现）或 O(|A| + |B|)（哈希集合）。这在 scope 较小时没问题，但如果单个 intent 的 scope 声明包含上千个文件（如大规模重构），且需要与 200 个活跃 intent 做交叉检查，计算量会显著增长。

`resource_path` 的 glob 匹配更昂贵——两个 glob pattern 的 overlap 判定在一般情况下是不可判定的（需要正则交集），spec 只要求 SHOULD 支持 `*` 和 `**`，但即使是这两个操作符，精确判定也不简单。

**问题严重度**: 中等
**建议**:
- 建议实现者为 scope overlap 检测维护索引结构（如 trie 或倒排索引）
- 定义 scope 声明的推荐大小上限（如：`file_set` 的 `resources` 数组 SHOULD 不超过 1000 个条目）
- 对 `resource_path` 的 glob overlap，提供参考算法或明确声明允许 false positive（保守判定为重叠）

### 3.4 Watermark 维护成本

`vector_clock` 的维护成本随参与者数量线性增长——每条消息的 watermark 需要包含所有参与者的时钟值。在 100 个参与者的 session 中，每个 watermark 对象约 2-3KB（100 个键值对），加上每条消息都需要 merge 逻辑。

Spec 选择 `lamport_clock` 作为 MUST 支持的 baseline 是正确的——它的维护成本为 O(1) 且与参与者数量无关。但 spec 没有建议大规模 session 应优先使用 `lamport_clock` 而非 `vector_clock`。

**问题严重度**: 低
**建议**: 增加实现指引——当 session 参与者超过 20 个时，SHOULD 优先使用 `lamport_clock`；`vector_clock` 适用于参与者少且需要精确因果追溯的场景

**扩展性总评**: 协议在 10 个以内参与者的场景下运行良好。扩展到 100 个参与者时，消息扇出、coordinator 瓶颈和 scope overlap 计算是三个需要解决的工程问题。协议不会"崩溃"，但性能会显著退化。需要引入 scope-based subscription 和 session 分片机制。

---

## 四、语义对齐审计

### 4.1 异构 Agent 之间的意图理解

MPAC 的 intent 模型使用自然语言字段（`objective`、`assumptions`）和结构化字段（`scope`）的混合。这是务实的设计——在当前技术条件下，完全形式化的意图表示不现实。

**但核心问题是：不同能力的 Agent 如何准确理解彼此的意图？**

一个 coding Agent 声明 `objective: "Tune training stability"` + `scope: file_set ["train.py"]`，一个 DevOps Agent 声明 `objective: "Update infrastructure config"` + `scope: entity_set ["deployment.training"]`——这两个意图在语义上可能冲突（修改训练代码 vs 修改训练部署配置），但在 scope 层面使用了不同的 `kind`，且没有 `canonical_uris`。

Section 15.2.1.3 要求跨 kind overlap 必须通过 canonical URIs 或 resource registry 判定，否则 SHOULD 保守地假设可能重叠。这个保守策略是正确的，但它的代价是**大量 false positive 冲突报告**，这会降低系统的信噪比，导致参与者和人类审核者疲于处理虚假冲突。

**问题严重度**: 中高
**建议**:
- 将 Section 15.2.2 的 `canonical_uris` 从 SHOULD 提升为 MUST（至少在跨组织 session 中）
- 定义一个 `CAPABILITY_NEGOTIATION` 阶段，让参与者在 session 开始时对齐 scope kind 的使用规范
- 建议（非强制）在 session metadata 中声明 "preferred scope kind"，引导所有参与者使用统一的 scope 表示

### 4.2 `semantic_match` 的可靠性边界

Section 17.7.1 定义了 `semantic_match` 基础结构，包括 `confidence` 字段和可配置的阈值（推荐 0.7）。这个设计是前瞻性的，承认了 LLM 推理在冲突检测中的角色。

**但问题在于**：`semantic_match` 的结果完全依赖于 matcher 的能力，而不同实现的 matcher 可能产出截然不同的结果。两个 MPAC 实现对同一对 intent 做 semantic match，一个说 `contradictory` (confidence: 0.85)，另一个说 `uncertain` (confidence: 0.45)——协议没有定义如何调和这种分歧。

**问题严重度**: 中等
**建议**:
- 明确声明 `semantic_match` 的判定以**冲突报告发送者**的 matcher 为准，接收方可以 `disputed`（CONFLICT_ACK）但不能单方面否定
- 定义 "matcher registry"：session 级声明使用哪个 matcher 作为权威，避免双方各执一词
- 低 confidence 的语义冲突 SHOULD 自动 escalate 到人工审核，而非在 Agent 之间来回争议

### 4.3 Assumption 语义的对齐问题

`INTENT_ANNOUNCE` 的 `assumptions` 字段是字符串数组，内容完全是自然语言。例如 `"hidden_dim remains 256"` 和 `"model architecture unchanged"` 在语义上可能等价也可能不等价——取决于解释者的理解。

协议依赖 `semantic_match`（Section 17.7.1）来检测 assumption 矛盾，但如果 session 中的 Agent 来自不同的技术栈或使用不同的术语体系，自然语言 assumption 的语义对齐会非常脆弱。

**问题严重度**: 中低
**建议**:
- 建议（非强制）在 assumption 中使用 "namespace:key=value" 格式（如 `"model:hidden_dim=256"`），为结构化比较提供基础
- 这可以作为 extension 而非核心要求，兼顾灵活性和精确性

### 4.4 Protocol Version 协商缺失

Section 25 定义了版本字段但没有定义版本协商。如果 Agent A 发送 version "0.1.3" 的消息，Agent B 只理解 "0.1.0"，应该如何处理？当前行为是 B 可以发 `PROTOCOL_ERROR` (VERSION_MISMATCH)，但没有定义降级协商路径。

**问题严重度**: 低（当前只有 v0.1.x）
**建议**: 在 Section 25 中预留版本协商机制的设计空间——至少定义 HELLO 响应中可以携带 coordinator 支持的版本范围

**语义对齐总评**: 协议在结构化语义（scope 对象、枚举值）方面做得合理，在非结构化语义（objective、assumptions）方面依赖 LLM 推理和人工审核。`canonical_uris` 和 `semantic_match` 是正确的方向，但前者使用率难以保证（SHOULD 而非 MUST），后者的跨实现一致性无法保证。

---

## 五、状态机交叉安全性审计

MPAC 定义了三个核心状态机（intent lifecycle、operation lifecycle、conflict lifecycle）以及三条语义排序约束（session-first、intent-before-operation、conflict-before-resolution）。这些状态机在运行时并发执行、相互引用。本节通过穷举关键交叉场景，检验协议是否存在不可达状态、孤儿对象或活锁风险。

### 5.1 Intent TTL 过期 + 孤儿 OP_PROPOSE（已确认漏洞）

**场景**：Agent A 发送 `INTENT_ANNOUNCE`（ttl_sec: 120）+ `OP_PROPOSE`，intent 到期后 OP_PROPOSE 仍在等待 reviewer 审批。

**协议覆盖情况**：**未覆盖**。

Intent 生命周期定义了 `ACTIVE → EXPIRED`（Section 15.6），operation 生命周期定义了 `PROPOSED → COMMITTED / REJECTED / ABANDONED`（Section 16.6）。但 `ABANDONED` 状态仅在 Section 14.4.3 中针对**参与者不可用**时定义。当 intent 因 TTL 到期而消亡时，协议没有定义其关联的 pending proposal 应如何处置——这条 proposal 引用了一个已不存在的 intent，但自身状态既不是 COMMITTED 也不是 REJECTED 也不是 ABANDONED。

**风险等级**: 高——这是最常见的操作路径上的状态不一致
**建议**: 增加规则：当 intent 状态变为 EXPIRED 时，所有引用该 intent 的 PROPOSED 状态操作 MUST 自动转为 REJECTED（reason: `intent_expired`），或提供一个宽限期（grace period）让提交者重新关联到新的 intent

### 5.2 Intent SUSPENDED + 他人的 Pending Proposal

**场景**：Agent B 基于 Agent A 的 intent（通过 OP_PROPOSE 的 intent_id 字段引用）提交了一条 proposal。随后 Agent A 掉线，其 intent 被标记为 SUSPENDED。

**协议覆盖情况**：**部分覆盖，存在残留漏洞**。

Section 14.4.2 明确禁止新的 OP_PROPOSE/OP_COMMIT 引用 suspended intent。Section 14.4.3 覆盖了不可用参与者自己发出的 in-flight proposal（标记为 ABANDONED）。但如果 proposal 的发送者（Agent B）仍然在线，只是它引用的 intent 的所有者（Agent A）不可用——Agent B 的 proposal 进入了一个 spec 没有定义的灰色地带：它不满足 ABANDONED 的触发条件（发送者在线），也不能继续推进（引用的 intent 已 suspended）。

**风险等级**: 中
**建议**: 扩展 Section 14.4.2 的规则——当 intent 进入 SUSPENDED 状态时，所有引用该 intent 的 PROPOSED 状态操作（无论发送者是谁）SHOULD 被冻结或提交到治理审核

### 5.3 Frozen Scope 期间 Intent TTL 耗尽

**场景**：A 和 B 的 intent 发生 scope overlap → CONFLICT_REPORT → 治理超时 → scope 冻结。冻结期间，A 和 B 的 intent 因 TTL 到期进入 EXPIRED 状态。

**协议覆盖情况**：**未覆盖**。

此时系统进入一个语义上自相矛盾的状态：
- 冲突（OPEN/ESCALATED）仍然存在，引用着两个已过期的 intent
- Frozen scope 的解除条件是"收到有效 RESOLUTION"（Section 18.6.2），但 RESOLUTION 需要对冲突中的 intent/operation 做出裁决（accepted/rejected/merged）
- 对已经 EXPIRED 的 intent 做出 accepted/rejected 裁决在语义上是空操作——无论裁决结果如何，这些 intent 都已经不存在了

Section 18.6.2.1 的 `frozen_scope_timeout_sec` 最终会兜底释放（自动拒绝 + 关闭冲突），但在 intent 过期到 frozen scope 超时释放之间的窗口内，系统处于一个**冲突存在但其关联实体已消亡**的不自洽状态。

**风险等级**: 中
**建议**: 增加规则——当冲突的所有 `related_intents` 均已过期或撤回时，冲突 SHOULD 自动转为 DISMISSED（reason: `all_related_intents_expired`），同时释放关联的 frozen scope。无需等待 frozen_scope_timeout

### 5.4 RESOLUTION 拒绝已 COMMITTED 操作的状态分裂

**场景**：Agent A 的 OP_COMMIT 已应用到 shared state。随后 RESOLUTION 将该操作标记为 rejected。

**协议覆盖情况**：**承认了问题但未强制解决**。

Section 18.4 要求 resolver "SHOULD" 提供补偿操作或声明 `rollback: "not_required"`。但 SHOULD 不是 MUST，一个合规实现可以发出 RESOLUTION 拒绝已 committed 的操作，既不回滚也不声明不需要回滚。结果是：**operation 的协议状态是 REJECTED，但 shared state 中它的效果仍然存在**——信令层和数据层状态分裂。

**风险等级**: 中
**建议**: 将 SHOULD 提升为 MUST——当 RESOLUTION 拒绝一个状态为 COMMITTED 的操作时，MUST 包含 `outcome.rollback` 字段（值为补偿操作引用或 `"not_required"`）

### 5.5 INTENT_CLAIM 审批与原参与者重连竞态

**场景**：Agent A 不可用 → intent 被 SUSPENDED → Agent B 提交 INTENT_CLAIM → 审批期间 Agent A 重连。

**协议覆盖情况**：**已解决**。

Section 14.4.4 明确定义："if the original participant reconnects before the claim is approved, the claim SHOULD be automatically withdrawn and the original intent restored to ACTIVE"。原参与者重连优先级高于 claim 审批。并发 claim 通过 first-claim-wins + CLAIM_CONFLICT 错误码解决。**这条路径完整闭合。**

### 5.6 超时级联与活锁风险

**场景**：A 和 B 反复提交 → 冲突 → 冻结 → 超时释放 → 重新提交 → 再次冲突，形成循环。

**协议覆盖情况**：**未覆盖**。

三条语义排序约束（session-first、intent-before-operation、conflict-before-resolution）本身是单向依赖链，不构成循环依赖，因此不会产生传统意义上的死锁。但当 TTL 超时（intent 层）、resolution_timeout（治理层）和 frozen_scope_timeout（冲突层）三个定时器并发触发时，级联效应可能表现为：scope 释放后 Agent 立刻重新提交 → 再次 overlap → 再次冻结 → 再次超时释放... 这是一个 **liveness violation**——系统在技术上一直在推进（状态在变化），但有效工作量为零。

**风险等级**: 中低——需要多个条件同时满足
**建议**: 增加 SHOULD 级规则——session 策略 MAY 定义同一 scope 上的最大冲突轮次（推荐默认值: 3），超过后该 scope 强制升级为人工仲裁，阻止自动化 Agent 无限重试

### 5.7 状态机交叉安全性总表

| 场景 | 涉及的状态机交叉 | 是否已解决 | 风险等级 |
|------|----------------|-----------|---------|
| Intent TTL 过期 + 孤儿 OP_PROPOSE | intent × operation | **未解决** | 高 |
| Intent SUSPENDED + 他人的 pending proposal | intent × operation × session | **部分解决** | 中 |
| Frozen scope + intent TTL 耗尽 | conflict × intent × governance | **未解决** | 中 |
| RESOLUTION 拒绝已 COMMITTED 操作 | governance × operation × shared state | **部分解决** (SHOULD) | 中 |
| INTENT_CLAIM vs 原参与者重连 | session × intent | **已解决** | — |
| 超时级联活锁 | intent × conflict × governance (三重超时) | **未解决** | 中低 |

**状态机交叉安全性总评**: 协议的三个核心状态机各自设计完整，排序约束方向正确。但状态机之间的**跨生命周期联动规则**严重不足——尤其是 intent 消亡（EXPIRED/SUSPENDED）对下游 operation 和 conflict 的影响几乎没有定义。建议在 v0.2 中用 TLA+ 或 Alloy 对 intent × operation × conflict 三重状态空间进行形式化验证，系统性地发现和封堵剩余的交叉漏洞。

---

## 六、综合优缺点总结

### 核心优点

1. **五层分离的架构设计**是该协议最大的智力贡献。将 intent 作为一等公民独立于 operation，把冲突和治理从操作层解耦——这种设计在多主体协调领域是正确且有前瞻性的。

2. **Intent-Before-Action 原则**是对标 MCP/A2A 的核心差异化。在 Governance Profile 下升级为 MUST 是 v0.1.3 的关键正确决策。

3. **参与者不可用恢复机制**（SUSPENDED → INTENT_CLAIM → TRANSFERRED）设计精巧，first-claim-wins + grace period 的竞态解决方案干净利落。

4. **冻结作用域 + 超时释放**的死锁防护是务实的工程选择，既防止了无限阻塞，又保留了可配置性。

5. **三级安全 Profile**（Open / Authenticated / Verified）的分层设计合理，允许不同信任环境选择对应的安全等级。

6. **v0.1.3 的 payload schema、scope overlap 标准化、lamport_clock baseline** 三项改动显著提升了跨实现互操作性。

### 核心缺点

1. **Session Coordinator 单点故障**：协议的所有运行时保证都依赖 coordinator，但 coordinator 自身无故障恢复定义。

2. **消息效率未优化**：全量广播 + 重量级信封 + 无批处理，在大规模 session 中会成为性能瓶颈。

3. **Session Negotiation 缺失**：参与者加入后才能发现不兼容，没有 pre-join capability 验证。

4. **扩展性缺乏架构支撑**：没有 scope-based subscription、session 分片或 coordinator 分布式化的标准方案。

5. **语义对齐依赖自然语言**：assumption 和 objective 的理解高度依赖 matcher 能力，跨实现一致性无保证。

6. **TTL 语义模糊**：墙钟 vs 逻辑时钟的歧义未完全消除，coordinator 的检查行为未规范。

---

## 七、具体修改建议（按优先级排序）

| 优先级 | 建议 | 影响的维度 | 预计工作量 |
|--------|------|-----------|-----------|
| P0 | 定义 intent 消亡时关联 OP_PROPOSE 的处置规则（intent_expired → auto reject） | 状态机安全 | 低 |
| P0 | 定义 coordinator 故障恢复最低要求（状态持久化 + 重启重建） | 鲁棒性 | 中 |
| P0 | 引入 SESSION_INFO 响应消息实现 session negotiation | 语义对齐 / 鲁棒性 | 中 |
| P0 | 冲突关联 intent 全部消亡时自动 DISMISS 冲突并释放 frozen scope | 状态机安全 | 低 |
| P1 | 定义 scope-based subscription 机制 | 扩展性 | 高 |
| P1 | 引入 compact envelope 或二进制序列化选项 | 效率性 | 中 |
| P1 | `canonical_uris` 在跨组织 session 中提升为 MUST | 语义对齐 | 低 |
| P1 | 明确 TTL 由 coordinator 本地墙钟判定 + received_at 语义 | 鲁棒性 | 低 |
| P2 | 引入 OP_BATCH 消息类型 | 效率性 | 中 |
| P2 | 定义 session 规模推荐上限和分片指引 | 扩展性 | 中 |
| P2 | 定义 op_kind 最小枚举集 | 语义对齐 | 低 |
| P2 | state_ref_format 在 session metadata 中声明 | 语义对齐 | 低 |
| P1 | RESOLUTION 拒绝 COMMITTED 操作时 rollback 字段从 SHOULD 提升为 MUST | 状态机安全 | 低 |
| P2 | INTENT_UPDATE 扩大 scope 时 SHOULD 触发冲突重检 | 鲁棒性 | 低 |
| P2 | 定义同一 scope 最大冲突轮次防止超时级联活锁 | 状态机安全 | 低 |
| P3 | Assumption 结构化格式建议（namespace:key=value） | 语义对齐 | 低 |
| P3 | 大规模 session 优先使用 lamport_clock 的实现指引 | 扩展性 | 低 |
| P3 | 安全关键 PROTOCOL_ERROR 的后果定义 | 鲁棒性 | 低 |

---

## 八、评分

| 维度 | 得分 (1-10) | 说明 |
|------|------------|------|
| **效率性** | **5.5** | 语义完整性优先于传输效率是合理策略，但缺少 compact envelope、batching 和 fast-path 机制，高频场景下开销偏大 |
| **鲁棒性** | **7.0** | 参与者级故障恢复出色，死锁防护务实，但 coordinator 单点故障、网络分区和 TTL 竞态是系统级盲区 |
| **扩展性** | **5.0** | 10 个参与者以内表现良好，缺乏 scope subscription、session 分片和 coordinator 分布式化支撑，100 个参与者时性能显著退化 |
| **语义对齐** | **6.5** | 结构化 scope 和 canonical URIs 方向正确，semantic_match 设计有前瞻性，但自然语言 assumption 的跨实现一致性存疑 |
| **状态机交叉安全性** | **4.5** | 单个状态机设计完整，排序约束正确，但跨生命周期联动规则严重不足——intent 消亡对下游 operation/conflict 的影响几乎未定义，存在多个已确认的孤儿对象和状态不一致场景 |
| **综合评分** | **5.7** | 作为 v0.1 草案，MPAC 在多主体协调领域提出了正确的抽象和有价值的机制，迭代方向良好。但状态机交叉安全性的缺陷暴露出协议在"并发正确性"上的系统性不足，建议在 v0.2 前引入 TLA+ 形式化验证。从"可实现的协议草案"到"生产就绪的互操作协议"，还需在状态机联动规则、效率优化、扩展性架构和 session negotiation 上做实质性工作 |

---

*审计结论：MPAC v0.1.3 是一份有明确学术价值和工程潜力的协议草案。其五层抽象模型和 intent-before-action 原则是对多 Agent 协调领域的原创性贡献。但状态机交叉安全性审计揭示了多个跨生命周期联动漏洞（孤儿 proposal、frozen scope 与 TTL 耗尽的死区、超时级联活锁），这些问题仅靠人工审查难以穷举。建议在 v0.2 前：(1) 补齐 intent 消亡对下游对象的联动规则（两个 P0 项）；(2) 用 TLA+ 或 Alloy 对 intent × operation × conflict 三重状态空间进行形式化验证；(3) 解决 coordinator 故障恢复和 session negotiation；(4) 启动 conformance test suite 开发。*
