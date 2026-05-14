```markdown
# OnboardMe

AI-powered WhatsApp community onboarding engine. Automates 90-day member journeys via WhatsApp conversations.

## Stack
- Python 3.12, FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16
- APScheduler for cron/scheduled jobs
- Baileys WhatsApp bridge (Node.js, port 3000 inside Docker network)
- Anthropic Claude API (claude-sonnet-4-20250514) for AI responses
- Docker Compose for local dev — three services: api, postgres, whatsapp-bridge

## Project Structure
```

app/ main.py              # FastAPI app, middleware, router registration config.py            # pydantic-settings, all env vars models/              # SQLAlchemy ORM models routes/ webhooks.py        # /webhook/onboard + /webhook/inbound jobs.py            # cron endpoints settings.py        # config endpoints services/ database.py        # all DB queries (async SQLAlchemy) whatsapp.py        # Baileys bridge HTTP client groq.py            # AI service (being replaced with claude.py)

```
## Dev Commands
- Start everything: `docker compose up --build`
- API logs only: `docker compose logs -f api`
- DB shell: `docker compose exec postgres psql -U postgres -d onboardme`
- Restart API: `docker compose restart api`
- Run after code change: `docker compose up --build api`

## Critical Rules
- ALL DB operations must be async (use AsyncSession, SQLAlchemy 2.0 select() syntax)
- Always save user message to DB BEFORE loading history and calling Claude
- WhatsApp numbers stored with + prefix in international format (+2348012345678)
- Baileys bridge is at http://whatsapp-bridge:3000 inside Docker, localhost:3000 outside
- LID lookup before phone lookup on every inbound message (Baileys quirk)
- Never send a raw message template — pass it as a brief/context to Claude

## Architecture Decision: Conversational Delivery
Templates are NOT sent verbatim. Each touchpoint has a purpose + CTA brief. Claude reads the brief and sends a short 1-3 sentence opener. The member replies. The conversation happens. This is intentional.

## Known Quirks
- Baileys sometimes sends LID identifiers (e.g. 177897948114985@lid) instead of phone numbers
- whatsapp_lid must be stored on first message send and used for all subsequent delivery
- `maxSteps` in opencode config is deprecated — use `steps`
```