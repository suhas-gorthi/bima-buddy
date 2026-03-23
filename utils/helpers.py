"""
Utility helpers for Bima Buddy
"""

import json
import re


def extract_json_block(text: str) -> dict:
    """Extract the first JSON code block from agent response text."""
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Fallback: try to find a raw JSON object with known keys
    for key in ["profile_updates", "recommendations", "prefilled_fields", "rejection_type", "win_probability"]:
        pattern = rf'\{{[^{{}}]*"{key}"[^{{}}]*\}}'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


def clean_response_text(text: str) -> str:
    """Remove JSON code blocks from response text for display."""
    cleaned = re.sub(r"```json\s*.*?\s*```", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def calculate_profile_completeness(profile: dict) -> float:
    """Calculate what percentage of profile fields are filled."""
    if not profile:
        return 0.0
    filled = sum(1 for v in profile.values() if v is not None and v != "" and v != "None")
    return round(filled / len(profile), 2)


def format_currency(amount) -> str:
    """Format a number as Indian currency."""
    try:
        amt = int(amount)
        if amt >= 10_000_000:
            return f"₹{amt / 10_000_000:.1f}Cr"
        elif amt >= 100_000:
            return f"₹{amt / 100_000:.1f}L"
        elif amt >= 1000:
            return f"₹{amt:,}"
        else:
            return f"₹{amt}"
    except (ValueError, TypeError):
        return f"₹{amount}"


def get_phase_label(phase: str) -> str:
    """Human-readable label for conversation phase."""
    labels = {
        "greeting": "👋 Getting Started",
        "profiling": "📝 Building Your Profile",
        "recommending": "💡 Finding Best Plans",
        "buying": "🛒 Application Form",
        "complete": "✅ All Done",
    }
    return labels.get(phase, phase.title())


def merge_profile_updates(current_profile: dict, updates: dict) -> dict:
    """Merge profile updates from agent response into current profile."""
    updated = current_profile.copy()
    for key, value in updates.items():
        if value is not None and key in updated:
            # Don't overwrite with None or empty
            if value not in (None, "", "null", "None"):
                updated[key] = value
    return updated


SAMPLE_REJECTION_LETTER = """Dear Mr. Sharma,

Re: Claim No. SH/2024/78432 — Rejection Notice

We regret to inform you that your health insurance claim for the hospitalization of your daughter (Priya Sharma, aged 4) at Apollo Hospital, New Delhi from 15-Nov-2024 to 20-Nov-2024 has been rejected.

Amount Claimed: ₹1,45,000

Reason for Rejection: The patient has been diagnosed with Congenital Heart Defect (CHD), which is classified as a Pre-Existing Disease (PED) as per Clause 4.1 of your policy terms. As per our records, this condition was present at birth and therefore existed prior to the policy inception date.

Policy Number: SH-COMP-2019-112345
Policy Start Date: 01-March-2019
Hospitalization Date: 15-November-2024

Your policy has been in force for 5 years and 8 months. However, Congenital Heart Defect is listed as an exclusion under Schedule II, Sub-clause 4(b) of your policy.

We regret the inconvenience caused.

Regards,
Claims Department
Star Health & Allied Insurance Co. Ltd."""
