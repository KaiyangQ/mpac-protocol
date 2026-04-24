# MPAC v0.1.6 独立技术评审报告

**评审人角色**: 模拟 SOSP/OSDI/NSDI 级别审稿人
**评审日期**: 2026-04-03
**文档版本**: MPAC Specification v0.1.6 (Draft / Experimental)

---

## 总体评价

MPAC 试图解决一个真实且重要的问题：当多个独立 principal（各自有代理 agent）需要在共享状态上协作时，如何进行协调。这个问题在现有的 MCP（agent-to-tool）和 A2A（agent-to-agent，单 principal）之间确实存在空白。

然而，作为一个协议规范，MPAC v0.1.6 在多个关键维度上存在严重的设计模糊性和工程可实现性问题。以下是逐维度的深入分析。

---

## 1. 核心设计与抽象

### 1.1 概念定义

MPAC 的核心概念层次为 Session → Participant → Intent → Operation → Conflict → Resolution，这是一个合理的分层。每个概念都有明确的 Section 定义，术语表（Section 5）也较清晰。

**正面评价**：将 conflict 和 resolution 提升为一等协议对象（而非隐藏在应用逻辑中）是一个好的设计决策。Intent-before-action 的理念也值得肯定——它在概念上类似于两阶段锁定中的 "声明阶段"。

### 1.2 存在的问题

**抽象层次混乱**：协议同时试图做两件事——定义消息语义（协议层），又定义实体生命周期状态机（运行时层）。例如，Intent 有一个状态机（DRAFT→ANNOUNCED→ACTIVE→...），但 DRAFT 状态"不要求在线上体现"（Section 15.6），这使得状态机的规范性大打折扣。一个协议规范应该要么完整定义线上可观察的状态转换，要么明确将内部状态排除在协议范畴之外。

**Session 定义过于松散**：Session 的 shared state 可以是 "file set, document graph, task graph, database snapshot, tool state machine, simulation state"（Section 9.5）。这种过度泛化意味着协议实际上无法对 state 做任何有意义的保证。对比：Raft 明确定义 replicated log，Paxos 明确定义 consensus value。MPAC 的 shared state 是一个完全不透明的外部概念，导致 `state_ref_before` / `state_ref_after` 的语义完全依赖实现。

**Scope 抽象过载**：Scope 支持 6 种 kind（file_set, resource_path, task_set, query, entity_set, custom），其中 `query` 和 `custom` 的 overlap 判定完全留给实现（Section 15.2.1.2）。这意味着两个符合 MPAC 的实现可能对同一对 scope 得出相反的 overlap 结论——直接破坏了冲突检测的互操作性。

### 1.3 缺失的抽象

**缺少 "Resource" 一等实体**：协议大量讨论 resource 的 overlap、lock、freeze，但 resource 本身没有独立的数据模型。Scope 引用 resource，Operation target resource，Frozen scope 锁定 resource——但 "resource" 始终是 string 级别的标识符，没有类型、版本、所有权等属性。这在真实系统中会导致大量的边界情况。

**缺少事务语义**：协议定义了 OP_PROPOSE 和 OP_COMMIT，但没有 atomic batch commit 的概念。如果一个 intent 涉及修改 3 个文件，agent 必须发送 3 个独立的 OP_COMMIT。在第 2 个 commit 之后、第 3 个之前，系统处于一个部分提交的状态——协议对此没有任何保证或处理机制。

---

## 2. 一致性与无歧义性

### 2.1 关键歧义点

**`OP_COMMIT` 的语义二义性**：`OP_COMMIT` 到底是 "请求提交"（需要 coordinator 确认）还是 "声明已提交"（agent 已经修改了 shared state）？Section 16.3 说 "declare that a mutation has been committed into shared state"，这暗示 agent 已经直接修改了 state。但 Section 16.6 的状态机显示 PROPOSED→COMMITTED，暗示这是一个需要批准的流程。如果 agent 在发送 OP_COMMIT 时已经修改了底层 state，那么 OP_REJECT 的语义是什么？数据已经被改了。如果没有修改，"committed" 这个词就是误导性的。

这是一个致命歧义。不同实现团队会做出完全不同的选择，导致互操作不可能。

**冲突检测的责任不清**：谁负责检测冲突？Section 17 说任何参与者都可以发送 `CONFLICT_REPORT`，coordinator 也可以。但如果 coordinator 做了冲突检测而某个 agent 没做（或做出了不同结论），系统行为是什么？没有定义。对比 Perforce 的做法：server 是冲突检测的唯一权威。

**"SHOULD" vs "MUST" 的过度使用**：协议中大量使用 SHOULD，使得几乎所有关键行为都变成了可选的。例如：
- "participants SHOULD announce intent before non-trivial work"（Section 15.3）—— 如果不 announce 呢？
- "implementations SHOULD detect and flag operations that fall outside the scope"（Section 23.3）—— 如果不检测呢？
- Watermark 在非 OP_COMMIT/CONFLICT_REPORT/RESOLUTION 消息中是 "SHOULD include"（Section 7.3）

当协议的核心机制（intent announcement、scope violation detection）都是 SHOULD 级别时，一个只实现 MUST 的实现和一个实现了全部 SHOULD 的实现之间几乎无法互操作。

### 2.2 术语问题

**`principal` vs `participant` vs `sender`**：三个概念有交叉。Principal 是 "accountable actor"，Participant 是 "principal currently joined to a session"，Sender 是消息级别的标识。但一个 principal 可以有多个 agent？一个人类 principal 可以通过不同设备发送消息吗？这些边界情况没有定义。

**`arbiter` 角色的权限边界模糊**：Arbiter "may resolve any conflict and override any participant"（Section 18.2），但 Section 18.5 说 arbiter 之间的分歧需要 "session policy SHOULD define a precedence rule"。如果 policy 没有定义呢？两个 arbiter 发出矛盾的 RESOLUTION 时系统行为完全未定义。

---

## 3. 并发与冲突处理

### 3.1 Race Condition 分析

**Intent-Operation 时间窗口竞态**：考虑以下场景：
1. Agent A 发送 INTENT_ANNOUNCE（scope: auth.py）
2. Agent B 发送 INTENT_ANNOUNCE（scope: auth.py）
3. Agent A 在看到 B 的 intent 之前发送 OP_COMMIT（target: auth.py）
4. Agent B 在看到 A 的 commit 之前发送 OP_COMMIT（target: auth.py）

此时两个 commit 都是合法的（每个 agent 的 watermark 可能都不包含对方的消息）。协议没有定义谁赢。`state_ref_before` 可以作为乐观并发控制的基础，但只有当 coordinator 顺序化处理 commit 时才有效——而 coordinator 是否必须做这件事，协议没有明确规定。

**RESOLUTION 竞态**：如果两个有权限的参与者（比如两个 owner）同时发送 RESOLUTION 解决同一个 conflict，结果如何？Section 18.5 提到多个 arbiter 时"SHOULD define precedence rule"，但对于多个 owner 同时 resolve 的情况完全没有处理。

**Frozen scope 边界竞态**：当 scope 被 freeze 时（Section 18.6.2），OP_COMMIT 会被 reject。但如果一个 OP_COMMIT 消息在 scope freeze 之前被发送、在之后到达 coordinator 呢？这取决于 coordinator 是否用自己的接收时间判断，还是用消息的 watermark 判断。没有定义。

### 3.2 死锁风险

**循环 scope 依赖死锁**：
1. Agent A 声明 intent，scope = {file1.py, file2.py}
2. Agent B 声明 intent，scope = {file2.py, file3.py}
3. Agent C 声明 intent，scope = {file3.py, file1.py}

如果冲突触发了 frozen scope（Section 18.6.2），三个 scope 可能互相锁定。虽然 frozen_scope_timeout_sec（Section 18.6.2.1）提供了超时回退，但 30 分钟的默认超时对于实时协作来说太长了。更重要的是，超时后所有冲突操作被 reject——没有任何启发式来判断应该保留谁的工作。

### 3.3 活锁风险

**Intent TTL 重试活锁**：如果两个 agent 的 intent 反复 overlap、expire、re-announce，系统可能进入活锁。协议没有退避（backoff）机制、优先级仲裁、或者 lease-based 的排他锁来打破对称性。

---

## 4. 故障处理与恢复机制

### 4.1 正面评价

Section 8.1.1（Coordinator Fault Recovery）和 Section 14.7（Participant Unavailability）是本规范中最充实的部分。State snapshot + audit log replay 的恢复策略是合理的。INTENT_CLAIM 机制（Section 14.7.4）为孤儿 intent 提供了 ownership transfer 路径。

### 4.2 关键问题

**Snapshot 一致性无保证**：Section 8.1.1.2 要求 coordinator "至少每个 heartbeat interval 持久化一次 state snapshot"，但 snapshot 和 audit log 之间可能存在 gap。如果 coordinator 在 snapshot 之后、下一次 snapshot 之前崩溃，且 audit log 也丢失（例如写入 audit log 本身是异步的），恢复后的状态就是过时的。协议说 "SHOULD use a write-ahead or atomic write mechanism"，但这是 SHOULD，不是 MUST。在 SOSP/OSDI 级别的系统中，这种 "SHOULD" 级别的持久性保证是不可接受的。

**STATE_DIVERGENCE 处理过于模糊**：Section 8.1.1.3 说，如果参与者的本地状态和 coordinator 的 snapshot 不一致，coordinator "SHOULD emit a PROTOCOL_ERROR with error_code: STATE_DIVERGENCE"。然后呢？"include the divergent message IDs for manual or governance-level resolution"——把最难的问题踢给了人类。在一个多 agent 系统中，如果 coordinator 崩溃恢复后发现有 3 个 agent 在 coordinator down 期间各自 commit 了不同的修改，仅仅报告 divergence 是不够的。需要定义 reconciliation 协议。

**一致性模型未声明**：协议从未明确声明它提供的是强一致性还是最终一致性。从设计来看（coordinator 是 single point of authority，但 agent 可以在 coordinator down 时继续 "read-only or non-conflicting activities"），这看起来像是一个有 coordinator 时强一致、coordinator down 时降级为最终一致的混合模型。但这从未被形式化。读者不知道协议提供什么保证。

**网络分区处理**：Section 8.1.1.1 说参与者在检测到 coordinator 不可用时 "suspend all conflict-sensitive operations"。但如果分区是参与者和 coordinator 之间的网络问题（而非 coordinator 崩溃），coordinator 还在正常运行、其他参与者还在正常工作，而被分区的参与者自己暂停了所有操作——这是一个不必要的可用性损失。更糟的是，coordinator 也会将该参与者标记为 unavailable，可能触发其 intent 的 SUSPENDED 转换。当网络恢复时，reconciliation 的复杂度远超协议当前的处理能力。

---

## 5. 安全与信任模型

### 5.1 正面评价

三层安全配置（Open / Authenticated / Verified）是一个务实的设计。Credential exchange（Section 23.1.4）支持多种认证方式。在 Verified profile 中要求消息签名 + tamper-evident log 是正确的方向。

### 5.2 关键问题

**Coordinator 是单点信任根**：在所有安全配置下，coordinator 拥有完整的权力——验证身份、分配角色、执行 scope freeze、决定冲突解决顺序。如果 coordinator 被攻破，攻击者可以冒充任何 principal、修改角色分配、操纵冲突解决。Verified profile 要求消息签名，但 coordinator 自身的行为没有被任何机制约束。在真正的多方对抗场景中，这是不可接受的。需要某种形式的 coordinator accountability——例如，coordinator 的所有决策也必须签名并可被独立审计。

**Replay protection 不够严格**：Authenticated profile 要求 "rejecting messages with duplicate message_id values or timestamps outside an acceptable window (RECOMMENDED: 5 minutes)"（Section 23.1.2）。5 分钟的 replay window 太大了。而且 message_id 的唯一性检查需要 coordinator 维护一个 "已见 message_id 集合"——如果 coordinator 崩溃恢复后这个集合丢失了呢？Snapshot 中没有包含这个集合。

**HELLO 消息中的 credential 传输安全**：在 Authenticated profile 中，bearer token 直接放在 HELLO payload 的明文字段里（Section 23.1.4 示例）。如果传输层不是 TLS（协议声称 transport-independent），token 就是明文传输的。虽然 Section 23.4 说 "SHOULD use TLS 1.3"，但这是 SHOULD。一个安全协议不应该在 SHOULD 级别的传输安全上传递 credential。

**恶意 Agent 的 Scope 欺骗**：Agent 可以声明一个很窄的 intent scope，然后 commit 一个超出 scope 的 operation。Section 23.3 说这 "SHOULD be logged and MAY trigger a CONFLICT_REPORT"——这完全不够。在跨组织场景中，这应该是 MUST reject。

---

## 6. 可实现性

### 6.1 可直接实现的部分

消息格式（JSON envelope + payload）定义清晰，有完整的 payload schema（Section 13.1）。基本的消息流（HELLO → SESSION_INFO → INTENT_ANNOUNCE → OP_COMMIT → CONFLICT_REPORT → RESOLUTION）是可实现的。

### 6.2 实现障碍

**Scope overlap 的 cross-kind 判定**：Section 15.2.1.3 说 cross-kind overlap "MUST be determined via canonical URIs or session resource registry"，如果两者都不可用，"SHOULD treat cross-kind scopes as potentially overlapping"。但 "potentially overlapping" 意味着什么？是立即触发 CONFLICT_REPORT 吗？是阻止 OP_COMMIT 吗？实现者面对的是一个无法确定行为的规范。

**Semantic match 的实现负担**：Section 17.7.1 定义了 semantic_match basis kind，包含 confidence、matched_pair、explanation 等字段。但协议说 "The semantic matching algorithm itself is explicitly outside the scope of MPAC"。这意味着实现 Semantic Profile 需要集成一个 NLP/LLM 系统，但协议不提供任何关于 threshold calibration、false positive handling、或者不同 matcher 之间一致性的指导。

**缺少状态机的形式化定义**：Intent 和 Operation 的状态机用 ASCII art 表示（Section 15.6, 16.6），但没有形式化的转换表（from_state, event, guard_condition → to_state, action）。例如，谁可以触发 ACTIVE→SUSPENDED 的转换？只有 coordinator？任何 governance authority？在什么条件下？

**缺少时序图或交互序列**：Section 27 给了一个 8 步的 "minimal flow"，但对于复杂场景（例如 coordinator failover 期间的 intent claim、frozen scope 的 escalation + timeout 序列），没有时序图。工程团队需要自己推导所有边界情况。

### 6.3 缺少的关键细节

- **消息大小限制**：没有定义。如果一个 CONFLICT_REPORT 的 description 字段包含 10MB 的文本呢？
- **并发 session 限制**：一个 agent 可以同时参与多少个 session？
- **消息投递保证**：协议说 transport 负责 delivery，但没有定义如果消息丢失了协议该怎么办（除了 watermark 可以检测 gap）。
- **Lamport clock 的维护规则**：谁递增 Lamport clock？每条消息都递增吗？只有 coordinator 递增吗？接收消息时如何更新？这些是实现 Lamport clock 的基本规则，但协议没有定义。

---

## 7. 与现有系统的对比

### 7.1 相似范式

**乐观并发控制 (OCC)**：MPAC 的 intent-announce + OP_COMMIT + state_ref_before 本质上是一个 OCC 变体。但标准 OCC（如数据库中的 MVCC）有明确的 abort-and-retry 语义，MPAC 没有。

**Two-Phase Commit (2PC)**：OP_PROPOSE → OP_COMMIT 看起来像 2PC 的 prepare → commit，但缺少 abort 协议和 coordinator-driven 的 commit 决策。

**Google Docs 式 OT/CRDT**：MPAC 明确说不是 CRDT/OT 的替代品（Section 4），但它也没有定义如何与 CRDT/OT 共存。如果 shared state 用 CRDT 管理，MPAC 的 state_ref_before/after 和 CRDT 的 causal consistency 之间是什么关系？

**Paxos/Raft**：Coordinator 的 single-leader 设计类似 Raft leader，但没有 election protocol、没有 log replication、没有 committed index 的概念。Section 8.1.1.4 提到了 failover，但实际上是 "somebody else takes over and loads a snapshot"——远不如 Raft 的保证严格。

### 7.2 创新性评估

MPAC 的核心创新在于将 **intent** 作为一等协议对象引入多 agent 协调。这不同于传统数据库事务（不声明意图）、也不同于传统锁（意图不是排他的，而是可以 overlap 后通过 governance resolve）。"Soft lock + structured conflict resolution" 这个设计点是有价值的。

但这个创新更多是 **概念层面** 的，而非 **机制层面** 的。协议没有提供任何新的分布式算法——它使用 Lamport clock、状态 snapshot、基于 timeout 的故障检测，这些都是经典技术。创新在于将这些技术组合到一个 agent coordination 的问题域中，并增加了 governance 层。

---

## 8. 关键缺陷（Top 5）

### 缺陷 #1：OP_COMMIT 语义二义性（严重程度：致命）

**问题**：OP_COMMIT 到底是 "声明已修改" 还是 "请求提交"？如果是前者，则 OP_REJECT 和冲突解决都需要 rollback，但协议没有 rollback 机制。如果是后者，"commit" 这个命名是误导性的。

**为什么危险**：这是整个 operation layer 的语义基础。如果实现 A 将 OP_COMMIT 理解为 "已修改 shared state"，而实现 B 理解为 "请求 coordinator 批准后再修改"，两者在同一个 session 中会产生灾难性的不一致——A 的 state 已经变了，B 还在等批准。

### 缺陷 #2：缺乏原子性保证（严重程度：高）

**问题**：一个涉及多个 resource 的 intent 需要多个独立的 OP_COMMIT。在部分 commit 的中间状态，其他 agent 可能看到不一致的 shared state，可能基于此做出错误的冲突判断或新的 commit。

**为什么危险**：在真实的协作编程场景中，重构经常涉及跨多文件的原子修改（例如重命名一个被多处引用的函数）。没有原子 batch commit，MPAC 无法安全地支持这类操作。Section 29（Future Work）承认了这个问题（"atomic multi-target operations"），但在当前版本中这是一个已知的安全缺口。

### 缺陷 #3：一致性模型未定义（严重程度：高）

**问题**：协议没有声明它提供什么一致性保证。在 coordinator 正常运行时，是否保证 linearizability？在 coordinator down 时，参与者继续 "non-conflicting activities" 的语义是什么——eventual consistency？

**为什么危险**：分布式系统的用户需要知道系统的一致性保证，才能正确地构建上层应用。如果 MPAC 不声明一致性级别，实现者会做出不同的选择（有的选择阻塞等 coordinator、有的选择继续执行），导致在相同场景下不同实现表现出不同行为——直接违反了互操作性目标。

### 缺陷 #4：Coordinator 信任过度集中（严重程度：中高）

**问题**：Coordinator 是身份验证者、角色分配者、冲突裁判的执行者、scope freeze 的执行者、snapshot 的维护者——所有信任都集中在这一个组件上。但 coordinator 自身的行为没有被任何机制约束或审计（Verified profile 中，coordinator 的消息是否也需要签名？）。

**为什么危险**：在跨组织场景中（MPAC 的核心 use case），coordinator 通常由某一方运营。如果运营方有利益冲突，他们可以通过 coordinator 操纵冲突解决、延迟竞争对手的 intent、或者选择性地执行 scope freeze。没有 coordinator accountability 机制，Verified profile 的安全保证大打折扣。

### 缺陷 #5：Frozen Scope 的可用性影响（严重程度：中）

**问题**：当冲突触发 frozen scope 时（Section 18.6.2），相关 resource 上的所有 write 操作被阻塞，直到冲突解决。默认 frozen scope timeout 是 30 分钟。如果 arbiter 不在线，30 分钟的阻塞对于实时协作系统来说是不可接受的。

**为什么危险**：在实际使用中，一个高频修改的核心文件（如 main.py, index.ts）上的 frozen scope 会导致所有 agent 停滞。30 分钟后的 fallback 是 "reject all conflicting operations"——也就是说，30 分钟的等待之后所有人的工作都被丢弃。这不是一个渐进降级的设计，而是一个 "等 30 分钟然后全部失败" 的设计。

---

## 9. 改进建议

### 建议 1：明确 OP_COMMIT 的执行模型

定义两种明确的模式：
- **Pre-commit mode**：OP_PROPOSE 是意向声明，OP_COMMIT 需要 coordinator 确认后才修改 shared state。适用于 Governance Profile。
- **Post-commit mode**：OP_COMMIT 是已完成修改的声明，coordinator 负责检测冲突并在需要时触发 compensating action。适用于 Core Profile。

两种模式必须在 SESSION_INFO 中声明，不能混用。

### 建议 2：引入 OP_BATCH 消息类型

定义一个 OP_BATCH 消息，包含多个 target 的原子操作：

```json
{
  "message_type": "OP_BATCH",
  "payload": {
    "batch_id": "batch-001",
    "intent_id": "intent-123",
    "operations": [
      { "op_id": "op-1", "target": "auth.py", "op_kind": "replace", ... },
      { "op_id": "op-2", "target": "routes.py", "op_kind": "replace", ... }
    ],
    "atomicity": "all_or_nothing"
  }
}
```

这解决了多文件原子修改的问题，也为 coordinator 提供了明确的 batch 冲突检测边界。

### 建议 3：声明一致性模型

在 Section 7（Shared Principles）中增加：
- **Coordinator-available**: 所有状态转换通过 coordinator 序列化，提供 total order。
- **Coordinator-unavailable**: 参与者只能执行 read-only 操作和本地缓存写入。coordinator 恢复后必须运行 reconciliation 协议。
- 明确声明 MPAC 不提供 linearizability（因为 agent 可以在声明 intent 和 commit 之间进行本地操作）。

### 建议 4：引入 Coordinator Accountability

在 Verified profile 中增加：
- Coordinator 的所有决策消息（SESSION_INFO, OP_REJECT, SCOPE_FROZEN 通知等）也必须签名。
- 任何参与者可以向外部审计服务提交 coordinator 的签名决策链，验证 coordinator 是否公正执行了协议。
- 在 session metadata 中声明 coordinator 的公钥，使所有参与者可以独立验证 coordinator 的消息。

### 建议 5：改进 Frozen Scope 降级策略

替换当前的 "等 30 分钟然后全部 reject" 策略，采用渐进式降级：
1. **Phase 1（0-60s）**：正常等待 resolution。
2. **Phase 2（60-300s）**：自动 escalate 到 arbiter；如果无 arbiter，允许 intent 优先级更高的 agent 继续。
3. **Phase 3（300s+）**：采用 first-committer-wins 策略，后到的 commit 被 reject 但不丢弃（转为 PROPOSED 状态可重新提交）。

这避免了长时间阻塞和 "全部失败" 的极端情况。

### 建议 6：形式化状态机

为 Intent、Operation、Conflict 各定义一个完整的状态转换表：

| Current State | Event | Guard | Next State | Action |
|---|---|---|---|---|
| ACTIVE | HEARTBEAT_TIMEOUT | owner unavailable | SUSPENDED | notify all, freeze ops |
| SUSPENDED | HELLO received | original owner | ACTIVE | unfreeze ops |
| SUSPENDED | INTENT_CLAIM approved | claim authorized | TRANSFERRED | transfer scope |

这消除了当前 ASCII 状态图中的歧义，为实现者提供可直接编码的规范。

### 建议 7：定义 Lamport Clock 维护规则

增加一个专门的小节：
- 每个参与者维护一个本地 Lamport counter。
- 发送消息时：counter++，将 counter 值作为 watermark.value。
- 接收消息时：counter = max(local_counter, received_counter) + 1。
- Coordinator 维护 session-global 的 Lamport counter，用于 snapshot 和 session close。

这是 Lamport clock 的标准语义，但协议必须明确写出，否则实现者可能做出不同选择。

---

## 总结评分

| 维度 | 评分 (1-5) | 说明 |
|---|---|---|
| 问题重要性 | 4.5 | 多 principal agent 协调是真实且重要的问题 |
| 核心设计 | 3.0 | Intent-first 理念好，但抽象层次有混乱 |
| 一致性/无歧义 | 2.0 | 多处致命歧义，SHOULD 过多 |
| 并发处理 | 2.0 | 缺乏对 race condition 的系统性分析 |
| 故障处理 | 3.0 | 有合理的框架，但细节不足 |
| 安全模型 | 3.5 | 三层 profile 设计好，但 coordinator trust 问题大 |
| 可实现性 | 2.5 | 缺少形式化状态机、时序图、关键细节 |
| 创新性 | 3.0 | 概念创新有价值，机制层面无新贡献 |

**总体判断**：这是一个有前景的协议设计，解决的问题确实存在空白。但作为一个可以用于跨实现互操作的规范，当前版本在 OP_COMMIT 语义、一致性模型、原子性保证等基础问题上存在致命歧义。建议进行 major revision，重点解决上述 Top 5 缺陷后再进入 stable 状态。

---

*本评审基于 MPAC Specification v0.1.6 文档，模拟 SOSP/OSDI/NSDI 级别审稿标准进行独立技术评估。*
