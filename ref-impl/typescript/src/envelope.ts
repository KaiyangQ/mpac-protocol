import { v4 as uuidv4 } from "uuid";
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

export function createEnvelope(
  messageType: MessageType,
  sessionId: string,
  sender: Sender,
  payload: unknown,
  watermark?: Watermark,
  coordinatorEpoch?: number
): MessageEnvelope {
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

export function envelopeToJSON(envelope: MessageEnvelope): string {
  return JSON.stringify(envelope);
}

export function envelopeFromJSON(json: string): MessageEnvelope {
  const parsed = JSON.parse(json);
  // Basic validation
  if (
    !parsed.protocol ||
    !parsed.version ||
    !parsed.message_type ||
    !parsed.message_id ||
    !parsed.session_id ||
    !parsed.sender ||
    !parsed.ts ||
    parsed.payload === undefined
  ) {
    throw new Error("Invalid message envelope structure");
  }
  return parsed as MessageEnvelope;
}
