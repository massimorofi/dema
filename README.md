# MCP Control Plane (DEMA)

**Deus Ex Machina** - A high-integrity enterprise orchestration engine for agentic workflows.

## Overview

The MCP Control Plane is the "executive function" for autonomous workflows. It orchestrates complex, multi-stage plans using:

- **MCP Gateway** as the singular interface to tools and resources
- **Local OpenAI-compatible LLM** as the reasoning engine
- **Deterministic State Machine** for plan lifecycle management
- **4-Tier Context Focus Manager** for memory management
- **Human-in-the-Loop (HITL)** approval gates for high-risk decisions

## Architecture

### Core Components

1. **Orchestrator**: Main control loop that manages plan execution
2. **State Machine**: Enforces deterministic state transitions
3. **Context Focus Manager (CFM)**: Manages 4-tier context (P0-P3)
4. **Gateway Client**: Communicates with MCP Gateway
5. **LLM Connector**: Interfaces with local OpenAI-compatible LLM
6. **Skills Registry**: Dynamically discovers and manages skills
7. **Stage Gate**: Manages stage transitions with context scrubbing
8. **Memory Manager**: Handles context compaction and eviction
9. **Audit Store**: Logs all events for compliance

### Context Tiers (P0-P3)

| Tier | Scope | Duration | Purpose |
|------|-------|----------|---------|
| **P0** | Plan Intent | Never | Overarching goal, constraints, golden rules |
| **P1** | Task Context | Stage | Current stage instructions and available skills |
| **P2** | Observations | Intelligent | Tool results and system feedback (compacted when threshold reached) |
| **P3** | Signals | TTL-based | User chat, events, ephemeral data (expires after TTL) |

### State Machine

```
CREATED → PLANNING → EXECUTING ↔ PAUSED
                         ↓
                    AWAITING_HITL ↔ EXECUTING
                         ↓
                    COMPLETED/FAILED → CREATED (Retry)
```

## Setup

### Prerequisites

- Python 3.11+
- Local OpenAI-compatible LLM (Ollama, LM Studio, etc.)
- Running MCP Gateway instance
- Running Skills MCP Server

### Installation

```bash
# Clone repository
cd dema

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Edit `config.yaml`:

```yaml
system:
  env: "prod"
  port: 8080
  log_level: "info"

llm_provider:
  base_url: "http://localhost:1234/v1"
  api_key: "not-needed-for-local"
  model_name: "hermes-3-llama-3.1"
  max_tokens: 4096
  temperature: 0.2

gateway:
  url: "https://mcp-gateway.internal/api"
  auth_token: ${GATEWAY_SECRET}
  skills_server_name: "enterprise-skills-catalog"

memory:
  p2_summary_threshold_tokens: 2000
  p3_ttl_seconds: 3600
```

### Starting the Server

```bash
python main.py
```

The server will start on `http://0.0.0.0:8080`

## API Endpoints

### Plans

**Create a new plan**
```
POST /v1/plans
{
  "goal": "Analyze marketing data and generate insights",
  "constraints": ["No external API calls", "Complete within 1 hour"],
  "metadata": {"tenant_id": "acme", "priority": "high"}
}
```

**Add stages to a plan**
```
POST /v1/plans/{plan_id}/stages
{
  "stage_name": "Data Discovery",
  "description": "Gather and explore available data sources",
  "required_skills": ["data_analysis", "visualization"]
}
```

**Run a plan**
```
POST /v1/plans/{plan_id}/run
{
  "mode": "auto"
}
```

**Get plan state**
```
GET /v1/plans/{plan_id}/state
```

Returns P0-P3 context, current stage, and audit logs.

**Pause/Resume**
```
POST /v1/plans/{plan_id}/pause
POST /v1/plans/{plan_id}/resume
```

**Handle approval**
```
POST /v1/approvals/{approval_id}
{
  "approved": true,
  "approval_token": "approved-by-human"
}
```

**Get audit logs**
```
GET /v1/plans/{plan_id}/audit
```

### System

**Health check**
```
GET /health
```

**System info**
```
GET /v1/info
```

## Execution Flow

1. **Plan Creation**: User creates a plan with goal and constraints
2. **Decomposition**: LLM breaks goal into stages
3. **Execution Loop**:
   - Compile context (P0-P3)
   - Get LLM decision
   - Check policy/risk (triggers HITL if needed)
   - Execute tools via Gateway
   - Update memory with results
   - Handle stage transitions
4. **Completion**: Plan marked as COMPLETED or FAILED

## Memory Management

### P2 Compaction

When P2 (Observations) exceeds the token threshold:
1. LLM summarizes observations into bullet points
2. Original observations moved to historical archive
3. Summary replaces observations in memory

### P3 Eviction

P3 signals expire after TTL:
1. Signals added with timestamp
2. Expired signals automatically removed
3. Prevents context pollution

## Stage Transitions

When LLM requests stage transition:
1. Validate target stage exists
2. Archive current P1/P2
3. Load new skills for target stage
4. Fetch new P1 instructions
5. Update context snapshot
6. Log transition in audit store

## Human-in-the-Loop (HITL)

When decision flagged for approval:
1. Plan transitions to `AWAITING_HITL`
2. Approval request generated with decision details
3. External system handles approval
4. Response sent via `/v1/approvals/{approval_id}`
5. Plan resumes or fails based on approval

## Monitoring & Debugging

### Audit Logs

All events logged with timestamps:
- Plan lifecycle events
- LLM decisions
- Tool executions
- Stage transitions
- Approval requests

### Context Snapshots

Full context snapshot available at any time:
```
GET /v1/plans/{plan_id}/state
```

### Logging

Configure log level in `config.yaml`:
```yaml
system:
  log_level: "debug"  # debug, info, warning, error
```

## Best Practices

1. **Constraints**: Define clear constraints to guide LLM decisions
2. **Skills**: Register relevant skills for each stage
3. **Stages**: Break complex goals into logical stages
4. **Approval**: Set `requires_approval: true` for high-risk decisions
5. **Monitoring**: Check audit logs regularly for issues

## Development

### Running Tests

```bash
# Run unit tests
pytest tests/

# Run with coverage
pytest --cov=. tests/
```

### Project Structure

```
dema/
├── main.py              # Entry point
├── config.yaml          # Configuration
├── requirements.txt     # Dependencies
├── models.py            # Data models
├── state_machine.py     # State machine
├── orchestrator.py      # Main orchestration loop
├── context_manager.py   # Context Focus Manager
├── memory_manager.py    # Memory & compaction
├── gateway_client.py    # Gateway communication
├── llm_connector.py     # LLM interface
├── skills_registry.py   # Skills management
├── stage_gate.py        # Stage transitions
├── audit_store.py       # Audit logging
├── rest_api.py          # FastAPI endpoints
└── README.md            # This file
```

## License

Proprietary - Enterprise Use Only

## Support

For issues or questions, contact the platform team.
# dema
