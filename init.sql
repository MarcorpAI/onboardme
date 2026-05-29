-- OnboardMe V2 Schema
-- All tables created via SQLAlchemy, but this file serves as a reference
-- and is used by docker-compose for the initial database setup.

CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    community_name TEXT NOT NULL,
    community_description TEXT,
    agent_name TEXT NOT NULL,
    agent_tone TEXT DEFAULT 'warm and conversational',
    webhook_secret TEXT NOT NULL,
    invite_link TEXT,
    calendly_link TEXT,
    founder_stories_link TEXT,
    operator_session_link TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    whatsapp TEXT NOT NULL,
    whatsapp_lid TEXT,
    email TEXT,
    industry TEXT,
    company TEXT,
    stage TEXT,
    building TEXT,
    focus_areas TEXT[],
    why_community TEXT,
    goals TEXT,
    revenue_range TEXT,
    approved_at TIMESTAMPTZ,
    approval_source TEXT DEFAULT 'webhook',
    journey_day INT DEFAULT 0,
    journey_phase TEXT DEFAULT 'foundation',
    engagement_score FLOAT DEFAULT 0.0,
    state TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    touchpoint_key TEXT,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    state TEXT DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    touchpoint_key TEXT
);

CREATE TABLE IF NOT EXISTS journey_touchpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    touchpoint_key TEXT NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    fired_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    state TEXT DEFAULT 'pending',
    conversation_id UUID,
    requires_human BOOLEAN DEFAULT FALSE,
    nudge_sent BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    touchpoint_key TEXT NOT NULL,
    purpose TEXT NOT NULL,
    cta TEXT NOT NULL,
    brief TEXT NOT NULL,
    fallback_message TEXT,
    active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS community_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    purpose TEXT,
    link TEXT,
    activity_day TEXT,
    cta_guidance TEXT,
    sort_order INT DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS community_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ,
    location TEXT,
    link TEXT,
    reminder_hours_before INT DEFAULT 24,
    active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    brief TEXT,
    message TEXT NOT NULL,
    status TEXT DEFAULT 'draft',
    recipient_source TEXT DEFAULT 'manual',
    include_approved_members BOOLEAN DEFAULT FALSE,
    member_count INT DEFAULT 0,
    manual_count INT DEFAULT 0,
    total_recipients INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    queued_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS broadcast_recipients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    broadcast_id UUID NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
    member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    whatsapp TEXT NOT NULL,
    source TEXT DEFAULT 'manual',
    status TEXT DEFAULT 'pending',
    attempts INT DEFAULT 0,
    last_error TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_members_whatsapp ON members(whatsapp);
CREATE INDEX IF NOT EXISTS idx_members_whatsapp_lid ON members(whatsapp_lid);
CREATE INDEX IF NOT EXISTS idx_members_client_id ON members(client_id);
CREATE INDEX IF NOT EXISTS idx_members_state ON members(state);

CREATE INDEX IF NOT EXISTS idx_conversations_member_id ON conversations(member_id);
CREATE INDEX IF NOT EXISTS idx_conversations_state ON conversations(state);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_member_id ON messages(member_id);

CREATE INDEX IF NOT EXISTS idx_touchpoints_member_id ON journey_touchpoints(member_id);
CREATE INDEX IF NOT EXISTS idx_touchpoints_state ON journey_touchpoints(state);
CREATE INDEX IF NOT EXISTS idx_touchpoints_scheduled_for ON journey_touchpoints(scheduled_for);

CREATE INDEX IF NOT EXISTS idx_templates_client_id ON templates(client_id);
CREATE INDEX IF NOT EXISTS idx_templates_touchpoint_key ON templates(touchpoint_key);
CREATE INDEX IF NOT EXISTS idx_community_groups_client_id ON community_groups(client_id);
CREATE INDEX IF NOT EXISTS idx_community_events_client_id ON community_events(client_id);
CREATE INDEX IF NOT EXISTS idx_community_events_starts_at ON community_events(starts_at);
CREATE INDEX IF NOT EXISTS idx_broadcasts_client_id ON broadcasts(client_id);
CREATE INDEX IF NOT EXISTS idx_broadcasts_status ON broadcasts(status);
CREATE INDEX IF NOT EXISTS idx_broadcast_recipients_broadcast_id ON broadcast_recipients(broadcast_id);
CREATE INDEX IF NOT EXISTS idx_broadcast_recipients_status ON broadcast_recipients(status);
