import json
import re
from dataclasses import dataclass
from typing import Any

from app.ai.ai_client import get_openai_client

OUTREACH_AI_MODEL = "gpt-5-nano"

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")

RESEARCH_AND_OUTREACH_INSTRUCTIONS = """\
You are a research and outreach assistant helping a student find software engineering internships.

You MUST use the web search tool at least once to look up current, public information about the company (website, careers page, recent news, job postings, growth signals) and, when useful, the contact's public role context. Never fabricate facts — if you cannot determine something, say so in your reasoning.

The input payload includes an `industry` field representing the industry or sector the student is targeting. Use it alongside `company_industry` to gauge relevance when researching the company and writing the message.

──────────────────────────────────────
OUTPUT FORMAT
──────────────────────────────────────
Respond with a single JSON object only. No markdown fences, no prose before or after.

{
  "score_web_activity": <number 0-30>,
  "score_hiring_signals": <number 0-40>,
  "score_company_size": <number 0-30>,
  "reasoning": <string>,
  "message_score": <number 0-100>,
  "linkedin_message": <string>
}

──────────────────────────────────────
SCORING — three sub-scores that together define overall fit
──────────────────────────────────────

1. score_web_activity (0-30)
   LinkedIn / web presence and approachability of the contact.
   Higher when the person looks active (recent posts, public engagement, visible profile details).
   When you cannot determine activity level, say so in reasoning and assign a moderate default.

2. score_hiring_signals (0-40)
   Whether the company appears to be hiring interns or new-grads RIGHT NOW, based on web research.
   Consider: careers page listings, recent job postings, press about headcount growth, university partnerships, internship programmes, etc.
   If nothing is found, lean toward a lower score and note the absence in reasoning.

3. score_company_size (0-30)
   Weight toward smaller / earlier-stage companies when the student's goal is proactive DM outreach: tiny teams and founders often hire informally, while huge enterprise TA orgs are harder to reach cold.
   Use `company_size_range` from the input and anything you find via web search.

Calibration baseline: a score of 50 total (across the three sub-scores) represents a typical recruiter at a midsize business with mediocre web activity and no visible open positions for the role you are looking for.

──────────────────────────────────────
message_score (0-100, independent)
──────────────────────────────────────
Quality of the linkedin_message on its own — clarity, professionalism, specificity from research, appropriate length, and correct handling of the email branch below. This is NOT a duplicate of the fit scores.

──────────────────────────────────────
linkedin_message guidelines
──────────────────────────────────────
Write a natural, concise LinkedIn DM (roughly under 1200 characters). Sound like a capable student — not salesy, not desperate.

Use these placeholders where the recipient's details belong:
  {first_name}   — their first name
  {company_name} — their company
  {their_title}  — their job title

Beyond that, write freely. Incorporate specifics you discovered through research to make the message feel genuine, not templated.

Email branch (driven by the `has_verified_email` field in the input):
• If has_verified_email is TRUE  → you may mention that you have (or will) also reach out by email, since a direct address was available.
• If has_verified_email is FALSE → do NOT imply you have their email. Instead, politely ask if they could share one so you can send materials, or offer to share a link to your portfolio / hosted resume if they prefer.

──────────────────────────────────────
reasoning
──────────────────────────────────────
2-5 sentences covering: company scale/stage (from research), whether they appear to be hiring interns/new-grads now (with caveats if uncertain), whether this person can plausibly help, and any notes on LinkedIn approachability or public activity (state when you cannot tell)."""


@dataclass(frozen=True)
class LeadOutreachAIResult:
    fit_score: float
    reasoning: str
    linkedin_message: str
    message_score: float
    score_web_activity: float
    score_hiring_signals: float
    score_company_size: float
    ai_input_tokens: int | None = None
    ai_output_tokens: int | None = None
    ai_total_tokens: int | None = None


def _normalize_usage(u: Any) -> tuple[int | None, int | None, int | None]:
    if u is None:
        return None, None, None
    if hasattr(u, "input_tokens"):
        return int(u.input_tokens), int(u.output_tokens), int(u.total_tokens)
    if hasattr(u, "prompt_tokens"):
        return int(u.prompt_tokens), int(u.completion_tokens), int(u.total_tokens)
    return None, None, None


def _fallback_template(first_name: str, company_name: str, their_title: str) -> str:
    return (
        "Hi {first_name}, I am a software engineering student reaching out after seeing your role as {their_title} "
        "at {company_name}. I would love to learn whether your team has any internship or new-grad opportunities "
        "and who might be best to chat with. If you are open to it, could you share an email where I can send a short "
        "note and a link to my portfolio, or let me know if you would prefer a link to my site here instead?"
    )


def _parse_outreach_json(text: str) -> dict[str, Any] | None:
    m = _JSON_OBJECT_RE.search(text.strip())
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def _result_from_parsed(
    data: dict[str, Any],
    *,
    fallback_message: str,
    ai_input_tokens: int | None = None,
    ai_output_tokens: int | None = None,
    ai_total_tokens: int | None = None,
) -> LeadOutreachAIResult:
    web = max(0.0, min(30.0, float(data.get("score_web_activity", 0))))
    hiring = max(0.0, min(40.0, float(data.get("score_hiring_signals", 0))))
    size = max(0.0, min(30.0, float(data.get("score_company_size", 0))))
    fit = web + hiring + size

    msg_score = max(0.0, min(100.0, float(data.get("message_score", 0))))
    reasoning = str(data.get("reasoning", ""))[:4000]
    msg = str(data.get("linkedin_message", "")).strip() or fallback_message

    return LeadOutreachAIResult(
        fit_score=fit,
        reasoning=reasoning,
        linkedin_message=msg[:4000],
        message_score=msg_score,
        score_web_activity=web,
        score_hiring_signals=hiring,
        score_company_size=size,
        ai_input_tokens=ai_input_tokens,
        ai_output_tokens=ai_output_tokens,
        ai_total_tokens=ai_total_tokens,
    )


def _build_user_input_payload(
    *,
    full_name: str | None,
    first_name: str | None,
    title: str | None,
    company_name: str | None,
    company_domain: str | None,
    company_industry: str | None,
    company_size_range: str | None,
    company_location: str | None,
    linkedin_url: str | None,
    recipient_email: str | None,
    target_industry: str | None,
) -> str:
    has_email = bool((recipient_email or "").strip())
    payload = {
        "first_name": (first_name or "").strip() or None,
        "full_name": (full_name or "").strip() or None,
        "their_title": (title or "").strip() or None,
        "company_name": (company_name or "").strip() or None,
        "company_domain": (company_domain or "").strip() or None,
        "company_industry": (company_industry or "").strip() or None,
        "company_size_range": (company_size_range or "").strip() or None,
        "company_location": (company_location or "").strip() or None,
        "linkedin_url": (linkedin_url or "").strip() or None,
        "has_verified_email": has_email,
        "industry": (target_industry or "").strip() or None,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def research_and_draft_linkedin_outreach(
    *,
    full_name: str | None,
    first_name: str | None,
    title: str | None,
    company_name: str | None,
    company_domain: str | None,
    company_industry: str | None,
    company_size_range: str | None,
    company_location: str | None,
    linkedin_url: str | None,
    recipient_email: str | None,
    target_industry: str | None = None,
) -> LeadOutreachAIResult:
    fn = (first_name or "").strip() or ((full_name or "").split()[0] if (full_name or "").split() else "there")
    co = (company_name or "").strip() or "your company"
    tt = (title or "").strip() or "your role"
    fallback_msg = _fallback_template(fn, co, tt)

    client = get_openai_client()
    if client is None:
        return LeadOutreachAIResult(
            fit_score=0.0,
            reasoning="OPENAI_API_KEY is not set.",
            linkedin_message=fallback_msg,
            message_score=0.0,
            score_web_activity=0.0,
            score_hiring_signals=0.0,
            score_company_size=0.0,
        )

    user_block = _build_user_input_payload(
        full_name=full_name,
        first_name=first_name,
        title=title,
        company_name=company_name,
        company_domain=company_domain,
        company_industry=company_industry,
        company_size_range=company_size_range,
        company_location=company_location,
        linkedin_url=linkedin_url,
        recipient_email=recipient_email,
        target_industry=target_industry,
    )

    user_prompt = (
        "Research and produce the JSON described in your instructions.\n\n"
        "Contact and company JSON (from our database / PDL; may be incomplete):\n"
        f"{user_block}"
    )

    in_tok: int | None = None
    out_tok: int | None = None
    tot_tok: int | None = None

    def _try_responses(*, use_web_search: bool) -> str:
        nonlocal in_tok, out_tok, tot_tok
        kwargs: dict[str, Any] = {
            "model": OUTREACH_AI_MODEL,
            "instructions": RESEARCH_AND_OUTREACH_INSTRUCTIONS,
            "input": user_prompt,
            "max_output_tokens": 8192,
        }
        if use_web_search:
            kwargs["tools"] = [{"type": "web_search"}]
        resp = client.responses.create(**kwargs)
        inp, outp, tot = _normalize_usage(getattr(resp, "usage", None))
        if inp is not None:
            in_tok, out_tok, tot_tok = inp, outp, tot
        return (resp.output_text or "").strip()

    raw = ""
    try:
        raw = _try_responses(use_web_search=True)
    except Exception:
        try:
            raw = _try_responses(use_web_search=False)
        except Exception:
            raw = ""

    if not raw:
        try:
            r2 = client.chat.completions.create(
                model=OUTREACH_AI_MODEL,
                messages=[
                    {"role": "system", "content": RESEARCH_AND_OUTREACH_INSTRUCTIONS},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=4096,
            )
            raw = (r2.choices[0].message.content or "").strip()
            inp, outp, tot = _normalize_usage(getattr(r2, "usage", None))
            if inp is not None:
                in_tok, out_tok, tot_tok = inp, outp, tot
        except Exception:
            return LeadOutreachAIResult(
                fit_score=0.0,
                reasoning="AI request failed after retries.",
                linkedin_message=fallback_msg,
                message_score=0.0,
                score_web_activity=0.0,
                score_hiring_signals=0.0,
                score_company_size=0.0,
            )

    parsed = _parse_outreach_json(raw)
    if not parsed:
        return LeadOutreachAIResult(
            fit_score=40.0,
            reasoning=(raw[:800] if raw else "Empty model output."),
            linkedin_message=fallback_msg,
            message_score=35.0,
            score_web_activity=0.0,
            score_hiring_signals=0.0,
            score_company_size=0.0,
            ai_input_tokens=in_tok,
            ai_output_tokens=out_tok,
            ai_total_tokens=tot_tok,
        )
    return _result_from_parsed(
        parsed,
        fallback_message=fallback_msg,
        ai_input_tokens=in_tok,
        ai_output_tokens=out_tok,
        ai_total_tokens=tot_tok,
    )
