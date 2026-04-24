import { ConflictState, IntentState, OperationState } from "./models.js";
function normalizeIntentEvent(event) {
    const aliases = {
        activate: IntentState.ACTIVE,
        resume: IntentState.ACTIVE,
        active: IntentState.ACTIVE,
        expire: IntentState.EXPIRED,
        expired: IntentState.EXPIRED,
        withdraw: IntentState.WITHDRAWN,
        withdrawn: IntentState.WITHDRAWN,
        supersede: IntentState.SUPERSEDED,
        superseded: IntentState.SUPERSEDED,
        suspend: IntentState.SUSPENDED,
        suspended: IntentState.SUSPENDED,
        transfer: IntentState.TRANSFERRED,
        transferred: IntentState.TRANSFERRED,
    };
    return aliases[event.toLowerCase()] ?? (IntentState[event] ?? event);
}
function normalizeOperationEvent(event) {
    const aliases = {
        commit: OperationState.COMMITTED,
        committed: OperationState.COMMITTED,
        reject: OperationState.REJECTED,
        rejected: OperationState.REJECTED,
        abandon: OperationState.ABANDONED,
        abandoned: OperationState.ABANDONED,
        freeze: OperationState.FROZEN,
        frozen: OperationState.FROZEN,
        unfreeze: OperationState.PROPOSED,
        propose: OperationState.PROPOSED,
        proposed: OperationState.PROPOSED,
        supersede: OperationState.SUPERSEDED,
        superseded: OperationState.SUPERSEDED,
    };
    return aliases[event.toLowerCase()] ?? (OperationState[event] ?? event);
}
function normalizeConflictEvent(event) {
    const aliases = {
        ack: ConflictState.ACKED,
        acked: ConflictState.ACKED,
        escalate: ConflictState.ESCALATED,
        escalated: ConflictState.ESCALATED,
        dismiss: ConflictState.DISMISSED,
        dismissed: ConflictState.DISMISSED,
        resolve: ConflictState.RESOLVED,
        resolved: ConflictState.RESOLVED,
        close: ConflictState.CLOSED,
        closed: ConflictState.CLOSED,
    };
    return aliases[event.toLowerCase()] ?? (ConflictState[event] ?? event);
}
export class IntentStateMachine {
    state;
    constructor(initialState = IntentState.ANNOUNCED) {
        this.state = initialState;
    }
    get currentState() {
        return this.state;
    }
    transition(event) {
        const nextState = normalizeIntentEvent(event);
        const validTransitions = {
            [IntentState.ANNOUNCED]: [IntentState.ACTIVE, IntentState.WITHDRAWN],
            [IntentState.ACTIVE]: [
                IntentState.EXPIRED,
                IntentState.WITHDRAWN,
                IntentState.SUPERSEDED,
                IntentState.SUSPENDED,
                IntentState.TRANSFERRED,
            ],
            [IntentState.EXPIRED]: [],
            [IntentState.WITHDRAWN]: [],
            [IntentState.SUPERSEDED]: [],
            [IntentState.SUSPENDED]: [
                IntentState.ACTIVE,
                IntentState.WITHDRAWN,
                IntentState.EXPIRED,
                IntentState.TRANSFERRED,
            ],
            [IntentState.TRANSFERRED]: [],
        };
        if (!validTransitions[this.state].includes(nextState)) {
            throw new Error(`Invalid transition from ${this.state} to ${nextState}`);
        }
        this.state = nextState;
        return this.state;
    }
    isTerminal() {
        return [
            IntentState.EXPIRED,
            IntentState.WITHDRAWN,
            IntentState.SUPERSEDED,
            IntentState.TRANSFERRED,
        ].includes(this.state);
    }
}
export class OperationStateMachine {
    state;
    constructor(initialState = OperationState.PROPOSED) {
        this.state = initialState;
    }
    get currentState() {
        return this.state;
    }
    transition(event) {
        const nextState = normalizeOperationEvent(event);
        const validTransitions = {
            [OperationState.PROPOSED]: [
                OperationState.COMMITTED,
                OperationState.REJECTED,
                OperationState.ABANDONED,
                OperationState.FROZEN,
            ],
            [OperationState.COMMITTED]: [OperationState.SUPERSEDED],
            [OperationState.REJECTED]: [],
            [OperationState.ABANDONED]: [],
            [OperationState.FROZEN]: [
                OperationState.PROPOSED,
                OperationState.REJECTED,
                OperationState.ABANDONED,
            ],
            [OperationState.SUPERSEDED]: [],
        };
        if (!validTransitions[this.state].includes(nextState)) {
            throw new Error(`Invalid transition from ${this.state} to ${nextState}`);
        }
        this.state = nextState;
        return this.state;
    }
    isTerminal() {
        return [
            OperationState.COMMITTED,
            OperationState.REJECTED,
            OperationState.ABANDONED,
            OperationState.SUPERSEDED,
        ].includes(this.state);
    }
}
export class ConflictStateMachine {
    state;
    constructor(initialState = ConflictState.OPEN) {
        this.state = initialState;
    }
    get currentState() {
        return this.state;
    }
    transition(event) {
        const nextState = normalizeConflictEvent(event);
        const validTransitions = {
            [ConflictState.OPEN]: [ConflictState.ACKED, ConflictState.ESCALATED, ConflictState.DISMISSED],
            [ConflictState.ACKED]: [ConflictState.ESCALATED, ConflictState.RESOLVED, ConflictState.DISMISSED],
            [ConflictState.ESCALATED]: [ConflictState.RESOLVED, ConflictState.DISMISSED],
            [ConflictState.DISMISSED]: [],
            [ConflictState.RESOLVED]: [ConflictState.CLOSED],
            [ConflictState.CLOSED]: [],
        };
        if (!validTransitions[this.state].includes(nextState)) {
            throw new Error(`Invalid transition from ${this.state} to ${nextState}`);
        }
        this.state = nextState;
        return this.state;
    }
    isTerminal() {
        return [ConflictState.DISMISSED, ConflictState.CLOSED].includes(this.state);
    }
}
//# sourceMappingURL=state-machines.js.map