import { v4 as uuidv4 } from "uuid";
export function createEnvelope(messageType, sessionId, sender, payload, watermark, coordinatorEpoch) {
    return {
        protocol: "MPAC",
        version: "0.1.13",
        message_type: messageType,
        message_id: uuidv4(),
        session_id: sessionId,
        sender,
        ts: new Date().toISOString(),
        payload,
        watermark,
        coordinator_epoch: coordinatorEpoch,
    };
}
export function envelopeToJSON(envelope) {
    return JSON.stringify(envelope);
}
export function envelopeFromJSON(json) {
    const parsed = JSON.parse(json);
    // Basic validation
    if (!parsed.protocol ||
        !parsed.version ||
        !parsed.message_type ||
        !parsed.message_id ||
        !parsed.session_id ||
        !parsed.sender ||
        !parsed.ts ||
        parsed.payload === undefined) {
        throw new Error("Invalid message envelope structure");
    }
    return parsed;
}
//# sourceMappingURL=envelope.js.map