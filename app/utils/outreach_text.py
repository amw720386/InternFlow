def fill_outreach_placeholders(
    template: str,
    *,
    first_name: str,
    company_name: str,
    their_title: str,
) -> str:
    return (
        (template or "")
        .replace("{first_name}", first_name)
        .replace("{company_name}", company_name)
        .replace("{their_title}", their_title)
    )


def format_email_body(
    message_body: str,
    *,
    sender_name: str,
    portfolio_url: str | None = None,
) -> str:
    lines = [message_body.strip(), "", "Best,", sender_name.strip()]
    pu = (portfolio_url or "").strip()
    if pu:
        lines.extend(["", pu])
    return "\n".join(lines)
