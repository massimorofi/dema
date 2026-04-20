#!/usr/bin/env python
"""CLI tool for testing and interacting with the MCP Control Plane."""
import os
import click
import json
import requests
from dotenv import load_dotenv
from typing import Optional
from tabulate import tabulate

# Load .env file from the same directory as cli.py
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


class DemaClient:
    """Client for interacting with Dema API."""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url

    def _request(self, method: str, endpoint: str, **kwargs):
        """Make HTTP request to API."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            text = response.text.strip()
            if not text:
                return {}
            return response.json()
        except requests.exceptions.ConnectionError:
            click.echo(f"Error: Cannot connect to {self.base_url}", err=True)
            raise
        except requests.exceptions.HTTPError as e:
            click.echo(f"Error: {e.response.status_code} - {e.response.text}", err=True)
            raise
        except (json.JSONDecodeError, ValueError) as e:
            click.echo(f"Error: Received non-JSON response: {response.text[:200]}", err=True)
            raise

    def health(self):
        """Check API health."""
        return self._request("GET", "/health")

    def info(self):
        """Get system info."""
        return self._request("GET", "/v1/info")

    def create_plan(self, goal: str, constraints: list = None, metadata: dict = None):
        """Create a new plan."""
        payload = {
            "goal": goal,
            "constraints": constraints or [],
            "metadata": metadata or {},
        }
        return self._request("POST", "/v1/plans", json=payload)

    def get_plan(self, plan_id: str):
        """Get plan details."""
        return self._request("GET", f"/v1/plans/{plan_id}")

    def get_plan_state(self, plan_id: str):
        """Get plan state."""
        return self._request("GET", f"/v1/plans/{plan_id}/state")

    def add_stage(self, plan_id: str, stage_name: str, description: str, skills: list = None):
        """Add a stage to a plan."""
        payload = {
            "stage_name": stage_name,
            "description": description,
            "required_skills": skills or [],
        }
        return self._request("POST", f"/v1/plans/{plan_id}/stages", json=payload)

    def run_plan(self, plan_id: str, mode: str = "auto"):
        """Start execution of a plan."""
        payload = {"mode": mode}
        return self._request("POST", f"/v1/plans/{plan_id}/run", json=payload)

    def pause_plan(self, plan_id: str):
        """Pause plan execution."""
        return self._request("POST", f"/v1/plans/{plan_id}/pause")

    def resume_plan(self, plan_id: str):
        """Resume plan execution."""
        return self._request("POST", f"/v1/plans/{plan_id}/resume")

    def approve(self, approval_id: str, approved: bool, token: str = None):
        """Respond to approval request."""
        payload = {
            "approved": approved,
            "approval_token": token or ("approved" if approved else "denied"),
        }
        return self._request("POST", f"/v1/approvals/{approval_id}", json=payload)

    def get_audit(self, plan_id: str):
        """Get audit logs for a plan."""
        return self._request("GET", f"/v1/plans/{plan_id}/audit")


@click.group()
@click.option(
    "--url",
    default=None,
    help="API base URL (defaults to DEMA_HOST:DEMA_PORT from .env)",
)
@click.pass_context
def cli(ctx, url):
    """MCP Control Plane (Dema) CLI Tool."""
    ctx.ensure_object(dict)
    base_url = url or os.getenv("DEMA_URL")
    if not base_url:
        host = os.getenv("DEMA_HOST", "localhost")
        port = os.getenv("DEMA_PORT", "8090")
        base_url = f"http://{host}:{port}"
    ctx.obj["client"] = DemaClient(base_url)


@cli.command()
@click.pass_context
def health(ctx):
    """Check server health."""
    client = ctx.obj["client"]
    try:
        result = client.health()
        click.echo(click.style("✓ Server is healthy", fg="green"))
        click.echo(f"Status: {result.get('status')}")
    except Exception as e:
        click.echo(click.style(f"✗ Health check failed: {e}", fg="red"), err=True)


@cli.command()
@click.pass_context
def info(ctx):
    """Get system information."""
    client = ctx.obj["client"]
    try:
        info = client.info()
        click.echo(f"Name: {info.get('name')}")
        click.echo(f"Version: {info.get('version')}")
        click.echo(f"Active Plans: {info.get('active_plans')}")
        click.echo(f"Pending Approvals: {info.get('pending_approvals')}")
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)


@cli.command()
@click.argument("goal")
@click.option("--constraint", multiple=True, help="Add a constraint")
@click.option("--tenant", help="Tenant ID")
@click.pass_context
def create(ctx, goal, constraint, tenant):
    """Create a new plan."""
    client = ctx.obj["client"]
    try:
        metadata = {}
        if tenant:
            metadata["tenant_id"] = tenant
        
        result = client.create_plan(goal, list(constraint), metadata)
        plan_id = result.get("plan_id")
        click.echo(click.style(f"✓ Plan created: {plan_id}", fg="green"))
        click.echo(f"Status: {result.get('status')}")
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)


@cli.command()
@click.argument("plan_id")
@click.pass_context
def status(ctx, plan_id):
    """Get plan status."""
    client = ctx.obj["client"]
    try:
        plan = client.get_plan(plan_id)
        
        click.echo(f"Plan ID: {plan.get('plan_id')}")
        click.echo(f"Goal: {plan.get('goal')}")
        click.echo(f"Status: {click.style(plan.get('status'), fg='cyan')}")
        click.echo(f"Tenant: {plan.get('tenant_id')}")
        click.echo(f"Stages: {len(plan.get('stages', []))}")
        
        stages = plan.get("stages", [])
        if stages:
            click.echo("\nStages:")
            for i, stage in enumerate(stages):
                status_mark = "✓" if stage.get("completed") else "○"
                click.echo(f"  {status_mark} {i+1}. {stage.get('name')}: {stage.get('description')[:50]}")
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)


@cli.command()
@click.argument("plan_id")
@click.argument("stage_name")
@click.argument("description")
@click.option("--skill", multiple=True, help="Add a required skill")
@click.pass_context
def stage_add(ctx, plan_id, stage_name, description, skill):
    """Add a stage to a plan."""
    client = ctx.obj["client"]
    try:
        result = client.add_stage(plan_id, stage_name, description, list(skill))
        click.echo(click.style(f"✓ Stage added: {stage_name}", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)


@cli.command()
@click.argument("plan_id")
@click.option("--mode", default="auto", type=click.Choice(["auto", "step"]))
@click.pass_context
def run(ctx, plan_id, mode):
    """Run a plan."""
    client = ctx.obj["client"]
    try:
        result = client.run_plan(plan_id, mode)
        click.echo(click.style(f"✓ Plan execution started", fg="green"))
        click.echo(f"Status: {result.get('status')}")
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)


@cli.command()
@click.argument("plan_id")
@click.pass_context
def pause(ctx, plan_id):
    """Pause plan execution."""
    client = ctx.obj["client"]
    try:
        result = client.pause_plan(plan_id)
        click.echo(click.style(f"✓ Plan paused", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)


@cli.command()
@click.argument("plan_id")
@click.pass_context
def resume(ctx, plan_id):
    """Resume plan execution."""
    client = ctx.obj["client"]
    try:
        result = client.resume_plan(plan_id)
        click.echo(click.style(f"✓ Plan resumed", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)


@cli.command()
@click.argument("plan_id")
@click.pass_context
def state(ctx, plan_id):
    """Get detailed plan state."""
    client = ctx.obj["client"]
    try:
        state = client.get_plan_state(plan_id)
        
        plan = state.get("plan", {})
        context = state.get("context", {})
        
        click.echo(f"Plan: {plan.get('plan_id')}")
        click.echo(f"Status: {click.style(plan.get('status'), fg='cyan')}")
        click.echo(f"Iterations: {state.get('iteration')}")
        
        # Show context tiers
        click.echo("\nContext Tiers:")
        click.echo(f"  P0 (Plan Intent): {list(context.get('p0_plan_intent', {}).keys())}")
        click.echo(f"  P1 (Task Context): {list(context.get('p1_task_context', {}).keys())}")
        click.echo(f"  P2 (Observations): {len(context.get('p2_observations', []))} items")
        click.echo(f"  P3 (Signals): {len(context.get('p3_signals', []))} items")
        
        # Show audit logs
        logs = state.get("audit_logs", [])
        if logs:
            click.echo(f"\nRecent Audit Logs ({len(logs)} total):")
            for log in logs[-5:]:
                click.echo(f"  {log.get('event_type')}: {log.get('timestamp')}")
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)


@cli.command()
@click.argument("plan_id")
@click.pass_context
def audit(ctx, plan_id):
    """Get audit logs for a plan."""
    client = ctx.obj["client"]
    try:
        result = client.get_audit(plan_id)
        logs = result.get("logs", [])
        
        if not logs:
            click.echo("No audit logs found")
            return
        
        # Format logs for table
        table_data = []
        for log in logs[-20:]:  # Show last 20
            table_data.append([
                log.get("event_type"),
                log.get("timestamp"),
                json.dumps(log.get("details", {}))[:50] + "...",
            ])
        
        headers = ["Event", "Timestamp", "Details"]
        click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)


@cli.command()
@click.argument("approval_id")
@click.option("--approve/--deny", default=True)
@click.option("--token", help="Approval token")
@click.pass_context
def approve(ctx, approval_id, approve, token):
    """Respond to approval request."""
    client = ctx.obj["client"]
    try:
        result = client.approve(approval_id, approve, token)
        status = "approved" if approve else "denied"
        click.echo(click.style(f"✓ Approval {status}", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)


if __name__ == "__main__":
    cli()
