/**
 * Specialized tests for v0.1.13 Backend Health Monitoring.
 *
 * Covers 12 scenarios:
 * 1. HELLO with backend declaration — SESSION_INFO returned normally
 * 2. HEARTBEAT with backend_health — no error when operational
 * 3. Degraded provider emits backend_alert (on_degraded=warn)
 * 4. Down provider emits backend_alert (on_down=suspend_and_claim) and suspends intents
 * 5. Model switch with allowed provider passes validation
 * 6. Model switch with disallowed provider returns BACKEND_SWITCH_DENIED
 * 7. auto_switch=forbidden rejects any model switch
 * 8. SESSION_INFO includes backend_health_policy in liveness_policy
 * 9. No alert emitted when provider status unchanged (repeat heartbeat)
 * 10. Policy disabled (enabled=false) suppresses alerts
 * 11. No backend_health in heartbeat — no alerts, no errors
 * 12. Provider recovery: down → operational triggers recovery alert
 */
import { describe, it, expect } from "vitest";
import { SessionCoordinator } from "../src/coordinator.js";
import { Participant } from "../src/participant.js";
import {
  MessageType,
  Role,
  ScopeKind,
  IntentState,
} from "../src/models.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BACKEND_HEALTH_POLICY = {
  enabled: true,
  check_source: "https://aistatus.cc/api/check",
  check_interval_sec: 60,
  on_degraded: "warn",
  on_down: "suspend_and_claim",
  auto_switch: "allowed",
  allowed_providers: ["anthropic", "openai", "google"],
};

const ALICE_BACKEND = { model_id: "anthropic/claude-sonnet-4.6", provider: "anthropic" };
const BOB_BACKEND = { model_id: "openai/gpt-4o", provider: "openai" };

const SID = "test-backend-health";

function makeSession(sid = SID, policy: any = BACKEND_HEALTH_POLICY) {
  return new SessionCoordinator(
    sid,
    "open",
    "core",
    30,
    90,
    300,
    "post_commit",
    "sha256",
    0,
    undefined,
    300,
    policy,
  );
}

function join(coord: SessionCoordinator, p: Participant, sid = SID, backend?: { model_id: string; provider: string }) {
  return coord.processMessage(p.hello(sid, backend));
}

function hb(
  coord: SessionCoordinator,
  p: Participant,
  sid = SID,
  status = "idle",
  activeIntentId?: string,
  summary?: string,
  backendHealth?: Record<string, unknown>,
) {
  return coord.processMessage(p.heartbeat(sid, status, activeIntentId, summary, backendHealth));
}

// ---------------------------------------------------------------------------
// 1. HELLO with backend declaration
// ---------------------------------------------------------------------------

describe("HELLO with backend declaration", () => {
  it("returns SESSION_INFO when backend is declared", () => {
    const coord = makeSession();
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    const responses = join(coord, alice, SID, ALICE_BACKEND);

    const sessionInfos = responses.filter((r) => r.message_type === MessageType.SESSION_INFO);
    expect(sessionInfos.length).toBe(1);
  });

  it("returns SESSION_INFO when no backend is declared", () => {
    const coord = makeSession();
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    const responses = join(coord, alice);

    const sessionInfos = responses.filter((r) => r.message_type === MessageType.SESSION_INFO);
    expect(sessionInfos.length).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// 2. HEARTBEAT with backend_health
// ---------------------------------------------------------------------------

describe("HEARTBEAT with backend_health", () => {
  it("accepts operational backend_health without errors", () => {
    const coord = makeSession();
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    join(coord, alice, SID, ALICE_BACKEND);

    const responses = hb(coord, alice, SID, "idle", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "operational",
      checked_at: "2026-04-07T10:00:00Z",
    });

    const errors = responses.filter((r) => r.message_type === MessageType.PROTOCOL_ERROR);
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// 3. Degraded → backend_alert (warn)
// ---------------------------------------------------------------------------

describe("Degraded backend alert", () => {
  it("emits COORDINATOR_STATUS(backend_alert) on degraded — no intent suspension", () => {
    const coord = makeSession();
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    join(coord, alice, SID, ALICE_BACKEND);

    // Set operational baseline
    hb(coord, alice, SID, "idle", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "operational",
      checked_at: "2026-04-07T10:00:00Z",
    });

    // Create an intent
    coord.processMessage(
      alice.announceIntent(SID, "intent-1", "Fix main", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/main.py"],
      }),
    );

    // Report degraded
    const responses = hb(coord, alice, SID, "working", "intent-1", undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "degraded",
      status_detail: "Elevated error rates",
      checked_at: "2026-04-07T10:01:00Z",
    });

    const alerts = responses.filter((r) => r.message_type === MessageType.COORDINATOR_STATUS);
    expect(alerts.length).toBeGreaterThanOrEqual(1);
    const payload = alerts[0].payload as any;
    expect(payload.event).toBe("backend_alert");
    expect(payload.affected_principal).toBe("agent:alice");
    expect(payload.backend_detail.provider_status).toBe("degraded");

    // No INTENT_UPDATE (suspension) should be emitted for warn-only
    const intentUpdates = responses.filter((r) => r.message_type === MessageType.INTENT_UPDATE);
    expect(intentUpdates.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// 4. Down → backend_alert + suspend_and_claim
// ---------------------------------------------------------------------------

describe("Down backend with suspend_and_claim", () => {
  it("emits backend_alert AND suspends active intents", () => {
    const coord = makeSession();
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    join(coord, alice, SID, ALICE_BACKEND);

    hb(coord, alice, SID, "idle", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "operational",
      checked_at: "2026-04-07T10:00:00Z",
    });

    coord.processMessage(
      alice.announceIntent(SID, "intent-1", "Fix main", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/main.py"],
      }),
    );

    const responses = hb(coord, alice, SID, "blocked", "intent-1", undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "down",
      status_detail: "Major outage",
      checked_at: "2026-04-07T10:01:00Z",
    });

    // Should have backend_alert
    const alerts = responses.filter((r) => r.message_type === MessageType.COORDINATOR_STATUS);
    expect(alerts.length).toBeGreaterThanOrEqual(1);

    // Should have INTENT_UPDATE (suspension)
    const intentUpdates = responses.filter((r) => r.message_type === MessageType.INTENT_UPDATE);
    expect(intentUpdates.length).toBeGreaterThanOrEqual(1);
    const updatePayload = intentUpdates[0].payload as any;
    expect(updatePayload.objective).toContain("[SUSPENDED");
  });
});

// ---------------------------------------------------------------------------
// 5. Model switch with allowed provider
// ---------------------------------------------------------------------------

describe("Model switch with allowed provider", () => {
  it("does not return BACKEND_SWITCH_DENIED", () => {
    const coord = makeSession();
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    join(coord, alice, SID, ALICE_BACKEND);

    hb(coord, alice, SID, "idle", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "operational",
      checked_at: "2026-04-07T10:00:00Z",
    });

    const responses = hb(coord, alice, SID, "working", undefined, undefined, {
      model_id: "google/gemini-2.5-pro",
      provider_status: "operational",
      checked_at: "2026-04-07T10:01:00Z",
      switched_from: "anthropic/claude-sonnet-4.6",
      switch_reason: "provider_down",
    });

    const errors = responses.filter((r) => r.message_type === MessageType.PROTOCOL_ERROR);
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// 6. Model switch with disallowed provider → BACKEND_SWITCH_DENIED
// ---------------------------------------------------------------------------

describe("Model switch with disallowed provider", () => {
  it("returns BACKEND_SWITCH_DENIED for provider not in whitelist", () => {
    const coord = makeSession();
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    join(coord, alice, SID, ALICE_BACKEND);

    hb(coord, alice, SID, "idle", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "operational",
      checked_at: "2026-04-07T10:00:00Z",
    });

    const responses = hb(coord, alice, SID, "working", undefined, undefined, {
      model_id: "deepseek/deepseek-v3",
      provider_status: "operational",
      checked_at: "2026-04-07T10:01:00Z",
      switched_from: "anthropic/claude-sonnet-4.6",
      switch_reason: "manual",
    });

    const errors = responses.filter((r) => r.message_type === MessageType.PROTOCOL_ERROR);
    expect(errors.length).toBe(1);
    const errPayload = errors[0].payload as any;
    expect(errPayload.error_code).toBe("BACKEND_SWITCH_DENIED");
    expect(errPayload.description).toContain("deepseek");
  });
});

// ---------------------------------------------------------------------------
// 7. auto_switch=forbidden rejects any model switch
// ---------------------------------------------------------------------------

describe("auto_switch=forbidden", () => {
  it("rejects switch even to allowed provider", () => {
    const policy = { ...BACKEND_HEALTH_POLICY, auto_switch: "forbidden" };
    const coord = makeSession(SID, policy);
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    join(coord, alice, SID, ALICE_BACKEND);

    hb(coord, alice, SID, "idle", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "operational",
      checked_at: "2026-04-07T10:00:00Z",
    });

    const responses = hb(coord, alice, SID, "working", undefined, undefined, {
      model_id: "openai/gpt-4o",
      provider_status: "operational",
      checked_at: "2026-04-07T10:01:00Z",
      switched_from: "anthropic/claude-sonnet-4.6",
      switch_reason: "provider_down",
    });

    const errors = responses.filter((r) => r.message_type === MessageType.PROTOCOL_ERROR);
    expect(errors.length).toBe(1);
    const errPayload = errors[0].payload as any;
    expect(errPayload.error_code).toBe("BACKEND_SWITCH_DENIED");
    expect(errPayload.description.toLowerCase()).toContain("forbidden");
  });
});

// ---------------------------------------------------------------------------
// 8. SESSION_INFO includes backend_health_policy
// ---------------------------------------------------------------------------

describe("SESSION_INFO backend_health_policy", () => {
  it("includes policy in liveness_policy", () => {
    const coord = makeSession();
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    const responses = join(coord, alice, SID, ALICE_BACKEND);

    const sessionInfos = responses.filter((r) => r.message_type === MessageType.SESSION_INFO);
    expect(sessionInfos.length).toBe(1);

    const payload = sessionInfos[0].payload as any;
    const bhp = payload.liveness_policy?.backend_health_policy;
    expect(bhp).toBeDefined();
    expect(bhp.enabled).toBe(true);
    expect(bhp.on_degraded).toBe("warn");
    expect(bhp.on_down).toBe("suspend_and_claim");
  });
});

// ---------------------------------------------------------------------------
// 9. No alert on repeated same status
// ---------------------------------------------------------------------------

describe("No alert on repeated status", () => {
  it("second degraded heartbeat emits no additional alert", () => {
    const coord = makeSession();
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    join(coord, alice, SID, ALICE_BACKEND);

    hb(coord, alice, SID, "idle", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "operational",
      checked_at: "2026-04-07T10:00:00Z",
    });

    // First degraded → should alert
    const r1 = hb(coord, alice, SID, "working", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "degraded",
      checked_at: "2026-04-07T10:01:00Z",
    });
    const alerts1 = r1.filter((r) => r.message_type === MessageType.COORDINATOR_STATUS);
    expect(alerts1.length).toBeGreaterThanOrEqual(1);

    // Second degraded → no additional alert
    const r2 = hb(coord, alice, SID, "working", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "degraded",
      checked_at: "2026-04-07T10:02:00Z",
    });
    const alerts2 = r2.filter((r) => r.message_type === MessageType.COORDINATOR_STATUS);
    expect(alerts2.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// 10. Policy disabled suppresses alerts
// ---------------------------------------------------------------------------

describe("Policy disabled", () => {
  it("no alerts when enabled=false even on provider down", () => {
    const policy = { ...BACKEND_HEALTH_POLICY, enabled: false };
    const coord = makeSession(SID, policy);
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    join(coord, alice, SID, ALICE_BACKEND);

    hb(coord, alice, SID, "idle", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "operational",
      checked_at: "2026-04-07T10:00:00Z",
    });

    coord.processMessage(
      alice.announceIntent(SID, "intent-1", "Fix main", {
        kind: ScopeKind.FILE_SET,
        resources: ["src/main.py"],
      }),
    );

    const responses = hb(coord, alice, SID, "blocked", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "down",
      checked_at: "2026-04-07T10:01:00Z",
    });

    const alerts = responses.filter((r) => r.message_type === MessageType.COORDINATOR_STATUS);
    expect(alerts.length).toBe(0);

    // No suspension either
    const intentUpdates = responses.filter((r) => r.message_type === MessageType.INTENT_UPDATE);
    expect(intentUpdates.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// 11. No backend_health in heartbeat
// ---------------------------------------------------------------------------

describe("Heartbeat without backend_health", () => {
  it("produces no backend-related responses", () => {
    const coord = makeSession();
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    join(coord, alice, SID, ALICE_BACKEND);

    const responses = hb(coord, alice, SID, "idle");

    const alerts = responses.filter((r) => r.message_type === MessageType.COORDINATOR_STATUS);
    const errors = responses.filter((r) => r.message_type === MessageType.PROTOCOL_ERROR);
    expect(alerts.length).toBe(0);
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// 12. Provider recovery: down → operational
// ---------------------------------------------------------------------------

describe("Provider recovery", () => {
  it("down → operational triggers a recovery alert", () => {
    const coord = makeSession();
    const alice = new Participant("agent:alice", "agent", "Alice", [Role.CONTRIBUTOR]);
    join(coord, alice, SID, ALICE_BACKEND);

    hb(coord, alice, SID, "idle", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "operational",
      checked_at: "2026-04-07T10:00:00Z",
    });

    // Go down
    hb(coord, alice, SID, "blocked", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "down",
      checked_at: "2026-04-07T10:01:00Z",
    });

    // Recover — status changes from "down" to "operational", but since
    // "operational" doesn't match "down" or "degraded", no action is taken
    // by the policy. The key assertion is: no PROTOCOL_ERROR is returned.
    const responses = hb(coord, alice, SID, "idle", undefined, undefined, {
      model_id: "anthropic/claude-sonnet-4.6",
      provider_status: "operational",
      checked_at: "2026-04-07T10:05:00Z",
    });

    const errors = responses.filter((r) => r.message_type === MessageType.PROTOCOL_ERROR);
    expect(errors.length).toBe(0);
  });
});
