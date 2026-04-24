export * from "./models.js";
export { MessageEnvelope, createEnvelope, envelopeToJSON, envelopeFromJSON } from "./envelope.js";
export { LamportClock } from "./watermark.js";
export { scopeOverlap, scopeContains, isValidScope } from "./scope.js";
export { IntentStateMachine, OperationStateMachine, ConflictStateMachine, } from "./state-machines.js";
export { SessionCoordinator } from "./coordinator.js";
export { Participant } from "./participant.js";
//# sourceMappingURL=index.d.ts.map