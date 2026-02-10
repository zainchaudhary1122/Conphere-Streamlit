import os
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
import requests
from urllib.parse import urlencode

load_dotenv()

# -----------------------
# CONFIG
# -----------------------
TOKEN_URL = os.getenv("TOKEN_URL")
GRAPHQL_URL = os.getenv("GRAPHQL_URL")

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")

LOGO_URL = os.getenv("LOGO_URL")

# =====================================================
# SESSION STATE (TAB CONTROL)
# =====================================================
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "vip_lunch"


# =====================================================
# API HELPERS
# =====================================================
def get_access_token():
    payload = urlencode({
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }

    res = requests.post(TOKEN_URL, data=payload, headers=headers, timeout=30)
    res.raise_for_status()
    return res.json()["access_token"]


def fetch_regs(access_token):
    query = """
    query {
      regsByOrg(
        orgSlug: "315841",
        pidList: [991889],
        canceled: false
      ) {
        nameFirst
        nameLast
        email
        productVariantName
        form {
          question
          answer
        }
        addOns {
          name
        }
      }
    }
    """

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    res = requests.post(GRAPHQL_URL, headers=headers, json={"query": query})
    res.raise_for_status()
    return res.json()["data"]["regsByOrg"]


def process_and_count(regs):
    users_by_email = {}

    for reg in regs:
        email = reg["email"].strip().lower()

        vip = False
        lunch = False
        title = None
        company = None

        for f in reg.get("form", []):
            if f["question"] == "Job Title":
                title = f["answer"]
            elif f["question"] == "Company Name":
                company = f["answer"]

        for addon in reg.get("addOns", []):
            if addon["name"] == "Lunch":
                lunch = True
            elif addon["name"] == "Yes":
                vip = True

        if email not in users_by_email:
            users_by_email[email] = {
                "nameFirst": reg["nameFirst"],
                "nameLast": reg["nameLast"],
                "email": reg["email"],
                "productVariantName": reg["productVariantName"],
                "Title": title,
                "Company": company,
                "VIP": vip,
                "Lunch": lunch
            }
        else:
            users_by_email[email]["VIP"] |= vip
            users_by_email[email]["Lunch"] |= lunch

    rows = [u for u in users_by_email.values() if u["VIP"] or u["Lunch"]]
    df = pd.DataFrame(rows)

    summary = {
        "vip_count": int(df["VIP"].sum()),
        "lunch_count": int(df["Lunch"].sum()),
        "vip_and_lunch_count": int((df["VIP"] & df["Lunch"]).sum()),
        "vip_or_lunch_count": len(df)
    }

    return summary, df


# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title="Conphere | Insights",
    layout="wide"
)


# =====================================================
# SIDEBAR (TABS)
# =====================================================
with st.sidebar:
    st.image(LOGO_URL, width=160)
    st.markdown("TechCon SouthWest 2026")
    st.divider()

    # ---- TAB 1
    if st.button("📊 VIP & Lunch Insights", use_container_width=True):
        st.session_state.active_tab = "vip_lunch"
    st.divider()

    # ---- TAB 2 (DISABLED)
    st.button(
        "🕒 Check-ins (Coming Soon)",
        disabled=True,
        use_container_width=True
    )
    st.divider()


# =====================================================
# MAIN CONTENT
# =====================================================

# ---------- VIP & LUNCH TAB ----------
if st.session_state.active_tab == "vip_lunch":

    st.title("VIP & Lunch Insights")
    st.caption("Events.com attendee insights (deduplicated by email)")
    st.divider()

    if st.button("🔍 Generate Summary & CSV"):
        with st.spinner("Fetching and processing data..."):
            token = get_access_token()
            regs = fetch_regs(token)
            summary, df = process_and_count(regs)

        # ---- SUMMARY
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("VIP Users", summary["vip_count"])
        col2.metric("Lunch Users", summary["lunch_count"])
        col3.metric("VIP + Lunch", summary["vip_and_lunch_count"])
        col4.metric("VIP OR Lunch", summary["vip_or_lunch_count"])

        st.divider()

        # ---- DOWNLOAD
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download CSV",
            data=csv,
            file_name="vip_lunch_attendees.csv",
            mime="text/csv"
        )

        with st.expander("Preview Data"):
            st.dataframe(df, use_container_width=True)