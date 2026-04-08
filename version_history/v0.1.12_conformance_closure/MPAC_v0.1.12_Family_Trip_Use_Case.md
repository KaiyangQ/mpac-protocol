# MPAC Use Case: Family Trip Planning with Three AI Agents

**Protocol version:** v0.1.12
**Date:** 2026-04-06
**Category:** Multi-principal planning and orchestration — consumer/family scenario

---

## 1. Scenario Overview

A family of three is planning a summer vacation trip:

| Family Member | Role | AI Agent | Preferences & Constraints |
|---------------|------|----------|---------------------------|
| Dad (Zhang Wei) | Budget controller, driver | `agent:dad-planner` | Controls budget (total ¥15,000); prefers nature/outdoor; must drive ≤ 5 hours/day; wants to bring camping gear |
| Mom (Li Na) | Food & accommodation lead | `agent:mom-planner` | Responsible for restaurant & hotel booking; wants cultural experiences; needs kid-friendly dining; allergic to seafood |
| Kid (Zhang Xiaoming, 12 years old) | Activity lead | `agent:kid-planner` | Wants theme parks & water activities; school break July 10–25; needs at least 1 day of "free play" time |

Each family member has their own AI agent running on their personal device. The three agents need to collaboratively produce a single agreed-upon 5-day itinerary.

### Why This Requires MPAC (Not A2A)

This scenario is fundamentally **multi-principal**: Dad, Mom, and Kid are three independent stakeholders with potentially conflicting goals. No single agent "orchestrates" the others — instead, each agent advocates for its principal's preferences. A2A assumes a single orchestrator with full authority; MPAC handles the negotiation between independent parties.

---

## 2. Session Setup

### 2.1 Session Configuration

```json
{
  "session_id": "family-trip-2026-summer",
  "protocol_version": "0.1.12",
  "execution_model": "pre_commit",
  "security_profile": "authenticated",
  "governance_profile": true,
  "session_policy": {
    "auto_close": true,
    "session_ttl_sec": 86400,
    "arbiter_designation": "human:dad"
  },
  "shared_state": {
    "kind": "task_set",
    "resources": [
      "itinerary://day-1",
      "itinerary://day-2",
      "itinerary://day-3",
      "itinerary://day-4",
      "itinerary://day-5",
      "budget://total",
      "budget://accommodation",
      "budget://food",
      "budget://transportation",
      "budget://activities"
    ]
  }
}
```

Key design decisions:

- **Pre-commit model**: No itinerary change takes effect until the coordinator authorizes it. This prevents one agent from unilaterally booking a hotel that blows the budget.
- **Governance Profile**: Required by pre-commit. All changes go through proposal → review → authorization → commit.
- **Arbiter**: Dad serves as the human arbiter (final tiebreaker) because he controls the budget. Mom could equally serve as arbiter — the protocol doesn't prescribe who.
- **Shared state as `task_set`**: The itinerary is modeled as a set of resources (5 days + 5 budget categories). Scope overlap is detected per-resource.

### 2.2 Coordinator

The coordinator runs as a lightweight service — it could be a family's shared home server, a cloud service, or even a phone acting as the hub. The coordinator:

- Validates all proposals against budget constraints
- Detects scope overlap (e.g., two agents both trying to plan Day 3)
- Enforces the pre-commit flow (no booking happens until authorized)
- Tracks the `state_ref` for each itinerary day (SHA-256 of the current plan content)

### 2.3 HELLO Handshake

All three agents join the session. The kid's agent is configured with a `contributor` role (can propose but not override), while both parents' agents have `owner` role.

```json
// Dad's agent joins
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "HELLO",
  "message_id": "msg-001",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:dad-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-dad-01"
  },
  "ts": "2026-07-01T20:00:00+08:00",
  "payload": {
    "display_name": "Dad's Travel Planner",
    "roles": ["owner"],
    "capabilities": ["intent.broadcast", "op.commit", "conflict.report", "conflict.resolve"],
    "implementation": {
      "name": "family-agent-v1",
      "version": "1.0.0"
    },
    "credential": {
      "type": "bearer_token",
      "value": "tok-dad-xxxxx"
    }
  }
}
```

```json
// Mom's agent joins
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "HELLO",
  "message_id": "msg-002",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:mom-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-mom-01"
  },
  "ts": "2026-07-01T20:00:05+08:00",
  "payload": {
    "display_name": "Mom's Travel Planner",
    "roles": ["owner"],
    "capabilities": ["intent.broadcast", "op.commit", "conflict.report", "conflict.resolve"],
    "credential": {
      "type": "bearer_token",
      "value": "tok-mom-xxxxx"
    }
  }
}
```

```json
// Kid's agent joins
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "HELLO",
  "message_id": "msg-003",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:kid-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-kid-01"
  },
  "ts": "2026-07-01T20:00:10+08:00",
  "payload": {
    "display_name": "Xiaoming's Fun Planner",
    "roles": ["contributor"],
    "capabilities": ["intent.broadcast", "op.commit", "conflict.report"],
    "credential": {
      "type": "bearer_token",
      "value": "tok-kid-xxxxx"
    }
  }
}
```

---

## 3. Intent Announcement Phase — Each Agent Declares Plans

After joining, each agent independently researches options and announces what it wants to plan. This is the "intent before action" principle — agents declare their goals *before* making any changes.

### 3.1 Dad's Agent: Transportation & Outdoor Activities

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-010",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:dad-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-dad-01"
  },
  "ts": "2026-07-01T20:05:00+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 4
  },
  "payload": {
    "intent_id": "intent-dad-route",
    "objective": "Plan driving route and outdoor activities: Destination Moganshan, 3.5hr drive from Shanghai, with hiking and camping on Days 1-2",
    "scope": {
      "kind": "task_set",
      "resources": [
        "itinerary://day-1",
        "itinerary://day-2",
        "budget://transportation",
        "budget://activities"
      ]
    },
    "assumptions": [
      "Total budget is ¥15,000",
      "Driving ≤ 5 hours per day",
      "Camping gear available (already owned)",
      "Destination: Moganshan area, Zhejiang"
    ],
    "priority": "high",
    "ttl_sec": 3600
  }
}
```

### 3.2 Mom's Agent: Accommodation & Cultural Experiences

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-011",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:mom-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-mom-01"
  },
  "ts": "2026-07-01T20:05:30+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 5
  },
  "payload": {
    "intent_id": "intent-mom-hotel",
    "objective": "Book kid-friendly hotel with cultural experience: Prefer boutique homestay near Moganshan bamboo forest, with local cooking class on Day 2",
    "scope": {
      "kind": "task_set",
      "resources": [
        "itinerary://day-1",
        "itinerary://day-2",
        "itinerary://day-3",
        "budget://accommodation",
        "budget://food"
      ]
    },
    "assumptions": [
      "Accommodation budget: ¥4,000-6,000 for 4 nights",
      "Must be kid-friendly (12 year old)",
      "No seafood in any meal plan (allergy)",
      "Prefer local cultural activities"
    ],
    "priority": "high",
    "ttl_sec": 3600
  }
}
```

### 3.3 Kid's Agent: Theme Park & Water Activities

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "INTENT_ANNOUNCE",
  "message_id": "msg-012",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:kid-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-kid-01"
  },
  "ts": "2026-07-01T20:06:00+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 6
  },
  "payload": {
    "intent_id": "intent-kid-fun",
    "objective": "Plan fun activities: Water park on Day 3, theme park (Hello Kitty Park Anji) on Day 4, free play time on Day 5",
    "scope": {
      "kind": "task_set",
      "resources": [
        "itinerary://day-3",
        "itinerary://day-4",
        "itinerary://day-5",
        "budget://activities"
      ]
    },
    "assumptions": [
      "At least one water activity",
      "Hello Kitty Park is 1hr from Moganshan",
      "Day 5 must have free/unstructured time",
      "Activity budget should be ≤ ¥3,000"
    ],
    "priority": "normal",
    "ttl_sec": 3600
  }
}
```

---

## 4. Conflict Detection — Scope Overlaps Identified

The coordinator detects two scope overlaps from the three intents:

### 4.1 Conflict 1: Day 1-2 Schedule (Dad vs Mom)

Dad wants camping + hiking on Days 1-2. Mom wants hotel + cooking class on Day 2. These are incompatible — you can't camp and stay at a hotel on the same night.

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-020",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "service:coordinator",
    "principal_type": "service",
    "sender_instance_id": "inst-coord-01"
  },
  "ts": "2026-07-01T20:06:10+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 7
  },
  "payload": {
    "conflict_id": "conf-day12",
    "related_intents": ["intent-dad-route", "intent-mom-hotel"],
    "related_ops": [],
    "category": "scope_overlap",
    "severity": "high",
    "basis": {
      "kind": "rule",
      "rule_id": "scope.overlap.task_set"
    },
    "based_on_watermark": {
      "kind": "lamport_clock",
      "lamport_value": 7
    },
    "description": "Dad's camping plan (Days 1-2) and Mom's hotel plan (Days 1-3) overlap on itinerary://day-1 and itinerary://day-2. Camping and hotel are mutually exclusive accommodation choices for the same nights.",
    "suggested_action": "merge"
  }
}
```

### 4.2 Conflict 2: Activity Budget (Dad vs Kid)

Both Dad and Kid's intents target `budget://activities`. Dad assumes outdoor activities are cheap (camping gear owned), but Kid's theme parks + water park could cost ¥2,000+.

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "CONFLICT_REPORT",
  "message_id": "msg-021",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "service:coordinator",
    "principal_type": "service",
    "sender_instance_id": "inst-coord-01"
  },
  "ts": "2026-07-01T20:06:15+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 8
  },
  "payload": {
    "conflict_id": "conf-budget-activity",
    "related_intents": ["intent-dad-route", "intent-kid-fun"],
    "related_ops": [],
    "category": "resource_contention",
    "severity": "medium",
    "basis": {
      "kind": "semantic_match",
      "match_score": 0.82,
      "match_reason": "Both intents allocate portions of budget://activities without coordinating total spend"
    },
    "based_on_watermark": {
      "kind": "lamport_clock",
      "lamport_value": 8
    },
    "description": "Dad's outdoor activities and Kid's theme parks both draw from the activity budget. Combined spend may exceed the ¥3,000 activity allocation.",
    "suggested_action": "merge"
  }
}
```

---

## 5. Conflict Acknowledgment — Agents Express Positions

Each agent acknowledges the conflicts and states its principal's position. This is where MPAC's multi-principal nature shines — each agent advocates for its own principal.

### 5.1 Dad's Agent on Conflict 1 (Camping vs Hotel)

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "CONFLICT_ACK",
  "message_id": "msg-030",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:dad-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-dad-01"
  },
  "ts": "2026-07-01T20:07:00+08:00",
  "payload": {
    "conflict_id": "conf-day12",
    "ack_type": "disputed",
    "position": "Propose compromise: Day 1 camp at Moganshan campsite (Dad's priority — kids love campfires), Day 2 check into Mom's boutique minsu. This gives the camping experience AND the hotel comfort. Cooking class can happen Day 2 afternoon after check-in. Budget impact: campsite ¥200/night saves ¥800 vs 2 nights hotel."
  }
}
```

### 5.2 Mom's Agent on Conflict 1

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "CONFLICT_ACK",
  "message_id": "msg-031",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:mom-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-mom-01"
  },
  "ts": "2026-07-01T20:07:30+08:00",
  "payload": {
    "conflict_id": "conf-day12",
    "ack_type": "disputed",
    "position": "Acceptable compromise, but conditions: (1) campsite must have proper bathrooms and running water — Xiaoming is only 12, (2) cooking class must be confirmed for Day 2 afternoon before agreeing, (3) no seafood at any campsite BBQ. If campsite doesn't meet hygiene standards, fallback to hotel for both nights."
  }
}
```

### 5.3 Kid's Agent on Conflict 2 (Budget)

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "CONFLICT_ACK",
  "message_id": "msg-032",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:kid-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-kid-01"
  },
  "ts": "2026-07-01T20:08:00+08:00",
  "payload": {
    "conflict_id": "conf-budget-activity",
    "ack_type": "disputed",
    "position": "Hello Kitty Park tickets are ¥280/person (¥840 family). Water park is ¥150/person (¥450 family). Total ¥1,290 for both parks. Dad's hiking is free. Combined activity budget: ¥1,490 — well under the ¥3,000 cap. Suggest: allocate ¥1,500 to kid activities, ¥500 to outdoor gear/fees, ¥1,000 reserve."
  }
}
```

---

## 6. Resolution — Human Arbiter Decides

After collecting all positions, Dad (the designated human arbiter) reviews and resolves both conflicts. In practice, Dad's AI agent surfaces the conflict summary to Dad's phone, Dad makes the call, and the agent sends the RESOLUTION.

### 6.1 Resolution of Conflict 1: The Compromise Plan

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "RESOLUTION",
  "message_id": "msg-040",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "human:dad",
    "principal_type": "human",
    "sender_instance_id": "inst-dad-human"
  },
  "ts": "2026-07-01T20:15:00+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 12
  },
  "payload": {
    "resolution_id": "res-day12",
    "conflict_id": "conf-day12",
    "decision": "merged",
    "outcome": {
      "accepted": [],
      "rejected": [],
      "merged": ["intent-dad-route", "intent-mom-hotel"]
    },
    "rationale": "Merge plan: Day 1 camp (with Mom's hygiene conditions — I'll verify the campsite has proper facilities), Day 2 move to minsu + afternoon cooking class. Mom's agent books the minsu, Dad's agent books the verified campsite. Both agents update their intents to reflect the split."
  }
}
```

### 6.2 Resolution of Conflict 2: Budget Allocation

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "RESOLUTION",
  "message_id": "msg-041",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "human:dad",
    "principal_type": "human",
    "sender_instance_id": "inst-dad-human"
  },
  "ts": "2026-07-01T20:16:00+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 13
  },
  "payload": {
    "resolution_id": "res-budget",
    "conflict_id": "conf-budget-activity",
    "decision": "merged",
    "outcome": {
      "accepted": [],
      "rejected": [],
      "merged": ["intent-dad-route", "intent-kid-fun"]
    },
    "rationale": "Kid's math checks out — ¥1,290 for both parks is reasonable. Approve budget split: ¥1,500 kid parks, ¥500 outdoor, ¥1,000 reserve. Kid's agent proceeds with park tickets, Dad's agent handles campsite fees."
  }
}
```

---

## 7. Intent Update & Operation Phase — Agents Refine and Commit

After resolution, agents update their intents to reflect the merged plan, then propose and commit specific operations.

### 7.1 Dad's Agent Updates Intent (Post-Merge)

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "INTENT_UPDATE",
  "message_id": "msg-050",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:dad-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-dad-01"
  },
  "ts": "2026-07-01T20:20:00+08:00",
  "payload": {
    "intent_id": "intent-dad-route",
    "objective": "[Updated] Day 1: Drive Shanghai→Moganshan (3.5hr), verified campsite with facilities. Day 2 morning: Hike bamboo trail, then check out campsite. Day 5: Drive Anji→Shanghai (3hr).",
    "scope": {
      "kind": "task_set",
      "resources": [
        "itinerary://day-1",
        "itinerary://day-5",
        "budget://transportation"
      ]
    }
  }
}
```

### 7.2 Dad's Agent Proposes Day 1 Itinerary (Pre-Commit Flow)

In pre-commit mode, the agent first proposes, then waits for coordinator authorization before committing.

```json
// Step 1: OP_PROPOSE
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "OP_PROPOSE",
  "message_id": "msg-060",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:dad-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-dad-01"
  },
  "ts": "2026-07-01T20:25:00+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 16
  },
  "payload": {
    "op_id": "op-day1-plan",
    "intent_id": "intent-dad-route",
    "target": "itinerary://day-1",
    "op_kind": "create",
    "summary": "Day 1 complete itinerary: 8:00 depart Shanghai, 11:30 arrive Moganshan, 12:00 lunch at local restaurant (no seafood — confirmed), 14:00 check in campsite (Moganshan Starlight Camp, verified: flush toilets, hot showers, BBQ area), 15:00 bamboo forest short hike (2km, kid-friendly), 18:00 campfire BBQ dinner, 20:00 stargazing",
    "state_ref_before": "sha256:0000000000000000",
    "state_ref_after": "sha256:a1b2c3d4e5f6..."
  }
}
```

```json
// Step 2: Coordinator authorizes via COORDINATOR_STATUS
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "COORDINATOR_STATUS",
  "message_id": "msg-061",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "service:coordinator",
    "principal_type": "service",
    "sender_instance_id": "inst-coord-01"
  },
  "ts": "2026-07-01T20:25:05+08:00",
  "payload": {
    "coordinator_id": "service:coordinator",
    "coordinator_epoch": 1,
    "session_health": "healthy",
    "event": "authorization",
    "authorized_op_id": "op-day1-plan",
    "authorized_by": "service:coordinator"
  }
}
```

```json
// Step 3: Agent confirms execution via OP_COMMIT
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "OP_COMMIT",
  "message_id": "msg-062",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:dad-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-dad-01"
  },
  "ts": "2026-07-01T20:25:30+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 18
  },
  "payload": {
    "op_id": "op-day1-plan",
    "intent_id": "intent-dad-route",
    "target": "itinerary://day-1",
    "op_kind": "create",
    "state_ref_before": "sha256:0000000000000000",
    "state_ref_after": "sha256:a1b2c3d4e5f6...",
    "summary": "Day 1 itinerary committed: Shanghai → Moganshan drive, campsite check-in, hiking, campfire dinner"
  }
}
```

### 7.3 Mom's Agent Commits Day 2 (Hotel + Cooking Class)

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "OP_COMMIT",
  "message_id": "msg-070",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:mom-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-mom-01"
  },
  "ts": "2026-07-01T20:30:00+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 20
  },
  "payload": {
    "op_id": "op-day2-plan",
    "intent_id": "intent-mom-hotel",
    "target": "itinerary://day-2",
    "op_kind": "create",
    "state_ref_before": "sha256:0000000000000000",
    "state_ref_after": "sha256:b2c3d4e5f6a1...",
    "summary": "Day 2: 8:00 campsite breakfast, 9:00 bamboo trail hike (Dad leads), 11:30 check out camp → drive to Moganshan Bamboo Villa (homestay), 12:30 lunch at homestay (local vegetable dishes, NO seafood), 14:30 local bamboo weaving class + cooking class (learn to make Moganshan smoked tofu), 18:00 farm-to-table dinner at homestay"
  }
}
```

### 7.4 Kid's Agent Uses OP_BATCH_COMMIT for Days 3-5

The kid's agent commits all three remaining days as an atomic batch — either all succeed or none. This uses `all_or_nothing` semantics because the park schedule depends on the driving route.

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "OP_BATCH_COMMIT",
  "message_id": "msg-080",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:kid-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-kid-01"
  },
  "ts": "2026-07-01T20:35:00+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 22
  },
  "payload": {
    "batch_id": "batch-kid-days345",
    "intent_id": "intent-kid-fun",
    "atomicity": "all_or_nothing",
    "entries": [
      {
        "op_id": "op-day3-waterpark",
        "target": "itinerary://day-3",
        "op_kind": "create",
        "state_ref_before": "sha256:0000000000000000",
        "state_ref_after": "sha256:c3d4e5f6a1b2...",
        "summary": "Day 3: 9:00 drive Moganshan→Anji water park (40min), 10:00-16:00 Tianhuangping Water Park (wave pool, lazy river, family slides — all age-appropriate), 17:00 check in Anji hotel, 18:30 dinner (Mom picks restaurant, no seafood)"
      },
      {
        "op_id": "op-day4-themepark",
        "target": "itinerary://day-4",
        "op_kind": "create",
        "state_ref_before": "sha256:0000000000000000",
        "state_ref_after": "sha256:d4e5f6a1b2c3...",
        "summary": "Day 4: 8:30 drive Anji→Hello Kitty Park (30min), 9:30-17:00 Hello Kitty Park (rides, shows, character meet & greet), 17:30 souvenir shopping, 18:30 dinner at park restaurant area"
      },
      {
        "op_id": "op-day5-free",
        "target": "itinerary://day-5",
        "op_kind": "create",
        "state_ref_before": "sha256:0000000000000000",
        "state_ref_after": "sha256:e5f6a1b2c3d4...",
        "summary": "Day 5: FREE DAY! 9:00 sleep in, 10:00 Anji bamboo museum (if everyone wants, optional), 12:00 lunch, 13:00 Dad drives home Anji→Shanghai (3hr), 16:00 arrive home. Xiaoming gets to pick music for the drive!"
      }
    ]
  }
}
```

---

## 8. Budget Reconciliation — Cross-Agent Coordination

After all days are committed, Dad's agent performs a final budget check as an `OP_SUPERSEDE` on the budget resource — superseding the initial empty budget with the reconciled totals.

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "OP_COMMIT",
  "message_id": "msg-090",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "agent:dad-planner",
    "principal_type": "agent",
    "sender_instance_id": "inst-dad-01"
  },
  "ts": "2026-07-01T20:45:00+08:00",
  "watermark": {
    "kind": "lamport_clock",
    "lamport_value": 28
  },
  "payload": {
    "op_id": "op-budget-final",
    "intent_id": "intent-dad-route",
    "target": "budget://total",
    "op_kind": "create",
    "state_ref_before": "sha256:0000000000000000",
    "state_ref_after": "sha256:f6a1b2c3d4e5...",
    "summary": "Final budget reconciliation: Transportation (gas + tolls): ¥1,200 | Campsite (1 night): ¥300 | Minsu (1 night): ¥1,200 | Anji hotel (2 nights): ¥1,600 | Food (5 days): ¥3,000 | Water park (3 tickets): ¥450 | Hello Kitty Park (3 tickets): ¥840 | Misc/reserve: ¥1,000 | TOTAL: ¥9,590 / ¥15,000 budget (¥5,410 remaining)"
  }
}
```

---

## 9. Session Close — Final Itinerary Confirmed

Once all operations are committed and all conflicts resolved, the coordinator auto-closes the session.

```json
{
  "protocol": "MPAC",
  "version": "0.1.12",
  "message_type": "SESSION_CLOSE",
  "message_id": "msg-100",
  "session_id": "family-trip-2026-summer",
  "sender": {
    "principal_id": "service:coordinator",
    "principal_type": "service",
    "sender_instance_id": "inst-coord-01"
  },
  "ts": "2026-07-01T20:50:00+08:00",
  "payload": {
    "reason": "all_settled",
    "final_lamport_clock": 30,
    "active_intents_disposition": "completed",
    "summary": {
      "total_intents": 3,
      "completed_intents": 3,
      "expired_intents": 0,
      "withdrawn_intents": 0,
      "total_operations": 7,
      "committed_operations": 7,
      "rejected_operations": 0,
      "abandoned_operations": 0,
      "total_conflicts": 2,
      "resolved_conflicts": 2,
      "total_participants": 4,
      "duration_sec": 3000
    }
  }
}
```

---

## 10. Complete Itinerary Summary (Post-Session Output)

| Day | Morning | Afternoon | Evening | Accommodation | Agent Responsible |
|-----|---------|-----------|---------|---------------|-------------------|
| Day 1 | Drive Shanghai → Moganshan (3.5hr) | Campsite check-in, bamboo forest hike (2km) | Campfire BBQ (no seafood) + stargazing | Moganshan Starlight Camp | Dad's agent |
| Day 2 | Campsite breakfast → bamboo trail hike | Check in Bamboo Villa (homestay), bamboo weaving + cooking class | Farm-to-table dinner at homestay | Moganshan Bamboo Villa | Mom's agent |
| Day 3 | Drive to Anji water park (40min) | Tianhuangping Water Park (wave pool, slides) | Dinner at Anji (Mom-selected, no seafood) | Anji hotel | Kid's agent |
| Day 4 | Drive to Hello Kitty Park (30min) | Hello Kitty Park full day (rides, shows) | Dinner + souvenir shopping | Anji hotel | Kid's agent |
| Day 5 | Sleep in! Optional: Anji bamboo museum | Drive Anji → Shanghai (3hr) | Arrive home ~16:00 | — | Dad's agent + Kid's agent |

**Budget: ¥9,590 / ¥15,000 (63.9% utilized, ¥5,410 in reserve)**

---

## 11. Protocol Features Demonstrated

| MPAC Feature | How It Was Used |
|--------------|----------------|
| **Multi-principal coordination** | Three independent principals (Dad, Mom, Kid) with different goals and constraints |
| **Intent before action** | Each agent declared plans before making any bookings |
| **Scope overlap detection** | Coordinator detected Day 1-2 conflict and budget conflict automatically |
| **Conflict as first-class object** | Two `CONFLICT_REPORT` messages with category, severity, and basis |
| **Position-based resolution** | Each agent expressed its principal's position via `CONFLICT_ACK` |
| **Human arbiter** | Dad made final decisions on both conflicts as designated arbiter |
| **Merged resolution** | Both conflicts were resolved via merge (not accept/reject), preserving all principals' core needs |
| **Pre-commit execution model** | No booking happened until coordinator authorized the operation |
| **OP_BATCH_COMMIT** | Kid's agent committed Days 3-5 atomically — the park schedule depends on the route |
| **Causal context (watermarks)** | Every commit carried a Lamport clock watermark ensuring causal ordering |
| **State references** | SHA-256 refs on each itinerary day for optimistic concurrency control |
| **Session lifecycle** | Full lifecycle: HELLO → INTENT → CONFLICT → RESOLUTION → COMMIT → SESSION_CLOSE |
| **Role-based governance** | Kid = `contributor` (propose only), Parents = `owner` (propose + resolve) |
| **Assumption declaration** | Each intent explicitly stated assumptions (budget, allergies, time constraints) |

---

## 12. What-If Scenarios — Edge Cases This Protocol Handles

### 12.1 What if Mom's Agent Finds the Campsite Unsatisfactory?

Mom's agent can submit a new `CONFLICT_REPORT` with `category: "assumption_violation"` citing that the campsite doesn't meet the hygiene conditions from the merged resolution. This triggers a new resolution cycle. Dad (arbiter) can then approve a fallback: replace Day 1 camping with an extra hotel night at the minsu.

### 12.2 What if Kid Wants to Change Day 4 After Commit?

Kid's agent sends `INTENT_ANNOUNCE` for a new intent targeting `itinerary://day-4` with a different plan. Since Day 4 is already `COMMITTED`, the new intent would use `OP_SUPERSEDE` to replace the existing plan. Because it's pre-commit, the coordinator must authorize the supersession — and since Kid is only a `contributor`, the supersession requires an `owner` to approve.

### 12.3 What if Dad's Phone Loses Connection Mid-Resolution?

The coordinator detects Dad's agent's absence after `2 × heartbeat_interval_sec`. Dad's intents transition to `SUSPENDED`. Mom or Kid's agents can file an `INTENT_CLAIM` to take over Dad's transportation planning (e.g., Mom's agent claims the driving route intent). When Dad reconnects, his agent sees the `INTENT_CLAIM_STATUS` and can accept or dispute the claim.

### 12.4 What if the Budget Gets Exceeded?

If the budget reconciliation shows an overage, Dad's agent submits a `CONFLICT_REPORT` with `category: "constraint_violation"`, referencing the budget operations that caused the breach. The resolution cycle restarts — perhaps Kid's agent reduces to just one park, or Mom finds a cheaper minsu.

### 12.5 What if a Second Family Wants to Join?

MPAC supports additional principals joining mid-session via HELLO. A second family's agents could join the same session, introducing new constraints (e.g., "we need wheelchair-accessible venues"). Their intents would naturally conflict with existing committed plans, triggering new conflict-resolution cycles. This is the power of multi-principal coordination — it scales to N principals without architectural changes.

---

## 13. Implementation Notes

### 13.1 Agent LLM Integration

Each agent uses its principal's preferences as a system prompt:

```
You are Dad's travel planning agent. Your principal's constraints:
- Total budget: ¥15,000
- Prefers nature and outdoor activities
- Driving ≤ 5 hours per day
- Has camping gear

When announcing intents, always include budget impact estimates.
When responding to conflicts, prioritize budget efficiency but respect family harmony.
When the kid's requests are reasonable and within budget, support them.
```

The agent uses the LLM to:
1. **Decide intents**: "Given these preferences and the current session state, what should I plan?"
2. **Express positions on conflicts**: "Here's why my principal's plan makes sense, and here's where I can compromise."
3. **Generate operations**: "Here's a detailed itinerary for Day 1 based on the resolved plan."

### 13.2 Transport Binding

For a family scenario, a WebSocket-based coordinator on a home device or cloud server works well. Each family member's phone runs an agent that connects via WebSocket. The message flow is the same as the distributed validation (v0.1.12) — just with a different domain.

### 13.3 Optimistic Concurrency for Itinerary Changes

If two agents try to modify the same day simultaneously (e.g., Mom adds a restaurant to Day 3 while Kid changes the water park times), the `state_ref_before` validation catches the conflict — the second commit gets `STALE_STATE_REF` and must rebase on the first commit's version, exactly like the code-editing scenario in the distributed validation.
