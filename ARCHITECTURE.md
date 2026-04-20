# MCP Control Plane Architecture

## System Overview

The MCP Control Plane (DEMA - Deus Ex Machina) is an enterprise-grade orchestration engine designed to manage complex, multi-stage agentic workflows. It enforces deterministic execution through a state machine, manages memory efficiently through 4-tier context management, and maintains high integrity through human-in-the-loop approval gates.

## Core Principles

1. **Gateway-Only Egress**: All external communication flows through the MCP Gateway
2. **Stateless Inference**: LLM is treated as a pure function; state is managed externally
3. **Zero-Trust Context**: Every request partitioned by tenant_id, plan_id, and run_id
4. **Deterministic State Machine**: LLM proposes changes; Control Plane validates and commits
5. **Context Compaction**: Memory management through intelligent P2/P3 eviction

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI REST API Server                       │
│                       (Port 8080)                                │
└────────────────────┬──────────────────────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   Orchestrator      │  Main execution loop
          │  (Execution Loop)   │  State transitions
          └──────────┬──────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
    ┌────────┐  ┌──────────┐  ┌──────────────┐
    │  State │  │ Context  │  │    Policy    │
    │Machine │  │  Focus   │  │   Engine     │
    │        │  │ Manager  │  │              │
    └────────┘  └────┬─────┘  └──────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
    ┌──────────┐  ┌─────────┐  ┌──────────┐
    │ Memory   │  │  Stage  │  │  Audit   │
    │ Manager  │  │  Gate   │  │   Store  │
    │ (P0-P3)  │  │         │  │          │
    └──────────┘  └─────────┘  └──────────┘
        │
    ┌───┴───┐
    │       │
    ▼       ▼
┌──────────────────┐  ┌──────────────────┐
│  Skills Registry │  │  LLM Connector   │
│  (Dynamic)       │  │  (OpenAI API)    │
└──────────────────┘  └──────────────────┘
    │                        │
    └────────────┬───────────┘
                 │
    ┌────────────▼─────────────┐
    │   Gateway Client (HTTP)  │
    │   JSON-RPC via streamable-http
    └────────────┬─────────────┘
                 │
    ┌────────────▼─────────────┐
    │   MCP Gateway (External) │
    │   - Tools/Resources      │
    │   - Skills Server        │
    │   - Other Servers        │
    └──────────────────────────┘
```

## Component Details

### 1. Orchestrator (`orchestrator.py`)

**Purpose**: Main control loop that manages plan lifecycle

**Key Responsibilities**:
- Create and manage plans
- Decompose goals into stages
- Run the main execution loop
- Handle approvals
- Manage plan state transitions

**Execution Loop Flow**:
```
1. Gather context (P0-P3) from Memory Manager
2. Get LLM decision based on context
3. Check memory compaction threshold
4. Evaluate decision against policies
5. If high-risk, pause for HITL approval
6. Execute tools via Gateway
7. Process results and update memory
8. Handle stage transitions
9. Check for completion
10. Repeat until done
```

### 2. State Machine (`state_machine.py`)

**Purpose**: Enforces deterministic state transitions

**Valid States**:
```
CREATED → PLANNING → EXECUTING ↔ PAUSED
                        ↓
                   AWAITING_HITL ↔ EXECUTING
                        ↓
                  COMPLETED/FAILED → CREATED (Retry)
```

**Key Features**:
- Validates all transitions
- Executes side effects (context scrubbing)
- Logs all state changes
- Prevents invalid transitions

### 3. Context Focus Manager (`memory_manager.py`)

**Purpose**: Manages 4-tier context hierarchy

**Tiers**:

| Tier | Scope | Lifetime | Purpose | Eviction |
|------|-------|----------|---------|----------|
| **P0** | Plan/Intent | Permanent | Goal, constraints, rules | Never |
| **P1** | Task/Stage | Stage | Current stage context | On stage change |
| **P2** | Observations | Intelligent | Tool results | Summarized threshold |
| **P3** | Signals | Ephemeral | User chat, events | TTL-based |

**Key Operations**:
- Create snapshots
- Add observations (with token counting)
- Add signals
- Compact P2 when threshold exceeded
- Evict expired P3 signals
- Clear P1 on stage transitions

### 4. Stage Gate (`stage_gate.py`)

**Purpose**: Manages stage transitions with context scrubbing

**Transition Process**:
1. Validate target stage exists
2. Archive current P2 observations
3. Load skills for new stage
4. Update P1 task context
5. Create new stage instructions
6. Log transition in audit store

### 5. Gateway Client (`gateway_client.py`)

**Purpose**: HTTP client for MCP Gateway communication

**Features**:
- JSON-RPC over HTTP
- Idempotency keys (SHA256 hash of tool + args)
- Error handling and retry logic
- Batch tool execution
- Skills management

**Key Methods**:
- `list_skills()`: Get available skills
- `get_skill()`: Get skill details
- `execute_tool()`: Execute single tool
- `execute_batch()`: Execute multiple tools

### 6. LLM Connector (`llm_connector.py`)

**Purpose**: Interface to OpenAI-compatible local LLM

**Features**:
- OpenAI SDK with local base_url
- Automatic JSON parsing from markdown code blocks
- Context-aware prompts
- Observation summarization
- Stateless (no conversation history)

**Decisions**:
- Tool intents (what to call)
- Next actions
- Stage transitions
- Approval requirements
- Confidence scores

### 7. Skills Registry (`skills_registry.py`)

**Purpose**: Dynamic management of available skills

**Operations**:
- Refresh skills from Gateway
- Get skills for specific stages
- Validate skill existence
- Generate skills summary for prompts

### 8. Memory Manager (`memory_manager.py`)

**Purpose**: Implements CFM with 4-tier context

**Key Methods**:
- `create_snapshot()`: Initialize context
- `add_observation()`: Add tool result to P2
- `add_signal()`: Add event to P3
- `compact_p2()`: Summarize observations
- `clean_p3_expired()`: Remove expired signals
- `clear_p1_context()`: Clear on stage transition
- `get_full_context()`: Get LLM context

### 9. Policy Engine (`policy_engine.py`)

**Purpose**: Validate decisions against policies

**Default Rules**:
- Low confidence decisions require approval
- Dangerous tools require approval
- Large batches require approval
- Stage changes are logged

**Severity Levels**:
- `critical`: Block execution
- `error`: Require approval
- `warning`: Flag but allow
- `info`: Log only

### 10. Context Compactor (`context_compactor.py`)

**Purpose**: Handle context space management

**Features**:
- Token count estimation
- Observation summarization via LLM
- Stale signal pruning
- Fallback summarization

### 11. Audit Store (`audit_store.py`)

**Purpose**: Log all events for compliance

**Events**:
- Plan lifecycle
- State transitions
- Tool executions
- Stage transitions
- Approval requests
- Errors and warnings

### 12. REST API (`rest_api.py`)

**Purpose**: FastAPI endpoints for external interaction

**Endpoints**:
- `POST /v1/plans` - Create plan
- `POST /v1/plans/{id}/stages` - Add stage
- `POST /v1/plans/{id}/run` - Execute
- `GET /v1/plans/{id}/state` - Get state
- `POST /v1/plans/{id}/pause` - Pause
- `POST /v1/plans/{id}/resume` - Resume
- `POST /v1/approvals/{id}` - Handle approval
- `GET /v1/plans/{id}/audit` - Audit logs

## Data Flow

### Plan Creation → Execution

```
1. API: POST /v1/plans
   ↓
2. Orchestrator.create_plan()
   - Generates plan_id, run_id
   - Sets status to CREATED
   - Logs event
   ↓
3. API: POST /v1/plans/{id}/run
   ↓
4. Orchestrator.start_execution()
   - Transition to PLANNING
   - Decompose goal into stages
   - Transition to EXECUTING
   - Create memory snapshot
   ↓
5. Orchestrator.run_execution_loop()
   - Iteration N:
     A. Memory.get_full_context() → P0-P3
     B. LLM.get_decision(context) → decision
     C. Policy.evaluate_decision() → violations
     D. If high-risk: pause for HITL
     E. Gateway.execute_batch(tools) → results
     F. Memory.add_observation(results)
     G. Handle stage transitions
     H. Repeat or complete
```

### High-Risk Decision Flow

```
1. LLM decision requires approval
   ↓
2. State Machine: EXECUTING → AWAITING_HITL
   ↓
3. Create ApprovalRequest
   ↓
4. Save approval_id
   ↓
5. API: POST /v1/approvals/{approval_id}
   ↓
6. If approved:
   - Inject approval token into P2
   - State Machine: AWAITING_HITL → EXECUTING
   - Resume execution loop
   
7. If denied:
   - State Machine: AWAITING_HITL → FAILED
   - Stop execution
```

### Memory Compaction Flow

```
1. P2 token count > threshold?
   ↓
2. LLM.summarize_observations() → summary
   ↓
3. Archive current P2 to historical_archives
   ↓
4. Replace P2 observations with summary
   ↓
5. Log compaction event
```

## Idempotency & Error Handling

### Idempotency Keys

Gateway requests include idempotency keys:
```
key = SHA256(tool_name + json(arguments))
```

Prevents duplicate tool execution if request retried.

### Error Recovery

1. **Tool Execution Error**:
   - Captured as ToolResult with status="error"
   - Added to P2 observations
   - LLM sees error in context, can decide to retry

2. **Policy Violation**:
   - Decision flagged
   - Plan paused for HITL
   - Approval required before continuing

3. **LLM Failure**:
   - Logged and returned to loop
   - Safe default decision returned
   - Loop continues or fails gracefully

## Tenant Isolation

Every plan includes:
- `tenant_id`: Tenant identifier
- `run_id`: Unique run identifier
- `plan_id`: Global plan identifier

All operations scoped to tenant via context routing.

## Performance Optimizations

1. **Batch Tool Execution**: Execute multiple tools in parallel
2. **Context Compression**: P2 summarization prevents context bloat
3. **Signal Pruning**: P3 TTL prevents memory leaks
4. **Lazy Skills Loading**: Skills loaded per stage, not upfront

## Security Considerations

1. **Zero-Trust Policy Engine**: All decisions validated
2. **Approval Gates**: High-risk decisions require human approval
3. **Immutable Audit Trail**: All events logged for compliance
4. **Context Isolation**: Tenant data never mixes
5. **No Conversation History**: LLM stateless, prevents context injection attacks

## Extensibility

### Adding New Policies

Create PolicyRule in policy_engine.py:
```python
def my_check(decision, plan):
    return decision.confidence < 0.7

rule = PolicyRule("my_policy", "My description", my_check, severity="warning")
policy_engine.add_rule(rule)
```

### Adding New Tools

Register via Gateway Skills Server; automatically discovered and available.

### Custom Memory Strategies

Implement new eviction policies in memory_manager.py.

## Testing Strategy

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **End-to-End Tests**: Test full workflows
- **Load Tests**: Test under high concurrency

See `tests/` directory for examples.

## Deployment

### Docker

```bash
docker-compose up
```

### Kubernetes

See Helm charts in `k8s/` directory (if available).

### Local Development

```bash
pip install -r requirements.txt
python main.py
```

## Monitoring & Observability

### Logging

- Structured logging to stdout
- Log levels: DEBUG, INFO, WARNING, ERROR
- All events tagged with plan_id, component name

### Metrics

Via Audit Store:
- Plans created/executed/failed
- Tool execution success rate
- Approval requests/approvals
- Average execution time

### Tracing

All operations tagged with:
- plan_id
- run_id
- tenant_id
- iteration count

## Future Enhancements

1. **LLM Decision Caching**: Cache identical context decisions
2. **Distributed Execution**: Multi-instance load balancing
3. **Advanced Scheduling**: Priority queues, rate limiting
4. **Real-time Streaming**: WebSocket for real-time updates
5. **Auto-Recovery**: Automatic plan restart/continuation
6. **ML-based Risk Scoring**: Learned confidence thresholds
