# Community Onboarding Agent

## What This Is

A lightweight AI-powered WhatsApp agent that automatically onboards new members into a community the moment they submit a signup form. No human moderator needed, no rule-based scripts — just a natural back-and-forth conversation that makes the user feel welcomed, answers their questions, and gets them into the group.

The agent is triggered by a webhook from a Hercules-built website. When someone submits their name and WhatsApp number on the form, the agent takes over from there.

---

## The Problem It Solves

Community owners collect signups but then have to manually message each person, qualify them, and share the invite link. This is slow, inconsistent, and doesn't scale. People drop off between signup and actually joining.

This agent handles the entire onboarding conversation automatically — warmly, conversationally, at any time of day.

---

## How It Works

### Trigger

The Hercules site fires a `POST` request to this service whenever a form is submitted, carrying the user's name, WhatsApp number, and any other fields collected.

### The Conversation

The agent initiates the WhatsApp conversation and handles the entire onboarding flow from there. It's not scripted — it's an LLM that knows the context of the community, knows what it needs to find out from the user, and converses naturally to get there.

The agent's job is to:
- Make the user feel welcomed and not like they're talking to a bot
- Learn enough about the user to personalise the experience (what they do, what they're hoping to get from the community)
- Answer any questions they have about the community
- Deliver the invite link once the conversation reaches a natural close

If the user goes off-script, asks questions, or responds weirdly — the agent handles it. It's not going to break because someone said "who are you?" instead of "yes".

### After the Conversation

Once the user has been sent the invite link and the conversation closes naturally, the session is logged as onboarded. If the user ghosts mid-conversation, the agent sends one gentle follow-up after 30 minutes, then marks the session as abandoned after 24 hours of silence.

---

## Architecture

```
Hercules Form Submission
        │
        ▼
POST /webhook/onboard  (FastAPI)
        │
        ▼
Create session in Supabase
        │
        ▼
Agent sends first WhatsApp message (via Baileys)
        │
        ▼
User replies  ──────────────────────────────────────┐
        │                                           │
        ▼                                           │
Inbound message hits /webhook/inbound               │
        │                                           │
        ▼                                           │
Load session + conversation history from Supabase   │
        │                                           │
        ▼                                           │
Pass full history to Claude (with system prompt)    │
        │                                           │
        ▼                                           │
Claude generates next message                       │
        │                                           │
        ▼                                           │
Send via Baileys ───────────────────────────────────┘
        │
        ▼ (when agent determines onboarding is complete)
Mark session onboarded, log to Supabase
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python |
| Web framework | FastAPI |
| WhatsApp messaging | Baileys (existing layer) |
| AI | Claude via Anthropic API |
| Database | Supabase |
| Hosting | Standalone service (Railway or Render) |

---

## Agent System Prompt (shape of it)

The system prompt tells Claude:
- What the community is and who it's for
- What the agent's personality is (warm, human, not corporate)
- What it needs to learn from the user before handing over the link
- That it should never sound scripted or robotic
- That it should handle off-topic questions gracefully and bring the conversation back
- The invite link to share when the time is right
- That it should recognise when the conversation is done and close warmly

The conversation history is passed in full on every turn so Claude always has full context.

---

## Supabase Schema

### `onboarding_sessions`

```sql
id                uuid primary key
name              text
whatsapp          text
email             text nullable
state             text  -- 'initiated' | 'in_progress' | 'onboarded' | 'abandoned'
onboarded         boolean default false
submitted_at      timestamptz
last_message_at   timestamptz
follow_up_sent    boolean default false
```

### `onboarding_messages`

```sql
id                uuid primary key
session_id        uuid references onboarding_sessions(id)
role              text  -- 'agent' | 'user'
content           text
sent_at           timestamptz
```

The full message history for a session is loaded from `onboarding_messages` and passed to Claude on every turn.

---

## API Routes

### `POST /webhook/onboard`
Receives form submission from Hercules. Creates a session and fires the first message.

**Payload:**
```json
{
  "name": "Amaka",
  "whatsapp": "2348012345678",
  "email": "amaka@example.com",
  "submitted_at": "2026-05-11T10:00:00Z"
}
```

---

### `POST /webhook/inbound`
Receives incoming WhatsApp messages from Baileys. Loads session, calls Claude, sends reply.

---

### `POST /jobs/follow-up`
Cron job (runs every 15 mins). Checks for sessions that have been silent for 30+ minutes and haven't had a follow-up sent yet. Sends one gentle nudge.

---

### `POST /jobs/abandon`
Cron job (runs every hour). Marks sessions silent for 24+ hours as `abandoned`.

---

## Configuration (Per Client)

Everything client-specific is environment-variable driven, so this service can be reused for different community clients without code changes:

```env
COMMUNITY_NAME=
COMMUNITY_DESCRIPTION=
INVITE_LINK=
AGENT_NAME=
AGENT_TONE=          # e.g. "warm and casual" or "professional but friendly"
FOLLOW_UP_DELAY_MINS=30
ABANDON_AFTER_HOURS=24
```

---

## What This Is Not

- It is not rule-based. There are no `if user says X → reply Y` decision trees.
- It is not a chatbot widget. It runs entirely over WhatsApp.
- It is not part of Sellbot. It is a standalone service that shares the same WhatsApp/Baileys infrastructure pattern but has its own codebase, database, and agent logic.
