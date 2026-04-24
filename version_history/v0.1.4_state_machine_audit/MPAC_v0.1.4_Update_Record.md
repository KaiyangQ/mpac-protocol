# MPAC v0.1.4 Update Record

**Date**: 2026-04-02
**Update Name**: State Machine Cross-Safety & Session Negotiation
**Previous Version**: v0.1.3 (Interoperability Hardening)
**Trigger**: Five-dimension audit (MPAC_v0.1.3_Audit_Report.md) identifying state machine cross-lifecycle gaps, coordinator single-point-of-failure, and session negotiation absence

---

## Overview

This update addresses the findings from the v0.1.3 audit, with priority on **state machine cross-safety** (the newly added fifth audit dimension) and **session negotiation**. The core protocol model (Session → Intent → Operation → Conflict → Governance) is unchanged. All changes are additive rules, new message types, or normative language upgrades on the existing architecture.

---

## Audit Findings → Resolution Map

### Resolved (P0)

| Audit Finding | Severity | Resolution | Spec Location |
|---------------|----------|------------|---------------|
| Intent TTL 过期时关联的 pending OP_PROPOSE 成为孤儿，状态既非 COMMITTED 也非 REJECTED | 高 | 新增 Intent Expiry Cascade 规则：intent 进入终态时，关联 PROPOSED 操作 MUST 自动 reject；SUSPENDED 时操作进入 FROZEN 状态 | Section 15.7 (new) |
| Frozen scope 期间所有关联 intent 过期，冲突引用已消亡实体但无法自然解除 | 中 | 新增 Conflict Auto-Dismissal：所有关联 intent 和 operation 均终结时，冲突自动 DISMISS 并立即释放 frozen scope | Section 17.9 (new) |
| Session Coordinator 单点故障无恢复定义 | 高 | 新增 Coordinator Fault Recovery：状态持久化 SHOULD、重启状态重建、参与者在 coordinator 不可用时的行为规范 | Section 8.1.1 (new) |
| Session Negotiation 缺失，参与者加入后才发现不兼容 | 中 | 新增 SESSION_INFO 消息类型：coordinator 对 HELLO 的响应，携带 session 配置和兼容性检查结果 | Section 14.2 (new), Section 13.1 payload schema |

### Resolved (P1)

| Audit Finding | Severity | Resolution | Spec Location |
|---------------|----------|------------|---------------|
| TTL 基于墙钟还是逻辑时钟存在歧义 | 中 | 明确 TTL 由 coordinator 本地墙钟判定，基于 received_at + ttl_sec 计算，sender 的 ts 仅用于审计 | Section 15.3 semantics |
| RESOLUTION 拒绝已 COMMITTED 操作时 rollback 字段为 SHOULD，可产生信令层与数据层状态分裂 | 中 | SHOULD → MUST；缺失 rollback 字段的 resolution 被 coordinator reject | Section 18.4 |
| canonical_uris 为 SHOULD，跨组织 session 中跨 scope kind 冲突检测大量 false positive | 中高 | Authenticated/Verified profile 的跨 scope kind session 中提升为 MUST | Section 15.2.2 |

### Not Yet Resolved (Deferred to v0.2)

| Audit Finding | Severity | Reason for Deferral |
|---------------|----------|-------------------|
| 消息信封开销偏重（compact envelope / 二进制序列化） | 中 | 需要评估对现有实现的兼容性影响，适合作为 v0.2 的 transport optimization track |
| 缺少 OP_BATCH 消息批处理机制 | 中 | 需要定义原子性语义（全部成功 or 全部失败 or 部分成功），设计空间较大 |
| 大规模 session 消息扇出（scope-based subscription） | 高 | 架构性变更，需要重新设计 coordinator 的消息路由模型 |
| Session 分片（sharding）机制 | 中高 | 需要定义 cross-session intent 引用和跨 coordinator 协调语义 |
| op_kind 最小枚举集 | 中 | 需要收集更多实际使用场景后再确定枚举范围 |
| state_ref_format 在 session metadata 中声明 | 中 | SESSION_INFO 已包含 state_ref_format 字段，但 coordinator 在 HELLO 时的格式验证逻辑未规范化 |
| 同一 scope 最大冲突轮次（防止超时级联活锁） | 中低 | 需要更多实际场景数据确定合理默认值 |
| Conformance test suite | — | 属于工具链而非 spec 内容，建议作为独立项目启动 |

---

## Change Log

### 1. Intent Expiry Cascade [NEW Section 15.7]

**Problem**: Intent 进入终态（EXPIRED/WITHDRAWN/SUPERSEDED）时，引用该 intent 的 pending OP_PROPOSE 状态无归属——协议未定义处置规则，产生孤儿 proposal。

**Change**:
- Intent 终态 → 关联 PROPOSED 操作 MUST 自动 reject（reason: `intent_terminated`）
- Intent SUSPENDED → 关联 PROPOSED 操作进入 FROZEN 状态（不可推进但不拒绝）
- FROZEN 操作在 intent 恢复 ACTIVE 后自动解冻回 PROPOSED
- 可配置 `intent_expiry_grace_sec`（默认 30 秒），允许提交者在宽限期内重新关联到新 intent
- 已 COMMITTED 的操作不受 intent 终态影响

**Impact**: 封堵了审计报告中风险等级最高的状态机交叉漏洞。Operation lifecycle 新增 FROZEN 状态及其转换路径。

---

### 2. Conflict Auto-Dismissal [NEW Section 17.9]

**Problem**: Frozen scope 期间如果所有关联 intent 过期，冲突在语义上已失去意义，但协议无自动解除机制，只能等待 frozen_scope_timeout（默认 30 分钟）。

**Change**:
- 当冲突的所有 `related_intents` 均已终结，且所有 `related_ops` 均在终态时，冲突 SHOULD 自动 DISMISS
- 自动 dismiss MUST 生成系统归属的 RESOLUTION（decision: dismissed, rationale: all_related_entities_terminated）
- 自动 dismiss 立即释放关联 frozen scope，优先于 frozen_scope_timeout
- 仅 intent 终结但 operation 仍为非终态时不触发自动 dismiss

**Impact**: 消除了"冲突存在但关联实体已消亡"的不自洽窗口。Conflict lifecycle 新增从 OPEN/ESCALATED 到 DISMISSED 的 intent 终结触发路径。

---

### 3. Coordinator Fault Recovery [NEW Section 8.1.1]

**Problem**: 协议所有运行时保证依赖 coordinator，但 coordinator 自身崩溃时的恢复完全未定义。

**Change**:
- 状态持久化 SHOULD（participant roster, intent registry, operation states, conflict states）
- 重启后通过 persisted snapshot + audit log 重建状态
- 参与者检测 coordinator 不可用（2× unavailability_timeout_sec 无 coordinator 消息）后暂停冲突敏感操作
- Coordinator 恢复后广播通知，参与者重发 HELLO

**Impact**: 从"完全未定义"提升到"有明确的 SHOULD 级恢复路径"。

---

### 4. SESSION_INFO Message [NEW Section 14.2, NEW payload schema]

**Problem**: 参与者在 HELLO 后无法得知 session 的配置是否与自身兼容，只能在后续交互中逐步发现不兼容（如 watermark kind 不匹配、security profile 不支持）。

**Change**:
- 新增 SESSION_INFO 消息类型，coordinator MUST 在收到 HELLO 后响应
- 携带：protocol_version, security_profile, compliance_profile, watermark_kind, state_ref_format, governance_policy, liveness_policy, granted_roles, compatibility_errors
- `granted_roles` 可能与 HELLO 中请求的 roles 不同（权限校验结果）
- `compatibility_errors` 列出检测到的不兼容项，参与者可据此决定是否退出
- 加入 Core Profile 必须支持的消息列表

**Impact**: 实现了 session negotiation，解决了"加入后才发现不兼容"的问题。

---

### 5. TTL Wall-Clock Semantics [REVISED Section 15.3]

**Problem**: ttl_sec 名义上是墙钟秒数，但 coordinator 的检查方式、clock skew 处理均未定义。

**Change**: TTL MUST 由 coordinator 本地墙钟判定，基于 coordinator 的 received_at + ttl_sec 计算，sender 的 ts 仅用于审计。

---

### 6. Resolution Rollback: SHOULD → MUST [REVISED Section 18.4]

**Problem**: RESOLUTION 拒绝已 COMMITTED 操作时 rollback 字段为 SHOULD，可产生信令层（REJECTED）与数据层（效果仍存在）的状态分裂。

**Change**: MUST 包含 rollback 字段。缺失时 coordinator MUST 以 PROTOCOL_ERROR (MALFORMED_MESSAGE) 拒绝该 resolution。

---

### 7. Canonical URIs: SHOULD → MUST (Cross-Org) [REVISED Section 15.2.2]

**Problem**: canonical_uris 为 SHOULD，跨组织 session 中使用不同 scope kind 的参与者之间冲突检测会产生大量 false positive。

**Change**: Authenticated/Verified security profile 下的跨 scope kind session MUST 包含 canonical_uris。Open profile 或同质 scope kind session 保持 SHOULD。

---

## Structural Changes

- Section 14.x 编号顺移：原 14.2 HEARTBEAT → 14.3，原 14.3 GOODBYE → 14.4，原 14.4 Unavailability → 14.5（含全部子节 14.5.1–14.5.5）
- Operation lifecycle (Section 16.6) 新增 FROZEN 状态及 4 条转换路径
- Conflict lifecycle (Section 17.8) 新增 2 条 intent 终结触发的 DISMISSED 路径
- 全文交叉引用更新（Section 14.4.x → 14.5.x，共 12 处）
- 版本号更新至 v0.1.4（Section 1, Section 30）

---

## Cross-References

- Audit report: `version_history/v0.1.4_state_machine_audit/MPAC_v0.1.3_Audit_Report.md`
- Archived pre-update spec: `version_history/v0.1.4_state_machine_audit/SPEC_v0.1.3_2026-04-02.md`
