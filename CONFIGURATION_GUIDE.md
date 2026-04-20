# DEMA Configuration Guide

Complete guide to configuring the MCP Control Plane (DEMA - Deus Ex Machina) for your environment.

## Overview

There are **two ways** to configure DEMA:

1. **config.yaml** (Primary Configuration File)
2. **Environment Variables** (Overrides for deployment)

Configuration is automatically loaded on startup, with environment variables taking precedence over config.yaml settings.

---

## Table of Contents

- [System Configuration](#system-configuration)
- [LLM Provider Configuration](#llm-provider-configuration)
- [Gateway Configuration](#gateway-configuration)
- [Memory Configuration](#memory-configuration)
- [Environment Variables](#environment-variables)
- [Configuration Examples](#configuration-examples)
- [Verifying Configuration](#verifying-configuration)
- [Common Scenarios](#common-scenarios)
- [Quick Reference](#quick-reference)

---

## System Configuration

### Overview

Control how DEMA listens for connections and logs operations.

### Configuration File (config.yaml)

```yaml
system:
  env: "prod"          # Environment: "prod" or "dev"
  port: 8080          # Port to listen on (0-65535)
  log_level: "info"   # Logging level: debug, info, warning, error
```

### IP Address Binding

**Default Behavior:**
- The server listens on `0.0.0.0` (all network interfaces)
- Accessible via:
  - `http://localhost:8080` (local machine)
  - `http://<your-ip>:8080` (from other machines)
  - `http://<hostname>:8080` (if DNS configured)

### Port Configuration

**To use a different port:**

```yaml
system:
  port: 9000  # Change from default 8080
```

**Valid port ranges:**
- 1-1023: Reserved (requires root/admin)
- 1024-65535: Available for user processes

**Example configurations:**
```yaml
# Development
system:
  port: 8000

# Production
system:
  port: 8080

# Testing
system:
  port: 3000
```

### Environment Setting

**Development:**
```yaml
system:
  env: "dev"          # More verbose logging, debug info
  log_level: "debug"
```

**Production:**
```yaml
system:
  env: "prod"         # Optimized for performance
  log_level: "info"   # or "warning"
```

### Logging Levels

| Level | Use Case | Output |
|-------|----------|--------|
| `debug` | Development, troubleshooting | Everything (verbose) |
| `info` | Production, monitoring | Important events |
| `warning` | Production | Only warnings and errors |
| `error` | Critical issues | Only errors |

**Configure logging:**
```yaml
system:
  log_level: "debug"  # Most verbose
```

### Environment Variables

Override system settings:
```bash
export DEMA_ENV=prod
export DEMA_PORT=9000
export DEMA_LOG_LEVEL=debug
python main.py
```

---

## LLM Provider Configuration

### Overview

Configure the language model that powers DEMA's decision-making.

### Supported LLM Types

#### 1. Local LLM (Recommended for Development)

**Ollama:**
```yaml
llm_provider:
  base_url: "http://localhost:11434/v1"
  api_key: "not-needed-for-local"
  model_name: "llama2"
```

**LM Studio:**
```yaml
llm_provider:
  base_url: "http://localhost:1234/v1"
  api_key: "not-needed-for-local"
  model_name: "hermes"
```

**vLLM:**
```yaml
llm_provider:
  base_url: "http://localhost:8000/v1"
  api_key: "not-needed-for-local"
  model_name: "meta-llama/Llama-2-7b-chat-hf"
```

#### 2. Cloud-Based LLM (Production)

**OpenAI:**
```yaml
llm_provider:
  base_url: "https://api.openai.com/v1"
  api_key: "sk-your-actual-key-here"  # Never hardcode in config!
  model_name: "gpt-4"
  max_tokens: 8192
  temperature: 0.2
```

**Anthropic Claude:**
```yaml
llm_provider:
  base_url: "https://api.anthropic.com/v1"
  api_key: ${ANTHROPIC_API_KEY}
  model_name: "claude-3-opus"
```

**Azure OpenAI:**
```yaml
llm_provider:
  base_url: "https://<resource>.openai.azure.com/v1"
  api_key: ${AZURE_OPENAI_KEY}
  model_name: "gpt-4"
```

### Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `base_url` | URL | http://localhost:1234/v1 | LLM API endpoint |
| `api_key` | String | not-needed-for-local | API authentication |
| `model_name` | String | hermes-3-llama-3.1 | Model identifier |
| `max_tokens` | Integer | 4096 | Max completion length |
| `temperature` | Float | 0.2 | Response randomness (0.0-2.0) |

### Common LLM Endpoints

| LLM Service | Endpoint | Port | Key Required |
|-------------|----------|------|--------------|
| Ollama (local) | http://localhost:11434/v1 | 11434 | No |
| LM Studio (local) | http://localhost:1234/v1 | 1234 | No |
| vLLM (local) | http://localhost:8000/v1 | 8000 | No |
| OpenAI (cloud) | https://api.openai.com/v1 | 443 | Yes |
| Azure OpenAI (cloud) | https://<resource>.openai.azure.com | 443 | Yes |
| Anthropic (cloud) | https://api.anthropic.com/v1 | 443 | Yes |

### Parameter Tuning

**Temperature (Creativity)**
- `0.0`: Deterministic, predictable (use for analysis)
- `0.5`: Balanced
- `1.0+`: Creative, variable (use for brainstorming)

**Recommended values:**
```yaml
llm_provider:
  temperature: 0.1   # Analytical work, code generation
  temperature: 0.2   # Default, balanced
  temperature: 0.5   # Creative tasks
  temperature: 1.0   # Brainstorming
```

**Max Tokens**
- Larger = longer responses, higher cost
- Smaller = faster, cheaper
- Must not exceed model's context window

```yaml
llm_provider:
  max_tokens: 2048   # Short completions
  max_tokens: 4096   # Standard
  max_tokens: 8192   # Long-form outputs
```

### Remote LLM Setup

**LM Studio on different machine:**
```yaml
llm_provider:
  base_url: "http://192.168.1.100:1234/v1"
  model_name: "hermes"
```

**Internal network LLM:**
```yaml
llm_provider:
  base_url: "http://llm-server.internal.company:8000/v1"
  model_name: "hermes-large"
```

### Secure API Key Handling

**Never hardcode sensitive keys in config.yaml!**

Instead, use environment variables:

```yaml
llm_provider:
  base_url: "https://api.openai.com/v1"
  api_key: ${OPENAI_API_KEY}  # From environment
  model_name: "gpt-4"
```

Set the environment variable:
```bash
export OPENAI_API_KEY="sk-..."
python main.py
```

Or in .env file:
```bash
OPENAI_API_KEY=sk-...
```

### Environment Variables

```bash
export LLM_BASE_URL="http://localhost:11434/v1"
export LLM_API_KEY="sk-..."
export LLM_MODEL_NAME="llama2"
export LLM_MAX_TOKENS=8192
export LLM_TEMPERATURE=0.2
```

---

## Gateway Configuration

### Overview

Configure connection to the MCP Gateway that provides tools and resources.

### Configuration File (config.yaml)

```yaml
gateway:
  url: "https://mcp-gateway.internal/api"           # Gateway endpoint
  auth_token: ${GATEWAY_SECRET}                     # Authentication
  skills_server_name: "enterprise-skills-catalog"  # Skills source
```

### Gateway URL

The URL must point to the Gateway API endpoint.

**Local Gateway:**
```yaml
gateway:
  url: "http://localhost:8000/api"
```

**Production Gateway:**
```yaml
gateway:
  url: "https://mcp-gateway.production.company.com/api"
```

**Internal Network:**
```yaml
gateway:
  url: "http://gateway.internal.company:8000/api"
```

**IP Address:**
```yaml
gateway:
  url: "http://10.0.1.50:8000/api"
```

### Authentication

**Local (no auth):**
```yaml
gateway:
  auth_token: "local-dev-token"
```

**Production (use environment variable):**
```yaml
gateway:
  auth_token: ${GATEWAY_SECRET}
```

**Set the token:**
```bash
export GATEWAY_SECRET="your-secret-token-here"
python main.py
```

**Or in .env:**
```bash
GATEWAY_SECRET=production-token-xyz123
```

### Skills Server

The Gateway may host multiple skills servers. Specify which one:

```yaml
gateway:
  skills_server_name: "enterprise-skills-catalog"
```

**Alternatives:**
```yaml
gateway:
  skills_server_name: "data-analytics-tools"
gateway:
  skills_server_name: "deployment-tools"
gateway:
  skills_server_name: "local-skills"
```

### Gateway Protocol

DEMA communicates with the Gateway using:
- **Protocol**: JSON-RPC 2.0 over HTTP
- **Format**: `streamable-http`
- **Features**: Idempotent requests, batch execution

### Environment Variables

```bash
export GATEWAY_URL="https://gateway.internal/api"
export GATEWAY_SECRET="token-here"
export GATEWAY_SKILLS_SERVER="enterprise-skills"
```

### Connection Troubleshooting

**Test Gateway connectivity:**
```bash
# Check if gateway is reachable
curl "https://mcp-gateway.internal/api/health"

# With authentication
curl -H "Authorization: Bearer ${GATEWAY_SECRET}" \
  "https://mcp-gateway.internal/api/tools"
```

**Debug in logs:**
```bash
DEMA_LOG_LEVEL=debug python main.py
```

Look for:
```
[Init] Gateway Client initialized: https://...
[Gateway] Listing skills from enterprise-skills-catalog
```

---

## Memory Configuration

### Overview

Configure how DEMA manages context memory and data retention.

### Context Tiers (P0-P3)

**P0 (Plan Intent)**: Never deleted
- Overarching goal and constraints

**P1 (Task Context)**: Stage-scoped
- Current stage instructions

**P2 (Observations)**: Intelligent eviction
- Tool results and feedback

**P3 (Signals)**: TTL-based eviction
- User messages and events

### Configuration

```yaml
memory:
  p2_summary_threshold_tokens: 2000   # Compaction trigger
  p3_ttl_seconds: 3600                # Signal lifetime
```

### P2 Observation Compaction

When P2 (Observations) exceeds the token threshold, DEMA:
1. Uses LLM to summarize observations
2. Archives original data
3. Replaces with summary

**Tune for your needs:**

```yaml
# Frequent compaction (resource-constrained)
memory:
  p2_summary_threshold_tokens: 500

# Standard (balanced)
memory:
  p2_summary_threshold_tokens: 2000

# Large context (memory-rich)
memory:
  p2_summary_threshold_tokens: 5000
```

**Guidelines:**
- Smaller threshold = frequent compaction, more LLM calls
- Larger threshold = more memory usage, fewer LLM calls
- Token count ≈ characters / 4

### P3 Signal TTL (Time-To-Live)

How long signals (events) are kept before deletion:

```yaml
# Short retention (30 minutes)
memory:
  p3_ttl_seconds: 1800

# Standard (1 hour)
memory:
  p3_ttl_seconds: 3600

# Long retention (2 hours)
memory:
  p3_ttl_seconds: 7200
```

**Choose based on:**
- Workflow duration
- Real-time responsiveness needs
- Memory constraints

### Environment Variables

```bash
export MEMORY_P2_THRESHOLD=5000
export MEMORY_P3_TTL=7200
```

---

## Environment Variables

### Using .env File

Create a `.env` file in the dema directory:

```bash
cp .env.example .env
nano .env
```

**Example .env contents:**
```bash
# System
DEMA_ENV=prod
DEMA_PORT=8080
DEMA_LOG_LEVEL=info

# LLM
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=llama2
LLM_API_KEY=sk-...
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.2

# Gateway
GATEWAY_URL=https://mcp-gateway.internal/api
GATEWAY_SECRET=your-secret-token
GATEWAY_SKILLS_SERVER=enterprise-skills

# Memory
MEMORY_P2_THRESHOLD=2000
MEMORY_P3_TTL=3600
```

**Load and run:**
```bash
source .env
python main.py
```

### Using Environment Variables Directly

```bash
export DEMA_PORT=9000
export LLM_BASE_URL="http://192.168.1.100:1234/v1"
export GATEWAY_SECRET="production-token"
python main.py
```

### Variable Substitution in config.yaml

Reference environment variables in config.yaml:

```yaml
llm_provider:
  api_key: ${OPENAI_API_KEY}  # Reads from environment

gateway:
  auth_token: ${GATEWAY_SECRET}
```

**Set the env var:**
```bash
export OPENAI_API_KEY="sk-..."
```

### Precedence Order

1. **Environment Variables** (highest priority)
2. **Environment variable substitution in config.yaml**
3. **config.yaml values**
4. **Defaults** (lowest priority)

---

## Configuration Examples

### Example 1: Local Development (Ollama + Local Gateway)

**config.yaml:**
```yaml
system:
  env: "dev"
  port: 8080
  log_level: "debug"

llm_provider:
  base_url: "http://localhost:11434/v1"
  api_key: "not-needed-for-local"
  model_name: "llama2"
  max_tokens: 4096
  temperature: 0.2

gateway:
  url: "http://localhost:8000/api"
  auth_token: "dev-token"
  skills_server_name: "local-skills"

memory:
  p2_summary_threshold_tokens: 2000
  p3_ttl_seconds: 3600
```

**Start:**
```bash
python main.py
```

### Example 2: Production (OpenAI + Cloud Gateway)

**config.yaml:**
```yaml
system:
  env: "prod"
  port: 8080
  log_level: "warning"

llm_provider:
  base_url: "https://api.openai.com/v1"
  api_key: ${OPENAI_API_KEY}
  model_name: "gpt-4"
  max_tokens: 8192
  temperature: 0.1

gateway:
  url: "https://api.company.com/mcp-gateway"
  auth_token: ${GATEWAY_SECRET}
  skills_server_name: "enterprise-skills-catalog"

memory:
  p2_summary_threshold_tokens: 5000
  p3_ttl_seconds: 7200
```

**Environment (.env or export):**
```bash
export OPENAI_API_KEY="sk-..."
export GATEWAY_SECRET="prod-token-123"
python main.py
```

### Example 3: On-Premise Production (Internal LLM + Internal Gateway)

**config.yaml:**
```yaml
system:
  env: "prod"
  port: 8080
  log_level: "info"

llm_provider:
  base_url: "http://llm-server.internal.company:8000/v1"
  api_key: "not-needed"
  model_name: "hermes-large"
  max_tokens: 8192
  temperature: 0.1

gateway:
  url: "https://mcp-gateway.internal.company/api"
  auth_token: ${GATEWAY_SECRET}
  skills_server_name: "enterprise-skills-catalog"

memory:
  p2_summary_threshold_tokens: 5000
  p3_ttl_seconds: 7200
```

**Set secrets:**
```bash
export GATEWAY_SECRET="internal-prod-token"
python main.py
```

### Example 4: Docker Deployment

**config.yaml:**
```yaml
system:
  env: "prod"
  port: 8080
  log_level: "info"

llm_provider:
  base_url: "http://ollama:11434/v1"  # Docker service name
  api_key: "not-needed"
  model_name: "llama2"
  max_tokens: 4096
  temperature: 0.2

gateway:
  url: "http://gateway:8000/api"  # Docker service name
  auth_token: ${GATEWAY_SECRET}
  skills_server_name: "default-skills"

memory:
  p2_summary_threshold_tokens: 2000
  p3_ttl_seconds: 3600
```

**docker-compose.yml:**
```yaml
services:
  dema:
    build: .
    ports:
      - "8080:8080"
    environment:
      - GATEWAY_SECRET=docker-secret-token
    depends_on:
      - ollama
      - gateway

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"

  gateway:
    image: mcp-gateway:latest
    ports:
      - "8000:8000"
```

**Start:**
```bash
docker-compose up
```

### Example 5: Kubernetes Deployment

**config.yaml:**
```yaml
system:
  env: "prod"
  port: 8080
  log_level: "info"

llm_provider:
  base_url: "http://ollama.default.svc.cluster.local:11434/v1"
  api_key: "not-needed"
  model_name: "llama2"

gateway:
  url: "http://gateway.default.svc.cluster.local:8000/api"
  auth_token: ${GATEWAY_SECRET}
  skills_server_name: "k8s-skills"

memory:
  p2_summary_threshold_tokens: 5000
  p3_ttl_seconds: 7200
```

**Environment (ConfigMap/Secret):**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: dema-secrets
type: Opaque
data:
  GATEWAY_SECRET: base64-encoded-secret
```

---

## Verifying Configuration

### 1. Check Health

```bash
curl http://localhost:8080/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "mcp-control-plane"
}
```

### 2. Check System Info

```bash
curl http://localhost:8080/v1/info
```

Expected response:
```json
{
  "name": "Dema (Deus Ex Machina)",
  "version": "1.0.0",
  "active_plans": 0,
  "pending_approvals": 0
}
```

### 3. Use CLI Tool

```bash
python cli.py health
python cli.py info
```

Expected output:
```
✓ Server is healthy
Status: healthy
```

### 4. Check Logs

Run with debug logging:
```bash
DEMA_LOG_LEVEL=debug python main.py
```

Look for initialization logs:
```
[Init] Gateway Client initialized: https://...
[LLM] Initialized with model: llama2 at http://localhost:11434/v1
[Init] Skills Registry initialized (N skills)
```

### 5. Verify LLM Connection

The server will log errors if LLM is unreachable:
```
[LLM] Error getting decision: Connection refused
```

### 6. Verify Gateway Connection

The server will log errors if Gateway is unreachable:
```
[Gateway] Request error: [Errno -2] Name or service not known
```

### 7. Test with API

Create a test plan:
```bash
curl -X POST http://localhost:8080/v1/plans \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Test plan",
    "constraints": [],
    "metadata": {"tenant_id": "test"}
  }'
```

---

## Common Scenarios

### Scenario 1: Change Port

**Requirement**: I need to run DEMA on port 9000

**Solution:**
```yaml
system:
  port: 9000
```

Or:
```bash
export DEMA_PORT=9000
python main.py
```

### Scenario 2: Use Cloud OpenAI

**Requirement**: Use GPT-4 from OpenAI API

**Solution:**
```yaml
llm_provider:
  base_url: "https://api.openai.com/v1"
  api_key: ${OPENAI_API_KEY}
  model_name: "gpt-4"
  max_tokens: 8192
```

Set key:
```bash
export OPENAI_API_KEY="sk-..."
python main.py
```

### Scenario 3: Use Remote Ollama

**Requirement**: Connect to Ollama on another machine

**Solution:**
```yaml
llm_provider:
  base_url: "http://192.168.1.100:11434/v1"
  model_name: "llama2"
```

### Scenario 4: Production with Secrets

**Requirement**: Production deployment with secure secrets

**Solution:**
Create `.env` (don't commit to git):
```bash
OPENAI_API_KEY=sk-...
GATEWAY_SECRET=prod-token
```

Add to `.gitignore`:
```
.env
```

Load and run:
```bash
source .env
python main.py
```

### Scenario 5: Multiple Instances

**Requirement**: Run multiple DEMA instances for load balancing

**Solution:**
Instance 1:
```yaml
system:
  port: 8080
```

Instance 2:
```yaml
system:
  port: 8081
```

Or use environment:
```bash
DEMA_PORT=8080 python main.py
DEMA_PORT=8081 python main.py
```

### Scenario 6: Low Memory Environment

**Requirement**: Configure for resource-constrained system

**Solution:**
```yaml
system:
  log_level: "warning"  # Less logging

llm_provider:
  max_tokens: 2048      # Smaller responses

memory:
  p2_summary_threshold_tokens: 1000  # More frequent compaction
  p3_ttl_seconds: 1800               # Shorter signal lifetime
```

### Scenario 7: High Throughput

**Requirement**: Optimize for many concurrent plans

**Solution:**
```yaml
system:
  log_level: "warning"  # Reduce overhead

llm_provider:
  max_tokens: 4096

memory:
  p2_summary_threshold_tokens: 5000  # Less frequent compaction
  p3_ttl_seconds: 7200               # Longer signal lifetime
```

---

## Quick Reference

### All Configuration Options

```yaml
system:
  env: "prod"                                    # prod|dev
  port: 8080                                     # 1-65535
  log_level: "info"                              # debug|info|warning|error

llm_provider:
  base_url: "http://localhost:1234/v1"          # LLM endpoint URL
  api_key: "not-needed-for-local"               # API key (or ${ENV_VAR})
  model_name: "hermes-3-llama-3.1"              # Model name
  max_tokens: 4096                               # 1-unlimited
  temperature: 0.2                               # 0.0-2.0

gateway:
  url: "https://mcp-gateway.internal/api"       # Gateway URL
  auth_token: "${GATEWAY_SECRET}"               # Token or ${ENV_VAR}
  skills_server_name: "enterprise-skills-catalog" # Server name

memory:
  p2_summary_threshold_tokens: 2000              # 500-10000
  p3_ttl_seconds: 3600                           # 60-86400
```

### All Environment Variables

```bash
DEMA_ENV=prod
DEMA_PORT=8080
DEMA_LOG_LEVEL=info

LLM_BASE_URL=http://localhost:1234/v1
LLM_API_KEY=not-needed-for-local
LLM_MODEL_NAME=hermes-3-llama-3.1
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.2

GATEWAY_URL=https://mcp-gateway.internal/api
GATEWAY_SECRET=your-token-here
GATEWAY_SKILLS_SERVER=enterprise-skills-catalog

MEMORY_P2_THRESHOLD=2000
MEMORY_P3_TTL=3600
```

### Common LLM Endpoints

```
Ollama:        http://localhost:11434/v1
LM Studio:     http://localhost:1234/v1
vLLM:          http://localhost:8000/v1
OpenAI:        https://api.openai.com/v1
Azure OpenAI:  https://<resource>.openai.azure.com/v1
Anthropic:     https://api.anthropic.com/v1
```

### Configuration Workflow

1. **Copy example:**
   ```bash
   cp .env.example .env
   ```

2. **Edit config.yaml** or **.env** with your settings

3. **Set critical secrets:**
   ```bash
   export OPENAI_API_KEY="sk-..."
   export GATEWAY_SECRET="token"
   ```

4. **Load environment:**
   ```bash
   source .env
   ```

5. **Start server:**
   ```bash
   python main.py
   ```

6. **Verify:**
   ```bash
   python cli.py health
   ```

---

## Troubleshooting Configuration

### Issue: Server won't start

**Check:**
- Port already in use: Try different port
- Invalid YAML syntax: Run `python -m yaml config.yaml`
- Missing files: Verify `config.yaml` exists

**Solution:**
```bash
# Try different port
export DEMA_PORT=9000
python main.py
```

### Issue: LLM connection failed

**Check logs:**
```bash
DEMA_LOG_LEVEL=debug python main.py
```

**Verify LLM running:**
```bash
curl http://localhost:1234/v1/models
```

**Solution:**
- Start Ollama: `ollama serve`
- Or update base_url in config.yaml

### Issue: Gateway connection failed

**Check logs:**
```bash
DEMA_LOG_LEVEL=debug python main.py
```

**Verify Gateway running:**
```bash
curl https://mcp-gateway.internal/api/health
```

**Solution:**
- Start Gateway
- Check URL and token in config.yaml
- Verify network connectivity

### Issue: API Key not working

**Verify:**
```bash
echo $OPENAI_API_KEY
```

**Solution:**
```bash
export OPENAI_API_KEY="sk-..."
python main.py
```

**Don't hardcode keys in config.yaml!**

---

## Best Practices

1. **Never commit secrets to version control**
   - Use `.env` files (add to `.gitignore`)
   - Use environment variables in CI/CD

2. **Use environment variables for all secrets**
   ```yaml
   api_key: ${OPENAI_API_KEY}
   ```

3. **Test configuration before production**
   ```bash
   python cli.py health
   ```

4. **Use appropriate logging levels**
   - Development: `debug`
   - Production: `warning` or `info`

5. **Monitor critical connections**
   - LLM availability
   - Gateway availability
   - Network connectivity

6. **Document your configuration**
   - Comment changes in config.yaml
   - Keep `.env.example` updated
   - Document any custom settings

7. **Version your configuration**
   - Track config.yaml in git
   - Keep `.env` out of git
   - Use `.env.example` as template

8. **Test after configuration changes**
   ```bash
   python cli.py health
   python cli.py info
   ```

---

## Support

- **Logs**: Check application logs for details
- **Documentation**: See README.md, ARCHITECTURE.md
- **Examples**: See QUICKSTART.md for common use cases
- **API Reference**: See REST API documentation

