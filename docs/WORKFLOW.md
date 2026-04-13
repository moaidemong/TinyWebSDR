# TinyWebSDR Development Workflow

## Request Format
When requesting work or feature development:

- **Goal**: Clear objective statement (what needs to be achieved)
- **DoD**: Definition of Done - measurable criteria for completion
- **Constraints**: Technical limitations, dependencies, or blockers
- **Priority/Deadline**: Urgency level and timeline expectations

### Example:
```
Goal: Implement producer core with RTL-SDR integration
DoD: Producer reads IQ samples, computes FFT rows, writes to shared memory with <50ms processing time
Constraints: Must work in WSL2, RTL-SDR v4 hardware only
Priority: High - blocks gateway development
```

## Progress Format
Regular status updates should include:

- **Done**: Completed components with verification status
- **Next**: Immediate next steps and dependencies
- **Blockers**: Current obstacles and proposed mitigation

### Example:
```
Done: RTL-SDR API integration tested, FFT pipeline working
Next: Implement shared memory writer with latest-only policy
Blockers: Need to resolve numpy version conflict in WSL2 environment
```

## Decision Record Rule
For architectural decisions (ADR format):

- **Decision**: What was decided, including technical specifics
- **Rationale**: Why this approach was chosen over alternatives
- **Alternatives**: Other options considered and why they were rejected
- **Date**: When the decision was made and by whom

### ADR Lifecycle:
1. **Proposed** - Initial decision draft, open for review
2. **Accepted** - Approved and ready for implementation
3. **Deprecated** - Superseded by newer decision
4. **Rejected** - Not approved, with reasoning

## Code Review Guidelines
- All changes require testing against performance targets
- Focus on latency measurement and frame drop analysis
- Verify WebSocket protocol compliance
- Test recovery scenarios (device disconnect, process restart)
