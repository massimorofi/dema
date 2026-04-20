
This specification outlines the architecture and implementation requirements for a high-integrity **MCP Control Plane**. This system acts as the "executive function" for agentic workflows, using an MCP Gateway as its singular interface to the world and a local OpenAI-compatible LLM as its reasoning engine.
The name of the application is Dema = "Deus Ex Machina"
---

# MCP Control Plane: Technical Specification v1.0

## 0. References
* **The MCP Control plane will use FastMCP library**
* **The MCP Control Plane will use as gateway tinymcp and will only use, tools, resources and skills exposed by it**: see /home/briggen/Dev/code/python/tinymcp project for more info
* **The MCP Control Plane will read skills from skillsmcp server registered to teh gateway**: look at /home/briggen/Dev/code/python/skillsmcp for more info

## 1. Architectural Invariants
To ensure enterprise-grade safety and determinism, the following rules are non-negotiable:
* **Gateway-Only Egress:** The Control Plane (CP) connects **only** to the MCP Gateway. It cannot directly dial any MCP server or external URL (except the local LLM).
* **Protocol:** All communication with the Gateway is via `streamable-http` (production standard).
* **Stateless Inference:** The LLM is treated as a pure function. No conversation history is stored within the LLM provider; the CP manages all memory.
* **Zero-Trust Context:** Every request is partitioned by `tenant_id`, `plan_id`, and `run_id` to prevent context leakage.

---

## 2. System Components

### 2.1 Context Focus Manager (CFM)
The CFM is responsible for the "Deterministic Snapshot" of memory. It compiles the prompt sent to the LLM based on four tiers of data:

| Tier | Scope | Description | Eviction Strategy |
| :--- | :--- | :--- | :--- |
| **P0** | **Plan/Intent** | The overarching goal, constraints, and "Golden Rules." | **Never evicted.** |
| **P1** | **Task/Stage** | The current sub-step of the plan (e.g., "Data Discovery"). | Cleared on stage transition. |
| **P2** | **Observations** | Structured tool results and system feedback. | **Summarized** when threshold reached. |
| **P3** | **Signals** | Ephemeral user chat and low-level event logs. | **Sliding window** (TTL-based). |



### 2.2 Orchestrator (State Machine)
The Orchestrator manages the lifecycle of a **Plan**.
1.  **Creation:** Receives a high-level goal via REST API and generates a multi-stage `Plan Object`.
2.  **Execution Loop:** * Fetches skills/tools from the Gateway.
    * Calls LLM to decide the `next_action`.
    * Submits tool intents to the Gateway.
    * Updates the `Plan` state based on results.
3.  **Human-in-the-loop (HITL):** Pauses execution if a tool's risk level or a policy check requires manual approval.

---

## 3. Configuration Schema (`config.yaml`)
The CP must be entirely driven by a configuration file to allow for environment-specific tuning.

```yaml
system:
  env: "prod"
  port: 8080
  log_level: "info"

llm_provider:
  base_url: "http://localhost:1234/v1" # Local OpenAI-compatible API
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

---

## 4. REST API Specification (OpenAPI 3.0)
The Control Plane exposes the following endpoints for external interaction:

### `POST /v1/plans`
Creates a new orchestration plan.
* **Input:** `{ "goal": "string", "constraints": [], "metadata": {} }`
* **Output:** `201 Created` with `plan_id`.

### `POST /v1/plans/{plan_id}/run`
Triggers or resumes execution of a plan.
* **Input:** `{ "mode": "auto|step" }`

### `GET /v1/plans/{plan_id}/state`
Returns the current P0-P3 status, active stage, and audit logs.

### `POST /v1/approvals/{approval_id}`
Provides the HITL signal to resume a paused execution.

---

## 5. Skills Integration Logic
The CP does not hardcode its capabilities. It discovers them dynamically:
1.  **Bootstrap:** On startup (or per-run), the CP calls `tools.call("skills.list")` via the Gateway.
2.  **Mapping:** It maps returned skills to the **P1 Task** currently active.
3.  **Injection:** The CP injects the "How-to" logic (retrieved via `skills.get`) into the system prompt to guide the LLM's reasoning without hardcoding prompts in the CP source code.

---

## 6. Implementation Blueprint (Coding Agent Instructions)

### Task 1: Setup the Gateway Client
Implement a robust HTTP client that communicates with the MCP Gateway. It must handle `JSON-RPC` over HTTP and include logic for **Idempotency Keys** (generated as a hash of the tool name + arguments).

### Task 2: Context Compaction
Write a utility that calculates token counts for P2 (Observations). When tokens exceed `p2_summary_threshold_tokens`, the agent must invoke a "Summary Reflex"—a separate LLM call that condenses results into a bulleted list while preserving key data points.

### Task 3: The Orchestration Loop
Construct a loop that follows this logic:
```python
while plan.status == "ACTIVE":
    # 1. Gather all tier data
    context = CFM.compile(plan_id)
    
    # 2. Get LLM Decision
    decision = LLM.get_decision(context, schema=LLMDecisionSchema)
    
    # 3. Policy & Risk Check
    if decision.requires_approval or Policy.is_high_risk(decision):
        plan.pause_for_hitl(decision)
        break
        
    # 4. Gateway Execution
    results = Gateway.execute_batch(decision.tool_intents)
    
    # 5. Update State
    Memory.persist(results)
    plan.update_stage(decision.update_stage_to)
```

### Task 4: Local LLM Connector
Ensure the connector uses the standard `openai` Python library but points to `base_url`. This allows the CP to switch from a local **Ollama** or **LM Studio** instance to a cloud provider by changing only the config.

---

To ensure the Orchestrator doesn't drift or "hallucinate" its way into an invalid state, you need a deterministic **State Machine**. The LLM can *propose* a state change, but the Control Plane must *validate* it against the Plan’s defined stages before committing.

Here is the additional specification for the **State Machine Transition Logic**.

---

## 7. State Machine Specification

### 7.1 Plan Statuses
The overarching `Plan` object must strictly exist in one of the following statuses:

| Status | Description | Allowed Next Statuses |
| :--- | :--- | :--- |
| `CREATED` | Plan initialized, objective defined. | `PLANNING` |
| `PLANNING` | LLM is decomposing the goal into stages. | `EXECUTING`, `FAILED` |
| `EXECUTING` | Active loop; tool calls being dispatched. | `AWAITING_HITL`, `PAUSED`, `COMPLETED`, `FAILED` |
| `AWAITING_HITL` | Paused for human intervention (Policy/Risk). | `EXECUTING`, `PAUSED`, `FAILED` |
| `PAUSED` | Execution suspended via API. | `EXECUTING` |
| `COMPLETED` | Objective met. | `CREATED` (Reset) |
| `FAILED` | Terminal error or terminal policy violation. | `CREATED` (Retry) |

### 7.2 The Transition Function ($\delta$)
For a coding agent, the transition logic should be implemented as a formal function where:
$$\delta(S_{current}, E_{input}) \rightarrow S_{next}$$

**Logic Rules for the Agent:**
1.  **LLM-Triggered Stage Change:** The LLM output includes `update_stage_to`. The CP checks if this stage exists in the `Plan.stages` array. If it doesn't, the transition is rejected, and an error is fed back to the LLM.
2.  **Stateful Memory Reset:** Transitions have side effects on the Context Focus Manager (CFM):
    * **Stage Transition:** When moving from "Awareness" to "Engagement," the CP MUST purge **P1 (Task Context)** and archive/summarize **P2 (Observations)** to prevent old data from polluting the new stage.
    * **Status Transition:** Moving to `AWAITING_HITL` freezes the context snapshot entirely until approval is granted.

### 7.3 State Transition Table (JSON-encoded for Agent)
```json
{
  "transitions": [
    {
      "trigger": "LLM_SUGGEST_STAGE_MOVE",
      "from": "EXECUTING",
      "to": "EXECUTING",
      "action": "clear_p1_context",
      "validation": "is_valid_stage_name"
    },
    {
      "trigger": "POLICY_RISK_DETECTED",
      "from": "EXECUTING",
      "to": "AWAITING_HITL",
      "action": "create_approval_request"
    },
    {
      "trigger": "API_RESUME",
      "from": "AWAITING_HITL",
      "to": "EXECUTING",
      "action": "inject_approval_token_into_p2"
    }
  ]
}
```

---

## 8. Integration: The "Stage Gate" Implementation
The Coding Agent should implement a `StageGate` class that wraps the Orchestrator loop.

### Logic Flow for Coding Agent:
1.  **Read LLM Decision:** Parse `update_stage_to`.
2.  **Verify Invariant:** Is `update_stage_to` different from `current_stage`?
3.  **Perform "Context Scrub":**
    * Move all current **P2 (Observations)** to a "Historical Archive."
    * Fetch new **Skills** associated with the new stage from the **Skills MCP Server** (via Gateway).
    * Re-compile **P1 (Task Instructions)** based on the new stage's definition.
4.  **Log Transition:** Every transition must be logged in the `AuditStore` with the rationale provided by the LLM (`decision.rationale`).

---

## 9. Failure & Compensation Logic
If the state machine reaches `FAILED`, the Control Plane must:
1.  **Stop Egress:** Immediately block all tool calls to the Gateway for that `plan_id`.
2.  **Snapshot:** Save the final P0-P3 state for debugging.
3.  **Notify:** Emit an event via the REST API/Webhook to inform the supervisor system.

### Summary for your Coding Agent:
> "The LLM is the driver, but the State Machine is the rails. The driver can steer, but the rails determine where it's physically possible to go. If the LLM tries to steer off the rails, the Control Plane pulls the emergency brake (HITL)."


