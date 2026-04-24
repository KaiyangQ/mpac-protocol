export class LamportClock {
    clock = 0;
    constructor(initialValue = 0) {
        this.clock = initialValue;
    }
    /**
     * Increment clock and return new value (for outgoing messages)
     */
    tick() {
        this.clock += 1;
        return this.clock;
    }
    /**
     * Update clock based on received message (max of local and received + 1)
     */
    update(receivedClock) {
        this.clock = Math.max(this.clock, receivedClock) + 1;
        return this.clock;
    }
    /**
     * Get current clock value
     */
    get value() {
        return this.clock;
    }
    /**
     * Create a watermark for sending
     */
    createWatermark() {
        const clock = this.tick();
        return {
            kind: "lamport_clock",
            value: clock,
        };
    }
    /**
     * Process received watermark
     */
    processWatermark(watermark) {
        const receivedValue = watermark.kind === "lamport_clock"
            ? watermark.value
            : (watermark.lamport_value ?? 0);
        this.update(receivedValue);
    }
}
//# sourceMappingURL=watermark.js.map