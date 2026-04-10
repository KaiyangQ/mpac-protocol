import { Watermark } from "./models.js";

export class LamportClock {
  private clock: number = 0;

  constructor(initialValue: number = 0) {
    this.clock = initialValue;
  }

  /**
   * Increment clock and return new value (for outgoing messages)
   */
  tick(): number {
    this.clock += 1;
    return this.clock;
  }

  /**
   * Update clock based on received message (max of local and received + 1)
   */
  update(receivedClock: number): number {
    this.clock = Math.max(this.clock, receivedClock) + 1;
    return this.clock;
  }

  /**
   * Get current clock value
   */
  get value(): number {
    return this.clock;
  }

  /**
   * Create a watermark for sending
   */
  createWatermark(): Watermark {
    const clock = this.tick();
    return {
      kind: "lamport_clock",
      value: clock,
    };
  }

  /**
   * Process received watermark
   */
  processWatermark(watermark: Watermark): void {
    const receivedValue = watermark.kind === "lamport_clock"
      ? (watermark.value as number)
      : (watermark.lamport_value ?? 0);
    this.update(receivedValue);
  }
}
