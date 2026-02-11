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

if "selected_event" not in st.session_state:
    st.session_state.selected_event = None


TICKET_TYPE_MAPPING = {
    "Full-Access Registration": "Attendee",
    "Standard Registration": "Attendee",
    "Student Registration": "Attendee",
    "Entrepreneur Registration": "Attendee",
    "Exhibitor Full-Access Registration": "Exhibitor",
    "Exhibitor Standard Registration": "Exhibitor",
    "Second Exhibitor": "Exhibitor",
    "Guest Full-Access Registration": "Attendee",
    "Guest Standard Registration": "Attendee",
    "Guest Registration with Lunch": "Attendee",
    "Speaker": "Speaker",
    "Sponsor": "Attendee",
    "Volunteer": "Volunteer",
    "Media Registration": "Attendee",
    "Member Innovator Pass": "Attendee",
    "Member Visionary Pass": "Attendee",
    "Bronze Sponsorship": "Sponsor",
    "Silver Sponsorship": "Sponsor",
    "Gold Sponsorship": "Sponsor",
    "Platinum Sponsorship": "Sponsor"
}


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

def fetch_events(access_token):
    query = """
    query {
      events(
        orgSlug: "315841",
        eventsAfter: "2024-07-10T17:14:16.000Z",
        completed: false,
        live: true
      ) {
        productId
        productName
      }
    }
    """

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    res = requests.post(GRAPHQL_URL, headers=headers, json={"query": query})
    res.raise_for_status()

    return res.json()["data"]["events"]


def fetch_regs(access_token, product_id):
    query = f"""
    query {{
      regsByOrg(
        orgSlug: "315841",
        pidList: [{product_id}],
        canceled: false
      ) {{
        nameFirst
        nameLast
        email
        productVariantName
        form {{
          question
          answer
        }}
        addOns {{
          name
        }}
      }}
    }}
    """

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    res = requests.post(GRAPHQL_URL, headers=headers, json={"query": query})
    res.raise_for_status()

    return res.json()["data"]["regsByOrg"]


def process_and_count(regs):
    users_by_email = []
    
    if not regs:
        summary = {
            "vip_count": 0,
            "lunch_count": 0,
            "vip_and_lunch_count" : 0,
            "vip_or_lunch_count" : 0
        }
        df = pd.DataFrame()
        return summary, df

    for reg in regs:
        email = reg["email"].strip().lower()
        ticket_type = reg.get("productVariantName", "")

        # Check if the ticket type exists in the mapping
        entity_type = TICKET_TYPE_MAPPING.get(ticket_type, None)

        # If the ticket type doesn't match any entity type, skip the registration
        if entity_type is None:
            continue  # Skip this iteration and do not add this registration

        vip = False
        lunch = False
        title = None
        company = None

        # Extract form data
        for f in reg.get("form", []):
            if f["question"] == "Job Title":
                title = f["answer"]
            elif f["question"] == "Company Name":
                company = f["answer"]

        # Check add-ons for VIP and Lunch
        for addon in reg.get("addOns", []):
            if addon["name"] == "Lunch":
                lunch = True
            elif addon["name"] == "Yes":
                vip = True

        # Add the registration to the list if ticket type is valid
        users_by_email.append({
            "nameFirst": reg["nameFirst"],
            "nameLast": reg["nameLast"],
            "email": reg["email"],
            "EntityType": entity_type.upper(),
            "Title": title,
            "Company": company,
            "VIP": vip,
            "Lunch": lunch
        })

    df = pd.DataFrame(users_by_email)

    # ----------------------------
    # 1️⃣ CALCULATE SUMMARY FIRST (USING BOOLEAN)
    # ----------------------------
    summary = {
        "vip_count": int(df["VIP"].sum()),
        "lunch_count": int(df["Lunch"].sum()),
        "vip_and_lunch_count": int((df["VIP"] & df["Lunch"]).sum()),
        "vip_or_lunch_count": len(df)
    }

    # ----------------------------
    # 2️⃣ THEN FORMAT FOR DISPLAY
    # ----------------------------
    df["VIP"] = df["VIP"].map({True: "VIP", False: ""})
    df["Lunch"] = df["Lunch"].map({True: "LUNCH", False: ""})

    # Drop the old `productVariantName` column if it exists
    if "productVariantName" in df.columns:
        df.drop(columns=["productVariantName"], inplace=True)

    return summary, df


# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title="Conphere | Insights",
    page_icon=os.getenv("APP_TITLE"),
    layout="wide"
)


# =====================================================
# SIDEBAR (TABS)
# =====================================================
with st.sidebar:
    st.image(LOGO_URL, width=160)
    # st.markdown("## Conphere")
    st.divider()

    # ---- EVENT SELECTION
    token = get_access_token()
    events = fetch_events(token)

    event_map = {e["productName"]: e["productId"] for e in events}

    selected_event_name = st.selectbox(
        "Select Event",
        options=["-- Select an Event --"] + list(event_map.keys())
    )

    if selected_event_name != "-- Select an Event --":
        st.session_state.selected_event = {
            "name": selected_event_name,
            "product_id": event_map[selected_event_name]
        }

    st.divider()

    # ---- TABS (enabled only after event selection)
    vip_disabled = st.session_state.selected_event is None

    if st.button(
        "📊 VIP & Lunch Insights",
        use_container_width=True,
        disabled=vip_disabled
    ):
        st.session_state.active_tab = "vip_lunch"

    st.divider()

    st.button(
        "🕒 Check-ins (Coming Soon)",
        disabled=True,
        use_container_width=True
    )

    st.divider()



# =====================================================
# MAIN CONTENT
# =====================================================

if st.session_state.active_tab == "vip_lunch":

    if not st.session_state.selected_event:
        st.info("👈 Please select an event from the sidebar to continue.")
    else:
        event_name = st.session_state.selected_event["name"]
        product_id = st.session_state.selected_event["product_id"]

        st.title("VIP & Lunch Insights")
        st.caption(f"Event: {event_name}")
        st.divider()

        if st.button("🔍 Generate Summary & CSV"):
            with st.spinner("Fetching and processing data..."):
                token = get_access_token()
                regs = fetch_regs(token, product_id)
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
                file_name=f"{event_name.replace(' ', '_')}_vip_lunch.csv",
                mime="text/csv"
            )

            with st.expander("Preview Data"):
                st.dataframe(df, use_container_width=True)
