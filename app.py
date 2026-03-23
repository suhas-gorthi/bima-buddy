"""
Bima Buddy — AI Insurance Concierge
Streamlit Prototype
"""

import base64
import json
import os
import sys

import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.prefill_flag import PrefillFlagAgent
from agents.profile_builder import ProfileBuilderAgent
from agents.recommender import RecommenderAgent
from agents.rejection_fighter import RejectionFighterAgent
from utils.helpers import (
    SAMPLE_REJECTION_LETTER,
    calculate_profile_completeness,
    clean_response_text,
    extract_json_block,
    get_phase_label,
    merge_profile_updates,
)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Bima Buddy — AI Insurance Concierge",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.bb-header {
    background: linear-gradient(135deg, #0d3b66 0%, #1a7abf 100%);
    color: white; padding: 18px 24px; border-radius: 12px; margin-bottom: 24px;
}
.bb-header h1 { margin: 0; color: white; font-size: 2rem; }
.bb-header p  { margin: 4px 0 0; opacity: 0.88; font-size: 0.95rem; }

.plan-card {
    background: #fff; border: 1px solid #e0e7ef; border-left: 5px solid #1a7abf;
    border-radius: 10px; padding: 18px 20px; margin: 10px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.plan-card-top { border-left-color: #27ae60; }

.flag-red    { background:#fdecea; color:#c0392b; border:1px solid #e74c3c; border-radius:6px; padding:10px 14px; margin:6px 0; }
.flag-yellow { background:#fef9e7; color:#935116; border:1px solid #f39c12; border-radius:6px; padding:10px 14px; margin:6px 0; }
.flag-green  { background:#eafaf1; color:#1e8449; border:1px solid #2ecc71; border-radius:6px; padding:10px 14px; margin:6px 0; }

.trust-badge {
    background: #eafaf1; border: 1px solid #27ae60; border-radius: 8px;
    padding: 8px 14px; font-size: 0.85rem; color: #1e8449; margin: 10px 0; display: inline-block;
}
.phase-pill {
    display: inline-block; background: #1a7abf; color: #ffffff !important;
    border-radius: 20px; padding: 4px 14px; font-size: 0.78rem; font-weight: 600; margin-bottom: 8px;
}
.pf-row {
    background: #f4f8fc; border-radius: 6px; padding: 6px 10px; margin: 3px 0; font-size: 0.88rem;
    color: #1a2a3a !important;
}
.pf-row strong { color: #0d3b66 !important; }
.win-dial {
    text-align: center; padding: 20px 16px; border-radius: 12px; margin: 8px 0;
}
.upload-hint {
    background: #f0f4ff; border: 1px dashed #1a7abf; border-radius: 8px;
    padding: 8px 14px; font-size: 0.82rem; color: #1a5276; margin: 6px 0;
}
</style>
""", unsafe_allow_html=True)


# ── Session state ──────────────────────────────────────────────────────────────
def init_state():
    defaults = {
        "messages": [],
        "profile": {
            "age": None, "gender": None, "city": None, "income_bracket": None,
            "family_composition": None, "existing_coverage": None,
            "health_history": None, "risk_appetite": None,
            "occupation": None, "sum_insured_preference": None,
        },
        "profile_confidence": 0.0,
        "phase": "greeting",
        "recommendations": [],
        "selected_plan_id": None,
        "prefill_data": {}, "flags": [], "riders": [],
        "greeted": False,
        "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "upload_key": 0,
        "payment_ready": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Helpers ────────────────────────────────────────────────────────────────────
@st.cache_data
def load_plans():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "insurance_plans.json")
    with open(path) as f:
        return json.load(f)


def get_client():
    return Anthropic(api_key=st.session_state.api_key)


def current_system_prompt():
    phase = st.session_state.phase
    plans = load_plans()
    if phase in ("greeting", "profiling"):
        return ProfileBuilderAgent().get_system_prompt()
    elif phase == "recommending":
        return RecommenderAgent().get_system_prompt(plans, st.session_state.profile)
    elif phase == "buying":
        plan = next((p for p in plans if p["plan_id"] == st.session_state.selected_plan_id), {})
        return PrefillFlagAgent().get_system_prompt(st.session_state.profile, plan)
    return ProfileBuilderAgent().get_system_prompt()


REJECTION_KEYWORDS = {
    "rejection", "rejected", "repudiation", "denied", "disallowed",
    "not payable", "we regret to inform", "claim has been rejected",
    "claim rejection", "inadmissible", "non-payable",
}


def looks_like_rejection(text: str) -> bool:
    t = text.lower()
    return sum(1 for kw in REJECTION_KEYWORDS if kw in t) >= 2


# ── Core processors ────────────────────────────────────────────────────────────
def process_message(user_text: str):
    """Standard chat message → active agent."""
    client = get_client()
    st.session_state.messages.append({"role": "user", "content": user_text})

    api_msgs = []
    for m in st.session_state.messages:
        if m["role"] == "assistant":
            clean = clean_response_text(m["content"])
            if clean:
                api_msgs.append({"role": "assistant", "content": clean})
        else:
            api_msgs.append({"role": "user", "content": m["content"]})

    with st.spinner("Bima Buddy is thinking…"):
        resp = get_client().messages.create(
            model="claude-sonnet-4-6", max_tokens=2048,
            system=current_system_prompt(), messages=api_msgs,
        )

    return _handle_response(resp.content[0].text)


def process_file_upload(uploaded_file):
    """Route an uploaded file through the appropriate agent."""
    client = get_client()
    file_name = uploaded_file.name
    file_ext = file_name.rsplit(".", 1)[-1].lower()
    is_image = file_ext in ("png", "jpg", "jpeg", "webp", "gif")

    # Show upload indicator in chat
    st.session_state.messages.append({
        "role": "user",
        "content": f"📎 Uploaded: **{file_name}**",
        "_display": f"📎 Uploaded: **{file_name}**",
    })

    if is_image:
        _process_image_file(uploaded_file, file_name, file_ext, client)
    else:
        _process_text_file(uploaded_file, file_name, file_ext, client)


def _process_image_file(uploaded_file, file_name, file_ext, client):
    media_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                 "webp": "image/webp", "gif": "image/gif"}
    media_type = media_map.get(file_ext, "image/png")
    raw = uploaded_file.read()
    b64 = base64.standard_b64encode(raw).decode()
    img_block = {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}

    # Quick detect: rejection letter or general document?
    with st.spinner("Reading document…"):
        detect = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=10,
            messages=[{"role": "user", "content": [
                img_block,
                {"type": "text", "text": "Is this an insurance claim rejection letter? Reply YES or NO only."}
            ]}]
        )
    is_rejection = "yes" in detect.content[0].text.lower()

    if is_rejection:
        system = RejectionFighterAgent().get_system_prompt()
        user_content = [img_block, {"type": "text", "text": "Analyse this rejection letter and help me fight it."}]
    else:
        system = current_system_prompt()
        user_content = [img_block, {"type": "text", "text": f"I've uploaded '{file_name}'. Please analyse it and help with my insurance needs."}]

    with st.spinner("Analysing document…"):
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=3500,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
    _handle_response(resp.content[0].text, is_rejection=is_rejection)


def _process_text_file(uploaded_file, file_name, file_ext, client):
    if file_ext == "pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(uploaded_file)
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            text = ""
            st.warning(f"Could not read PDF: {e}. Try uploading as .txt")
    else:
        text = uploaded_file.read().decode("utf-8", errors="replace")

    if not text.strip():
        st.error("Could not extract text from this file.")
        return

    is_rejection = looks_like_rejection(text)

    if is_rejection:
        system = RejectionFighterAgent().get_system_prompt()
        user_msg = f"Please analyse this rejection letter and help me fight it:\n\n{text}"
    else:
        system = current_system_prompt()
        user_msg = (
            f"I've uploaded a document called '{file_name}'. "
            f"Here's its content:\n\n{text[:4000]}\n\n"
            "Please analyse it and help me with my insurance needs."
        )

    with st.spinner("Analysing document…"):
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=3500,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
    _handle_response(resp.content[0].text, is_rejection=is_rejection)


def _handle_response(full_text: str, is_rejection: bool = False):
    """Parse agent response, update state, store message."""
    data = extract_json_block(full_text)
    display = clean_response_text(full_text)
    phase = st.session_state.phase

    # Update state based on phase / content
    if is_rejection:
        msg = {"role": "assistant", "content": full_text, "_display": display,
               "_type": "rejection_result", "_analysis": data}
        st.session_state.messages.append(msg)
        return display

    if phase in ("greeting", "profiling"):
        if "profile_updates" in data:
            st.session_state.profile = merge_profile_updates(
                st.session_state.profile, data["profile_updates"])
        st.session_state.profile_confidence = float(
            data.get("profile_confidence") or calculate_profile_completeness(st.session_state.profile))
        if data.get("ready_for_recommendation") and st.session_state.profile_confidence >= 0.65:
            st.session_state.phase = "recommending"
        elif phase == "greeting":
            st.session_state.phase = "profiling"

    elif phase == "recommending":
        if "recommendations" in data:
            st.session_state.recommendations = data["recommendations"]
        if data.get("ready_for_buy"):
            st.session_state.phase = "buying"

    elif phase == "buying":
        if "prefilled_fields" in data:
            st.session_state.prefill_data = data["prefilled_fields"]
        if "flags" in data:
            st.session_state.flags = data["flags"]
        if "recommended_riders" in data:
            st.session_state.riders = data["recommended_riders"]

    st.session_state.messages.append({"role": "assistant", "content": full_text, "_display": display})
    return display


# ── Sidebar ────────────────────────────────────────────────────────────────────
def render_sidebar():
    st.sidebar.markdown("## 🛡️ Bima Buddy")
    st.sidebar.caption("AI Insurance Concierge")
    st.sidebar.divider()

    if not st.session_state.api_key:
        st.sidebar.subheader("🔑 API Key Required")
        key = st.sidebar.text_input("Anthropic API Key", type="password", key="api_key_input")
        if key:
            st.session_state.api_key = key
            st.rerun()
        st.sidebar.warning("Enter key to activate Bima Buddy")
        return

    st.sidebar.markdown(
        f'<div class="phase-pill">{get_phase_label(st.session_state.phase)}</div>',
        unsafe_allow_html=True)

    conf = st.session_state.profile_confidence
    if conf > 0:
        st.sidebar.progress(conf, text=f"Profile: {int(conf * 100)}% complete")
    st.sidebar.divider()

    profile = st.session_state.profile
    filled = {k: v for k, v in profile.items() if v not in (None, "", "None")}
    if filled:
        st.sidebar.subheader("📋 Your Profile")
        icons = {"age": "👤", "gender": "⚧️", "city": "🏙️", "income_bracket": "💰",
                 "family_composition": "👨‍👩‍👧", "existing_coverage": "📄",
                 "health_history": "🏥", "risk_appetite": "📊",
                 "occupation": "💼", "sum_insured_preference": "💎"}
        for field, val in filled.items():
            icon = icons.get(field, "•")
            label = field.replace("_", " ").title()
            st.sidebar.markdown(
                f'<div style="background:#e8f0fe;border-radius:6px;padding:7px 10px;margin:3px 0;'
                f'font-size:0.88rem;color:#1a2a3a;">'
                f'{icon} <span style="font-weight:600;color:#0d3b66;">{label}:</span> {val}</div>',
                unsafe_allow_html=True)
    else:
        st.sidebar.info("💬 Start chatting to build your profile…")

    if st.session_state.selected_plan_id:
        plans = load_plans()
        plan = next((p for p in plans if p["plan_id"] == st.session_state.selected_plan_id), None)
        if plan:
            st.sidebar.divider()
            st.sidebar.subheader("✅ Selected Plan")
            st.sidebar.markdown(f"**{plan['name']}**")
            st.sidebar.caption(plan["insurer"])
            st.sidebar.markdown(f"₹{plan['premium_monthly']:,}/month")

    st.sidebar.divider()
    if st.sidebar.button("🔄 Start Over", use_container_width=True):
        for k in ["messages", "profile", "phase", "recommendations", "selected_plan_id",
                  "prefill_data", "flags", "riders", "greeted", "profile_confidence",
                  "upload_key", "payment_ready"]:
            st.session_state.pop(k, None)
        st.rerun()


# ── Inline components rendered after specific messages ─────────────────────────
def render_rejection_result_card(analysis: dict):
    """Render win probability + download button inline in the chat."""
    if not analysis:
        return
    prob = analysis.get("win_probability", 0)
    if prob >= 65:
        color, verdict = "#27ae60", "Strong Case"
    elif prob >= 45:
        color, verdict = "#f39c12", "Moderate Case"
    else:
        color, verdict = "#e74c3c", "Challenging Case"

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        st.markdown(
            f'<div class="win-dial" style="background:{color}18;border:2px solid {color};border-radius:12px">'
            f'<div style="font-size:2.5rem;font-weight:900;color:{color};line-height:1">{prob}%</div>'
            f'<div style="color:{color};font-weight:700">Win Probability</div>'
            f'<div style="color:{color};font-size:0.8rem;margin-top:3px">{verdict}</div>'
            f'</div>', unsafe_allow_html=True)
    with c2:
        rej_type = analysis.get("rejection_type", "—").replace("_", " ").title()
        st.metric("Rejection Type", rej_type)
        omb = analysis.get("ombudsman_state") or "—"
        st.metric("Ombudsman", omb)
    with c3:
        reg = analysis.get("key_regulation")
        if reg:
            st.info(f"📖 **Key Regulation:**\n{reg}")
        letter = analysis.get("appeal_letter_text", "")
        if letter:
            st.download_button(
                "📥 Download Appeal Letter",
                data=letter,
                file_name="bima_buddy_appeal_letter.txt",
                mime="text/plain",
                use_container_width=True,
                type="primary",
            )


def render_recommendation_cards():
    if not st.session_state.recommendations:
        return
    plans_dict = {p["plan_id"]: p for p in load_plans()}

    st.markdown("---")
    st.subheader("💡 Your Personalised Recommendations")

    for rec in st.session_state.recommendations:
        is_top = rec.get("is_top_pick", False)
        plan_data = plans_dict.get(rec.get("plan_id"), {})
        title = f"⭐ TOP PICK — {rec.get('plan_name', '')}" if is_top else rec.get("plan_name", "")
        card_cls = "plan-card plan-card-top" if is_top else "plan-card"

        st.markdown(f'<div class="{card_cls}">', unsafe_allow_html=True)
        col_info, col_action = st.columns([3, 1])

        with col_info:
            st.markdown(f"### {title}")
            st.caption(f"{rec.get('insurer', '')} · {rec.get('type','health').upper()} · Score: **{rec.get('score','—')}/100**")
            st.markdown(rec.get("why_fits", ""))
            feats = rec.get("top_features", [])
            if feats:
                st.markdown("  ".join(f"✓ {f}" for f in feats))
            riders = rec.get("suggested_riders", [])
            if riders:
                with st.expander("➕ Suggested Riders"):
                    for r in riders:
                        st.markdown(f"• {r}")

        with col_action:
            premium = rec.get("monthly_premium")
            if premium:
                st.metric("Monthly", f"₹{premium:,}" if isinstance(premium, int) else f"₹{premium}")
            st.metric("Sum Insured", rec.get("sum_insured", "—"))
            csr = plan_data.get("claim_settlement_ratio")
            if csr:
                st.metric("Claim Ratio", f"{csr}%")
            if st.button("Select This Plan →", key=f"pick_{rec.get('plan_id', rec.get('rank',0))}",
                         type="primary", use_container_width=True):
                st.session_state.selected_plan_id = rec.get("plan_id")
                st.session_state.phase = "buying"
                process_message(f"I'd like to proceed with the {rec.get('plan_name')}.")
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)
        st.write("")


INSURER_URLS = {
    "star_comprehensive":    "https://www.starhealth.in",
    "hdfc_optima_restore":   "https://www.hdfcergo.com/health-insurance",
    "niva_bupa_reassure":    "https://www.nivabupa.com",
    "care_supreme":          "https://www.careinsurance.com",
    "aditya_birla_activ":    "https://healthinsurance.adityabirlacapital.com",
    "hdfc_click2protect":    "https://www.hdfclife.com/term-insurance-plans",
    "icici_iprotect":        "https://www.iciciprulife.com/term-life-insurance.html",
    "max_life_smart_secure": "https://www.maxlifeinsurance.com/term-insurance-plans",
    "tata_aia_sampurna":     "https://www.tataaia.com/term-insurance.html",
    "lic_tech_term":         "https://licindia.in/home",
}


def render_buy_flow():
    if st.session_state.phase != "buying" or not st.session_state.selected_plan_id:
        return
    plans = load_plans()
    plan = next((p for p in plans if p["plan_id"] == st.session_state.selected_plan_id), None)
    if not plan:
        return

    st.markdown("---")
    st.subheader(f"🛒 Application — {plan['name']}")
    st.caption(plan["insurer"])
    st.markdown(
        '<div class="trust-badge">✅ A licensed advisor has reviewed this recommendation</div>',
        unsafe_allow_html=True)
    st.write("")

    prefill = st.session_state.prefill_data
    flags = st.session_state.flags
    riders = st.session_state.riders

    if flags:
        st.markdown("#### ⚠️ Answer These Carefully")
        for flag in flags:
            lvl = flag.get("level", "green")
            icon = "🔴" if lvl == "red" else "🟡" if lvl == "yellow" else "🟢"
            st.markdown(
                f'<div class="flag-{lvl}">{icon} <strong>{flag.get("field","").replace("_"," ").title()}</strong>'
                f'<br><small>{flag.get("guidance","")}</small></div>',
                unsafe_allow_html=True)

    if riders:
        st.markdown("#### 💊 Recommended Riders")
        cols = st.columns(len(riders))
        for i, rider in enumerate(riders):
            cost = rider.get("monthly_cost", "")
            cost_str = f"₹{cost:,}/mo" if isinstance(cost, (int, float)) else str(cost)
            with cols[i]:
                st.info(f"**{rider.get('name','')}**\n\n{cost_str}\n\n{rider.get('why','')}")

    with st.form("insurance_application_form"):
        st.markdown("**Personal Details**")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.text_input("Full Name *", value=prefill.get("full_name") or "")
            st.text_input("Age *", value=str(prefill.get("age") or ""))
            st.text_input("City *", value=prefill.get("city") or "")
        with c2:
            gender_idx = 1 if (prefill.get("gender") or "").lower().startswith("f") else 0
            st.selectbox("Gender *", ["Male", "Female", "Other"], index=gender_idx)
            st.text_input("Occupation *", value=prefill.get("occupation") or "")
            st.text_input("Annual Income (₹) *", value=prefill.get("annual_income") or "")
        with c3:
            st.text_input("Mobile Number *", placeholder="10-digit mobile")
            st.text_input("Email Address *", placeholder="your@email.com")
            st.text_input("PAN Number", placeholder="ABCDE1234F")

        st.markdown("**Health Declaration**")
        h1, h2 = st.columns(2)
        with h1:
            st.radio("Tobacco/Smoking use?", ["No", "Yes", "Quit > 12 months ago"])
            st.radio("Hospitalized in last 3 years?", ["No", "Yes"])
        with h2:
            st.radio("Ever had an insurance application rejected?", ["No", "Yes"])
            st.radio("Hazardous occupation?", ["No", "Yes"])

        st.text_area(
            "Pre-existing Conditions (declare ALL truthfully) *",
            value=prefill.get("existing_conditions") or "",
            placeholder="e.g. Type 2 Diabetes diagnosed 2018, on Metformin. OR: None",
            help="🔴 Non-disclosure is the #1 cause of claim rejection.", height=90)

        st.markdown("**Nominee Details**")
        n1, n2 = st.columns(2)
        with n1:
            st.text_input("Nominee Full Name *")
        with n2:
            st.selectbox("Relationship *", ["Spouse", "Parent", "Child", "Sibling", "Other"])

        st.markdown(f"**Selected:** {plan['name']} · ₹{plan['premium_monthly']:,}/month")
        agree = st.checkbox(
            "I declare that all information provided is true and accurate. "
            "Non-disclosure may result in claim rejection or policy cancellation.")

        submitted = st.form_submit_button(
            f"Proceed to Payment — ₹{plan['premium_monthly']:,}/month →",
            type="primary", use_container_width=True)

        if submitted:
            if not agree:
                st.error("⚠️ Please check the declaration box above before proceeding.")
            else:
                st.session_state["payment_ready"] = plan["plan_id"]

    # ── Payment redirect (outside form so link_button renders properly) ────────
    if st.session_state.get("payment_ready") == plan["plan_id"]:
        insurer_url = INSURER_URLS.get(plan["plan_id"], "https://www.policybazaar.com")
        ref = f"BB-{plan['plan_id'].upper()[:8]}-2024"
        st.success(f"🎉 Application complete! Your reference: **{ref}**")
        st.balloons()
        st.markdown(
            f"Click below to complete your payment on the **{plan['insurer']}** website. "
            f"Have your reference number **{ref}** ready.")
        st.link_button(
            f"🔗 Go to {plan['insurer']} →",
            url=insurer_url,
            type="primary",
            use_container_width=True,
        )


# ── Main chat ──────────────────────────────────────────────────────────────────
def render_chat():
    if not st.session_state.api_key:
        st.info("👈 Enter your Anthropic API key in the sidebar to start.")
        return

    # Auto-greet
    if not st.session_state.greeted:
        st.session_state.greeted = True
        greeting = ProfileBuilderAgent().get_opening_message()
        st.session_state.messages.append(
            {"role": "assistant", "content": greeting, "_display": greeting})

    # Render message history
    for msg in st.session_state.messages:
        content = msg.get("_display") or clean_response_text(msg.get("content", ""))
        if not content:
            continue
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(content)
        else:
            with st.chat_message("assistant", avatar="🛡️"):
                st.markdown(content)
                # Inline rejection result card
                if msg.get("_type") == "rejection_result" and msg.get("_analysis"):
                    render_rejection_result_card(msg["_analysis"])

    # Recommendations
    if st.session_state.recommendations and st.session_state.phase in ("recommending", "buying"):
        render_recommendation_cards()

    # Buy flow
    if st.session_state.phase == "buying" and st.session_state.selected_plan_id:
        render_buy_flow()

    # ── File upload widget ─────────────────────────────────────────────────────
    with st.expander("📎 Upload a document  (rejection letter · policy · any insurance file)"):
        st.markdown(
            '<div class="upload-hint">'
            "Supports <strong>PDF, TXT, PNG, JPG</strong> — "
            "rejection letters are automatically routed to the Rejection Fighter ⚔️"
            "</div>", unsafe_allow_html=True)

        col_upload, col_demo = st.columns([3, 1])
        with col_upload:
            uploaded = st.file_uploader(
                "Choose file",
                type=["pdf", "txt", "png", "jpg", "jpeg", "webp"],
                key=f"uploader_{st.session_state.upload_key}",
                label_visibility="collapsed",
            )
        with col_demo:
            if st.button("📄 Load demo\nrejection letter", use_container_width=True):
                # Inject sample letter as a text file upload via session state
                st.session_state["_demo_rejection"] = True
                st.rerun()

        if uploaded:
            if st.button("🔍 Analyse Document", type="primary", use_container_width=True):
                process_file_upload(uploaded)
                st.session_state.upload_key += 1
                st.rerun()

    # Demo rejection letter trigger
    if st.session_state.pop("_demo_rejection", False):
        _run_demo_rejection()
        st.rerun()

    # Text chat input
    if user_input := st.chat_input("Ask about insurance, your policy, or paste a rejection letter…"):
        with st.chat_message("user"):
            st.markdown(user_input)

        # Auto-detect if user pasted a rejection letter directly
        if looks_like_rejection(user_input) and len(user_input) > 200:
            st.session_state.messages.append(
                {"role": "user", "content": user_input, "_display": user_input})
            with st.chat_message("assistant", avatar="🛡️"):
                with st.spinner("Analysing rejection letter…"):
                    client = get_client()
                    resp = client.messages.create(
                        model="claude-sonnet-4-6", max_tokens=3500,
                        system=RejectionFighterAgent().get_system_prompt(),
                        messages=[{"role": "user", "content":
                                   f"Analyse this rejection letter and help me fight it:\n\n{user_input}"}],
                    )
                full_text = resp.content[0].text
                data = extract_json_block(full_text)
                display = clean_response_text(full_text)
                st.markdown(display)
                if data:
                    render_rejection_result_card(data)
                st.session_state.messages.append(
                    {"role": "assistant", "content": full_text, "_display": display,
                     "_type": "rejection_result", "_analysis": data})
        else:
            reply = process_message(user_input)
            with st.chat_message("assistant", avatar="🛡️"):
                st.markdown(reply)

        if st.session_state.phase in ("recommending", "buying"):
            st.rerun()


def _run_demo_rejection():
    """Process the sample rejection letter for demo purposes."""
    client = get_client()
    st.session_state.messages.append({
        "role": "user",
        "content": "📎 Uploaded: **demo_rejection_letter.txt** (Star Health / CHD claim)",
        "_display": "📎 Uploaded: **demo_rejection_letter.txt** (Star Health / CHD claim)",
    })
    with st.spinner("Analysing demo rejection letter…"):
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=3500,
            system=RejectionFighterAgent().get_system_prompt(),
            messages=[{"role": "user", "content":
                       f"Analyse this rejection letter and help me fight it:\n\n{SAMPLE_REJECTION_LETTER}"}],
        )
    full_text = resp.content[0].text
    data = extract_json_block(full_text)
    display = clean_response_text(full_text)
    st.session_state.messages.append({
        "role": "assistant", "content": full_text, "_display": display,
        "_type": "rejection_result", "_analysis": data,
    })


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    init_state()
    render_sidebar()

    st.markdown(
        '<div class="bb-header"><h1>🛡️ Bima Buddy</h1>'
        '<p>Your AI Insurance Concierge — from zero to covered, and covered when it matters</p></div>',
        unsafe_allow_html=True)

    # Capability cards
    st.markdown("""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;">
      <div style="background:#1a7abf15;border:1px solid #1a7abf40;border-radius:10px;padding:14px 16px;">
        <div style="font-size:1.5rem">💬</div>
        <div style="font-weight:700;font-size:0.9rem;margin:6px 0 4px;">Smart Profiling</div>
        <div style="font-size:0.78rem;opacity:0.8;">Just chat — no forms. Bima Buddy learns your age, family, income &amp; health through natural conversation.</div>
      </div>
      <div style="background:#27ae6015;border:1px solid #27ae6040;border-radius:10px;padding:14px 16px;">
        <div style="font-size:1.5rem">💡</div>
        <div style="font-weight:700;font-size:0.9rem;margin:6px 0 4px;">Plan Recommendations</div>
        <div style="font-size:0.78rem;opacity:0.8;">Get 2–3 personalised insurance plans ranked by fit, with plain-English explanations and side-by-side comparison.</div>
      </div>
      <div style="background:#f39c1215;border:1px solid #f39c1240;border-radius:10px;padding:14px 16px;">
        <div style="font-size:1.5rem">🛒</div>
        <div style="font-weight:700;font-size:0.9rem;margin:6px 0 4px;">Guided Buy Flow</div>
        <div style="font-size:0.78rem;opacity:0.8;">Auto-filled application forms with 🔴🟡🟢 flags on critical questions — so you never get a claim rejected for wrong answers.</div>
      </div>
      <div style="background:#e74c3c15;border:1px solid #e74c3c40;border-radius:10px;padding:14px 16px;">
        <div style="font-size:1.5rem">⚔️</div>
        <div style="font-weight:700;font-size:0.9rem;margin:6px 0 4px;">Rejection Fighter</div>
        <div style="font-size:0.78rem;opacity:0.8;">Paste or upload a rejection letter — get IRDAI-cited analysis, win probability &amp; a ready-to-send appeal letter in 30 seconds.</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    render_chat()


if __name__ == "__main__":
    main()
