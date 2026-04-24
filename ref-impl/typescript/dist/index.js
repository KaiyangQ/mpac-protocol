// Re-export all models and enums
export * from "./models.js";
// Re-export envelope
export { createEnvelope, envelopeToJSON, envelopeFromJSON } from "./envelope.js";
// Re-export watermark
export { LamportClock } from "./watermark.js";
// Re-export scope utilities
export { scopeOverlap, scopeContains, isValidScope } from "./scope.js";
// Re-export state machines
export { IntentStateMachine, OperationStateMachine, ConflictStateMachine, } from "./state-machines.js";
// Re-export coordinator and participant
export { SessionCoordinator } from "./coordinator.js";
export { Participant } from "./participant.js";
//# sourceMappingURL=index.js.map