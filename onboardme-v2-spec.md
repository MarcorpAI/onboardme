# OnboardMe — V2 Spec
### AI-Powered WhatsApp Community Onboarding Engine

> Continuing from V1. V1 covered the basic webhook trigger → single conversation → invite link flow.
> V2 covers the full 90-day journey engine, conversational message delivery, settings dashboard, client integration docs, and multi-tenant architecture.

---

## What Changed from V1

V1 was a simple: signup → AI talks → sends invite link.

V2 is a full 90-day onboarding journey engine. The key differences:

- **Approval-gated** — the journey doesn't start on signup. It starts when the client's backend fires an approval signal to our webhook.
- **Scheduled journey** — 30+ touchpoints across 90 days, each with a defined purpose, not just a single conversation.
- **Conversational delivery** — messages are no longer long blobs of text fired at the member. The AI delivers the intent of each touchpoint through natural back-and-forth conversation. The CTA still lands. It just lands better.
- **Conditional logic** — silence triggers Yellow Flag nudges. Deeper silence triggers Red Flag escalation to a human.
- **Settings dashboard** — a simple web app for the community admin to configure templates, view member journeys, and override the AI when needed.
- **Headless-first** — built for clients who have their own backend. They just call our webhook. No dashboard required on their side.

---

## The Core Insight: Conversational Delivery

The MBN onboarding templates are excellent. But they are written for a human to copy-paste, so they're long — 150 to 300 words per message. A WhatsApp member receiving a 300-word message from an unknown number at 9am is going to scroll past it.

The fix: **the AI doesn't send the full template. It uses the template as a brief.**

Each scheduled touchpoint has:
- A **purpose** (what this interaction needs to achieve)
- A **CTA** (the one thing we need the member to do or feel)
- A **template** (the full message, used as context/brief for the AI, not as a script)

When the touchpoint fires, the AI sends a short, warm, human opening — 1 to 3 sentences max. If the member replies, the AI continues the conversation naturally until the CTA is delivered. If the member doesn't reply, the full template intent is still captured in a single follow-up message (shorter version) after the configured delay.

**Example — Day 7 Focus Question**

Template intent: Understand what the member is most focused on in their business right now. Use the answer to connect them to the right people and conversations.

❌ What the old way looks like:
> "Hi Amaka, You've been in MBN for a full week. That's worth marking. One question before the weekend: What's the one thing you're most focused on in your business right now? Your answer helps me connect you to the right people and the right conversations inside MBN. Have a good weekend. — Uvie"

✅ What the AI sends instead:
> "Amaka 👋 one week in MBN. What's the one thing taking most of your energy in your business right now?"

Member replies. AI responds. Conversation happens. CTA lands.

---

## System Architecture

```
CLIENT BACKEND
      │
      │  POST /webhook/onboard  (on admin approval)
      ▼
ONBOARDME API (FastAPI)
      │
      ├── Create member record
      ├── Schedule 90-day journey (APScheduler)
      └── Fire Day 1 messages immediately
            │
            ▼
      JOURNEY ENGINE
            │
            ├── Scheduled touchpoints fire per timeline
            │         │
            │         ▼
            │   AI generates short opening message
            │         │
            │         ▼
            │   Send via WhatsApp (Baileys bridge)
            │
            └── Member replies
                      │
                      ▼
              POST /webhook/inbound
                      │
                      ▼
              Load member + journey state + conversation history
                      │
                      ▼
              Pass context to Claude
                      │
                      ▼
              Claude continues conversation toward touchpoint CTA
                      │
                      ▼
              Save to DB → Send via Baileys

SILENCE DETECTION (cron every 15 mins)
      │
      ├── Silent 30+ mins on active touchpoint → Yellow Flag nudge
      └── Silent 3+ days → Red Flag → escalate to human in dashboard

SETTINGS DASHBOARD (Next.js)
      │
      ├── Configure community profile
      ├── Edit message templates
      ├── View member journeys
      ├── Read conversation threads
      └── Send manual override message
```

---

## The 90-Day Journey Engine

### Journey Phases

| Phase | Days | Focus |
|---|---|---|
| Foundation | 1–14 | Welcome, orientation, buddy intro, first engagement |
| Integration | 15–56 | Deepening, re-engagement, programme routing |
| Consolidation | 57–90 | Review, reflection, full member status |

### Touchpoint Schedule

Each touchpoint has a `day`, `name`, `purpose`, `cta`, `channel`, `automation` flag, and `conditional` flag.

| Day | Name | Automation | Conditional |
|---|---|---|---|
| 1 | Welcome DM | Yes | No |
| 1 | Orientation Checklist | Yes | No |
| 2 | Buddy Intro | No (human sends) | No |
| 3 | No Response Follow-up | Yes | Yes — only if no reply to Day 1 |
| 5 | First Personal Check-in | Yes | No |
| 7 | Focus Question | Yes | No |
| 9 | Operator Session Invite | Yes | No |
| 14 | 2-Week Check-in | Yes | No |
| 15 | Session Reminder (48hrs) | Yes | No |
| 21 | Yellow Flag DM | Yes | Yes — only if silent |
| 21 | Red Flag Escalation | No (human call) | Yes — only if still silent |
| 28 | 4-Week Check-in | Yes | No |
| 30 | Personal Wellbeing Check | Yes | No |
| 35 | Founder Lab Pitch | No (human sends) | Yes — conditional on profile |
| 35 | Founder Stories Invite | Yes | Conditional |
| 42 | Operator Session Feedback | Yes | No |
| 49 | Member Spotlight Invite | Yes | No |
| 56 | Buddy Closure | Yes | No |
| 60 | 60-Day Review Invite | Yes | No |
| 90 | Integration Confirmed | System | No |

Touchpoints marked `No` on automation are surfaced in the dashboard as tasks for the admin to action manually.

### Touchpoint Data Model

Each touchpoint in the DB is an instance tied to a member:

```sql
journey_touchpoints
  id                uuid primary key
  member_id         uuid references members(id)
  touchpoint_key    text              -- e.g. 'day_1_welcome', 'day_7_focus'
  scheduled_for     timestamptz       -- absolute datetime calculated from approval_date + day offset
  fired_at          timestamptz nullable
  completed_at      timestamptz nullable
  state             text              -- 'pending' | 'fired' | 'in_conversation' | 'completed' | 'skipped'
  conversation_id   uuid nullable     -- links to the conversation thread for this touchpoint
  requires_human    boolean default false
```

### Silence & Conditional Logic

When a touchpoint fires and enters `in_conversation` state:

- After **30 minutes** of no reply → send one short nudge (different per touchpoint, AI-generated)
- After **24 hours** of no reply → mark touchpoint `completed` (timed out), move to next
- Day 21 Yellow Flag fires only if `engagement_score < threshold` (calculated from reply rate across previous touchpoints)
- Day 21 Red Flag is surfaced as a task in the admin dashboard — it cannot be automated because it's a call

---

## Conversational AI Design

### How Claude Gets Context Per Turn

On every inbound message, Claude receives:

```
SYSTEM PROMPT:
  - Community profile (name, description, values, what MBN is)
  - Agent persona (name, tone, who they are)
  - Member profile (name, business, industry, stage, goals — from signup data)
  - Current touchpoint brief (purpose + CTA for this phase of the journey)
  - Instructions on message length and style

USER/ASSISTANT HISTORY:
  - Full conversation thread for the current touchpoint

CURRENT MESSAGE:
  - The member's latest reply
```

Claude's job: continue the conversation naturally toward the touchpoint CTA. It doesn't know it's on "Day 7". It knows it's trying to understand what the member is currently most focused on in their business.

### Message Style Rules (in system prompt)

- WhatsApp messages, not emails. 1–3 sentences per message.
- Never use bullet points or numbered lists unless explicitly making a list that can't be avoided.
- Use the member's name occasionally — not every message.
- One thing at a time. Never ask two questions in one message.
- Never say "as an AI" or anything that breaks the persona.
- If the member asks something outside the community context, answer helpfully and briefly, then return naturally to the conversation.
- When the CTA has been delivered and the member has acknowledged — close the touchpoint warmly and don't keep the conversation going unnecessarily.

### Touchpoint Brief Format (passed to Claude)

```
CURRENT TOUCHPOINT:
  Purpose: Understand what the member is most focused on in their business right now.
  CTA: Get a clear answer to "what's the one thing you're most focused on right now?" and acknowledge it warmly.
  Context: This is Day 7. The member has been in the community for a week. This answer will be used to connect them to relevant people and sessions.
  Do not: Pitch anything. Don't mention Founder Lab. Just have a genuine conversation.
```

---

## Database Schema

### `members`

```sql
id                  uuid primary key
name                text not null
whatsapp            text not null
whatsapp_lid        text nullable
email               text nullable
industry            text nullable
company             text nullable
stage               text nullable           -- 'idea' | 'pre-revenue' | 'first_customers' | 'growing' | 'scaling'
building            text nullable           -- what they're building (freeform)
focus_areas         text[] nullable         -- challenges they flagged on signup
why_community       text nullable
goals               text nullable
revenue_range       text nullable
approved_at         timestamptz nullable
approval_source     text default 'webhook'  -- 'webhook' | 'dashboard'
journey_day         int default 0
journey_phase       text default 'foundation'
engagement_score    float default 0.0       -- 0.0 to 1.0, calculated from reply rate
state               text default 'pending'  -- 'pending' | 'active' | 'completed' | 'churned'
created_at          timestamptz default now()
last_active_at      timestamptz
```

### `conversations`

```sql
id                  uuid primary key
member_id           uuid references members(id)
touchpoint_key      text nullable           -- null for free-form inbound outside a touchpoint
opened_at           timestamptz default now()
closed_at           timestamptz nullable
state               text default 'open'     -- 'open' | 'closed'
```

### `messages`

```sql
id                  uuid primary key
conversation_id     uuid references conversations(id)
member_id           uuid references members(id)
role                text not null           -- 'agent' | 'member'
content             text not null
sent_at             timestamptz default now()
touchpoint_key      text nullable
```

### `journey_touchpoints`

```sql
id                  uuid primary key
member_id           uuid references members(id)
touchpoint_key      text not null
scheduled_for       timestamptz not null
fired_at            timestamptz nullable
completed_at        timestamptz nullable
state               text default 'pending'
conversation_id     uuid nullable
requires_human      boolean default false
nudge_sent          boolean default false
```

### `templates`

```sql
id                  uuid primary key
client_id           uuid references clients(id)
touchpoint_key      text not null
purpose             text not null
cta                 text not null
brief               text not null           -- full context for AI
fallback_message    text nullable           -- if member doesn't reply, send this after timeout
active              boolean default true
updated_at          timestamptz
```

### `clients`

```sql
id                  uuid primary key
name                text not null
community_name      text not null
community_description text
agent_name          text not null
agent_tone          text default 'warm and conversational'
webhook_secret      text not null           -- for verifying inbound webhook calls
invite_link         text nullable
calendly_link       text nullable
founder_stories_link text nullable
operator_session_link text nullable
created_at          timestamptz default now()
```

---

## API Routes

### Webhook Endpoints

#### `POST /webhook/onboard`
Triggered by client backend on member approval. Starts the 90-day journey.

**Headers:**
```
X-Webhook-Secret: <client_webhook_secret>
```

**Payload:**
```json
{
  "name": "Amaka Okonkwo",
  "whatsapp": "2348012345678",
  "email": "amaka@example.com",
  "industry": "Technology & Software",
  "company": "PayStack Clone Ltd",
  "stage": "growing",
  "building": "A payments API for West Africa",
  "focus_areas": ["marketing_growth", "hiring"],
  "why_community": "I want to be around founders who are actually building",
  "goals": "Get to 1000 active merchants",
  "revenue_range": "100k-1M",
  "approved_at": "2026-05-11T10:00:00Z"
}
```

**What happens:**
1. Creates member record
2. Schedules all 90 touchpoints with absolute timestamps
3. Fires Day 1 Welcome DM and Checklist immediately
4. Returns `{ "status": "success", "member_id": "uuid" }`

---

#### `POST /webhook/inbound`
Receives incoming WhatsApp messages from the Baileys bridge.

**Payload:**
```json
{
  "whatsapp": "2348012345678",
  "message": "Yeah I'm really focused on getting my first 10 customers right now",
  "jid": "2348012345678@s.whatsapp.net"
}
```

**What happens:**
1. Finds member by whatsapp/jid
2. Finds open conversation for that member
3. Saves member message to DB
4. Loads full conversation history + member profile + touchpoint brief
5. Calls Claude, gets response
6. Saves agent response + sends via Baileys
7. Updates touchpoint state if CTA detected as completed

---

### Cron Jobs

#### `POST /jobs/fire-touchpoints`
Runs every 5 minutes. Finds all `journey_touchpoints` where `state = 'pending'` and `scheduled_for <= now()`. Fires each one.

#### `POST /jobs/nudge-silent`
Runs every 15 minutes. Finds touchpoints in `in_conversation` state with no member reply in the last 30 minutes and `nudge_sent = false`. Sends a short AI-generated nudge and sets `nudge_sent = true`.

#### `POST /jobs/timeout-touchpoints`
Runs every hour. Finds touchpoints in `in_conversation` state with no activity in 24 hours. Marks them `completed` and closes the conversation.

#### `POST /jobs/flag-disengaged`
Runs daily. Finds members with `engagement_score < 0.3` who have been active for 14+ days. Creates a `requires_human = true` touchpoint task in the dashboard.

---

## Settings Dashboard

A simple Next.js web app. Not a full CRM — just enough for the community admin to configure and monitor.

### Pages

**`/login`**
Simple email + password. Supabase Auth.

**`/dashboard`**
Overview:
- Total active members
- Members in Foundation / Integration / Consolidation phase
- Touchpoints fired today
- Members flagged for human follow-up (Red Flags)
- Recent activity feed (last 10 messages across all members)

**`/members`**
Table of all members with:
- Name, business, industry, stage
- Journey day (e.g. "Day 23")
- Engagement score (low / medium / high)
- Last active
- Quick action: View conversation, Send message, Mark churned

**`/members/[id]`**
Member detail page:
- Full profile (from signup data)
- Journey timeline — all 90 touchpoints, each showing state (pending / fired / completed / requires human)
- Conversation threads — click any touchpoint to expand the full conversation
- Manual message box — admin can type and send directly, overriding the AI for that member

**`/templates`**
List of all touchpoints. For each:
- Touchpoint name + day
- Purpose field (editable)
- CTA field (editable)
- Brief field (editable — this is what Claude reads)
- Fallback message (editable — sent if member doesn't reply)
- Toggle: active / inactive

**`/settings`**
Community configuration:
- Community name + description
- Agent name + tone
- Invite link
- Calendly link (for 60-day review bookings)
- Founder Stories link + schedule
- Operator Session link + schedule
- Webhook secret (read-only, with regenerate button)
- Follow-up delay (minutes before nudge)
- Timeout window (hours before touchpoint auto-completes)

---

## Productisation Model (Headless vs Hosted)

### Mode A — Headless (for clients with their own backend)
Client calls `POST /webhook/onboard` when they approve a member. That's their entire integration. See Integration Docs below.

### Mode B — Hosted (future — for clients without a backend)
OnboardMe provides a hosted signup form + approval dashboard. Client shares the form link. Signups land in OnboardMe. Admin approves from the OnboardMe dashboard directly. No webhook integration needed.

MBN is a Mode A client. Mode B is built when the next client needs it.

---

## Client Integration Docs

> This section is the handoff document for MBN (or any Mode A client).

---

### Integrating OnboardMe into Your Backend

OnboardMe is a headless onboarding engine. You own the signup flow and the approval decision. When you approve a member, you fire one API call to us and we handle everything from there — WhatsApp messages, follow-ups, the full 90-day journey.

#### Step 1 — Get your webhook secret

Log into your OnboardMe dashboard at `[your-dashboard-url]` and go to **Settings**. Copy your **Webhook Secret**. You'll need it to authenticate requests.

#### Step 2 — Call the webhook on approval

When your admin approves a member in your backend, make a `POST` request to:

```
POST https://api.onboardme.app/webhook/onboard
```

**Headers:**
```
Content-Type: application/json
X-Webhook-Secret: your_webhook_secret_here
```

**Body:**
```json
{
  "name": "Full name of the member",
  "whatsapp": "International format e.g. 2348012345678",
  "email": "member@example.com",
  "industry": "Technology & Software",
  "company": "Company name",
  "stage": "growing",
  "building": "What they're building (freeform text)",
  "focus_areas": ["marketing_growth", "sales"],
  "why_community": "Why they want to join (freeform)",
  "goals": "What they're hoping to get (freeform)",
  "revenue_range": "100k-1M",
  "approved_at": "2026-05-11T10:00:00Z"
}
```

**Required fields:** `name`, `whatsapp`
**Optional but recommended:** everything else. The more context you pass, the more personalised the AI's conversations will be.

**WhatsApp format:** always send in international format without the `+`. For Nigerian numbers: `2348012345678`, not `08012345678` or `+2348012345678`.

**Successful response:**
```json
{
  "status": "success",
  "member_id": "a1b2c3d4-..."
}
```

**Error responses:**
```json
{ "status": "error", "detail": "Invalid webhook secret" }           // 401
{ "status": "error", "detail": "Missing required field: name" }     // 422
{ "status": "error", "detail": "Member already exists" }            // 409
```

#### Step 3 — Test it

Use this test payload to verify the integration:

```bash
curl -X POST https://api.onboardme.app/webhook/onboard \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: your_secret" \
  -d '{
    "name": "Test Member",
    "whatsapp": "2348012345678",
    "email": "test@example.com"
  }'
```

A WhatsApp message will arrive on the number you provided within 30 seconds of a successful call.

#### Step 4 — Handle duplicate signups (optional but recommended)

If a member resubmits your signup form, your backend should check before calling the webhook again. If you call `/webhook/onboard` with a WhatsApp number that already has an active journey, OnboardMe will return a `409` and not create a duplicate.

#### Notes

- You do not need to do anything else. Inbound replies from members come directly to the Baileys bridge — you don't receive or handle them.
- You can monitor member journeys and conversations from your OnboardMe dashboard.
- If you need to pause or cancel a member's journey, do it from the dashboard or call `DELETE /members/{member_id}/journey`.

---

## What's Not in V2 (Parked for V3)

- **Mode B hosted form + dashboard** — build when the second non-technical client comes
- **Buddy intro automation** — Day 2 buddy intro is still manual because it requires a 3-way WhatsApp group, which Baileys can do but needs careful handling
- **Email channel** — Day 1 welcome email is still manual. Email automation (Resend/Postmark) is a V3 addition
- **Analytics** — engagement score trends, cohort drop-off, reply rate per touchpoint
- **Multi-client isolation** — V2 is single-tenant per deployment. Multi-tenant (one deployment, many clients) is a V3 architecture decision
