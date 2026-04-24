import { ConflictState, IntentState, OperationState } from "./models.js";
export declare class IntentStateMachine {
    private state;
    constructor(initialState?: IntentState);
    get currentState(): IntentState;
    transition(event: string): IntentState;
    isTerminal(): boolean;
}
export declare class OperationStateMachine {
    private state;
    constructor(initialState?: OperationState);
    get currentState(): OperationState;
    transition(event: string): OperationState;
    isTerminal(): boolean;
}
export declare class ConflictStateMachine {
    private state;
    constructor(initialState?: ConflictState);
    get currentState(): ConflictState;
    transition(event: string): ConflictState;
    isTerminal(): boolean;
}
//# sourceMappingURL=state-machines.d.ts.map