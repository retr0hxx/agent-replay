export class AgentReplayError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}
export class CassetteMissError extends AgentReplayError {}
export class DivergenceError extends AgentReplayError {}
export class NonTargetHostError extends AgentReplayError {}
export class CassetteFormatError extends AgentReplayError {}
