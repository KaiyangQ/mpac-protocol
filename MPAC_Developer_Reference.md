# MPAC v0.1.14 Developer Reference

面向实现者的技术参考文档。本文档以数据结构为中心，定义所有模块、字段、枚举值、状态机和模块间引用关系。

**约定**：R = 必填，O = 可选，C = 条件必填（取决于其他字段的值）

---

## 1. 核心数据对象

MPAC 的所有消息和状态都由以下核心数据对象组成。理解它们之间的引用关系是实现协议的基础。

### 1.1 Principal（参与者身份）

描述一个参与 session 的主体。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `principal_id` | string | R | 唯一标识，格式推荐 `{type}:{name}`，如 `agent:alice-coder-1` |
| `principal_type` | string | R | 枚举：`human` / `agent` / `service` |
| `display_name` | string | O | 人类可读名称 |
| `roles` | string[] | O | 角色列表，见 [枚举：Roles](#61-roles) |
| `capabilities` | string[] | O | 能力列表，见 [枚举：Capabilities](#62-capabilities) |

**被引用于**：Message Envelope 的 `sender` 字段、INTENT_CLAIM 的 `original_principal_id`、CONFLICT_ESCALATE 的 `escalate_to`

---

### 1.2 Message Envelope（消息信封）

所有 MPAC 消息的外层包装。每条消息无论类型都必须有这个结构。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `protocol` | string | R | 固定值 `"MPAC"` |
| `version` | string | R | 协议版本，如 `"0.1.13"` |
| `message_type` | string | R | 消息类型，见 [消息类型清单](#2-消息类型清单) |
| `message_id` | string | R | 消息唯一 ID，在系统范围内唯一 |
| `session_id` | string | R | 所属 session 的 ID → 关联 [Session](#13-session) |
| `sender` | object | R | 发送者信息，结构为 `{ principal_id, principal_type, sender_instance_id }`。其中 `sender_instance_id` 标识该 sender 在本 session 内的进程实例/发送者化身 → 关联 [Principal](#11-principal参与者身份) |
| `ts` | string | R | RFC 3339 UTC 时间戳，如 `"2026-04-02T10:00:00Z"` |
| `payload` | object | R | 消息体，结构因 `message_type` 不同而不同 |
| `watermark` | Watermark | O | 因果上下文，见 [Watermark](#14-watermark因果水位) |
| `in_reply_to` | string | O | 回复的目标 `message_id` |
| `trace_id` | string | O | 分布式追踪 ID |
| `policy_ref` | string | O | 策略引用 |
| `signature` | string | O | 消息签名（Authenticated/Verified profile 下使用） |
| `coordinator_epoch` | integer | C | 仅 coordinator-authored message 必填。Coordinator 权威 epoch，用于 failover/handover fencing |
| `extensions` | object | O | 扩展字段，格式 `{ "vendor.name": { ... } }` |

**关键约束**：
- `OP_COMMIT`、`CONFLICT_REPORT`、`RESOLUTION` 的 `watermark` 为 **MUST**（虽然信封层面它是 optional 字段，但这三种消息类型强制要求）
- `message_id` 在 Authenticated / Verified profile 下用于重放检测，coordinator 会拒绝重复值；恢复后必须继续执行同一 replay-protection 策略
- Lamport 单调性按 `(sender.principal_id, sender.sender_instance_id)` 这对 sender incarnation 进行判断，而不是只看 `principal_id`
- 所有 coordinator-authored message 都必须携带 `coordinator_epoch`；接收方在判断 coordinator 权威时优先比较 epoch，再在同 epoch 内比较 Lamport watermark

---

### 1.3 Session（会话）

Session 不是一条消息，而是一个状态容器，通过 session metadata 配置。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | string | R | 唯一标识 |
| `protocol_version` | string | R | MPAC 版本 |
| `security_profile` | string | R | 枚举：`open` / `authenticated` / `verified` |
| `compliance_profile` | string | O | 枚举：`core` / `governance` / `semantic` |
| `execution_model` | string | R | 枚举：`pre_commit` / `post_commit`。声明本 session 的执行模型，见 [Section 7.8] |
| `governance_policy` | object | O | 治理配置，见 [Governance Policy](#15-governance-policy治理策略) |
| `liveness_policy` | object | O | 活性配置，见 [Liveness Policy](#16-liveness-policy活性策略) |
| `resource_registry` | object | O | 资源注册表，见 [Resource Registry](#17-resource-registry资源注册表) |
| `state_ref_format` | string | O | state_ref 的格式声明，如 `"sha256"` / `"git_hash"` / `"monotonic_version"` |

**注意**：Session 不在消息中直接传输。它通过 `SESSION_INFO` 消息的 payload 暴露给参与者。

---

### 1.4 Watermark（因果水位）

表达"我发送这条消息时，已经知道了哪些前置状态"。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `kind` | string | R | 枚举：`lamport_clock`（MUST 支持） / `vector_clock` / `causal_frontier` / `opaque` |
| `value` | any | R | kind 决定类型：`lamport_clock` → integer，`vector_clock` → `{ participant: clock }` 对象，其他 → string |
| `lamport_value` | integer | O | 当 kind 不是 `lamport_clock` 时 SHOULD 提供此字段作为降级比较值 |

**比较语义**（`lamport_clock`）：
- `a < b` → a happened-before b
- `a == b` 或不可比 → 并发或不确定

**被引用于**：Message Envelope 的 `watermark` 字段、CONFLICT_REPORT 的 `based_on_watermark` 字段

---

### 1.5 Governance Policy（治理策略）

Session 级配置，控制冲突解决和权限行为。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `require_arbiter` | boolean | `false` | Governance profile 下 MUST 为 true |
| `resolution_timeout_sec` | integer | `300` | 冲突未解决超时秒数，0 = 禁用 |
| `timeout_action` | string | `"escalate_then_freeze"` | 超时后动作 |
| `frozen_scope_behavior` | string | `"reject_writes_and_intents"` | frozen scope 下的拒绝策略 |
| `frozen_scope_phase_1_sec` | integer | `60` | Phase 1（正常解决）持续时间 |
| `frozen_scope_phase_2_sec` | integer | `240` | Phase 2（自动升级 + 优先级旁路）持续时间 |
| `frozen_scope_phase_3_action` | string | `"first_committer_wins"` | Phase 3 降级动作 |
| `frozen_scope_disable_phase_3` | boolean | `false` | 是否禁用 Phase 3 自动降级。`true` = scope 无限冻结直到手动解决（不推荐） |
| `intent_expiry_grace_sec` | integer | `30` | Intent 过期后，关联 proposal 被自动拒绝前的宽限期 |

---

### 1.6 Liveness Policy（活性策略）

Session 级配置，控制心跳和不可用检测。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `heartbeat_interval_sec` | integer | `30` | 心跳发送间隔 |
| `unavailability_timeout_sec` | integer | `90` | 连续无消息超过此时间判定不可用 |
| `orphaned_intent_action` | string | `"suspend"` | 不可用时 intent 的处理方式 |
| `orphaned_proposal_action` | string | `"abandon"` | 不可用时 proposal 的处理方式 |
| `intent_claim_approval` | string | `"governance"` | INTENT_CLAIM 的审批方式 |
| `intent_claim_grace_period_sec` | integer | `30` | Core profile 下 claim 自动审批前的宽限期 |
| `backend_health_policy` | object | O | AI 模型后端健康监控策略 | |

---

### 1.7 Resource Registry（资源注册表）

可选的 session 级配置。将不同 scope kind 的表示映射到统一的 canonical URI。

```
resource_registry.mappings[] → 每项包含：
  canonical_uri: string        → 标准资源 URI
  aliases[]:                   → 别名列表
    kind: string               → scope kind
    value: string              → 该 kind 下的资源标识
```

**用途**：当 session 中的参与者使用不同 scope kind（如一方用 `file_set`，另一方用 `entity_set`）时，registry 让 coordinator 能判断它们是否指向同一资源。

---

### 1.8 Scope（作用域）

描述一个 intent 或 operation 的目标资源集合。是冲突检测的核心输入。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `kind` | string | R | 枚举：`file_set` / `resource_path` / `task_set` / `query` / `entity_set` / `custom` |
| `resources` | string[] | C | kind = `file_set` 时必填。文件路径数组 |
| `pattern` | string | C | kind = `resource_path` 时必填。glob 模式 |
| `task_ids` | string[] | C | kind = `task_set` 时必填。任务 ID 数组 |
| `expression` | string | C | kind = `query` 时必填。查询表达式 |
| `language` | string | C | kind = `query` 时必填。查询语言标识 |
| `entities` | string[] | C | kind = `entity_set` 时必填。实体名称数组 |
| `canonical_uris` | string[] | O | 标准资源 URI。Authenticated/Verified profile 跨 kind session 下为 MUST |
| `extensions` | object | O | 实现特定扩展 |

**Overlap 判定规则**：

| kind | 算法 | 级别 |
|------|------|------|
| `file_set` | 规范化路径（去 `./`、折叠 `//`、去尾 `/`）后字符串精确匹配，取集合交集 | MUST |
| `entity_set` | 字符串精确匹配，取集合交集 | MUST |
| `task_set` | 字符串精确匹配，取集合交集 | MUST |
| `resource_path` | 最小支持 `*` 和 `**` glob 匹配 | SHOULD |
| `query` / `custom` | 保守假设：可能重叠 | 默认行为 |
| 跨 kind | 通过 `canonical_uris` 或 resource registry 判定；均不可用时保守假设重叠 | MUST NOT 仅凭 kind 不同就假设不重叠 |

**被引用于**：INTENT_ANNOUNCE / INTENT_UPDATE / INTENT_CLAIM 的 `scope` 字段

---

### 1.9 Basis（冲突检测依据）

描述冲突是如何被检测到的。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `kind` | string | R | 枚举：`rule` / `heuristic` / `model_inference` / `semantic_match` / `human_report` |
| `rule_id` | string | O | kind = `rule` 时的规则标识 |
| `matcher` | string | O | kind = `semantic_match` 时的匹配器标识 |
| `match_type` | string | O | kind = `semantic_match` 时的匹配结果：`contradictory` / `equivalent` / `uncertain` |
| `confidence` | number | O | 0.0–1.0 之间的置信度。低于阈值（默认 0.7）时应视为 `uncertain` |
| `matched_pair` | object | O | `{ left: { source_intent_id, content }, right: { source_intent_id, content } }` |
| `explanation` | string | O | 人类可读的匹配解释 |

**被引用于**：CONFLICT_REPORT 的 `basis` 字段

---

### 1.10 Outcome（解决结果）

描述 RESOLUTION 的具体决策结果。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `accepted` | string[] | O | 被接受的 intent/operation ID 列表 |
| `rejected` | string[] | O | 被拒绝的 intent/operation ID 列表 |
| `merged` | string[] | O | 被合并的 intent/operation ID 列表 |
| `rollback` | string | C | 当 rejected 列表中存在 COMMITTED 状态的 operation 时 **MUST 填写**。值为补偿 OP_COMMIT 的引用或 `"not_required"` |

**被引用于**：RESOLUTION 的 `outcome` 字段

---

## 2. 消息类型清单

MPAC v0.1.14 共 22 种消息类型，分布在 Session / Intent / Operation / Conflict / Governance / Error 六类中。

| 层 | 消息类型 | 方向 | Core Profile | Governance Profile |
|----|---------|------|-------------|-------------------|
| Session | `HELLO` | 参与者 → Coordinator | ✅ | ✅ |
| Session | `SESSION_INFO` | Coordinator → 参与者 | ✅ | ✅ |
| Session | `SESSION_CLOSE` | Coordinator → All | ✅ | ✅ |
| Session | `COORDINATOR_STATUS` | Coordinator → All | ✅ | ✅ |
| Session | `HEARTBEAT` | 参与者 → All | ✅ | ✅ |
| Session | `GOODBYE` | 参与者 → All | ✅ | ✅ |
| Intent | `INTENT_ANNOUNCE` | 参与者 → All | ✅ | ✅ |
| Intent | `INTENT_UPDATE` | 参与者 → All | | ✅ |
| Intent | `INTENT_WITHDRAW` | 参与者 → All | | ✅ |
| Intent | `INTENT_DEFERRED` *(v0.1.14+)* | 参与者 → Coordinator → All | ⚪ | ⚪ |
| Intent | `INTENT_CLAIM` | 参与者 → Coordinator | | ✅ |
| Intent | `INTENT_CLAIM_STATUS` | Coordinator → All | | ✅ |
| Operation | `OP_PROPOSE` | 参与者 → Coordinator | | ✅ |
| Operation | `OP_COMMIT` | 参与者 → All | ✅ | ✅ |
| Operation | `OP_REJECT` | Reviewer/Coordinator → 参与者 | | ✅ |
| Operation | `OP_SUPERSEDE` | 参与者 → All | | ✅ |
| Operation | `OP_BATCH_COMMIT` | 参与者 → Coordinator | ✅ | ✅ |
| Conflict | `CONFLICT_REPORT` | 检测者 → All | ✅ | ✅ |
| Conflict | `CONFLICT_ACK` | 参与者 → All | | ✅ |
| Conflict | `CONFLICT_ESCALATE` | 参与者 → Arbiter | | ✅ |
| Governance | `RESOLUTION` | Arbiter/Owner → All | ✅ | ✅ |
| Error | `PROTOCOL_ERROR` | Any → Any | ✅ | ✅ |

**图例**：✅ = MUST 实现；⚪ = Optional（不属于任一 profile 的强制集，但实现 SHOULD 支持以获得完整 UX）。

**关于 `INTENT_DEFERRED`**：v0.1.14 新增的"非声明性"信号——记录"我看到了某个 active intent 选择避让"，纯 UX 提示。**不是 intent**，不锁 scope，不参与 overlap detection，不阻塞同 principal 后续 `INTENT_ANNOUNCE`。详见 §3.7.1 / §8.15。

---

## 3. 消息 Payload 详细定义

### 3.1 HELLO

加入 session，声明身份和能力。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `display_name` | string | R | 人类可读名称 | |
| `roles` | string[] | R | 请求的角色列表 | → [Roles 枚举](#61-roles) |
| `capabilities` | string[] | R | 支持的能力列表 | → [Capabilities 枚举](#62-capabilities) |
| `implementation` | object | O | `{ name: string, version: string }` | |
| `credential` | object | C | Authenticated/Verified profile 下必填。`{ type: string, value: string, issuer?: string, expires_at?: string }` | → [Security Profile](#63-security-profile) |
| `backend` | object | O | Agent 的 AI 模型后端依赖 | |

**后续**：Coordinator 收到后 MUST 回复 SESSION_INFO。

---

### 3.2 SESSION_INFO

Coordinator 对 HELLO 的响应，携带 session 配置和兼容性检查结果。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `session_id` | string | R | Session ID | → [Session](#13-session) |
| `protocol_version` | string | R | 协议版本 | |
| `security_profile` | string | R | 安全级别 | → [Security Profile 枚举](#63-security-profile) |
| `compliance_profile` | string | R | 合规级别 | → [Compliance Profile 枚举](#64-compliance-profile) |
| `execution_model` | string | R | 枚举：`pre_commit` / `post_commit`。声明 session 的执行模型 | → 执行模型（Section 8.2） |
| `watermark_kind` | string | R | 基线 watermark 类型 | → [Watermark](#14-watermark因果水位) |
| `state_ref_format` | string | R | state_ref 格式 | → OP_COMMIT 的 `state_ref_before/after` |
| `governance_policy` | object | O | 治理配置 | → [Governance Policy](#15-governance-policy治理策略) |
| `liveness_policy` | object | O | 活性配置 | → [Liveness Policy](#16-liveness-policy活性策略) |
| `participant_count` | integer | O | 当前参与者数 | |
| `granted_roles` | string[] | R | 实际授予的角色（可能与 HELLO 请求不同） | → [Roles 枚举](#61-roles) |
| `identity_verified` | boolean | O | 参与者凭证是否已验证。Authenticated/Verified profile 下为必填 | → [Security Profile](#63-security-profile) |
| `identity_method` | string | O | 验证使用的凭证类型，如 `bearer_token` / `mtls_fingerprint` | |
| `identity_issuer` | string | O | 签发凭证的身份提供者或 CA，如 `https://auth.example.com`。Authenticated/Verified profile 相关 | → Spec §23.1.4 |
| `compatibility_errors` | string[] | O | 检测到的不兼容项列表 | |

**信封要求**：作为 coordinator-authored message，`SESSION_INFO` 的 Message Envelope MUST 包含 `coordinator_epoch`。

**兼容性说明**：对早于 v0.1.7 的旧实现，如果收到不含 `execution_model` 的 `SESSION_INFO`，接收方 MUST 按 `post_commit` 处理。

---

### 3.3 HEARTBEAT

维持活性，发布状态摘要。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `status` | string | R | 枚举：`idle` / `working` / `blocked` / `awaiting_review` / `offline` | |
| `active_intent_id` | string | O | 当前活跃的 intent ID | → INTENT_ANNOUNCE 的 `intent_id` |
| `summary` | string | O | 人类可读的活动摘要 | |
| `backend_health` | object | O | 后端提供者健康状态 | |

**频率**：SHOULD 每 30 秒发送一次。连续 90 秒无消息 → 判定不可用。

---

### 3.4 GOODBYE

离开 session。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `reason` | string | R | 枚举：`user_exit` / `session_complete` / `error` / `timeout` | |
| `active_intents` | string[] | O | 离开时仍活跃的 intent ID 列表 | → INTENT_ANNOUNCE 的 `intent_id` |
| `intent_disposition` | string | O | 枚举：`withdraw` / `transfer` / `expire`。默认 `withdraw` | |

**Transfer 机制**：当 `intent_disposition` = `transfer` 时，coordinator SHOULD 将离开参与者的活跃 intent 转为 `SUSPENDED`，使其可被其他参与者通过 `INTENT_CLAIM`（§14.7.4）认领。具体的 claim 征集机制由实现定义。

---

### 3.5 INTENT_ANNOUNCE

声明计划执行的工作。**Governance Profile 下 MUST 在 OP_PROPOSE/OP_COMMIT 之前发送。**

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `intent_id` | string | R | 唯一标识 | 被 OP_PROPOSE/OP_COMMIT/CONFLICT_REPORT 引用 |
| `objective` | string | R | 人类可读的目标描述 | |
| `scope` | Scope | R | 目标资源集合 | → [Scope](#18-scope作用域) |
| `assumptions` | string[] | O | 重要的隐含依赖。默认 `[]` | 被 semantic_match 用于矛盾检测 |
| `priority` | string | O | 枚举：`low` / `normal` / `high` / `critical`。默认 `normal` | |
| `ttl_sec` | integer | O | 墙钟秒数，由 coordinator 基于 received_at 判定过期。默认 `300` | |
| `parent_intent_id` | string | O | 父级 intent ID（层级关系） | → 另一个 intent 的 `intent_id` |
| `supersedes_intent_id` | string | O | 被本 intent 替代的 intent ID | → 另一个 intent 的 `intent_id` |

---

### 3.6 INTENT_UPDATE

修改活跃 intent 的属性。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `intent_id` | string | R | 要更新的 intent ID | → INTENT_ANNOUNCE 的 `intent_id` |
| `objective` | string | O | 新目标 | |
| `scope` | Scope | O | 新作用域 | → [Scope](#18-scope作用域) |
| `assumptions` | string[] | O | 新假设列表 | |
| `ttl_sec` | integer | O | 新 TTL | |

**约束**：除 `intent_id` 外至少填一个字段。

**Scope 扩大重检**：当 `scope` 字段被更新且新 scope **严格大于**原 scope（涵盖了原始 `INTENT_ANNOUNCE` 未声明的资源）时，coordinator SHOULD 对扩大部分重新进行 overlap 检测，如发现新重叠则 SHOULD 生成 `CONFLICT_REPORT`。这防止参与者通过增量 update 绕过冲突检测。

---

### 3.7 INTENT_WITHDRAW

取消活跃 intent。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `intent_id` | string | R | 要取消的 intent ID | → INTENT_ANNOUNCE 的 `intent_id` |
| `reason` | string | O | 取消原因 | |

**副作用**：触发 Intent Expiry Cascade（Section 15.7），关联的 pending proposal 被自动 reject。

---

### 3.7.1 INTENT_DEFERRED *(v0.1.14+)*

记录"参与者**看到**了某个 scope 上的 active intent 并选择**避让**"的一面信号。**不是 intent**，**不参与 overlap detection**，**不阻塞**同一 principal 后续的 `INTENT_ANNOUNCE`。纯 UX 用途——sibling participants 在冲突面板上渲染"yielded"提示。

同一 message_type 有两种 form。

**Active form**（由让让方发送；coordinator 在重广播时填入 `principal_id` 和 `expires_at`）：

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `deferral_id` | string | R | 发送方自选的唯一 ID | 被 resolution form 引用 |
| `principal_id` | string | C | Coordinator 重广播时填入；客户端 SHOULD 省略 | → [Principal](#11-principal参与者身份) |
| `scope` | Scope | R | 准备让出的 scope | → [Scope](#18-scope作用域) |
| `reason` | string | O | 自由文本，如 `"yielded_to_active_editor"` | |
| `observed_intent_ids` | string[] | O | 看到的 intent ID 列表 | → INTENT_ANNOUNCE 的 `intent_id` |
| `observed_principals` | string[] | O | 看到的对方 principal ID 列表 | → [Principal](#11-principal参与者身份) |
| `ttl_sec` | number | O | TTL，默认 60 秒 | |
| `expires_at` | string | C | ISO 时间戳；coordinator MUST 在重广播时基于 `received_at + ttl_sec` 填入 | |

**Resolution form**（仅由 coordinator 发送，标记 deferral 已被清理）：

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `deferral_id` | string | R | 被清理的 deferral ID | → active form 的 `deferral_id` |
| `principal_id` | string | R | 原让让方的 principal ID | → [Principal](#11-principal参与者身份) |
| `status` | string | R | 枚举：`resolved` / `expired` | → [§6.9 Deferral Status 枚举](#69-deferral-status) |
| `reason` | string | O | 自由文本，常见 `"observed_intents_terminated"` / `"principal_announced"` / `"ttl"` | |

**Coordinator 三轴清理规则**（任一满足即 emit `status=resolved` follow-up）：

1. `observed_intent_ids` 中所有 intent 都进入终态
2. 同一 `principal_id` 后续发送了 `INTENT_ANNOUNCE`（不再让让）
3. 终结的 intent 的 owner principal 命中 `observed_principals`，**或** 命中 `observed_intent_ids`（防御性匹配——兼容把两个字段混用的旧客户端）

**TTL 过期**：墙钟超过 `expires_at` 时，coordinator MUST emit `status=expired` follow-up。客户端 SHOULD 自行做 local TTL sweep 防止丢失广播导致 UI 滞留。

**约束**：deferral 不进入 intent 状态机，是 ephemeral 记录。SPEC §15.5.1 是权威定义。

---

### 3.8 INTENT_CLAIM

认领不可用参与者的 suspended intent。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `claim_id` | string | R | Claim 的唯一标识 | |
| `original_intent_id` | string | R | 被认领的 suspended intent | → 必须是 SUSPENDED 状态的 intent |
| `original_principal_id` | string | R | 原 intent 所有者的 principal ID | → [Principal](#11-principal参与者身份) |
| `new_intent_id` | string | R | 新创建的 intent ID | |
| `objective` | string | R | 新 intent 的目标 | |
| `scope` | Scope | R | 新 scope（必须等于或窄于原 scope） | → [Scope](#18-scope作用域) |
| `justification` | string | O | 认领理由 | |

**竞态规则**：
- first-claim-wins，后续 claim 收到 `CLAIM_CONFLICT` 错误
- claim 在 coordinator 发出 `INTENT_CLAIM_STATUS(decision=approved)` 之前都不生效
- 原参与者在审批前重连 → coordinator MUST 发出 `INTENT_CLAIM_STATUS(decision=withdrawn)`，原 intent 恢复为 `ACTIVE`

---

### 3.8.1 INTENT_CLAIM_STATUS

Coordinator 对 `INTENT_CLAIM` 的权威处置结果。用于明确 claim 是已批准、被拒绝，还是因原所有者恢复而被撤回。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `claim_id` | string | R | 被处置的 claim ID | → INTENT_CLAIM 的 `claim_id` |
| `original_intent_id` | string | R | 被认领的 suspended intent | → INTENT_ANNOUNCE 的 `intent_id` |
| `new_intent_id` | string | C | 当 `decision=approved` 时必填：替代 intent 的 ID | → INTENT_ANNOUNCE 的 `intent_id` |
| `decision` | string | R | 枚举：`approved` / `rejected` / `withdrawn` | |
| `reason` | string | C | 当 `decision=rejected` 或 `withdrawn` 时必填 | |
| `approved_by` | string | C | Governance Profile 下当 `decision=approved` 时必填：批准该 claim 的 principal ID | → [Principal](#11-principal参与者身份) |

**语义**：
- 仅 session coordinator 可以发送 `INTENT_CLAIM_STATUS`
- `approved`：原 intent 进入 `TRANSFERRED`，新 intent 进入 `ACTIVE`
- Governance Profile 下 `approved` 必须附带 `approved_by`；Core Profile 下若是 coordinator 按 no-objection 策略自动批准，可省略
- `rejected`：原 intent 保持 `SUSPENDED`，除非其他规则另有改变
- `withdrawn`：表示原所有者在审批完成前恢复，原 intent 回到 `ACTIVE`，新 intent 不得激活

---

### 3.9 OP_PROPOSE

提议一个待审批的变更（Governance Profile 下使用）。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `op_id` | string | R | 操作唯一标识 | 被 OP_COMMIT/OP_REJECT/CONFLICT_REPORT 引用 |
| `intent_id` | string | O | 关联的 intent ID | → INTENT_ANNOUNCE 的 `intent_id` |
| `target` | string | R | 被修改的资源 | |
| `op_kind` | string | R | 变更类型，如 `replace` / `insert` / `delete` / `patch` | |
| `change_ref` | string | O | 变更内容的引用（如 diff blob 的 hash） | |
| `summary` | string | O | 人类可读摘要 | |

---

### 3.10 OP_COMMIT

声明变更已提交到 shared state。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `op_id` | string | R | 操作唯一标识 | |
| `intent_id` | string | O (Governance: R) | 关联的 intent ID | → INTENT_ANNOUNCE 的 `intent_id` |
| `target` | string | R | 被修改的资源 | |
| `op_kind` | string | R | 变更类型 | |
| `state_ref_before` | string | R | 变更前的状态引用（格式由 session 的 `state_ref_format` 决定） | |
| `state_ref_after` | string | R | 变更后的状态引用 | |
| `change_ref` | string | O | 变更内容的引用 | |
| `summary` | string | O | 人类可读摘要 | |

**关键逻辑**：接收方如果本地状态与 `state_ref_before` 不匹配，SHOULD 标记为 `causally_unverifiable`，不基于此操作做冲突判断。

---

### 3.11 OP_REJECT

拒绝一个 proposed 操作。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `op_id` | string | R | 被拒绝的操作 ID | → OP_PROPOSE 的 `op_id` |
| `reason` | string | R | 拒绝原因（如 `policy_violation` / `intent_terminated` / `participant_unavailable` / `frozen_scope_fallback`） | |

---

### 3.12 OP_SUPERSEDE

用新操作替代已提交的旧操作。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `op_id` | string | R | 新操作 ID | |
| `supersedes_op_id` | string | R | 被替代的操作 ID | → 必须是 COMMITTED 状态的操作 |
| `intent_id` | string | O | 关联的 intent ID | → INTENT_ANNOUNCE 的 `intent_id` |
| `target` | string | R | 目标资源 | |
| `reason` | string | O | 替代原因 | |

---

### 3.13 CONFLICT_REPORT

发布一个结构化的冲突判定。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `conflict_id` | string | R | 冲突唯一标识 | 被 CONFLICT_ACK/ESCALATE/RESOLUTION 引用 |
| `related_intents` | string[] | O | 相关 intent ID 列表。默认 `[]` | → INTENT_ANNOUNCE 的 `intent_id` |
| `related_ops` | string[] | O | 相关 operation ID 列表。默认 `[]` | → OP_PROPOSE/OP_COMMIT 的 `op_id` |
| `category` | string | R | 冲突类别 | → [Conflict Category 枚举](#65-conflict-category) |
| `severity` | string | R | 严重程度 | → [Severity 枚举](#66-severity) |
| `basis` | Basis | R | 检测依据 | → [Basis](#19-basis冲突检测依据) |
| `based_on_watermark` | Watermark | R | 判定时的因果状态 | → [Watermark](#14-watermark因果水位) |
| `description` | string | R | 人类可读描述 | |
| `suggested_action` | string | O | 建议的下一步 | |

**约束**：`related_intents` 和 `related_ops` 至少有一个非空。

---

### 3.14 CONFLICT_ACK

确认收到冲突报告。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `conflict_id` | string | R | 被确认的冲突 ID | → CONFLICT_REPORT 的 `conflict_id` |
| `ack_type` | string | R | 枚举：`seen` / `accepted` / `disputed` | |

---

### 3.15 CONFLICT_ESCALATE

将冲突升级给更高权限的裁决者。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `conflict_id` | string | R | 被升级的冲突 ID | → CONFLICT_REPORT 的 `conflict_id` |
| `escalate_to` | string | R | 升级目标的 principal ID | → [Principal](#11-principal参与者身份)，通常是 owner/arbiter |
| `reason` | string | R | 升级原因 | |
| `context` | string | O | 给裁决者的附加上下文 | |

---

### 3.16 RESOLUTION

对冲突做出裁决。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `resolution_id` | string | R | 裁决唯一标识 | |
| `conflict_id` | string | R | 被裁决的冲突 ID | → CONFLICT_REPORT 的 `conflict_id` |
| `decision` | string | R | 裁决类型 | → [Decision 枚举](#67-decision) |
| `outcome` | Outcome | O | 结构化结果 | → [Outcome](#110-outcome解决结果) |
| `rationale` | string | R | 人类可读的裁决理由 | |

**信封要求**：MUST 包含 `watermark`。Authenticated/Verified profile 下缺失 watermark 的 RESOLUTION 会被拒绝。

**并发裁决规则**（Section 18.4）：同一 `conflict_id` 的多条 RESOLUTION，coordinator MUST 先筛出“当前 authority phase 的合法 resolver”，再只接受其中第一条有效裁决（按 coordinator 接收顺序）。升级到 `ESCALATED` 后，owner 不再天然保留裁决权，优先尊重 `escalate_to` / session policy 明确授权的 arbiter / coordinator 系统裁决。

---

### 3.17 PROTOCOL_ERROR

信令协议级别错误。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `error_code` | string | R | 错误码 | → [Error Code 枚举](#68-error-code) |
| `refers_to` | string | O | 触发错误的消息的 `message_id` | → Message Envelope 的 `message_id` |
| `description` | string | R | 人类可读的错误描述 | |

---

### 3.18 SESSION_CLOSE

关闭 session。仅 coordinator 可发送。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `reason` | string | R | 枚举：`completed` / `timeout` / `policy` / `coordinator_shutdown` / `manual` | |
| `final_lamport_clock` | integer | R | Session 的最终 Lamport 时钟值 | → [Watermark](#14-watermark因果水位) |
| `summary` | object | O | Session 完成摘要（Section 9.6.2） | |
| `active_intents_disposition` | string | O | 处理剩余活跃 intent 的方式。枚举：`withdraw_all` / `expire_all`。默认 `withdraw_all` | |
| `transcript_ref` | string | O | 导出的会话记录 URI 或引用（Section 9.6.3） | |

**副作用**：收到后参与者 MUST 停止发送业务消息（`GOODBYE` 除外）。后续消息收到 `SESSION_CLOSED` 错误。关闭前 coordinator SHOULD 持久化最终状态快照。

---

### 3.19 COORDINATOR_STATUS

Coordinator 心跳及状态广播，兼作 coordinator 活性信号和故障恢复基础。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `event` | string | R | 枚举：`heartbeat` / `recovered` / `handover` / `assumed` / `authorization` / `backend_alert` | |
| `coordinator_id` | string | R | 发送此消息的 coordinator 的 principal ID | → [Principal](#11-principal参与者身份) |
| `session_health` | string | R | 枚举：`healthy` / `degraded` / `recovering` | |
| `active_participants` | integer | O | 当前可用参与者数 | |
| `open_conflicts` | integer | O | 未解决 conflict 数 | |
| `snapshot_lamport_clock` | integer | O | 最新持久化快照的 Lamport 时钟值 | → [Watermark](#14-watermark因果水位) |
| `successor_coordinator_id` | string | C | `event` = `handover` 时必填：继任者 principal ID | → [Principal](#11-principal参与者身份) |
| `next_coordinator_epoch` | integer | C | `event` = `handover` 时必填：继任者将使用的 epoch | |
| `authorized_op_id` | string | C | `event` = `authorization` 时必填：被授权的 operation ID | |
| `authorized_batch_id` | string | O | `event` = `authorization` 时可选：operation 所属 batch ID | |
| `authorized_by` | string | C | `event` = `authorization` 时必填：授权者的 principal ID | → [Principal](#11-principal参与者身份) |
| `affected_principal` | string | O | `event` = `backend_alert` 时：受影响的 principal ID | → [Principal](#11-principal参与者身份) |
| `backend_detail` | object | O | `event` = `backend_alert` 时：后端详细状态信息 | |

**频率**：MUST 至少每 `heartbeat_interval_sec` 发送一次。参与者连续 `2 × heartbeat_interval_sec` 未收到 → 判定 coordinator 不可用（Section 8.1.1.1）。

**信封要求**：
- 所有 `COORDINATOR_STATUS` 的 Message Envelope MUST 包含 `coordinator_epoch`
- `COORDINATOR_STATUS` SHOULD 携带 Lamport watermark；当两个 coordinator 宣称相同 epoch 时，用 watermark 作为 tie-breaker

**事件补充**：
- `recovered`：参与者 SHOULD 重新发送 `HELLO`；如果本地进程未重启，SHOULD 保留原 `sender_instance_id` 和本地 Lamport counter
- `handover`：必须同时给出 `successor_coordinator_id` 和 `next_coordinator_epoch`
- `assumed`：表示新的 coordinator 已按声明的 epoch 接管，可以接受新的 `HELLO`
- `authorization`：`pre_commit` 模式下 coordinator 授权某个 proposed operation 可以执行。proposer 收到后 MAY 执行 mutation 并发出完成声明。必须给出 `authorized_op_id` 和 `authorized_by`；如果 operation 属于 batch，还带 `authorized_batch_id`
- `backend_alert`：AI 模型后端发生故障或切换。必须给出 `affected_principal` 和 `backend_detail`

**Split-brain 防护**：参与者如果在同一 session 内收到来自两个不同 coordinator 的 coordinator-authored message，MUST 先比较 `coordinator_epoch`，拒绝较低 epoch 的消息；如果两者 epoch 相同，则比较 Lamport watermark，拒绝 Lamport 更低的 coordinator 的消息，并 SHOULD 向双方发送 `PROTOCOL_ERROR`（`error_code`: `COORDINATOR_CONFLICT`）。

---

### 3.20 OP_BATCH_COMMIT

多目标批次操作。将多个 OP_COMMIT 风格的变更打包为一个逻辑批次。

| 字段 | 类型 | 必填 | 说明 | 关联 |
|------|------|------|------|------|
| `batch_id` | string | R | 批次唯一标识 | |
| `intent_id` | string | O (Governance: R) | 关联的 intent ID | → INTENT_ANNOUNCE 的 `intent_id` |
| `atomicity` | string | R | 枚举：`all_or_nothing` / `best_effort` | |
| `operations` | object[] | R | 操作列表，每项结构见下 | |
| `summary` | string | O | 人类可读的批次摘要 | |

**operations[] 每项结构**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `op_id` | string | R | 操作唯一标识 |
| `target` | string | R | 目标资源 |
| `op_kind` | string | R | 变更类型 |
| `state_ref_before` | string | R | 变更前状态引用 |
| `state_ref_after` | string | R | 变更后状态引用 |
| `change_ref` | string | O | 变更内容引用 |

**批次语义**：`OP_BATCH_COMMIT` 在 conflict detection / governance 上按单一逻辑单元处理；Scope = 所有 target 的并集。`all_or_nothing` 模式下任一操作失败则整批失败；`best_effort` 模式下各 entry 独立跟踪生命周期，可部分成功。

**Pre-commit 模型**：coordinator 收到后先做 scope 检查、冲突检测和治理校验，显式授权后参与者才能执行；授权本身不等于 batch 已 `COMMITTED`，执行完成后还需要再发一次对应 `batch_id` 的 `OP_BATCH_COMMIT` 作为完成声明。
**Pre-commit 消歧义**：coordinator 通过检查同一 `batch_id` 是否已存在来区分首次提交（initial request）和执行完成声明（completion）。若 `batch_id` 不存在 → 首次提交，各 entry 进入 `PROPOSED`。若 `batch_id` 已注册且已授权 → 完成声明，各已授权 entry 转为 `COMMITTED`。此逻辑与 `OP_COMMIT` 的 pre-commit 消歧义规则一致。
**Post-commit 模型**：参与者已执行所有变更，OP_BATCH_COMMIT 为事后声明。

---

## 4. 实体关系图

下图展示所有核心实体之间的引用关系。箭头表示"引用/关联"。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              SESSION                                     │
│  session_id, security_profile, governance_policy, liveness_policy        │
│                                                                          │
│  ┌──────────┐   SESSION_INFO    ┌─────────────┐                        │
│  │Coordinator│ ────────────────→ │ Participant  │                        │
│  │ (service) │ ←──── HELLO ──── │ (Principal)  │                        │
│  └─────┬─────┘                  └──────┬───────┘                        │
│        │                               │                                 │
└────────┼───────────────────────────────┼─────────────────────────────────┘
         │ 管理/执行                     │ 发送
         ▼                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           INTENT LAYER                                   │
│                                                                          │
│  INTENT_ANNOUNCE ──┐                                                    │
│    intent_id ◄─────┼──── 被以下实体引用:                                │
│    scope ───────────┼──→ Scope 对象                                     │
│    ttl_sec          │    (冲突检测的输入)                                │
│                     │                                                    │
│  INTENT_UPDATE ─────┤ intent_id → 引用 INTENT_ANNOUNCE                  │
│  INTENT_WITHDRAW ───┤ intent_id → 引用 INTENT_ANNOUNCE                  │
│  INTENT_DEFERRED ───┤ (v0.1.14+) 非声明信号，不参与 overlap detection    │
│    (active form)    │ observed_intent_ids → 引用 INTENT_ANNOUNCE        │
│    (resolution)     │ deferral_id → 引用 active form 的 deferral_id     │
│  INTENT_CLAIM ──────┘ original_intent_id → 引用 SUSPENDED 的 intent     │
│                       new_intent_id → 创建新 intent                     │
│                       original_principal_id → 引用 Principal            │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ intent_id
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         OPERATION LAYER                                  │
│                                                                          │
│  OP_PROPOSE ────┐                                                       │
│    op_id ◄──────┼──── 被以下实体引用:                                   │
│    intent_id ───┼──→ INTENT_ANNOUNCE (可选, Governance 下必填)          │
│    target       │                                                        │
│                 │                                                        │
│  OP_COMMIT ─────┤ op_id, intent_id → 同上                              │
│    state_ref_before ──→ 变更前状态 (格式由 session.state_ref_format)    │
│    state_ref_after ───→ 变更后状态                                      │
│                 │                                                        │
│  OP_REJECT ─────┤ op_id → 引用 OP_PROPOSE                              │
│  OP_SUPERSEDE ──┘ supersedes_op_id → 引用 COMMITTED 的操作              │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ op_id, intent_id
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         CONFLICT LAYER                                   │
│                                                                          │
│  CONFLICT_REPORT ──┐                                                    │
│    conflict_id ◄───┼──── 被以下实体引用:                                │
│    related_intents ┼──→ INTENT_ANNOUNCE 的 intent_id (数组)             │
│    related_ops ────┼──→ OP_PROPOSE/OP_COMMIT 的 op_id (数组)            │
│    basis ──────────┼──→ Basis 对象                                      │
│    based_on_watermark → Watermark 对象                                  │
│                    │                                                     │
│  CONFLICT_ACK ─────┤ conflict_id → 引用 CONFLICT_REPORT                │
│  CONFLICT_ESCALATE ┤ conflict_id → 引用 CONFLICT_REPORT                │
│                    │ escalate_to → 引用 Principal                       │
└────────────────────┼─────────────────────────────────────────────────────┘
                     │ conflict_id
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        GOVERNANCE LAYER                                  │
│                                                                          │
│  RESOLUTION                                                              │
│    resolution_id                                                         │
│    conflict_id ────→ CONFLICT_REPORT 的 conflict_id                     │
│    outcome ────────→ Outcome 对象                                       │
│      accepted[] ──→ intent_id / op_id                                   │
│      rejected[] ──→ intent_id / op_id                                   │
│      merged[] ────→ intent_id / op_id                                   │
│      rollback ────→ 补偿 OP_COMMIT 引用 或 "not_required"              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.1 关键引用链总结

| 源字段 | → 目标字段 | 关系说明 |
|--------|-----------|---------|
| OP_PROPOSE.`intent_id` | → INTENT_ANNOUNCE.`intent_id` | 操作属于哪个 intent |
| OP_COMMIT.`intent_id` | → INTENT_ANNOUNCE.`intent_id` | 同上 |
| OP_REJECT.`op_id` | → OP_PROPOSE.`op_id` | 拒绝哪个提案 |
| OP_SUPERSEDE.`supersedes_op_id` | → OP_COMMIT.`op_id` | 替代哪个已提交操作 |
| CONFLICT_REPORT.`related_intents[]` | → INTENT_ANNOUNCE.`intent_id` | 冲突涉及哪些 intent |
| CONFLICT_REPORT.`related_ops[]` | → OP_PROPOSE/OP_COMMIT.`op_id` | 冲突涉及哪些操作 |
| CONFLICT_ACK.`conflict_id` | → CONFLICT_REPORT.`conflict_id` | 确认哪个冲突 |
| CONFLICT_ESCALATE.`conflict_id` | → CONFLICT_REPORT.`conflict_id` | 升级哪个冲突 |
| CONFLICT_ESCALATE.`escalate_to` | → Principal.`principal_id` | 升级给谁 |
| RESOLUTION.`conflict_id` | → CONFLICT_REPORT.`conflict_id` | 裁决哪个冲突 |
| RESOLUTION.`outcome.accepted/rejected[]` | → `intent_id` 或 `op_id` | 裁决结果涉及的实体 |
| INTENT_DEFERRED.`observed_intent_ids[]` | → INTENT_ANNOUNCE.`intent_id` | 让让方观察到的 active intent |
| INTENT_DEFERRED.`observed_principals[]` | → Principal.`principal_id` | 让让方观察到的工作中 principal |
| INTENT_DEFERRED (resolution).`deferral_id` | → INTENT_DEFERRED (active).`deferral_id` | resolution form 引用 active form |
| INTENT_CLAIM.`original_intent_id` | → INTENT_ANNOUNCE.`intent_id` | 认领哪个 suspended intent |
| INTENT_CLAIM.`original_principal_id` | → Principal.`principal_id` | 原 intent 所有者 |
| INTENT_CLAIM_STATUS.`claim_id` | → INTENT_CLAIM.`claim_id` | 对哪个 claim 做出处置 |
| INTENT_CLAIM_STATUS.`original_intent_id` | → INTENT_ANNOUNCE.`intent_id` | 被认领的 suspended intent |
| INTENT_CLAIM_STATUS.`new_intent_id` | → INTENT_ANNOUNCE.`intent_id` | claim 批准后激活的新 intent |
| INTENT_ANNOUNCE.`parent_intent_id` | → INTENT_ANNOUNCE.`intent_id` | Intent 层级关系 |
| INTENT_ANNOUNCE.`supersedes_intent_id` | → INTENT_ANNOUNCE.`intent_id` | Intent 替代关系 |
| OP_BATCH_COMMIT.`intent_id` | → INTENT_ANNOUNCE.`intent_id` | 批次操作属于哪个 intent |
| OP_BATCH_COMMIT.`operations[].op_id` | → 各操作的唯一标识 | 批次内各操作 |
| SESSION_CLOSE.`final_lamport_clock` | → Watermark (lamport) | Session 最终 Lamport 时钟值 |
| COORDINATOR_STATUS.`coordinator_id` | → Principal.`principal_id` | 发送 coordinator 的身份 |
| COORDINATOR_STATUS.`successor_coordinator_id` | → Principal.`principal_id` | handover 时的继任者 |
| COORDINATOR_STATUS.`authorized_op_id` | → OP_PROPOSE.`op_id` | authorization 事件授权的 operation |
| COORDINATOR_STATUS.`authorized_by` | → Principal.`principal_id` | authorization 事件的授权者 |
| COORDINATOR_STATUS.`snapshot_lamport_clock` | → Watermark (lamport) | 快照时因果水位 |
| HEARTBEAT.`active_intent_id` | → INTENT_ANNOUNCE.`intent_id` | 当前工作的 intent |
| GOODBYE.`active_intents[]` | → INTENT_ANNOUNCE.`intent_id` | 离开时的活跃 intent |
| Message Envelope.`in_reply_to` | → Message Envelope.`message_id` | 消息回复链 |

---

## 5. 状态机

### 5.1 Intent 状态机

```text
DRAFT -> ANNOUNCED -> ACTIVE -> SUPERSEDED
DRAFT -> ANNOUNCED -> ACTIVE -> EXPIRED
DRAFT -> ANNOUNCED -> WITHDRAWN
ACTIVE -> SUSPENDED -> ACTIVE           (participant reconnects)
ACTIVE -> SUSPENDED -> TRANSFERRED      (intent claimed by another participant)
ACTIVE -> SUSPENDED                     (owner departs with intent_disposition: transfer)
```

| 路径 | 说明 |
|------|------|
| DRAFT → ANNOUNCED → ACTIVE | `DRAFT` / `ANNOUNCED` 是帮助理解的概念阶段；规范状态机从参与者成功发出 `INTENT_ANNOUNCE` 后进入 `ACTIVE` |
| ACTIVE → EXPIRED / WITHDRAWN / SUPERSEDED | intent 进入终态时触发 Intent Expiry Cascade |
| ACTIVE → SUSPENDED → ACTIVE | 所有者恢复后，引用它的 FROZEN 操作恢复为 PROPOSED |
| ACTIVE → SUSPENDED → TRANSFERRED | claim 被批准后，原 intent 关闭，新 intent 激活 |

**规范状态转换表**（Section 15.6.1，权威参考）：

| # | 起始状态 | 目标状态 | 触发消息/事件 | 守卫条件 | 动作 |
|---|---------|---------|-------------|---------|------|
| 1 | (none) | ACTIVE | `INTENT_ANNOUNCE` received | sender 是已注册参与者 | 注册 intent，启动 TTL 计时器 |
| 2 | ACTIVE | ACTIVE | `INTENT_UPDATE` received | sender = intent owner | 更新字段，可选择重置 TTL |
| 3 | ACTIVE | WITHDRAWN | `INTENT_WITHDRAW` received | sender = intent owner | 触发 Expiry Cascade |
| 4 | ACTIVE | EXPIRED | TTL expired | coordinator 墙钟检查 | 触发 Expiry Cascade |
| 5 | ACTIVE | SUPERSEDED | `INTENT_ANNOUNCE` with `supersedes_intent_id` | 新 intent 来自同一 owner | 触发 Expiry Cascade |
| 6 | ACTIVE | SUSPENDED | owner unavailability detected | Section 14.7.1 | 冻结引用它的 PROPOSED 操作，保留 scope 参与冲突检测 |
| 6b | ACTIVE | SUSPENDED | owner departs with `intent_disposition`: `transfer` | GOODBYE from owner (§14.4) | 冻结引用操作，intent 可被 INTENT_CLAIM 认领 |
| 7 | SUSPENDED | ACTIVE | owner reconnects (`HELLO` or `HEARTBEAT` resumes) | 原所有者重新认证 | 解冻引用操作，并通知离线期间的变化 |
| 8 | SUSPENDED | TRANSFERRED | `INTENT_CLAIM_STATUS` received (`decision = approved`) | claim 已按治理规则获批 | 原 intent 关闭，新 intent 作为 ACTIVE 创建 |
| 9 | SUSPENDED | EXPIRED | TTL expired while suspended | coordinator 墙钟检查 | 触发 Expiry Cascade |

**补充**：`INTENT_CLAIM_STATUS(rejected)` 不改变原 intent 的 `SUSPENDED` 状态；`INTENT_CLAIM_STATUS(withdrawn)` 则使原 intent 返回 `ACTIVE`。

**关于 `INTENT_DEFERRED` (v0.1.14+)**：deferral **不是 intent**，没有正式状态机，不出现在上表。但 intent 状态机的**终态转换**会触发匹配 deferral 的清理（→ coordinator emit `INTENT_DEFERRED(status=resolved, reason=observed_intents_terminated)`）。详见 §5.4 跨状态机联动。

---

### 5.2 Operation 状态机

```
                INTENT 活跃时
   ┌────────────────────────────────────────┐
   │                                        │
   │  ┌──────────────┐    OP_COMMIT    ┌──────────────┐    OP_SUPERSEDE   ┌──────────────┐
   │  │   PROPOSED   │ ─────────────→ │  COMMITTED   │ ────────────────→│  SUPERSEDED  │
   │  └──┬──┬──┬─────┘                └──────────────┘                   └──────────────┘
   │     │  │  │
   │     │  │  │  OP_REJECT / intent_terminated / frozen_scope_fallback
   │     │  │  └──────────────────────────────────────────→ ┌──────────────┐
   │     │  │                                                │   REJECTED   │
   │     │  │                                                └──────────────┘
   │     │  │  发送者不可用
   │     │  └─────────────────────────────────────────────→ ┌──────────────┐
   │     │                                                   │  ABANDONED   │
   │     │  引用的 intent 进入 SUSPENDED                      └──────────────┘
   │     └────────────────────────────────────────────────→ ┌──────────────┐
   │                                                        │   FROZEN     │──→ PROPOSED (intent 恢复)
   │                                                        └──────┬───────┘
   │                                                               │ intent 终态
   │                                                               ▼
   │                                                        ┌──────────────┐
   │                                                        │   REJECTED   │
   └────────────────────────────────────────────────────────└──────────────┘
```

| 转换 | 触发条件 |
|------|---------|
| PROPOSED → COMMITTED | 变更已应用到 shared state |
| PROPOSED → REJECTED | Reviewer 拒绝 / 引用 intent 进入 `EXPIRED` / `WITHDRAWN` / `SUPERSEDED` / `TRANSFERRED` / frozen scope Phase 3 fallback |
| PROPOSED → ABANDONED | 发送者被判定不可用 |
| PROPOSED → FROZEN | 引用的 intent 进入 SUSPENDED |
| FROZEN → PROPOSED | 引用的 intent 恢复 ACTIVE |
| FROZEN → REJECTED | 引用的 intent 从 SUSPENDED 进入 `EXPIRED` / `WITHDRAWN` / `SUPERSEDED` / `TRANSFERRED` |
| COMMITTED → SUPERSEDED | 被 OP_SUPERSEDE 替代 |

**规范状态转换表**（Section 16.6.1，权威参考）：

| # | 起始状态 | 目标状态 | 触发消息/事件 | 守卫条件 | 动作 |
|---|---------|---------|-------------|---------|------|
| 1 | (none) | PROPOSED | OP_PROPOSE | sender 已注册，引用的 intent（若有）有效 | 注册操作 |
| 2 | (none) | COMMITTED | OP_COMMIT（post_commit） | sender 已注册，state_refs 有效 | 记录状态变更 |
| 3 | (none) | PROPOSED | OP_COMMIT（pre_commit，兼容旧路径） | 新 `op_id`，且只作为待授权请求处理 | 注册待授权操作 |
| 4 | PROPOSED | PROPOSED | Coordinator 授权（pre_commit） | scope 检查通过，无阻塞冲突 | 记录授权并通知参与者执行 |
| 5 | PROPOSED | COMMITTED | OP_COMMIT（pre_commit，完成声明） | 该 proposal 已获授权且变更已应用 | 记录 state_ref_after |
| 6 | PROPOSED | REJECTED | OP_REJECT / 引用 intent 进入 `EXPIRED` / `WITHDRAWN` / `SUPERSEDED` / `TRANSFERRED` / frozen scope Phase 3 fallback | | 通知发送者 |
| 7 | PROPOSED | ABANDONED | 发送者不可用 | 心跳超时 | |
| 8 | PROPOSED | FROZEN | 引用 intent 进入 SUSPENDED | | |
| 9 | FROZEN | PROPOSED | 引用 intent 恢复 ACTIVE | | |
| 10 | FROZEN | REJECTED | 引用 intent 从 SUSPENDED 进入 `EXPIRED` / `WITHDRAWN` / `SUPERSEDED` / `TRANSFERRED` | | |
| 11 | COMMITTED → SUPERSEDED | OP_SUPERSEDE | 被替代 op 必须为 COMMITTED | 记录 supersession chain |
| 12 | (none) | per-entry | OP_BATCH_COMMIT | post_commit: 按 `atomicity` 直接处理；pre_commit: 首次提交进入 PROPOSED，授权后再次发送同 `batch_id` 完成声明 | scope = union of targets，批次作为单一逻辑单元参与冲突检测 / 治理 |

**术语对齐**：`REJECTED` / `ABANDONED` / `SUPERSEDED` 是 operation 的终态；`COMMITTED` 是 stable state，不算终态。对 session 生命周期判断，`COMMITTED` / `REJECTED` / `ABANDONED` / `SUPERSEDED` 统称 **settled**。

---

### 5.3 Conflict 状态机

```text
OPEN -> ACKED -> RESOLVED -> CLOSED
OPEN -> RESOLVED -> CLOSED
OPEN -> ESCALATED -> RESOLVED -> CLOSED
ACKED -> ESCALATED -> RESOLVED -> CLOSED
OPEN / ACKED / ESCALATED -> DISMISSED    (all related entities terminated)
OPEN -> CLOSED                           (Phase 3 policy_override fallback)
```

| 转换 | 触发条件 |
|------|---------|
| OPEN → ACKED | 收到 `CONFLICT_ACK` |
| OPEN → RESOLVED | 当前 authority phase 的合法 resolver 直接发送 `RESOLUTION` |
| OPEN → ESCALATED | 收到 `CONFLICT_ESCALATE` |
| ACKED → ESCALATED | 收到 `CONFLICT_ESCALATE` |
| OPEN / ACKED / ESCALATED → DISMISSED | 所有关联实体终结（auto-dismiss） |
| ACKED / ESCALATED → RESOLVED | 收到 `RESOLUTION` |
| OPEN → CLOSED | frozen scope Phase 3 fallback 触发，coordinator 生成 `policy_override` |
| RESOLVED → CLOSED | 裁决执行完毕 |

**Auto-Dismiss 触发条件**：`related_intents` 全部在终态（EXPIRED/WITHDRAWN/SUPERSEDED/TRANSFERRED）且 `related_ops` 全部在终态（REJECTED/ABANDONED/SUPERSEDED）。

**规范状态转换表**（Section 17.8.1，权威参考）：

| # | 起始状态 | 目标状态 | 触发消息/事件 | 守卫条件 | 动作 |
|---|---------|---------|-------------|---------|------|
| 1 | (none) | OPEN | CONFLICT_REPORT | basis 有效，related_intents/ops 至少一个非空 | 通知所有参与者 |
| 2 | OPEN | ACKED | `CONFLICT_ACK` received (`ack_type: seen` 或 `accepted`) | acknowledger 是相关参与者 | 记录确认 |
| 3 | OPEN | ESCALATED | `CONFLICT_ESCALATE` received | escalation target 有 authority | 通知升级目标 |
| 4 | OPEN | RESOLVED | `RESOLUTION` received | resolver 对当前 authority phase 有 authority（owner / arbiter / coordinator） | 执行 outcome，释放 frozen scope |
| 5 | OPEN | DISMISSED | 所有关联实体终结 | auto-dismiss 条件满足 | coordinator 生成 `decision: dismissed` 的系统 RESOLUTION，并释放 frozen scope |
| 6 | OPEN | CLOSED | frozen scope Phase 3 fallback | 超过 Phase 2 超时 | coordinator 生成 `policy_override`；按 coordinator 接收顺序执行 first-committer-wins |
| 7 | ACKED | ESCALATED | `CONFLICT_ESCALATE` received | escalation target 有 authority | 通知升级目标 |
| 8 | ACKED | RESOLVED | `RESOLUTION` received | resolver 对当前 authority phase 有 authority | 执行 outcome，释放 frozen scope |
| 9 | ACKED | DISMISSED | 所有关联实体终结 | auto-dismiss 条件满足 | coordinator 生成系统 RESOLUTION，并释放 frozen scope |
| 10 | ESCALATED | RESOLVED | `RESOLUTION` received | resolver = `escalate_to`，或为 session policy 明确授权的 arbiter，或 coordinator 的系统裁决 | 执行 outcome，释放 frozen scope |
| 11 | ESCALATED | DISMISSED | 所有关联实体终结 | auto-dismiss 条件满足 | coordinator 生成系统 RESOLUTION，并释放 frozen scope |
| 12 | RESOLVED | CLOSED | 裁决执行完毕 | outcome 中动作已执行 | 归档 / 审计 |

---

### 5.4 跨状态机联动规则

定义状态机之间的因果传播（v0.1.4 引入，v0.1.7 新增规范状态转换表）。

```
Intent 终态 ─────────┬──→ 关联 PROPOSED 操作 auto-reject (或 grace period 后 reject)
(EXPIRED/WITHDRAWN/  │
 SUPERSEDED /
 TRANSFERRED)        └──→ 如果是冲突的最后一个活跃关联实体 → Conflict auto-dismiss
                                  └──→ 释放 frozen scope

Intent SUSPENDED ────────→ 关联 PROPOSED 操作 → FROZEN

Intent 恢复 ACTIVE ──────→ 关联 FROZEN 操作 → PROPOSED

参与者不可用 ─────────────→ Intent → SUSPENDED
                          → 本人的 PROPOSED 操作 → ABANDONED

Intent 终态 ─────────────→ 任一匹配 deferral 清理:
                            (匹配条件: 命中 observed_intent_ids
                             或终态 intent 的 owner ∈ observed_principals)
                          → coordinator emit
                            INTENT_DEFERRED(status=resolved,
                                           reason=observed_intents_terminated)

INTENT_ANNOUNCE 由 P 发出 ─→ P 的所有 active deferral 清理:
                          → coordinator emit
                            INTENT_DEFERRED(status=resolved,
                                           reason=principal_announced)

Deferral TTL 超时 ────────→ coordinator emit
                            INTENT_DEFERRED(status=expired, reason=ttl)
```

---

## 6. 枚举值注册表

### 6.1 Roles

| 值 | 权限 |
|----|------|
| `observer` | 只读，无决策权 |
| `contributor` | 可以提交 intent 和 operation |
| `reviewer` | 可以批准/拒绝 OP_PROPOSE |
| `owner` | 可以解决冲突，覆盖 contributor 操作 |
| `arbiter` | 最高裁决权，可解决任何冲突、覆盖任何参与者 |

### 6.2 Capabilities

| 值 | 说明 |
|----|------|
| `intent.broadcast` | 可发送 INTENT_ANNOUNCE |
| `intent.update` | 可发送 INTENT_UPDATE |
| `intent.withdraw` | 可发送 INTENT_WITHDRAW |
| `intent.claim` | 可发送 INTENT_CLAIM |
| `op.propose` | 可发送 OP_PROPOSE |
| `op.commit` | 可发送 OP_COMMIT |
| `op.reject` | 可发送 OP_REJECT |
| `op.batch_commit` | 可发送 OP_BATCH_COMMIT |
| `conflict.report` | 可发送 CONFLICT_REPORT |
| `conflict.ack` | 可发送 CONFLICT_ACK |
| `governance.vote` | 可参与治理投票 |
| `governance.override` | 可发送覆盖性 RESOLUTION |
| `causality.vector_clock` | 支持 vector_clock 水位 |
| `causality.lamport_clock` | 支持 lamport_clock 水位（MUST 支持） |
| `semantic.analysis` | 支持语义冲突检测 |

### 6.3 Security Profile

| 值 | 认证 | 签名 | 审计 | 适用场景 |
|----|------|------|------|---------|
| `open` | 无 | 无 | SHOULD | 内部团队/开发环境 |
| `authenticated` | MUST（OAuth/mTLS/API Key） | SHOULD（MAC 或数字签名） | MUST | 跨团队协作 |
| `verified` | MUST（X.509 证书链） | MUST（数字签名） | MUST（防篡改日志） | 跨组织高风险场景 |

**Authenticated / Verified 执行要求（Section 23.1.2–23.1.5）：**
- **角色策略评估**：Coordinator 必须根据 `role_policy` 评估 HELLO 中的 `requested_roles`，仅授予通过策略检查的角色。`SESSION_INFO.granted_roles` 反映实际授予角色，不是请求角色。Open profile 无策略时原样授予；Authenticated/Verified 无策略时，因策略为 MUST 要求，返回 `AUTHORIZATION_FAILED` 拒绝加入（不再回退为 `["participant"]`）。`max_count` 约束计数时排除正在加入的 principal 自身（避免 rejoin 被误拒）。
- **Replay 保护**：Coordinator 必须拒绝重复 `message_id`（返回 `REPLAY_DETECTED`）。此外应检查消息时间戳漂移：偏离超过 `replay_window`（RECOMMENDED: 5 minutes）也应拒绝。保护状态必须跨 coordinator recovery 延续（通过 snapshot 中的 `anti_replay` checkpoint）。

### 6.4 Compliance Profile

| 值 | 必须支持的消息类型 | 额外要求 |
|----|--------------------|---------|
| `core` | HELLO, SESSION_INFO, SESSION_CLOSE, COORDINATOR_STATUS, GOODBYE, HEARTBEAT, INTENT_ANNOUNCE, OP_COMMIT, OP_BATCH_COMMIT, CONFLICT_REPORT, RESOLUTION, PROTOCOL_ERROR | Lamport clock 规则、一致性模型语义；session 仅允许 `post_commit` |
| `governance` | core + INTENT_UPDATE, INTENT_WITHDRAW, INTENT_CLAIM, INTENT_CLAIM_STATUS, OP_PROPOSE, OP_REJECT, OP_SUPERSEDE, CONFLICT_ACK, CONFLICT_ESCALATE | 必须指定 arbiter；intent-before-action 为 MUST；`pre_commit` 仅可在该 profile 下启用；progressive degradation |
| `semantic` | governance + semantic conflict reporting | 支持 basis.kind = model_inference |

**注**：`INTENT_DEFERRED`（v0.1.14+）不在任何 profile 的强制实现集中，是 optional 的 UX-辅助消息。希望提供"yielded"提示的实现 SHOULD 支持。

### 6.5 Conflict Category

| 值 | 说明 |
|----|------|
| `scope_overlap` | 两个 intent/operation 的 scope 有交集 |
| `concurrent_write` | 同一资源的并发写入 |
| `semantic_goal_conflict` | 语义层面的目标冲突 |
| `assumption_contradiction` | 假设之间的矛盾 |
| `policy_violation` | 违反 session 策略 |
| `authority_conflict` | 权限冲突 |
| `dependency_breakage` | 依赖关系被破坏 |
| `resource_contention` | 资源争用 |

### 6.6 Severity

`info` < `low` < `medium` < `high` < `critical`

### 6.7 Decision

| 值 | 说明 |
|----|------|
| `approved` | 批准 |
| `rejected` | 拒绝 |
| `dismissed` | 驳回（冲突不成立或已失效） |
| `human_override` | 人工覆盖 |
| `policy_override` | 策略覆盖 |
| `merged` | 合并处理 |

### 6.8 Error Code

| 值 | 说明 | 触发场景 |
|----|------|---------|
| `MALFORMED_MESSAGE` | 消息格式错误或缺少必填字段 | 解析失败 |
| `UNKNOWN_MESSAGE_TYPE` | 未知的 message_type | 不支持的消息类型 |
| `INVALID_REFERENCE` | 引用了不存在的 session/intent/operation/conflict | 找不到引用目标 |
| `VERSION_MISMATCH` | 协议版本不兼容 | HELLO 中版本不匹配 |
| `CAPABILITY_UNSUPPORTED` | 消息要求接收方不支持的能力 | 能力缺失 |
| `AUTHORIZATION_FAILED` | 发送者权限不足 | 角色不匹配 |
| `PARTICIPANT_UNAVAILABLE` | 检测到参与者不可用 | 心跳超时 |
| `RESOLUTION_TIMEOUT` | 冲突解决超时 | 超过 resolution_timeout_sec |
| `SCOPE_FROZEN` | 目标 scope 被冻结 | 操作/intent 命中冻结区域 |
| `CLAIM_CONFLICT` | INTENT_CLAIM 目标已被他人认领 | 并发 claim |
| `COORDINATOR_CONFLICT` | Coordinator 冲突（split-brain 检测） | 多个 coordinator 实例被检测 |
| `STATE_DIVERGENCE` | 状态分歧（恢复后发现） | snapshot + audit log 回放后状态不一致 |
| `SESSION_CLOSED` | Session 已关闭 | SESSION_CLOSE 之后收到业务消息 |
| `CREDENTIAL_REJECTED` | 凭证验证失败 | HELLO 中的 credential 不被接受 |
| `REPLAY_DETECTED` | 重复消息被拒绝 | Authenticated/Verified profile 下检测到重复 `message_id`（Section 23.1.2） |
| `RESOLUTION_CONFLICT` | 同一冲突的重复裁决 | 已解决的 conflict 收到第二条 RESOLUTION（Section 18.4） |
| `CAUSAL_GAP` | 因果缺口信号 | 参与者通过 watermark 检测到遗漏消息（Section 12.8） |
| `INTENT_BACKOFF` | Intent 退避冷却中 | 冲突驱动拒绝后过早重新 announce 相同 scope（Section 15.3.1） |
| `BACKEND_SWITCH_DENIED` | 后端切换被拒绝 | 无法切换到请求的 AI 模型后端 |

### 6.9 Deferral Status *(v0.1.14+)*

`INTENT_DEFERRED` resolution form 的 `status` 字段：

| 值 | 触发场景 | 常见 `reason` |
|----|---------|---------------|
| `resolved` | observed intents 全部终结 / 同 principal 重新 announce / observed 端的对方 owner 进入终态 | `observed_intents_terminated` / `principal_announced` |
| `expired` | 墙钟超过 `expires_at`（默认 60s） | `ttl` |

active form 的 `reason` 字段是自由文本，常见 `yielded_to_active_editor`。

---

## 7. 协议顺序约束

实现时必须遵守的消息顺序规则：

| 约束 | 规则 | 违反时的行为 |
|------|------|-------------|
| **Session-first** | HELLO 必须是参与者在 session 中发送的第一条消息 | 拒绝或延迟处理非 HELLO 消息 |
| **Session-info-before-activity** | 参与者在收到 SESSION_INFO 前不应发送业务消息 | Coordinator 在 SESSION_INFO 之前不处理业务消息 |
| **Intent-before-operation** | OP_PROPOSE/OP_COMMIT 引用的 intent_id 必须已存在 | 可缓冲/警告/拒绝（PROTOCOL_ERROR） |
| **Conflict-before-resolution** | RESOLUTION 引用的 conflict_id 必须已存在 | 拒绝未知冲突的裁决 |
| **Causal consistency** | 携带 watermark 的消息不应被视为对 watermark 覆盖范围之外事件的权威声明 | 对超范围判断标记为 partial |

---

## 8. 版本新增协议语义

### v0.1.7 新增

### 8.1 一致性模型（Section 7.7）

MPAC 采用 **coordinator-serialized total order**：

- **正常模式**：coordinator 是唯一排序权威，所有消息由 coordinator 分配 Lamport 时钟值后广播，所有参与者看到相同的消息全序。
- **降级模式**（coordinator 不可用）：参与者 MUST NOT 执行新变更（mutation），可继续读取和维持心跳。
- **恢复后**：通过 snapshot + audit log 回放重建一致状态。状态分歧通过 governance 层解决。

MPAC **不提供**线性一致性（linearizability）。它提供的是 coordinator 串行化的全序 + 因果上下文标注。

### 8.2 执行模型（Section 7.8）

Session 在 SESSION_INFO 中 MUST 声明 `execution_model`：

| 模型 | OP_COMMIT 语义 | 适用场景 |
|------|---------------|---------|
| `pre_commit` | OP_PROPOSE → coordinator 授权 → 参与者执行 → OP_COMMIT；授权本身不等于 COMMITTED | 高协调场景，写前检查，仅 Governance Profile 可用 |
| `post_commit` | 参与者先执行变更 → OP_COMMIT 为事后声明 | 低延迟场景，事后协调 |

**Pre-commit 流程**：OP_PROPOSE → coordinator 做 scope 检查 + 冲突检测 + 治理校验 → 显式授权 → 参与者执行 → OP_COMMIT。
如果为了兼容旧实现而直接先发 `OP_COMMIT`，它在 `pre_commit` session 中也只能被当作“待授权请求”，先进入 `PROPOSED`，不能直接视为已提交。
**Post-commit 流程**：参与者直接执行 → OP_COMMIT（携带 state_ref_before/after）→ coordinator 做事后冲突检测。
**兼容默认值**：若旧实现返回的 `SESSION_INFO` 缺少 `execution_model`，接收方 MUST 默认按 `post_commit` 处理。

### 8.3 Lamport Clock 维护规则（Section 12.7）

7 条规范规则：

| # | 规则 | 说明 |
|---|------|------|
| 1 | 初始化 | 每个 sender incarnation 在创建新的 `sender_instance_id` 时从 0 开始；同一进程重连时保留原值。Coordinator 在 session 创建时从 0 开始，或恢复时从快照值继续 |
| 2 | 发送规则 | 发送消息前 clock++ |
| 3 | 接收规则 | 收到消息后 clock = max(local, received) + 1 |
| 4 | Coordinator 权威 | Coordinator 的 Lamport 值为权威值；参与者检测到本地值高于 coordinator 时 SHOULD 报告 |
| 5 | 快照持久化 | Coordinator 快照 MUST 包含当前 Lamport 值；恢复后从快照值继续 |
| 6 | 单调性 | 同一 sender incarnation（由 `(principal_id, sender_instance_id)` 标识）的 Lamport 值 MUST 严格递增，MUST NOT 回退 |
| 7 | 重连规则 | handover/recovery 后重新发送 `HELLO` 时，未重启进程的参与者 MUST 保留 `sender_instance_id` 与本地 Lamport counter；若进程已重启，则必须生成新的 `sender_instance_id` |

### 8.4 Frozen Scope 三阶段渐进降级（Section 18.6.2.1）

替代旧版"等 30 分钟然后拒绝全部"的二元策略：

| Phase | 时间窗口 | 行为 |
|-------|---------|------|
| Phase 1 | 0 – phase_1_sec（默认 60s） | 正常解决流程：参与者协商或仲裁者裁决 |
| Phase 2 | phase_1_sec – (phase_1 + phase_2)（默认 60–300s） | 自动升级 + 优先级旁路：高优先级 intent 可绕过冻结 |
| Phase 3 | > (phase_1 + phase_2)（默认 300s+） | first-committer-wins：按 coordinator 接收顺序选择首个获胜提交 |

### 8.5 Coordinator 问责制（Section 23.1.3.1，仅 Verified profile）

- Coordinator MUST 签署所有发出的消息
- 参与者 MUST 验证 coordinator 签名
- Coordinator 的所有操作记录在防篡改日志中
- 支持独立审计

### v0.1.8 新增

#### 8.6 并发 RESOLUTION 竞态规则（Section 18.4）

同一 `conflict_id` 的多条 RESOLUTION → coordinator 先判断“发送者是否属于当前 authority phase 的合法 resolver”，再只接受其中第一条有效裁决（按 coordinator 接收顺序），后续以 `RESOLUTION_CONFLICT` 拒绝。

- `ESCALATED` 之后，不再是“谁先到谁赢”；优先级切换为 `escalate_to` / session policy 明确授权的 arbiter / coordinator 系统裁决
- 与 INTENT_CLAIM 的 first-claim-wins 模式一致（Section 14.7.4）
- 排序依据：coordinator 接收顺序，非消息 `ts` 时间戳

#### 8.7 Intent Re-Announce 退避（Section 15.3.1）

防止活锁：intent 因 scope overlap conflict 被 reject 后，重新 announce 相同/重叠 scope 时 SHOULD 指数退避。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `intent_backoff_initial_sec` | `30` | 首次退避等待时间 |
| `intent_backoff_max_sec` | `300` | 退避上限 |
| `intent_backoff_multiplier` | `2` | 每次退避的倍数 |

- Coordinator MAY 强制执行退避，以 `INTENT_BACKOFF` 拒绝过早的 re-announce
- **不适用于**：TTL 过期后 re-announce、主动 withdraw 后 re-announce、不同 scope 的 announce

#### 8.8 因果缺口检测与行为（Section 12.8）

参与者通过 watermark 检测到遗漏消息时的行为规范：

| 行为 | 级别 | 说明 |
|------|------|------|
| 仍然更新 Lamport clock | MUST | `counter = max(local, received) + 1` |
| 不做冲突判断或裁决 | SHOULD NOT | 基于不完整因果上下文的判断可能是错误的 |
| 向 coordinator 发送 `CAUSAL_GAP` | MAY | 请求状态同步（机制由实现定义） |
| 继续非因果敏感操作 | MAY | 如 HEARTBEAT、INTENT_UPDATE 等 |

### v0.1.9–v0.1.12 新增 / 修订

#### 8.9 Coordinator Epoch Fencing

- 所有 coordinator-authored message 必须携带 `coordinator_epoch`
- handover 时通过 `next_coordinator_epoch` 显式声明继任 epoch
- split-brain 检测时先比较 epoch，再在同 epoch 内比较 Lamport watermark

#### 8.10 Sender Incarnation 与安全重连

- `sender_instance_id` 明确区分同一 principal 的不同进程/重启化身
- Lamport 单调性和 sender-frontier replay 检查按 `(principal_id, sender_instance_id)` 评估
- coordinator handover / recovery 后，未重启进程的参与者重发 `HELLO` 时必须保留原 `sender_instance_id` 和本地 Lamport counter

#### 8.11 显式 Claim 处置与 Replay Recovery 闭环

- 新增 `INTENT_CLAIM_STATUS`，把 `approved` / `rejected` / `withdrawn` 变成显式协议事件
- 被认领成功的原 intent 进入 `TRANSFERRED`
- Authenticated / Verified profile 的 replay protection 必须跨 coordinator recovery 延续，snapshot 需保留足够的 anti-replay checkpoint

#### 8.12 执行与治理闭合

- `pre_commit` 现在明确要求 Governance Profile；Core Profile session 只能使用 `post_commit`
- `pre_commit` 中 coordinator 的授权不再等同于 `COMMITTED`，真正进入 `COMMITTED` 仍要等 proposer 执行后再发 `OP_COMMIT`
- 并发 `RESOLUTION` 改成“按当前 authority phase 的 first-resolution-wins”：升级后优先尊重 `escalate_to` / 明确授权的 arbiter
- Conflict auto-dismiss 的 intent 终态集合补齐 `TRANSFERRED`
- Governance Profile 下 claim 批准必须记录 `approved_by`

#### 8.13 示例与 Schema 对齐（v0.1.12）

- Section 28 的所有示例消息补齐 `sender.sender_instance_id` 和正确的 `version`
- `SESSION_INFO` payload 表新增 `identity_issuer`（Optional），与 §23.1.4 credential exchange 响应一致
- `SESSION_CLOSE` 的 summary 示例对齐 §9.6.2 的详细结构
- `COORDINATOR_STATUS` 的 `heartbeat_interval_sec` 交叉引用修正为 §14.7.5
- `OP_BATCH_COMMIT` 新增 pre-commit 消歧义规则：coordinator 用 `batch_id` 是否已注册来区分首次提交 vs 完成声明
- `INTENT_UPDATE` scope 扩大时 coordinator SHOULD 重新做冲突检测
- `GOODBYE` 的 `transfer` disposition 明确走 `SUSPENDED` → `INTENT_CLAIM` 路径
- Semantic Profile（§20.3）标注为 v0.1.x placeholder

#### 8.14 后端健康监控（v0.1.13）

- `HELLO` payload 新增 `backend` 字段（Optional），声明 Agent 的 AI 模型后端依赖
- `HEARTBEAT` payload 新增 `backend_health` 字段（Optional），报告后端提供者的健康状态
- `COORDINATOR_STATUS` 的 `event` 枚举新增 `backend_alert`，用于 coordinator 通知 Agent 后端故障或切换
- `COORDINATOR_STATUS` 新增 `affected_principal` 和 `backend_detail` 字段，提供后端告警时的受影响者和详细信息
- `Liveness Policy` 新增 `backend_health_policy` 字段（Optional），控制后端健康监控和故障转移策略
- 新增错误码 `BACKEND_SWITCH_DENIED`，表示无法切换到请求的 AI 模型后端

### v0.1.14 新增

#### 8.15 INTENT_DEFERRED — 让让信号（Section 15.5.1）

新增一种**非声明性**的协调信号，让参与者可以"我看到 Alice 在改 X，那我先躲一下"留下显式痕迹，而不必发一个 `INTENT_ANNOUNCE` 来抢 scope。

**关键属性**：
- 不是 intent —— 不锁 scope、不进入 intent 状态机、不参与 overlap detection
- 不阻塞同一 principal 后续 `INTENT_ANNOUNCE`（一旦 announce，原 deferral 自动 resolved）
- 纯 UX 用途 —— sibling participants 渲染"yielded"提示给人类 owner 看

**两种 form 共用一个 `message_type`**：active form（让让方发，coordinator 重广播时填 `principal_id` 和 `expires_at`）+ resolution form（仅 coordinator 发，标 `status=resolved/expired`）。

**Coordinator 三轴清理规则**（任一满足即 emit `resolved`）：

| # | 触发条件 |
|---|---------|
| 1 | `observed_intent_ids` 中所有 intent 都进入终态 |
| 2 | 同一 `principal_id` 后续发送了 `INTENT_ANNOUNCE` |
| 3 | 终结的 intent 的 owner 命中 `observed_principals`，**或** 命中 `observed_intent_ids`（防御性匹配——兼容把两个字段混用的旧客户端） |

**TTL**：默认 60 秒；超时则 emit `status=expired`。客户端 SHOULD 自行 local TTL sweep。

**Compliance**：不在任何 profile 的 MUST 集中，是 optional UX 增强。

---

## 9. 实现检查清单

开发者实现 MPAC 时的快速对照表：

**基础（所有 profile）：**
- [ ] 所有消息包装在 Message Envelope 中，8 个必填字段齐全
- [ ] 所有消息的 `sender` 都带 `sender_instance_id`
- [ ] HELLO 作为首条消息发送，收到 SESSION_INFO 后验证兼容性
- [ ] SESSION_INFO 包含 `execution_model` 字段（R）
- [ ] 所有 coordinator-authored message 都带 `coordinator_epoch`
- [ ] 支持 `lamport_clock` watermark 的生成、比较和 lamport_value 降级
- [ ] Lamport clock 遵循 7 条维护规则（Section 12.7）
- [ ] 对同一 `(principal_id, sender_instance_id)` 强制 Lamport 严格单调递增
- [ ] OP_COMMIT 包含 state_ref_before 和 state_ref_after
- [ ] OP_COMMIT / CONFLICT_REPORT / RESOLUTION 的信封包含 watermark
- [ ] Scope overlap 对 file_set / entity_set / task_set 使用 MUST 级算法
- [ ] Intent 终态触发关联 PROPOSED 操作的 auto-reject（Section 15.7）
- [ ] 冲突关联实体全部终结时触发 auto-dismiss（Section 17.9）
- [ ] TTL 由 coordinator 基于 received_at + ttl_sec 墙钟判定
- [ ] RESOLUTION 拒绝 COMMITTED 操作时 MUST 包含 rollback 字段
- [ ] 心跳间隔 ≤ 30 秒，不可用超时 = 90 秒
- [ ] GOODBYE 时声明 active_intents 和 intent_disposition
- [ ] 支持 SESSION_CLOSE 和 COORDINATOR_STATUS 消息处理
- [ ] 支持 OP_BATCH_COMMIT（all_or_nothing / best_effort 两种模式）

**执行模型：**
- [ ] Core Profile session 仅使用 `post_commit`
- [ ] 声明 `pre_commit` 的 session 同时声明 Governance Profile
- [ ] Pre-commit: OP_PROPOSE → coordinator 显式授权 → 执行 → OP_COMMIT
- [ ] Post-commit: 执行 → OP_COMMIT（事后声明）
- [ ] 根据 SESSION_INFO.execution_model 选择正确流程
- [ ] `pre_commit` 中授权本身不把 operation 置为 `COMMITTED`
- [ ] `OP_BATCH_COMMIT` 与 `OP_COMMIT` 采用同一 execution_model 语义

**Frozen scope 三阶段降级：**
- [ ] Phase 1: 正常解决流程（默认 0–60s）
- [ ] Phase 2: 自动升级 + 优先级旁路（默认 60–300s）
- [ ] Phase 3: first-committer-wins 降级（默认 300s+）

**Coordinator 故障恢复：**
- [ ] 定期发送 COORDINATOR_STATUS，并独立持久化 state snapshot
- [ ] 支持 snapshot + audit log replay 恢复
- [ ] 快照至少保留 `snapshot_version: 2`、`coordinator_epoch`、`lamport_clock` 和 `anti_replay` checkpoint
- [ ] 恢复后先恢复 anti-replay checkpoint，再接受新的 post-recovery 消息
- [ ] 参与者在未重启进程的重连场景中保留 `sender_instance_id` 与 Lamport counter
- [ ] Split-brain 检测遵循“先 epoch，后 Lamport tie-break”

**并发裁决、claim 处置与活锁防护（v0.1.8+ / v0.1.12）：**
- [ ] Coordinator 只在“当前 authority phase 的合法 resolver”集合内执行 first-resolution-wins
- [ ] 支持 `INTENT_CLAIM_STATUS`，并正确处理 `approved` / `rejected` / `withdrawn`
- [ ] `INTENT_CLAIM_STATUS(approved)` 使原 intent 进入 `TRANSFERRED`
- [ ] Governance Profile 下 `INTENT_CLAIM_STATUS(approved)` 必带 `approved_by`
- [ ] Intent re-announce 退避：冲突驱动拒绝后，相同 scope 的 re-announce 遵循指数退避
- [ ] 因果缺口检测：watermark 跳跃时不发出 CONFLICT_REPORT 或 RESOLUTION，可发 `CAUSAL_GAP`

**v0.1.12 对齐项：**
- [ ] `OP_BATCH_COMMIT` pre-commit 消歧义：coordinator 用 `batch_id` 存在性区分首次提交 vs 完成声明
- [ ] `INTENT_UPDATE` scope 扩大时重新做 overlap 检测
- [ ] `GOODBYE` 的 `intent_disposition: "transfer"` 把 intent 转为 `SUSPENDED`，使其可被 `INTENT_CLAIM`
- [ ] `SESSION_INFO` 响应中可选填写 `identity_issuer`

**v0.1.14 INTENT_DEFERRED：**
- [ ] 发送端：发 `INTENT_DEFERRED` 不阻塞同 principal 的后续 `INTENT_ANNOUNCE`，也不参与 overlap detection
- [ ] Coordinator：active form 重广播时填入 `principal_id` 和 `expires_at`（基于 `received_at + ttl_sec`，默认 60s）
- [ ] Coordinator：实现三轴清理（observed_intent_ids 全部终态 / 同 principal 重新 announce / 终结 intent owner ∈ observed_principals 或 ∈ observed_intent_ids）
- [ ] Coordinator：TTL 超时 emit `status=expired` follow-up
- [ ] 客户端：实现 local TTL sweep 防止丢失广播导致 UI 滞留

**安全 / 合规：**
- [ ] Authenticated profile: 凭证交换（Section 23.1.4）、身份绑定
- [ ] Authenticated / Verified profile: **角色策略评估** — HELLO 中的 `requested_roles` 必须经 `role_policy` 检查，`SESSION_INFO.granted_roles` 反映实际授予角色（Section 23.1.5）。无 `role_policy` 时返回 `AUTHORIZATION_FAILED` 拒绝加入。`max_count` 计数排除正在加入的 principal 自身。
- [ ] Authenticated / Verified profile: **Replay 保护** — 拒绝重复 `message_id`（返回 `REPLAY_DETECTED`），同时检查消息时间戳漂移（RECOMMENDED: 5 minutes 窗口）。anti-replay checkpoint 持久化到 snapshot，恢复后继续执行同一策略（Section 23.1.2）
- [ ] Verified profile: coordinator 签署所有消息、防篡改日志、独立审计
