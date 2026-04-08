import { ConflictState, IntentState, OperationState } from "./models.js";

function normalizeIntentEvent(event: string): IntentState {
  const aliases: Record<string, IntentState> = {
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
  return aliases[event.toLowerCase()] ?? ((IntentState as Record<string, IntentState>)[event] ?? (event as IntentState));
}

function normalizeOperationEvent(event: string): OperationState {
  const aliases: Record<string, OperationState> = {
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
  return aliases[event.toLowerCase()] ?? ((OperationState as Record<string, OperationState>)[event] ?? (event as OperationState));
}

function normalizeConflictEvent(event: string): ConflictState {
  const aliases: Record<string, ConflictState> = {
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
  return aliases[event.toLowerCase()] ?? ((ConflictState as Record<string, ConflictState>)[event] ?? (event as ConflictState));
}

export class IntentStateMachine {
  private state: IntentState;

  constructor(initialState: IntentState = IntentState.ANNOUNCED) {
    this.state = initialState;
  }

  get currentState(): IntentState {
    return this.state;
  }

  transition(event: string): IntentState {
    const nextState = normalizeIntentEvent(event);
    const validTransitions: Record<IntentState, IntentState[]> = {
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

  isTerminal(): boolean {
    return [
      IntentState.EXPIRED,
      IntentState.WITHDRAWN,
      IntentState.SUPERSEDED,
      IntentState.TRANSFERRED,
    ].includes(this.state);
  }
}

export class OperationStateMachine {
  private state: OperationState;

  constructor(initialState: OperationState = OperationState.PROPOSED) {
    this.state = initialState;
  }

  get currentState(): OperationState {
    return this.state;
  }

  transition(event: string): OperationState {
    const nextState = normalizeOperationEvent(event);
    const validTransitions: Record<OperationState, OperationState[]> = {
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

  isTerminal(): boolean {
    return [
      OperationState.COMMITTED,
      OperationState.REJECTED,
      OperationState.ABANDONED,
      OperationState.SUPERSEDED,
    ].includes(this.state);
  }
}

export class ConflictStateMachine {
  private state: ConflictState;

  constructor(initialState: ConflictState = ConflictState.OPEN) {
    this.state = initialState;
  }

  get currentState(): ConflictState {
    return this.state;
  }

  transition(event: string): ConflictState {
    const nextState = normalizeConflictEvent(event);
    const validTransitions: Record<ConflictState, ConflictState[]> = {
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

  isTerminal(): boolean {
    return [ConflictState.DISMISSED, ConflictState.CLOSED].includes(this.state);
  }
}
