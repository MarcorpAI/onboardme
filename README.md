# Community Onboarding Agent

AI-powered WhatsApp agent for automatic community onboarding.

## Architecture

```
Hercules Form → POST /webhook/onboard → API → Groq LLM → WhatsApp Bridge → User
                    ↓
              PostgreSQL (sessions, messages)
```

## Quick Start

1. **Create `.env` from example:**
```bash
cp .env.example .env
# Fill in your values
```

2. **Start services:**
```bash
docker-compose up -d
```

3. **Connect WhatsApp:**
```bash
docker logs -f onboardme-whatsapp-bridge
# Scan QR code when prompted
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | FastAPI backend |
| PostgreSQL | 5432 | Database |
| WhatsApp Bridge | - | WhatsApp connection |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook/onboard` | POST | Receive Hercules form submissions |
| `/webhook/inbound` | POST | Receive incoming WhatsApp messages |
| `/jobs/follow-up` | POST | Send follow-up messages (cron) |
| `/jobs/abandon` | POST | Mark abandoned sessions (cron) |
| `/health` | GET | Health check |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GROQ_API_KEY` | Groq API key | Required |
| `COMMUNITY_NAME` | Name of your community | Required |
| `COMMUNITY_DESCRIPTION` | What the community is about | Required |
| `INVITE_LINK` | Link to join the community | Required |
| `AGENT_NAME` | Name of the bot | Required |
| `FOLLOW_UP_DELAY_MINS` | Minutes before follow-up | 30 |
| `ABANDON_AFTER_HOURS` | Hours before marking abandoned | 24 |

## Cron Jobs Setup

Set up these endpoints as cron jobs on your hosting platform:

```bash
# Every 15 minutes - send follow-ups
*/15 * * * * curl -X POST http://localhost:8000/jobs/follow-up

# Every hour - mark abandoned sessions
0 * * * * curl -X POST http://localhost:8000/jobs/abandon
```

## Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## MBN Template Seeding

For the Oracle-hosted compose setup with Neon, set `DATABASE_URL` in `.env`
first, then run:

```bash
docker compose -f docker-compose.oracle.yml build api
docker compose -f docker-compose.oracle.yml run --rm api python -m app.scripts.seed_mbn_templates --dry-run
docker compose -f docker-compose.oracle.yml run --rm api python -m app.scripts.seed_mbn_templates --apply
docker compose -f docker-compose.oracle.yml up --build api
```

The seed command upserts the MBN WhatsApp onboarding templates for the default
client. It does not delete custom templates.
