import { Watermark } from "./models.js";
export declare class LamportClock {
    private clock;
    constructor(initialValue?: number);
    /**
     * Increment clock and return new value (for outgoing messages)
     */
    tick(): number;
    /**
     * Update clock based on received message (max of local and received + 1)
     */
    update(receivedClock: number): number;
    /**
     * Get current clock value
     */
    get value(): number;
    /**
     * Create a watermark for sending
     */
    createWatermark(): Watermark;
    /**
     * Process received watermark
     */
    processWatermark(watermark: Watermark): void;
}
//# sourceMappingURL=watermark.d.ts.map