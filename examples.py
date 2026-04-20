"""Example usage of the MCP Control Plane."""
import time
from orchestrator import Orchestrator
from gateway_client import GatewayClient
from llm_connector import LLMConnector
from memory_manager import MemoryManager
from skills_registry import SkillsRegistry
from audit_store import AuditStore


def example_simple_workflow():
    """Example: Execute a simple workflow."""
    
    print("\n" + "="*80)
    print("Example: Simple Data Analysis Workflow")
    print("="*80 + "\n")
    
    # Initialize components
    gateway = GatewayClient("http://localhost:8080")
    llm = LLMConnector(
        base_url="http://localhost:1234/v1",
        api_key="not-needed",
        model_name="hermes-3-llama-3.1"
    )
    memory = MemoryManager()
    skills = SkillsRegistry(gateway)
    audit = AuditStore()
    
    orchestrator = Orchestrator(llm, gateway, memory, skills, audit)
    
    # Create a plan
    plan = orchestrator.create_plan(
        goal="Analyze marketing campaign data and generate insights",
        constraints=[
            "Use only available data sources",
            "Complete analysis within 1 hour",
            "Generate actionable recommendations"
        ],
        metadata={"tenant_id": "acme-corp", "priority": "high"}
    )
    
    print(f"Created Plan: {plan.plan_id}")
    print(f"Goal: {plan.goal}\n")
    
    # Add stages to the plan
    stages = [
        ("Data Discovery", "Identify and catalog available data sources", ["data_catalog", "profiling"]),
        ("Data Analysis", "Perform statistical analysis and identify patterns", ["analytics", "visualization"]),
        ("Insight Generation", "Generate business insights from analysis", ["reporting", "nlp"]),
        ("Recommendation", "Create actionable recommendations", ["recommendation_engine"]),
    ]
    
    for stage_name, description, skills_list in stages:
        orchestrator.add_stage_to_plan(plan.plan_id, stage_name, description, skills_list)
        print(f"Added stage: {stage_name}")
    
    print(f"\nPlan has {len(plan.stages)} stages\n")
    
    # Start execution
    print("Starting execution...\n")
    
    # In a real scenario, this would run the full execution loop
    # For demo, we'll just show the API flow
    
    # Get plan state
    state = orchestrator.get_plan_state(plan.plan_id)
    print(f"Plan Status: {state['plan']['status']}")
    print(f"Current Stage: {state['plan']['stages'][plan.current_stage_idx] if plan.stages else 'N/A'}\n")


def example_approval_workflow():
    """Example: Workflow with human-in-the-loop approval."""
    
    print("\n" + "="*80)
    print("Example: High-Risk Decision with Approval")
    print("="*80 + "\n")
    
    # Initialize components
    gateway = GatewayClient("http://localhost:8080")
    llm = LLMConnector(
        base_url="http://localhost:1234/v1",
        api_key="not-needed",
        model_name="hermes-3-llama-3.1"
    )
    memory = MemoryManager()
    skills = SkillsRegistry(gateway)
    audit = AuditStore()
    
    orchestrator = Orchestrator(llm, gateway, memory, skills, audit)
    
    # Create a plan with high-risk decisions
    plan = orchestrator.create_plan(
        goal="Deploy new version to production",
        constraints=[
            "Zero-downtime deployment",
            "Automatic rollback on failure",
            "Require manual approval"
        ],
        metadata={"tenant_id": "acme-corp", "approval_required": True}
    )
    
    print(f"Created Plan: {plan.plan_id}")
    print(f"Goal: {plan.goal}\n")
    
    # Add deployment stages
    stages = [
        ("Pre-deployment", "Verify prerequisites and health checks", ["health_check", "validation"]),
        ("Blue-Green Setup", "Setup parallel environment", ["infrastructure", "deployment"]),
        ("Traffic Switch", "Route traffic to new version", ["networking", "load_balancer"]),
        ("Monitoring", "Monitor for issues and rollback if needed", ["monitoring", "alerting"]),
    ]
    
    for stage_name, description, skills_list in stages:
        orchestrator.add_stage_to_plan(plan.plan_id, stage_name, description, skills_list)
    
    print("Deployment stages created")
    print("\nNote: In production, this would pause for human approval on critical operations\n")


def example_multi_plan_workflow():
    """Example: Managing multiple parallel plans."""
    
    print("\n" + "="*80)
    print("Example: Multiple Parallel Plans")
    print("="*80 + "\n")
    
    # Initialize components
    gateway = GatewayClient("http://localhost:8080")
    llm = LLMConnector(
        base_url="http://localhost:1234/v1",
        api_key="not-needed",
        model_name="hermes-3-llama-3.1"
    )
    memory = MemoryManager()
    skills = SkillsRegistry(gateway)
    audit = AuditStore()
    
    orchestrator = Orchestrator(llm, gateway, memory, skills, audit)
    
    # Create multiple plans for different tenants
    tenants = ["tenant-a", "tenant-b", "tenant-c"]
    plans = []
    
    for tenant in tenants:
        plan = orchestrator.create_plan(
            goal=f"Process data pipeline for {tenant}",
            constraints=["Isolation", "Resource limits"],
            metadata={"tenant_id": tenant, "priority": "medium"}
        )
        plans.append(plan)
        print(f"Created plan for {tenant}: {plan.plan_id}")
    
    print(f"\nManaging {len(plans)} plans concurrently\n")
    
    # Show that each plan has isolated context
    for plan in plans:
        state = orchestrator.get_plan_state(plan.plan_id)
        print(f"Plan {plan.plan_id[-8:]}: Status={state['plan']['status']}, Tenant={state['plan']['tenant_id']}")


def example_memory_management():
    """Example: Context compaction and memory management."""
    
    print("\n" + "="*80)
    print("Example: Memory Management (P0-P3 Context Tiers)")
    print("="*80 + "\n")
    
    memory = MemoryManager(p2_summary_threshold_tokens=500, p3_ttl_seconds=300)
    
    # Create a snapshot
    from models import Plan
    plan = Plan("Test goal", ["Constraint 1"], {"tenant_id": "test"})
    snapshot = memory.create_snapshot(plan, "Discovery")
    
    print("Initial Context Snapshot:")
    print(f"P0 (Plan Intent): {snapshot.p0_plan_intent}")
    print(f"P1 (Task Context): {snapshot.p1_task_context}")
    print(f"P2 Observations: {len(snapshot.p2_observations)}")
    print(f"P3 Signals: {len(snapshot.p3_signals)}\n")
    
    # Add observations
    from models import ToolResult
    for i in range(5):
        result = ToolResult(
            tool_name=f"tool_{i}",
            status="success",
            result={"data": f"result {i}" * 100}
        )
        memory.add_observation(plan.plan_id, result)
    
    print(f"Added 5 observations. P2 token count: {memory.get_p2_token_count(plan.plan_id)}")
    print(f"Should compact: {memory.should_compact_p2(plan.plan_id)}\n")
    
    # Add signals
    for i in range(3):
        memory.add_signal(plan.plan_id, {"type": f"event_{i}", "message": f"Something happened {i}"})
    
    print(f"Added 3 P3 signals\n")
    
    # Get full context
    context = memory.get_full_context(plan.plan_id)
    print(f"Full Context Structure:")
    print(f"- P0 Keys: {list(context['p0_plan_intent'].keys())}")
    print(f"- P1 Keys: {list(context['p1_task_context'].keys())}")
    print(f"- P2 Observations: {len(context['p2_observations'])}")
    print(f"- P3 Signals: {len(context['p3_signals'])}\n")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("MCP Control Plane (DEMA) - Examples")
    print("="*80)
    
    try:
        # Run examples
        example_simple_workflow()
        example_approval_workflow()
        example_multi_plan_workflow()
        example_memory_management()
        
        print("\n" + "="*80)
        print("Examples completed successfully!")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback
        traceback.print_exc()
