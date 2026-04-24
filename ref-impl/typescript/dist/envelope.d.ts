import { MessageType, Sender, Watermark } from "./models.js";
export interface MessageEnvelope {
    protocol: string;
    version: string;
    message_type: MessageType;
    message_id: string;
    session_id: string;
    sender: Sender;
    ts: string;
    payload: unknown;
    watermark?: Watermark;
    coordinator_epoch?: number;
}
export declare function createEnvelope(messageType: MessageType, sessionId: string, sender: Sender, payload: unknown, watermark?: Watermark, coordinatorEpoch?: number): MessageEnvelope;
export declare function envelopeToJSON(envelope: MessageEnvelope): string;
export declare function envelopeFromJSON(json: string): MessageEnvelope;
//# sourceMappingURL=envelope.d.ts.map