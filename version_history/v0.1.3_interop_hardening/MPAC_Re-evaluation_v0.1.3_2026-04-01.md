# MPAC v0.1.3 重新评审报告

**评审日期**: 2026-04-01
**评审对象**: SPEC.md (MPAC v0.1.3 — Interoperability Hardening)
**背景**: 此前对 v0.1.2 做了完整评审并提出改进建议，协议作者据此修订为 v0.1.3。本报告以独立评审者身份重新评估修订后的 spec，不预设之前的结论。

---

## 1. 协议设计：核心抽象评估

### 判断：显著改善，层间关系比之前清晰得多

五层模型（Session → Intent → Operation → Conflict → Governance）保持不变，这是正确的——核心架构不需要改。v0.1.3 的关键进步在于：

**Session Coordinator（Section 8.1）** 的引入解决了之前最大的架构悬空问题。原来 spec 暗示了一个中心化组件但不承认它，现在明确定义了 coordinator 的职责边界（状态维护、排序执行、活性检测、身份绑定、审计日志），同时保持了 transport independence 的立场。"每个 session MUST 有且只有一个逻辑 coordinator"这个约束把很多下游行为的执行者锚定住了。

**仍然存在的问题：**

- **Session negotiation 仍然缺失。** Section 9.2 定义了三种创建方式，但两个实现 join 同一 session 时仍然没有标准方法验证 capability 兼容性。HELLO 携带了 capabilities 列表（Section 14.1），但收到不兼容 capabilities 时的行为仍未定义。比如：A 只支持 lamport_clock，B 只支持 vector_clock——虽然 12.3 定义了 lamport_value 降级，但 session 级别没有 negotiation failure 路径。**建议**：在 Section 14.1 的 HELLO 语义中增加 coordinator 的兼容性检查职责——至少 SHOULD 验证关键 capability（如 causality kind）的兼容性，并在不兼容时返回 PROTOCOL_ERROR。

- **五层之间的交互契约仍然是隐式的。** Section 6 说 "externally visible semantics SHOULD remain distinct"，但"externally visible"的定义仍未给出。实际上在 v0.1.3 中，各层之间通过 Section 8.2 的排序约束和 Section 7.1–7.3 的共享原则间接关联了，只是没有统一成一个"层间接口"描述。这不是阻塞问题，但对于想严格分层实现的团队，spec 应提供更清晰的指引。

- **删除 winner/loser 简写是正确的决定。** 协议 spec 不应提供语法糖。

---

## 2. 可实现性

### 判断：从"无法互操作"提升到了"有条件可互操作"

v0.1.2 的三大互操作障碍在 v0.1.3 中都得到了处理：

**Payload Schema（Section 13.1）**：这是最有影响力的单项改动。16 种 message type 全部有了 field-level schema 表格，包括 required/optional 标注、type、enum values、条件依赖（Scope object 的 C 标记）。两个独立团队现在可以基于这些表格写出 field-level 兼容的 parser/validator。

**Scope Overlap 标准化（Section 15.2.1）**：file_set、entity_set、task_set 有了 MUST 级的判定规则（规范化路径 + 集合交集）。resource_path 有了 SHOULD 级的最小 glob 支持。cross-kind overlap 有了明确的判定链（canonical_uris → resource registry → conservative default）。这意味着最常见的 scope kind 上，两个合规实现会产出一致的 overlap 判定。

**Watermark 基线（Section 12.3）**：lamport_clock 作为 MUST 支持的 baseline，定义了比较语义，加了 lamport_value 降级字段。跨实现因果比较从"不可能"变成了"至少有一个可操作的降级路径"。

**仍然可能产生不兼容的地方：**

- **state_ref 格式仍是 implementation-defined。** Section 16.3 说 state_ref_before/after MUST 存在且"format is implementation-defined but MUST be consistent within a session"。这意味着 Team A 用 SHA-256，Team B 用 git commit hash，如果它们要 join 同一个 session，需要提前协商 state_ref 格式。但 spec 没有定义这个协商机制。**建议**：在 session metadata 中增加 `state_ref_format` 声明字段（如 `"sha256"`、`"git_hash"`、`"monotonic_version"`），让 coordinator 在 HELLO 时验证参与者的 state_ref 格式与 session 声明一致。

- **`op_kind` 的值空间未约束。** Section 13.1 的 OP_COMMIT schema 说 op_kind 是 string，给了例子（replace、insert、delete、patch），但没有 MUST 级枚举。如果 Team A 用 `"replace"` 而 Team B 用 `"overwrite"` 表示同一语义，冲突检测器无法判断它们是否等价。**建议**：定义一个 MUST 支持的最小 op_kind 枚举（`replace`、`insert`、`delete`），允许 extensions。

- **Scope object 的 file_set 路径规范化规则（Section 15.2.1.1）有遗漏。** 定义了去 `./`、折叠 `//`、去尾 `/`，但没有提及 `..` 的处理。如果 A 用 `src/../config.yaml` 而 B 用 `config.yaml`，按当前规则它们不匹配。**建议**：增加 `..` 段的规范化（解析父目录引用），或明确声明包含 `..` 的路径 MUST 在发送前由发送者完全解析。

---

## 3. 边界情况

### 判断：主要的死锁和竞态路径已封堵，但仍有残留

**已解决的边界情况：**

- 并发 INTENT_CLAIM 竞态（Section 14.4.4）——first-claim-wins + CLAIM_CONFLICT error
- Frozen scope 死锁（Section 18.6.2.1）——frozen_scope_timeout_sec fallback
- Frozen scope 下的 intent 堆积（Section 18.6.2）——fully contained intent 被 reject
- Resolution 回滚歧义（Section 18.4）——rollback 字段明确预期
- 信令-状态断层（Section 16.3）——causally_unverifiable 降级

**仍然存在的边界情况：**

- **TTL 与墙钟 vs 逻辑时钟的歧义仍未解决。** Section 13.1 的 INTENT_ANNOUNCE schema 明确说 `ttl_sec` 是 "Time-to-live in wall-clock seconds"，这很好。但 spec 从未定义 coordinator 如何检查 TTL 过期。如果 coordinator 在处理每条消息时检查 `ts + ttl_sec < now()`，那 clock skew 会导致不一致。如果用 lamport clock，又和 "wall-clock seconds" 语义不符。**建议**：明确 TTL 检查由 session coordinator 基于 coordinator 本地墙钟执行，参与者的 `ts` 字段仅用于审计，不用于 TTL 计算。

- **INTENT_UPDATE 扩大 scope 后的冲突重检未定义。** 如果 A 的 intent 原 scope 是 `["train.py"]`，update 后变成 `["train.py", "config.yaml"]`，而 B 的 intent 覆盖 `["config.yaml"]`——spec 没有说 INTENT_UPDATE 是否 SHOULD 触发冲突重新检测。参考实现会重检（engine.py line 228-229），但 spec 只在 INTENT_ANNOUNCE 的语义中暗示了冲突检测。**建议**：明确 INTENT_UPDATE 扩大 scope 时 SHOULD 触发与 INTENT_ANNOUNCE 等效的冲突检测。

- **Session coordinator 自身的故障恢复。** Section 8.1 说 coordinator 是 single point，但 coordinator 崩溃时怎么办？所有的 heartbeat 检测、frozen scope 执行、identity binding 都依赖它。Spec 只说"分布式部署 MUST 提供等价机制"，但对单 coordinator 部署的故障恢复没有建议。**建议**：在 Section 8.1 中增加 SHOULD 级建议——coordinator 应支持状态持久化，以便重启后能从 audit log 重建 session state。

---

## 4. 规范性语言

### 判断：v0.1.3 的 MUST/SHOULD 使用比 v0.1.2 精确得多

关键提升：
- Section 7.1 的 intent-before-action：Governance Profile 下 MUST，Core Profile 下 SHOULD——合理分层
- Section 7.3 的 causal context：三种关键消息类型 MUST，其他 SHOULD——精确
- Section 12.3 的 lamport_clock MUST 支持——解决了互操作基线
- Section 14.1 的 HELLO MUST——与 Section 8.2 的排序约束一致了
- Section 16.3 的 state_ref MUST——堵住了最大的 payload 歧义
- Section 23.1.2 的 replay protection MUST——安全关键路径不能是 SHOULD

**仍然值得调整的：**

| Section | 当前 | 建议 | 理由 |
|---------|------|------|------|
| 11.4 | `watermark` SHOULD describe causal state | 对 OP_COMMIT/CONFLICT_REPORT/RESOLUTION 应交叉引用 Section 7.3 的 MUST | 11.4 和 7.3 之间存在微妙矛盾：11.4 说 watermark 整体是 optional（Section 11.3），但 7.3 说三种消息 MUST 包含 watermark。应在 11.4 中加注释消除歧义 |
| 15.3 | "participants SHOULD announce intent before non-trivial work" | 删除或改为交叉引用 7.1 | 这句话是 v0.1 遗留的，和 7.1 的新措辞重复且更弱，容易让读者困惑 |
| 23.3.3 | governance authority verification 用 SHOULD | Authenticated Profile 下 MUST | 如果不强制检查 role 权限，role assertion validation（23.1.2）的价值减半 |

---

## 5. 与 MCP/A2A 的定位

### 判断：差异化定位明确成立，集成问题仍是最大的采用障碍

Section 2.1 的三协议定位（MCP = agent-to-tool，A2A = single-principal agent-to-agent，MPAC = multi-principal coordination）清晰准确。v0.1.3 没有越界去定义不该管的东西（Non-Goals Section 4 维护得很好），也没有遗漏自己该管的核心语义。

**但仍缺少与 MCP/A2A 的集成指引。** Section 29 的 future work 里提到了"integration architecture guidance"，但对于一个想采用 MPAC 的团队来说，这是最先会问的问题：

- 我的 agent 通过 MCP 调了一个工具修改了文件——这个工具调用如何变成一个 MPAC OP_COMMIT？state_ref_before 用什么？MCP 不提供 state hash。
- 我的 A2A orchestrator 把子任务委派给了一个 sub-agent——sub-agent 的结果如何 map 回 MPAC 的 intent/operation？

这些不需要 normative 定义，但一个 informative appendix 或 integration pattern 文档会极大降低采用门槛。**建议**：在 Section 29 的 future work 中将此项标记为 high priority，或者在 spec 外提供一个 non-normative 的 integration guide。

**Semantic Profile（Section 20.3）仍然偏早。** 它作为 optional profile 存在没有害处，但它的定义太薄了——只有三行，没有 MUST 级要求。与 Core Profile 和 Governance Profile 的详尽定义形成反差。**建议**：要么充实 Semantic Profile 的要求（比如 MUST 支持 `basis.kind = semantic_match` 的解析，MUST 在 confidence 低于阈值时 escalate），要么坦诚标注为 "placeholder for future definition"。

---

## 6. 安全模型

### 判断：从"纸面自洽"提升到了"可实施"

关键改善：
- Replay protection 从 SHOULD 升级为 MUST（Section 23.1.2）——关键安全修复
- Role assertion validation（Section 23.1.2）——堵住了 Open→Authenticated 升级时的角色注入漏洞
- Sender identity binding 的执行者明确为 session coordinator（Section 8.1 + 23.1）
- 端到端加密作为考虑项纳入（Section 23.4）

**仍然存在的安全关切：**

- **Open Profile 下的角色滥用仍无防护。** 这是设计意图（Open Profile 是给可信环境用的），但 spec 说"If no security profile is declared, implementations SHOULD default to the Open profile"（Section 23.2）。这意味着一个忘记声明 profile 的部署就自动落入无 role validation 的状态。**建议**：在 Section 23.2 中增加一个 MUST 级警告——如果 session 包含来自不同组织域的 principal（通过 principal_id 前缀或 authentication token 的 issuer 推断），coordinator MUST 拒绝使用 Open Profile。

- **Session coordinator 自身的认证未定义。** Authenticated Profile 要求 participant identity 验证，但谁来验证 coordinator 的身份？如果 coordinator 被中间人替换，所有 identity binding 和 audit logging 都失效。**建议**：在 Authenticated Profile 中增加 SHOULD——participants SHOULD verify the coordinator's identity via the same authentication mechanism (e.g., mTLS is mutual, OAuth token issuer is verified)。

- **watermark 伪造在 Authenticated Profile 下仍可能。** Section 23.3.4 说 watermark integrity 检查只在 Verified Profile 下。但在 Authenticated Profile 下，一个认证过的但恶意的参与者可以伪造 watermark 值（声称看到了更多消息），从而影响冲突判定。**建议**：在 Authenticated Profile 中增加 SHOULD——coordinator SHOULD cross-check participant watermark claims against its own message delivery records。

---

## 7. 三个最影响落地的问题

v0.1.3 解决了 v0.1.2 的三大阻塞问题（payload schema、scope overlap、watermark 基线），这些不再是阻塞项。对于当前版本，最影响落地的三个问题变成了：

### #1：缺少 MCP/A2A 集成指引（采用障碍）

这不是 spec 的技术缺陷，而是生态位问题。MPAC 的目标用户必然已经在用 MCP 和/或 A2A。如果他们不知道如何把 MCP 工具调用映射为 MPAC operation，或者如何在 A2A task delegation 中嵌入 MPAC intent，他们就不会采用 MPAC——不是因为 MPAC 不好，而是因为集成成本不可预估。一个 non-normative integration pattern appendix 可以解决这个问题。

### #2：Session negotiation 缺失（互操作隐患）

当前 spec 假设所有参与者提前知道 session 的 policy、security profile、watermark 策略、state_ref 格式。对于 out-of-band provisioned sessions（Section 9.2.3）这可能成立，但对于 implicit creation（Section 9.2.2）——第一个 HELLO 就创建 session——后来的参与者没有机会检查 session 配置是否与自己兼容。这会在真实部署中产生"加入后才发现不兼容"的问题。

**建议**：定义一个 `SESSION_INFO` 响应消息（coordinator 在收到 HELLO 后返回），包含 session 的 security profile、governance policy、watermark kind、state_ref format 等关键配置。参与者在收到 SESSION_INFO 后 SHOULD 验证兼容性，不兼容时 SHOULD 发送 GOODBYE 退出。

### #3：Conformance test suite 缺失（信任问题）

Spec 现在已经足够精确了——payload schema、scope overlap 规则、watermark 比较语义都有 MUST 级定义。但"精确的 spec"不等于"可验证的合规性"。如果没有 conformance test suite，一个实现声称"MPAC v0.1.3 compliant"没有客观验证方式。对于多方协议来说，这比单方协议更关键——因为你需要信任对方的实现也是合规的。

**建议**：将 conformance test suite 从 future work 提升为 v0.2 的 P0 目标。至少覆盖：message parsing（16 种类型的 required field 验证）、scope overlap 判定（file_set 的 path normalization + 集合交集）、watermark 比较（lamport_clock 基线 + lamport_value 降级）。

---

## 总体评价

MPAC v0.1.3 相比 v0.1.2 是一次实质性的提升。三个原先的阻塞问题（payload schema、scope overlap、watermark 基线）全部解决。Session coordinator 的引入消除了最大的架构模糊性。normative language 的精度显著提高。

当前版本已经达到了"一个工程团队可以开始实现，两个团队大概率能互通基本流程"的水平。剩余的问题（session negotiation、MCP/A2A 集成、conformance test）属于"v0.2 应该解决"的范畴而非"v0.1 不可发布"的范畴。

**成熟度评级**: 从 v0.1.2 的"设计理念文档"提升为 **"可实现的协议草案"**。距离"生产可互操作协议"还差 session negotiation 和 conformance test suite。

---

## 附录：v0.1.2 → v0.1.3 改动有效性评分

| 改动 | 有效性 | 说明 |
|------|--------|------|
| Payload schema tables (Section 13.1) | ★★★★★ | 互操作基础，最高优先级改动 |
| Scope overlap rules (Section 15.2.1) | ★★★★★ | 核心语义标准化 |
| Watermark baseline (Section 12.3) | ★★★★☆ | 解决了跨实现因果比较，但 lamport_value 作为 optional 字段意味着仍可能缺失 |
| Session coordinator (Section 8.1) | ★★★★☆ | 架构澄清，但 coordinator 自身的故障恢复未覆盖 |
| Intent-before-action MUST (Section 7.1) | ★★★★☆ | 分层合理，Governance Profile 下 MUST |
| state_ref MUST (Section 16.3) | ★★★★☆ | 关键修复，但 format negotiation 缺失 |
| Concurrent INTENT_CLAIM (Section 14.4.4) | ★★★★☆ | 干净利落的竞态解决 |
| Frozen scope fallback (Section 18.6.2.1) | ★★★★☆ | 解决死锁，且可禁用 |
| Frozen scope rejects INTENT_ANNOUNCE (Section 18.6.2) | ★★★☆☆ | 正确方向，但 partially overlapping scope 的处理有些复杂 |
| Resolution rollback semantics (Section 18.4) | ★★★☆☆ | 明确了预期，但 SHOULD 而非 MUST，实际执行率存疑 |
| Role assertion validation (Section 23.1.2) | ★★★★☆ | 关键安全修复 |
| Replay protection MUST (Section 23.1.2) | ★★★★★ | 安全硬性要求，不应有例外 |
