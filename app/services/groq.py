"""
OnboardMe V2 — Groq AI Service
V2 conversational delivery: community profile + agent persona + member profile + touchpoint brief.

Each call receives the full context so the AI can continue the conversation naturally
toward the touchpoint's CTA without ever sounding like it's reading a script.
"""

import groq
import logging
from typing import List, Dict, Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class GroqService:
    def __init__(self):
        self.client = groq.Groq(api_key=settings.groq_api_key)
        self.model = "llama-3.3-70b-versatile"

    def _build_system_prompt(
        self,
        client_data: Dict[str, Any],
        member: Dict[str, Any],
        template: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the full system prompt with community, agent, member, and touchpoint context."""

        # ─── Community & Agent Identity ───
        parts = [
            f"You are {client_data.get('agent_name', 'the assistant')}, a warm and friendly community "
            f"assistant for {client_data.get('community_name', 'the community')}.",
            "",
            f"About {client_data.get('community_name', 'the community')}:",
            client_data.get('community_description', 'A community for professionals.'),
            "",
        ]

        # ─── Member Profile ───
        member_lines = [f"About the member you're talking to:"]
        member_lines.append(f"- Name: {member.get('name', 'there')}")
        if member.get("industry"):
            member_lines.append(f"- Industry: {member['industry']}")
        if member.get("company"):
            member_lines.append(f"- Company: {member['company']}")
        if member.get("stage"):
            member_lines.append(f"- Business stage: {member['stage']}")
        if member.get("building"):
            member_lines.append(f"- What they're building: {member['building']}")
        if member.get("focus_areas"):
            member_lines.append(f"- Focus areas: {', '.join(member['focus_areas'])}")
        if member.get("goals"):
            member_lines.append(f"- Goals: {member['goals']}")
        if member.get("why_community"):
            member_lines.append(f"- Why they joined: {member['why_community']}")
        if member.get("revenue_range"):
            member_lines.append(f"- Revenue range: {member['revenue_range']}")

        parts.append("\n".join(member_lines))
        parts.append("")

        # ─── Current Touchpoint Brief ───
        if template:
            touchpoint_lines = [
                "Current touchpoint:",
                f"- Purpose: {template.get('purpose', 'Continue the conversation')}",
                f"- CTA: {template.get('cta', 'Keep the member engaged')}",
                f"- AI rules and action guide: {template.get('brief', '')}",
                "",
                "CTA discipline:",
                "- The CTA is the goal of this touchpoint. Every reply should either move one small step toward it, deliver it, or close after it is accepted.",
                "- Be conversational, but do not drift into general chat once you have enough context to make the ask.",
                "- If the CTA needs a link and the relevant link is available below, include it when making the ask.",
                "- When sharing a link, put the full URL on its own line. Do not put commas, full stops, brackets, or extra words on the same line as the URL.",
                "- If the member's latest message gives enough information, acknowledge it briefly and make the CTA explicit in the same reply.",
                "- If you still need information before the CTA, ask exactly one short question that helps you make the CTA naturally.",
            ]
            # Only include fallback message if it exists and we're on the initial message
            if template.get("fallback_message"):
                touchpoint_lines.append(
                    f"- Note: If the member doesn't reply, this fallback will be sent later: "
                    f"{template['fallback_message']}"
                )
            parts.append("\n".join(touchpoint_lines))
            parts.append("")

            groups = template.get("community_groups") or []
            if groups:
                group_lines = ["MBN community groups available to route the member into:"]
                for group in groups:
                    if not group.get("active", True):
                        continue
                    line = f"- {group.get('name')}: {group.get('description')}"
                    if group.get("purpose"):
                        line += f" Purpose: {group['purpose']}"
                    if group.get("activity_day"):
                        line += f" Activity day: {group['activity_day']}"
                    if group.get("cta_guidance"):
                        line += f" CTA guidance: {group['cta_guidance']}"
                    if group.get("link"):
                        line += f" Link: {group['link']}"
                    group_lines.append(line)
                group_lines.append("When a group is relevant, encourage the member to share there. Do not invent links.")
                parts.append("\n".join(group_lines))
                parts.append("")

            events = template.get("community_events") or []
            if events:
                event_lines = ["Upcoming MBN events available to mention when relevant:"]
                for event in events:
                    if not event.get("active", True):
                        continue
                    line = f"- {event.get('title')}: starts {event.get('starts_at')}"
                    if event.get("description"):
                        line += f". {event['description']}"
                    if event.get("location"):
                        line += f" Location: {event['location']}"
                    if event.get("link"):
                        line += f" Link: {event['link']}"
                    event_lines.append(line)
                event_lines.append("Mention events naturally when they match the touchpoint or member's interests. Do not invent event dates, titles, locations, or links.")
                parts.append("\n".join(event_lines))
                parts.append("")
        else:
            parts.append(
                "This is a free-form conversation (not tied to a specific touchpoint). "
                "Continue naturally and helpfully."
            )
            parts.append("")

        # ─── Community Links ───
        links = []
        if client_data.get("invite_link"):
            links.append(f"- Community invite link: {client_data['invite_link']}")
        if client_data.get("calendly_link"):
            links.append(f"- Calendly booking: {client_data['calendly_link']}")
        if client_data.get("founder_stories_link"):
            links.append(f"- Founder Stories: {client_data['founder_stories_link']}")
        if client_data.get("operator_session_link"):
            links.append(f"- Operator Session: {client_data['operator_session_link']}")

        if links:
            parts.append("Community links (share when relevant to the conversation):")
            parts.append("\n".join(links))
            parts.append("")

        # ─── Capability Boundaries ───
        boundary_lines = [
            "Capability boundaries (follow these strictly):",
            "- You cannot post in any WhatsApp group for the member.",
            "- You cannot create WhatsApp groups, add members, introduce members to each other, assign buddies, change profiles, book sessions, or notify admins unless the system explicitly provides that tool.",
            "- You cannot do a member's intro for them. Do not say you can help them do an intro, make an intro, or handle an intro.",
            "- You may suggest a simple intro format only when useful, then ask the member to post it themselves in the relevant group.",
            "- Never claim an action has been completed unless the conversation history or system context proves it was completed.",
            "- If the member asks for something outside your powers, say what you can do: guide them, suggest wording, point them to the right group or link, or ask a human admin to help when the workflow explicitly requires human action.",
        ]
        parts.append("\n".join(boundary_lines))
        parts.append("")

        # ─── MBN Operating Rules ───
        operating_lines = [
            "MBN operating rules:",
            "- Keep every reply grounded in MBN, the member's profile, the current touchpoint, and the available group list.",
            "- Do not give generic community-building advice unless the member directly asks for strategy advice.",
            "- Private WhatsApp is for guidance and check-ins. Meaningful updates, asks, wins, offers, and opportunities should be routed back into the MBN groups.",
            "- Introduce the ecosystem progressively. Mention one relevant group or next action at a time instead of listing everything.",
            "- For a first intro, ask the member to share who they are, what they are building, and what support or goal they are focused on. They must send/post it themselves.",
        ]
        parts.append("\n".join(operating_lines))
        parts.append("")

        # ─── Style Rules ───
        style_lines = [
            "Style rules (follow these strictly):",
            "- WhatsApp messages, not emails. Keep messages to 1-3 sentences.",
            "- Never use bullet points or numbered lists unless absolutely unavoidable.",
            "- Use the member's name occasionally — not every message, just when it feels natural.",
            "- One thing at a time. Never ask two questions in one message.",
            "- Never say 'as an AI' or anything that breaks the persona.",
            "- If the member asks something outside the community context, answer helpfully and briefly, then return naturally.",
            "- Do not start with broad lines like 'building a community can be challenging' unless the member specifically asks about building a community.",
            "- When the CTA has been delivered and the member has acknowledged it — close the touchpoint warmly.",
            "- Do not keep the conversation going unnecessarily once the goal is achieved.",
            f"- Tone: {client_data.get('agent_tone', 'warm and conversational')}.",
        ]
        parts.append("\n".join(style_lines))

        return "\n".join(parts)

    def _format_history(self, messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Format conversation history for the LLM.
        Messages are in chronological order (oldest first).
        Map 'member' → 'user', 'agent' → 'assistant'.
        """
        formatted = []
        for msg in messages:
            role = "user" if msg["role"] == "member" else "assistant"
            formatted.append({"role": role, "content": msg["content"]})
        return formatted

    def _build_opening_instruction(self, template: Optional[Dict[str, Any]]) -> str:
        if not template:
            return (
                "Start this free-form WhatsApp conversation now. Keep it brief and useful. "
                "Do not send a Day 1 welcome unless the context explicitly says this is a welcome."
            )

        return (
            "Write the opening WhatsApp message for THIS scheduled touchpoint only.\n"
            f"Touchpoint key: {template.get('touchpoint_key', '')}\n"
            f"Purpose: {template.get('purpose', '')}\n"
            f"CTA: {template.get('cta', '')}\n"
            f"Brief: {template.get('brief', '')}\n\n"
            "Important: do not reuse a previous welcome or Day 1 opener unless this touchpoint is explicitly a welcome. "
            "If this is a follow-up, reminder, check-in, invite, feedback request, or escalation, write that specific message. "
            "Keep it to 1-3 sentences and make the CTA clear when appropriate."
        )

    def generate_response(
        self,
        client_data: Dict[str, Any],
        member: Dict[str, Any],
        messages: List[Dict[str, Any]],
        template: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate an AI response given full V2 context.

        Args:
            client_data: Community/client profile (name, description, links, agent name/tone)
            member: Full member profile (name, industry, stage, goals, etc.)
            messages: Full conversation history for this touchpoint (oldest first, includes latest member msg)
            template: Optional touchpoint template (purpose, cta, brief)

        Returns:
            Generated response text
        """

        system_prompt = self._build_system_prompt(client_data, member, template)
        formatted_history = self._format_history(messages)
        if not formatted_history:
            formatted_history = [{
                "role": "user",
                "content": self._build_opening_instruction(template),
            }]

        logger.info(
            f"Calling Groq with {len(formatted_history)} messages, "
            f"template: {template.get('touchpoint_key', 'none') if template else 'none'}"
        )

        try:
            chat_completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *formatted_history,
                ],
                temperature=0.7,
                max_tokens=500,
            )

            response = chat_completion.choices[0].message.content
            logger.info(f"Groq response ({len(response)} chars): {response[:80]}...")
            return response

        except Exception as e:
            logger.exception(f"Groq API call failed: {e}")
            return "I appreciate you sharing that with me. Let me think about the best way to help you with that."

    def generate_nudge(
        self,
        client_data: Dict[str, Any],
        member: Dict[str, Any],
        template: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate a short nudge for a silent conversation.
        No history — just a 1-sentence gentle reminder based on touchpoint context.
        """
        system_prompt = self._build_system_prompt(client_data, member, template)

        nudge_prompt = (
            "The member hasn't replied yet. Send a very short, warm follow-up message "
            "(1 sentence max). Do not repeat the original question. Just a gentle nudge. "
            "Something like 'Hey, no pressure — just checking in!' but personalised to the context."
        )

        try:
            chat_completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": nudge_prompt},
                ],
                temperature=0.7,
                max_tokens=150,
            )

            response = chat_completion.choices[0].message.content
            logger.info(f"Groq nudge ({len(response)} chars): {response[:80]}...")
            return response

        except Exception as e:
            logger.exception(f"Groq nudge API call failed: {e}")
            return "Hey! Just checking in — no rush, I'm here when you're ready."


groq_service = GroqService()
