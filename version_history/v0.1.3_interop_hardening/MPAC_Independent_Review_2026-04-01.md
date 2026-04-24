# MPAC v0.1 独立评审报告

**评审日期**: 2026-04-01
**评审对象**: SPEC.md (MPAC v0.1，含 v0.1.1 和 v0.1.2 的增补内容)
**评审者立场**: 协议设计领域独立评审，假设我需要指导一个工程团队基于此 spec 实现一个可互操作的 runtime

---

## 1. 协议设计：核心抽象评估

### 1.1 五层抽象基本合理，但层间耦合定义不足

Session → Intent → Operation → Conflict → Governance 这五层（Section 6）的划分方向是对的。在多 principal 协调场景下，intent 作为 pre-execution 声明是核心差异化设计，把冲突和治理独立出来也是正确的选择。

**但问题在于层间的交互契约几乎是空的。** Section 6 说"Implementations MAY merge these layers internally, but their externally visible semantics SHOULD remain distinct"，这句话本身就是矛盾的——如果你允许内部合并但要求外部语义不同，你必须定义什么构成"外部语义"。目前没有这个定义。

### 1.2 Intent 是最有价值也最脆弱的抽象

Intent-before-action（Section 7.1）是 MPAC 对比 MCP/A2A 的最强设计点。但 spec 把它定义为 SHOULD 而非 MUST（"Participants SHOULD announce intent before committing non-trivial operations"），这意味着一个完全合规的实现可以永远不发 intent，直接发 OP_COMMIT。此时 MPAC 退化成一个没有冲突预检的操作日志协议，核心价值归零。

**建议**：Section 7.1 应将 intent-before-action 提升为 MUST（至少在 Governance Profile 下），或者在 Core Profile 中明确说明跳过 intent 的后果（比如操作自动标记为 uncoordinated，优先级降低）。

### 1.3 缺失的抽象：Session Negotiation

目前 Session 的创建（Section 9.2）支持三种方式（显式、隐式、带外），但没有 capability negotiation 阶段。两个实现 join 同一个 session 时，没有标准方法确认：双方支持的 watermark kind 是否兼容？冲突检测策略是否对齐？安全 profile 是否匹配？

HELLO 消息（Section 14.1）携带了 capabilities 列表，但 spec 没有定义收到不兼容 capabilities 时该怎么办。没有 negotiation 失败的路径。

### 1.4 多余的概念：winner/loser 简写

Section 18.4 引入了 `winner`/`loser` 作为 `outcome` 的简写。这在 spec 层面引入了两种不等价的表达同一语义的方式，直接增加互操作负担。协议 spec 不应该提供语法糖。**建议删除。**

---

## 2. 可实现性：两个团队能否写出兼容实现？

### 2.1 最大的互操作风险：scope overlap 判定无标准算法

Section 15.2 定义了 6 种 scope kind（file_set、resource_path、task_set、query、entity_set、custom），但 overlap 判定完全留给实现。Section 15.2.1 的 canonical_uris 是 MAY，Section 15.2.2 的 resource registry 也是 MAY。

**这意味着**：Team A 用 file_set 精确匹配判断无冲突，Team B 用 resource_path 的 glob 展开判断有冲突，两个完全合规的实现对同一场景产生矛盾的冲突报告。这不是边界情况，这是最常见的操作路径上的分歧。

参照实际代码（`conflict_detector.py`），参考实现用的是纯字符串集合交集（`targets & existing.scope.targets()`），resource_path 的 glob 根本没有被展开——这已经是一个 spec-vs-implementation 的分歧了。

**建议**：至少对 file_set 这个最常见的 scope kind，MUST 级定义 overlap 判定规则（规范化路径后的字符串精确匹配）。对 resource_path，定义 MUST 支持的最小 glob 子集。

### 2.2 Watermark 互操作是假的

Section 12.2 列出四种 watermark kind（vector_clock、lamport_clock、causal_frontier、opaque），Section 12.3 说"如果收到不认识的 kind，MAY 继续处理但 SHOULD 视因果判断为 partial"。

**问题**：两个实现如果分别用 vector_clock 和 lamport_clock，它们完全无法比较因果关系。Spec 没有定义 watermark 的比较语义，没有定义一个实现如何验证另一个实现的 watermark 声称的因果完整性。这意味着 watermark 在跨实现场景下只是一个不透明的审计字段，不是一个可操作的因果机制。

**建议**：要么 MUST 规定至少一种 watermark kind 的比较语义（推荐 lamport_clock，最简单），要么坦诚承认跨实现因果比较在 v0.1 中不可行，将 watermark 降级为纯审计用途。

### 2.3 没有 JSON Schema，payload 结构全靠例子推断

Section 29 把 JSON Schema 定义列为 future work，但这意味着所有 payload 结构只能从 Section 28 的例子中反向推导。比如：

- `INTENT_ANNOUNCE` 的 `assumptions` 是 MUST 还是 MAY？（spec 说 SHOULD include，但如果不包含呢？）
- `OP_COMMIT` 的 `state_ref_before` 可以为 null 吗？（参考实现允许 None）
- `CONFLICT_REPORT` 的 `related_intents` 和 `related_ops` 可以都为空吗？

没有 schema，每个 field 的 required/optional 和类型约束完全是猜的。**这是阻碍互操作的最基础问题。**

**建议**：v0.1 必须包含每种 message type 的 payload schema，至少定义 required fields、field types、枚举值集合。不需要完整的 JSON Schema 文件，嵌入 spec 的表格形式足矣。

---

## 3. 边界情况

### 3.1 并发 INTENT_CLAIM 竞态

Section 14.4.4 定义了 INTENT_CLAIM 但没有处理两个 participant 同时 claim 同一个 suspended intent 的情况。谁赢？先到先得？需要治理审批？如果两个 claim 同时到达 session coordinator，coordinator 的行为未定义。

**建议**：MUST 定义竞争 claim 的仲裁规则，最简单的方案是 first-claim-wins + 后续 claim 收到 PROTOCOL_ERROR。

### 3.2 TTL 过期与 OP_COMMIT 的竞态

Intent 有 TTL（Section 15.3），但如果 agent 在 TTL 到期的同时提交了 OP_COMMIT 且引用了该 intent，该操作是否有效？参考实现（`engine.py` line 453-459）在每次 `_process` 时检查 TTL，使用 lamport clock 而非墙钟——这意味着 TTL 语义与 spec 描述的 `ttl_sec`（秒）完全不一致。

**这不是实现 bug，是 spec 的歧义**：TTL 是墙钟时间还是逻辑时间？在分布式环境下这两者差异巨大。

**建议**：明确 TTL 基于墙钟（UTC timestamp），因为 `ttl_sec` 的命名已经暗示了这一点。将逻辑时钟用法标记为参考实现的简化。

### 3.3 Frozen Scope 的活锁风险

Section 18.6.2 说 frozen scope 下 OP_PROPOSE 和 OP_COMMIT 被拒绝，但 INTENT_ANNOUNCE 仍然被接受。这意味着在 scope 冻结期间，新的 intent 可以不断声明覆盖冻结区域的计划，但没有任何操作能推进，而每个新 intent 可能触发新的 CONFLICT_REPORT，进一步复杂化治理决策。

**建议**：frozen scope 下也应 reject 或 defer 新的 INTENT_ANNOUNCE（而非仅 warn），或者至少 SHOULD NOT 允许新 intent 的 scope 完全包含在 frozen scope 内。

### 3.4 Resolution 后状态恢复未定义

Section 18.4 定义了 RESOLUTION 可以 accept/reject intent 和 operation，但没有定义：如果被 reject 的 operation 已经 COMMITTED（即已经修改了 shared state），会发生什么？Spec 只定义了操作的 lifecycle 状态变迁，但没有定义 shared state 的回滚语义。

参考实现（`governor.py` line 88-104）在 resolution 时直接修改 intent/operation 的状态，但从不回滚 `shared_state` dict 中已经写入的值。这意味着 reject 一个已 committed 的 operation 在状态上是矛盾的。

**建议**：明确声明 MPAC 不负责 shared state 回滚（这交给应用层），但 MUST 要求 RESOLUTION 的 `rejected` 列表中的 operation 如果状态为 COMMITTED，resolver 必须同时提供一个补偿操作（compensating OP_COMMIT）或声明 no-rollback-needed。

---

## 4. 规范性语言

### 4.1 以下 SHOULD 应升级为 MUST

| Section | 当前措辞 | 建议 | 理由 |
|---------|----------|------|------|
| 7.1 | "Participants SHOULD announce intent" | MUST（Governance Profile 下） | 否则核心价值空转 |
| 7.3 | "Committed operations and conflict reports SHOULD include causal context" | MUST | 因果追溯是核心设计目标，SHOULD 会导致大量无因果上下文的消息 |
| 11.4 | "`ts` SHOULD use RFC 3339" | MUST | 时间戳格式不统一会导致排序和审计失败 |
| 14.1 | "a participant SHOULD send HELLO when entering" | MUST | Section 8.1 已要求 session-first，HELLO 语义上已是 MUST |
| 18.7 | "RESOLUTION SHOULD include watermark" | MUST（Verified Profile 下已是 MUST，但 Authenticated Profile 下也应是） | 无因果上下文的 resolution 无法审计 |

### 4.2 以下 MUST 可能过严

| Section | 当前措辞 | 建议 | 理由 |
|---------|----------|------|------|
| 14.4.2 | "active intents MUST be transitioned to SUSPENDED" | SHOULD | 实现可能选择直接 WITHDRAW 而非 SUSPEND，取决于业务场景 |
| 23.1 | "Sessions MUST declare which security profile they operate under" | SHOULD，未声明时默认 Open | 对简单开发环境过于严格 |

---

## 5. 与 MCP 和 A2A 的定位

### 5.1 差异化定位基本成立

Section 2.1 对 MCP（agent-to-tool）和 A2A（single-principal agent-to-agent）的定位分析是准确的。MPAC 锚定在 multi-principal 协调层，这确实是一个未被覆盖的空间。

### 5.2 但 spec 没有定义与 MCP/A2A 的集成点

如果 MPAC 要在真实系统中落地，agent 几乎必然同时使用 MCP（调工具）、A2A（委派子任务）和 MPAC（跨 principal 协调）。Spec 没有定义：

- 一个 MPAC operation 如何包装一个通过 MCP 执行的工具调用？
- 一个 A2A 的 task delegation 如何映射到 MPAC 的 intent？
- 三个协议的 session/context 如何关联？

**这不是 scope creep 的问题——这是采用者最先问的问题。** 建议至少在 Section 29 的 future work 中给出一个集成架构的草图，或者在 Non-Goals（Section 4）中明确说明 MPAC 不负责定义这些集成点。

### 5.3 过度设计的部分

Semantic Profile（Section 20.3）和 semantic_match basis（Section 17.7.1）对于 v0.1 来说可能过早。标准化 LLM 推理结果的输出格式在没有 interop test suite 的情况下价值有限——每个实现的 LLM 会产出完全不同的 confidence 和 explanation，"格式统一"并不带来"语义互操作"。

### 5.4 不足的部分

缺少对**批量操作**的任何考虑。真实场景中 agent 经常一次性修改多个文件（一个 git commit 可能改 20 个文件），但 OP_COMMIT 的 `target` 是单数。Spec 没有定义 atomic multi-target operation，也没有说明如何用多个 OP_COMMIT 表达原子性。

---

## 6. 安全模型

### 6.1 三级安全 profile 的设计思路正确

Open → Authenticated → Verified 的渐进式安全模型（Section 23.1）是务实的，避免了"one-size-fits-all"的陷阱。

### 6.2 Authenticated Profile 缺少 sender 绑定的执行机制

Section 23.1.2 说"implementations MUST bind each sender field to the authenticated identity"，但没有定义这个绑定在哪里执行。如果是 session coordinator 执行，那中心化的 coordinator 成了安全瓶颈。如果是 peer-to-peer 执行，那每个 peer 都需要持有所有参与者的 credential。

**建议**：明确声明 sender 绑定由 session coordinator（或等价的 gateway 层）在消息入口处执行，或者定义一个 token-binding 机制让任何参与者都能验证。

### 6.3 没有防止 governance 权限升级的机制

Spec 定义了角色（Section 10.3）和权限映射（Section 18.2），但没有定义角色变更流程。一个 contributor 如何/能否在 session 中被提升为 owner？如果能，由谁授权？如果不能，spec 应该说明。

目前的 spec 下，如果 session coordinator 被攻陷，attacker 可以在 HELLO 时声明任意 role（包括 arbiter），在 Open Profile 下没有任何阻止机制，在 Authenticated Profile 下也只验证了 identity 而未验证 role 声称的合法性。

**建议**：Section 23 应增加 role assertion 验证要求——至少在 Authenticated Profile 下，role 声明 MUST 由 session policy 或 coordinator 验证后才能生效。

### 6.4 缺失：消息机密性

三个 security profile 都没有提及消息内容的加密。在 cross-organizational 场景下（Verified Profile 的目标场景），transport-level TLS 可能不够——中间的 session coordinator 能看到所有消息明文。如果 coordinator 由第三方运营，这是一个真实的隐私风险。

**建议**：至少在 Section 23.4 的 general considerations 中提及端到端加密的需求。

---

## 7. 三个最影响落地的问题

如果只能指出三个问题，我选择这三个：

### #1：没有 Payload Schema（Section 29 的最大 debt）

没有 schema 就没有互操作。每个实现都在猜 field 的 required/optional、类型、默认值。两个团队基于同一份 spec 写出的实现在 field 级别必然不兼容。这不是 future work，这是 v0.1 的前置条件。

**行动项**：在发布 v0.1 stable 之前，为 Section 13 中列出的所有 16 种 message type 添加 payload schema 表格。每个 field 标注 required/optional、type、default、enum values。这比写 JSON Schema 文件快得多，但足以让两个独立团队写出兼容实现。

### #2：Scope Overlap 判定无标准化（Section 15.2）

冲突检测是 MPAC 的核心价值，而冲突检测的第一步是 scope overlap 判定。当前 spec 把这完全留给实现，相当于把协议最核心的语义决策外包了。结果是两个合规实现对同一场景产出不同的冲突判断，用户无法信任冲突报告的一致性。

**行动项**：为 file_set 和 entity_set 定义 MUST 级的 overlap 判定规则（规范化后字符串精确匹配 + 集合交集）。将 canonical_uris（Section 15.2.1）从 MAY 提升为 SHOULD（在多 scope kind 环境下）。承认 query 和 custom kind 的 overlap 在 v0.1 中无法标准化。

### #3：Watermark 的假性互操作（Section 12）

Spec 给出了四种 watermark kind 但没有比较语义，导致 watermark 在跨实现场景下实际上不可操作。这使得因果追溯——spec 的六大设计目标之一——在异构部署中无法实现。

**行动项**：选择 lamport_clock 作为 MUST 支持的 baseline watermark kind。定义其比较规则（单调递增整数，greater-than 表示 happens-after）。允许其他 kind 作为 optional extension，但 MUST 能降级到 lamport_clock 比较。

---

## 附录：参考实现与 Spec 的偏差

在审查参考实现代码时发现以下 spec-vs-code 不一致：

1. **IntentState 缺失 SUSPENDED 和 TRANSFERRED**：`models/intent.py` 的 `IntentState` 枚举没有这两个状态，但 Section 14.4 和 15.6 定义了它们。参考实现无法执行 unavailability recovery 流程。

2. **TTL 使用 lamport clock 而非墙钟**：`engine.py` line 458 用 `lamport_clock - created_at_tick >= ttl_sec` 做 TTL 检查，但 `ttl_sec` 的命名和 Section 15.3 的语义暗示墙钟秒数。

3. **Scope.contains 的空集逻辑反转**：`intent.py` line 54 在 `targets()` 返回空集时 `contains()` 返回 True（即空 scope 包含一切），这与 spec 没有明确对应。

4. **canonical_uris 完全未实现**：conflict_detector.py 做 overlap 检测时只用 `targets()` 集合交集，没有任何 canonical_uris 处理逻辑。

5. **INTENT_CLAIM 未实现**：engine.py 的 handler map 中没有 INTENT_CLAIM 的处理。

这些偏差本身可以理解（参考实现是 v0.1 baseline 时期写的，后续 spec 增补没有同步回代码），但它们恰好印证了前面的结论：spec 中太多关键语义停留在 SHOULD/MAY 层面，参考实现可以"合规地"不实现它们。

---

## 总体评价

MPAC 瞄准了一个真实且未被覆盖的协议空间（multi-principal agent coordination），核心抽象（intent → operation → conflict → governance）的方向是正确的。与 MCP/A2A 的定位区分是有说服力的。

但当前版本在三个层面上离"可互操作的协议规范"还有距离：**数据格式不精确**（无 schema）、**核心语义太灵活**（scope overlap、watermark 全部 MAY）、**安全模型缺执行细节**。这三个问题不解决，MPAC 更接近一个"设计理念文档"而非一个"协议规范"。

好消息是这些问题都是可修复的，且不需要修改协议的核心架构。建议在 v0.2 中优先解决 payload schema 和 scope overlap 标准化，这两项改动可以在不改变协议模型的前提下显著提升互操作性。
