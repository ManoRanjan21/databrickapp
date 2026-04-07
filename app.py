import os
import json
import requests
import streamlit as st

st.set_page_config(page_title="Provisioning Forms", page_icon="🧩", layout="centered")

# -----------------------------
# API endpoint mapping (8 total)
# AWS: 1-4, Azure: 5-8 (same order)
# -----------------------------
API_MAP = {
    ("AWS", "Catalog"): os.getenv("API_AWS_CATALOG", "").strip(),
    ("AWS", "External location"): os.getenv("API_AWS_EXTERNAL_LOCATION", "").strip(),
    ("AWS", "Storage credential"): os.getenv("API_AWS_STORAGE_CREDENTIAL", "").strip(),
    ("AWS", "SCIM sync"): os.getenv("API_AWS_SCIM_SYNC", "").strip(),

    ("Azure", "Catalog"): os.getenv("API_AZURE_CATALOG", "").strip(),
    ("Azure", "External location"): os.getenv("API_AZURE_EXTERNAL_LOCATION", "").strip(),
    ("Azure", "Storage credential"): os.getenv("API_AZURE_STORAGE_CREDENTIAL", "").strip(),
    ("Azure", "SCIM sync"): os.getenv("API_AZURE_SCIM_SYNC", "").strip(),
}

CARDS = ["Catalog", "External location", "Storage credential", "SCIM sync"]

# -----------------------------
# Small helper: bordered card + button
# Uses st.container(border=True) for a "card" look [2](https://docs.streamlit.io/develop/api-reference/layout/st.container)
# and st.columns for layout [1](https://docs.streamlit.io/develop/api-reference/layout/st.columns)
# -----------------------------
def card_button(title: str, subtitle: str, key: str):
    with st.container(border=True):
        st.markdown(f"### {title}")
        st.caption(subtitle)
        return st.button("Open", key=key, use_container_width=True)

def post_json(url: str, payload: dict):
    resp = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    return resp

# -----------------------------
# UI Header
# -----------------------------
st.title("🧩 Provisioning Request")
st.caption("Choose cloud → pick a card → fill form → submit to API Gateway (Lambda).")

# -----------------------------
# Step 1: Choose Cloud
# -----------------------------
cloud = st.radio("Choose Cloud", ["AWS", "Azure"], horizontal=True)

# Keep selection in session state
if "selected_card" not in st.session_state:
    st.session_state.selected_card = None

st.subheader(f"Step 2: Choose an action ({cloud})")

# -----------------------------
# Step 2: Show 4 cards (2x2 grid)
# -----------------------------
col1, col2 = st.columns(2)  # layout via columns [1](https://docs.streamlit.io/develop/api-reference/layout/st.columns)
with col1:
    if card_button("Catalog", "Create / configure catalog", f"{cloud}_Catalog"):
        st.session_state.selected_card = "Catalog"
    if card_button("Storage credential", "Create / update credential", f"{cloud}_Storage credential"):
        st.session_state.selected_card = "Storage credential"

with col2:
    if card_button("External location", "Create / configure external location", f"{cloud}_External location"):
        st.session_state.selected_card = "External location"
    if card_button("SCIM sync", "Sync users/groups via SCIM", f"{cloud}_SCIM sync"):
        st.session_state.selected_card = "SCIM sync"

selected = st.session_state.selected_card

# If nothing selected, stop here
if not selected:
    st.info("Select one of the cards to open the form.")
    st.stop()

st.divider()
st.subheader(f"Step 3: {cloud} → {selected} form")

# Resolve endpoint
api_url = API_MAP.get((cloud, selected), "")

if not api_url:
    st.warning("API endpoint for this form is not configured (missing env var).")

# -----------------------------
# Step 3: Dynamic forms per card
# -----------------------------
payload = {"cloud": cloud, "formType": selected}

with st.form(f"form_{cloud}_{selected}", clear_on_submit=False):
    # Common: show fields based on the selected form
    if selected == "Catalog":
        account_id = st.text_input("Account ID *", placeholder="123456789012")
        external_location_name = st.text_input("External Location Name *", placeholder="ext_loc_name")
        catalog_name = st.text_input("Catalog Name *", placeholder="catalog_name")

        payload.update({
            "accountId": account_id,
            "externalLocationName": external_location_name,
            "catalogName": catalog_name
        })

    elif selected == "External location":
        account_id = st.text_input("Account ID *", placeholder="123456789012")
        external_location_name = st.text_input("External Location Name *", placeholder="ext_loc_name")

        payload.update({
            "accountId": account_id,
            "externalLocationName": external_location_name
        })

    elif selected == "Storage credential":
        account_id = st.text_input("Account ID *", placeholder="123456789012")

        payload.update({
            "accountId": account_id
        })

    elif selected == "SCIM sync":
        workspace_url = st.text_input("Workspace URL *", placeholder="https://adb-xxxxx.azuredatabricks.net")
        plme = st.text_input("PLME *", placeholder="your-plme")
        user_id = st.text_input("User ID *", placeholder="user@company.com")
        ad_groups = st.text_area("AD Groups *", placeholder="Group1\nGroup2\nGroup3")

        payload.update({
            "workspaceUrl": workspace_url,
            "plme": plme,
            "userId": user_id,
            "adGroups": [g.strip() for g in ad_groups.splitlines() if g.strip()]
        })

    submitted = st.form_submit_button("Submit 🚀")

# -----------------------------
# Submit handling
# -----------------------------
if submitted:
    # Minimal validation: ensure all values that end with * were provided
    missing = [k for k, v in payload.items()
               if k not in ("cloud", "formType") and (v is None or v == "" or v == [])]

    if missing:
        st.error(f"Please fill required fields. Missing: {', '.join(missing)}")
        st.stop()

    st.success("✅ Form captured")
    st.subheader("Outgoing JSON")
    st.code(json.dumps(payload, indent=2), language="json")

    if not api_url:
        st.error("No API URL configured for this selection. Set the env var in app.yaml.")
        st.stop()

    try:
        with st.spinner("Calling API Gateway..."):
            resp = post_json(api_url, payload)

        st.subheader("API Response")
        st.write(f"Status: **{resp.status_code}**")

        try:
            st.json(resp.json())
        except Exception:
            st.code(resp.text)

        if 200 <= resp.status_code < 300:
            st.success("✅ API triggered successfully!")
        else:
            st.error("❌ API returned an error. See response above.")

    except requests.exceptions.Timeout:
        st.error("⏱️ Request timed out. Check endpoint/network.")
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed: {e}")
