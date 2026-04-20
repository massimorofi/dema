# Quick Start Guide

## Installation

```bash
# 1. Clone/navigate to the project
cd dema

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

## Configuration

```bash
# Copy example config
cp .env.example .env

# Edit .env with your settings (especially LLM and Gateway URLs)
nano .env
```

## Running Locally

### Option 1: Direct Python

```bash
# Start the server
python main.py
```

Server runs on http://localhost:8080

### Option 2: Docker

```bash
# Build and run with Docker
docker-compose up
```

### Option 3: Using Make

```bash
# Install dependencies
make install

# Run the server
make run
```

## First Steps

### 1. Check Health

```bash
# In another terminal
python cli.py health
```

### 2. Get System Info

```bash
python cli.py info
```

### 3. Create a Plan

```bash
python cli.py create "Analyze marketing data" \
  --constraint "Use only internal data" \
  --constraint "Complete in 1 hour" \
  --tenant acme
```

Example output:
```
✓ Plan created: a1b2c3d4-e5f6-7890-1234-567890abcdef
Status: CREATED
```

### 4. Add Stages

```bash
PLAN_ID="a1b2c3d4-e5f6-7890-1234-567890abcdef"

python cli.py stage-add $PLAN_ID "Data Gathering" \
  "Collect and organize data" \
  --skill data_collection

python cli.py stage-add $PLAN_ID "Analysis" \
  "Analyze the data" \
  --skill data_analysis \
  --skill visualization

python cli.py stage-add $PLAN_ID "Reporting" \
  "Generate insights" \
  --skill report_generation
```

### 5. Check Plan Status

```bash
python cli.py status $PLAN_ID
```

### 6. Run the Plan

```bash
python cli.py run $PLAN_ID --mode auto
```

Plan will start executing and process through stages.

### 7. Monitor Execution

```bash
# Get current state
python cli.py state $PLAN_ID

# Watch audit logs
python cli.py audit $PLAN_ID
```

### 8. Handle Approvals (if needed)

If plan pauses for approval:

```bash
# List approval requests from audit logs
python cli.py audit $PLAN_ID

# Approve (substitute actual approval_id)
python cli.py approve $APPROVAL_ID --approve --token human-approved

# Or deny
python cli.py approve $APPROVAL_ID --deny
```

## API Examples

### Using cURL

#### Create Plan

```bash
curl -X POST http://localhost:8080/v1/plans \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Process customer data",
    "constraints": ["Use only internal sources"],
    "metadata": {"tenant_id": "acme"}
  }'
```

#### Get Plan State

```bash
curl http://localhost:8080/v1/plans/{plan_id}/state
```

#### Run Plan

```bash
curl -X POST http://localhost:8080/v1/plans/{plan_id}/run \
  -H "Content-Type: application/json" \
  -d '{"mode": "auto"}'
```

#### Handle Approval

```bash
curl -X POST http://localhost:8080/v1/approvals/{approval_id} \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "approval_token": "human-approved"}'
```

### Using Python Requests

```python
import requests
import json

BASE_URL = "http://localhost:8080"

# Create plan
response = requests.post(f"{BASE_URL}/v1/plans", json={
    "goal": "Analyze data",
    "constraints": [],
    "metadata": {"tenant_id": "test"}
})
plan = response.json()
plan_id = plan["plan_id"]

# Get plan state
response = requests.get(f"{BASE_URL}/v1/plans/{plan_id}/state")
state = response.json()
print(f"Status: {state['plan']['status']}")

# Run plan
response = requests.post(f"{BASE_URL}/v1/plans/{plan_id}/run", json={"mode": "auto"})
print(response.json())
```

## Running Examples

See example workflows:

```bash
python examples.py
```

This demonstrates:
- Simple data analysis workflow
- High-risk approval workflow
- Multiple parallel plans
- Memory management

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=html
```

### Code Quality

```bash
# Format code
make format

# Run linters
make lint
```

## Troubleshooting

### Server Won't Start

**Problem**: Port 8080 already in use
```bash
# Change port in config.yaml
system:
  port: 8081
```

**Problem**: LLM connection error
```
# Ensure local LLM is running (e.g., Ollama)
# Check base_url in config.yaml
# Default: http://localhost:1234/v1
```

### Plan Execution Fails

**Check logs**:
```bash
# Change log level in config.yaml
system:
  log_level: debug
```

**Check audit logs**:
```bash
python cli.py audit $PLAN_ID
```

### Tools Not Found

**Problem**: Tools not available from Gateway

```bash
# Ensure Gateway is running and accessible
# Check gateway.url in config.yaml
# Verify skills_server_name matches registered server
```

## Next Steps

1. **Read Architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md)
2. **Understand Workflows**: See [README.md](README.md)
3. **Integration**: Connect to your MCP Gateway
4. **Deployment**: Configure for production
5. **Monitoring**: Set up logging/metrics collection

## Common Workflows

### Data Processing Pipeline

```
Goal: "Process and analyze sales data"

Stages:
1. Data Discovery - Find available data sources
2. Data Extraction - Extract relevant data
3. Data Cleaning - Clean and normalize
4. Analysis - Generate insights
5. Reporting - Create reports
```

### Deployment Orchestration

```
Goal: "Deploy to production with zero downtime"

Stages:
1. Pre-flight Checks - Verify requirements (requires approval)
2. Environment Setup - Create parallel environment
3. Application Deploy - Deploy new version (requires approval)
4. Health Verification - Run health checks
5. Traffic Switch - Route to new version (requires approval)
6. Monitoring - Monitor for issues
```

### Content Generation

```
Goal: "Generate marketing content"

Stages:
1. Research - Gather relevant information
2. Planning - Outline content structure
3. Generation - Create content
4. Review - Initial quality check (requires approval)
5. Refinement - Improve based on feedback
6. Publishing - Publish to target channels (requires approval)
```

## Support & Documentation

- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **API Reference**: [README.md](README.md#api-endpoints)
- **Examples**: [examples.py](examples.py)
- **Tests**: [tests/](tests/)

## Configuration Reference

See `config.yaml` for all available options:

```yaml
system:
  env: "prod|dev"           # Environment
  port: 8080                # Server port
  log_level: "info"         # Log level

llm_provider:
  base_url: "..."           # LLM endpoint
  api_key: "..."            # API key
  model_name: "..."         # Model to use
  max_tokens: 4096          # Max completion tokens
  temperature: 0.2          # Response randomness

gateway:
  url: "..."                # Gateway URL
  auth_token: "..."         # Auth token
  skills_server_name: "..." # Skills server

memory:
  p2_summary_threshold_tokens: 2000   # Compaction threshold
  p3_ttl_seconds: 3600               # Signal TTL
```

Enjoy using DEMA! 🚀
