import os
import re
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from collections import defaultdict

# -----------------------
# CONFIG
# -----------------------
load_dotenv()

LOGO_URL = os.getenv("LOGO_URL", "")  # Optional logo URL

# =====================================================
# ENTITY TYPE MAPPING
# =====================================================
TICKET_TYPE_MAPPING = {
    "Full-Access Registration": "ATTENDEE",
    "Standard Registration": "ATTENDEE",
    "Student Registration": "ATTENDEE",
    "Entrepreneur Registration": "ATTENDEE",
    "Exhibitor Full-Access Registration": "EXHIBITOR",
    "Exhibitor Standard Registration": "EXHIBITOR",
    "Second Exhibitor": "EXHIBITOR",
    "Guest Full-Access Registration": "ATTENDEE",
    "Guest Standard Registration": "ATTENDEE",
    "Guest Registration with Lunch": "ATTENDEE",
    "Speaker": "SPEAKER",
    "Sponsor": "SPONSOR",
    "Volunteer": "VOLUNTEER",
    "Media Registration": "ATTENDEE",
    "Member Innovator Pass": "ATTENDEE",
    "Member Visionary Pass": "ATTENDEE",
    "Bronze Sponsorship": "SPONSOR",
    "Silver Sponsorship": "SPONSOR",
    "Gold Sponsorship": "SPONSOR",
    "Platinum Sponsorship": "SPONSOR"
}

# =====================================================
# UTILITY FUNCTIONS
# =====================================================

def extract_quantity_from_string(value):
    """
    Extract quantity from strings like "2 'Lunch' - Not Picked Up" or "1 'Yes' - Not Picked Up"
    Returns the quantity as an integer, or 0 if not found.
    """
    if pd.isna(value) or value == '':
        return 0
    
    value_str = str(value).strip()
    
    # Try to find a number at the start of the string
    match = re.match(r'^(\d+)', value_str)
    if match:
        return int(match.group(1))
    
    return 0


def check_lunch_status(row):
    """
    Check all lunch-related columns and determine if lunch is included.
    Returns "LUNCH" if any lunch is available, "" otherwise.
    Handles "No Lunch" cases (explicit negation).
    """
    lunch_columns = [
        'Lunch (Included)',
        'Guest Lunch Ticket',
        'Purchase Lunch'
    ]
    
    for col in lunch_columns:
        if col in row and pd.notna(row[col]):
            value_str = str(row[col]).lower()
            
            # Check for explicit "No Lunch" (negative indicator)
            if 'no lunch' in value_str:
                continue  # Skip this column if explicitly "No Lunch"
            
            # Check for positive indicators: "Lunch" or quantity > 0
            if ('lunch' in value_str or extract_quantity_from_string(row[col]) > 0):
                return "LUNCH"
    
    return ""


def check_vip_status(row):
    """
    Check all VIP-related columns and determine if VIP is included.
    Returns "VIP" if any VIP is available, "" otherwise.
    Handles "No" cases as well.
    """
    vip_columns = [
        'VIP Social (Included)',
        'Guest VIP Social Ticket',
        'Purchase VIP Social'
    ]
    
    for col in vip_columns:
        if col in row and pd.notna(row[col]):
            value_str = str(row[col]).lower()
            
            # Check for negative indicators first (No, etc.)
            if '"no"' in value_str:
                continue  # Skip this column if explicitly "No"
            
            # Check for positive indicators
            if ('yes' in value_str or extract_quantity_from_string(row[col]) > 0):
                return "VIP"
    
    return ""


def map_entity_type(ticket_type):
    """
    Map registration/ticket type to entity type.
    """
    if pd.isna(ticket_type):
        return "ATTENDEE"
    
    ticket_str = str(ticket_type).strip()
    return TICKET_TYPE_MAPPING.get(ticket_str, "ATTENDEE")


# =====================================================
# MAIN PROCESSING FUNCTION
# =====================================================

def process_registration_data(file):
    """
    Process Excel file with VIP and Lunch distribution logic.
    Handles multiple attendees under the same buyer.
    
    Intelligently detects column headers - tries row 1 first, then row 3 if needed.
    """
    # Required columns
    required_columns = [
        'Buyer Email',
        'Attendee First Name',
        'Attendee Last Name',
        'Attendee Email',
        'Registration/Ticket Type',
        'Lunch (Included)',
        'Guest Lunch Ticket',
        'Purchase Lunch',
        'VIP Social (Included)',
        'Guest VIP Social Ticket',
        'Purchase VIP Social'
    ]
    
    # Try reading with header at row 0 (first row)
    df = pd.read_excel(file, header=0)
    
    # Check if all required columns exist
    missing_cols = [col for col in required_columns if col not in df.columns]
    
    # If columns not found in first row, try row 2 (which is the 3rd row, 0-indexed)
    if missing_cols:
        # Reset file pointer and try with header at row 2 (3rd row)
        df = pd.read_excel(file, header=2)
        
        # Check again if columns exist
        missing_cols = [col for col in required_columns if col not in df.columns]
        
        if missing_cols:
            raise ValueError(
                f"Required columns not found in row 1 or row 3. Missing: {missing_cols}\n"
                f"Please ensure your Excel file has headers either in row 1 or row 3 with the correct column names."
            )
    
    # Filter to required columns
    df = df[required_columns].copy()
    
    # Remove rows with missing critical data
    df = df.dropna(subset=['Buyer Email', 'Attendee Email', 'Attendee First Name', 'Attendee Last Name'])
    
    # Group by Buyer Email to identify multiple attendees per buyer
    buyer_groups = df.groupby('Buyer Email')
    
    processed_rows = []
    
    for buyer_email, group in buyer_groups:
        # Get the first row to extract guest ticket info
        first_row = group.iloc[0]
        
        # Extract quantities from guest ticket columns
        guest_lunch_qty = extract_quantity_from_string(first_row.get('Guest Lunch Ticket', 0))
        guest_vip_qty = extract_quantity_from_string(first_row.get('Guest VIP Social Ticket', 0))
        
        num_attendees = len(group)
        
        for idx, (_, attendee_row) in enumerate(group.iterrows()):
            output_row = {
                'Attendee First Name': attendee_row['Attendee First Name'],
                'Attendee Last Name': attendee_row['Attendee Last Name'],
                'Attendee Email': attendee_row['Attendee Email'],
                'EntityType': map_entity_type(attendee_row.get('Registration/Ticket Type', ''))
            }
            
            # Determine VIP and Lunch status
            # Priority: Guest columns (if qty > 0) > Individual columns (Lunch (Included), VIP Social (Included), Purchase columns)
            
            # Check VIP
            if guest_vip_qty > 0 and idx < guest_vip_qty:
                # Distribute guest VIP tickets across attendees
                output_row['VIP'] = 'VIP'
            else:
                # Check individual VIP columns
                output_row['VIP'] = check_vip_status(attendee_row)
            
            # Check Lunch
            if guest_lunch_qty > 0 and idx < guest_lunch_qty:
                # Distribute guest lunch tickets across attendees
                output_row['Lunch'] = 'LUNCH'
            else:
                # Check individual lunch columns
                output_row['Lunch'] = check_lunch_status(attendee_row)
            
            processed_rows.append(output_row)
    
    result_df = pd.DataFrame(processed_rows)
    
    return result_df


# =====================================================
# CALCULATE SUMMARY STATISTICS
# =====================================================

def calculate_summary(df):
    """
    Calculate summary statistics from processed data.
    """
    summary = {
        "total_attendees": len(df),
        "vip_count": int((df["VIP"] == "VIP").sum()),
        "lunch_count": int((df["Lunch"] == "LUNCH").sum()),
        "vip_and_lunch_count": int(((df["VIP"] == "VIP") & (df["Lunch"] == "LUNCH")).sum()),
        "vip_only": int(((df["VIP"] == "VIP") & (df["Lunch"] != "LUNCH")).sum()),
        "lunch_only": int(((df["VIP"] != "VIP") & (df["Lunch"] == "LUNCH")).sum()),
    }
    
    # Entity type breakdown
    summary["entity_breakdown"] = df['EntityType'].value_counts().to_dict()
    
    return summary


# =====================================================
# PAGE CONFIG
# =====================================================

st.set_page_config(
    page_title="Conphere | Registration Insights",
    page_icon=os.getenv("APP_TITLE"),
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    [data-testid="stMetricDelta"] {
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

# =====================================================
# SIDEBAR (UPLOAD FILE)
# =====================================================

with st.sidebar:
    if LOGO_URL:
        st.image(LOGO_URL, width=160)
    
    st.markdown("### 📋 Upload Registration Data")
    st.divider()
    
    uploaded_file = st.file_uploader(
        "Choose an Excel file",
        type="xlsx",
        help="Upload your RegistrationReport Excel file"
    )
    
    if uploaded_file is not None:
        st.success("✅ File uploaded successfully!")
        st.divider()
        st.markdown("#### 📌 Processing Info")
        st.info(
            """
            **Processing Logic:**
            - ✓ Auto-detects column headers (Row 1 or Row 3)
            - ✓ Checks 6 ticket columns
            - ✓ Distributes guest tickets across attendees
            - ✓ Maps entity types from ticket types
            - ✓ Extracts quantities from text values
            """
        )

# =====================================================
# MAIN CONTENT
# =====================================================

if uploaded_file is not None:
    try:
        # Process the data
        processed_df = process_registration_data(uploaded_file)
        summary = calculate_summary(processed_df)
        
        # Header
        st.title("🎟️ VIP & Lunch Insights")
        st.caption(f"Registration data processed | Total Attendees: {summary['total_attendees']}")
        
        st.divider()
        
        # Summary Metrics
        col1, col2, col3, col4, col5 = st.columns(5)
        
        col1.metric(
            "👥 Total Attendees",
            summary["total_attendees"],
            help="Total number of attendees in the report"
        )
        col2.metric(
            "🌟 VIP Users",
            summary["vip_count"],
            help="Attendees with VIP access"
        )
        col3.metric(
            "🍽️ Lunch Users",
            summary["lunch_count"],
            help="Attendees with lunch included"
        )
        col4.metric(
            "⭐ VIP + Lunch",
            summary["vip_and_lunch_count"],
            help="Attendees with both VIP and Lunch"
        )
        col5.metric(
            "📊 VIP OR Lunch",
            summary["vip_only"] + summary["lunch_only"],
            help="Attendees with either VIP or Lunch (but not both)"
        )
        
        st.divider()
        
        # Entity Type Breakdown
        if summary["entity_breakdown"]:
            st.markdown("### 📈 Entity Type Breakdown")
            entity_col1, entity_col2 = st.columns(2)
            
            with entity_col1:
                entity_data = pd.DataFrame(
                    list(summary["entity_breakdown"].items()),
                    columns=["Entity Type", "Count"]
                )
                st.bar_chart(entity_data.set_index("Entity Type"))
            
            with entity_col2:
                st.dataframe(entity_data, use_container_width=True, hide_index=True)
        
        st.divider()
        
        # Download Section
        st.markdown("### 📥 Download Results")
        
        csv = processed_df.to_csv(index=False).encode("utf-8")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.download_button(
                "📥 Download as CSV",
                data=csv,
                file_name="processed_vip_lunch_insights.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # Excel download
            buffer = pd.ExcelWriter('processed_vip_lunch_insights.xlsx', engine='openpyxl')
            processed_df.to_excel(buffer, index=False, sheet_name='Attendees')
            buffer.close()
            
            with open('processed_vip_lunch_insights.xlsx', 'rb') as f:
                st.download_button(
                    "📊 Download as Excel",
                    data=f,
                    file_name="processed_vip_lunch_insights.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        
        st.divider()
        
        # Data Preview
        st.markdown("### 👀 Data Preview")
        
        with st.expander("View Full Dataset", expanded=False):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown("**Processed Attendee Data**")
            
            with col2:
                # Filter options
                filter_col = st.selectbox(
                    "Filter by:",
                    ["All", "VIP Only", "Lunch Only", "VIP + Lunch", "No VIP/Lunch"],
                    key="filter_select"
                )
            
            # Apply filters
            if filter_col == "VIP Only":
                display_df = processed_df[(processed_df["VIP"] == "VIP") & (processed_df["Lunch"] != "LUNCH")]
            elif filter_col == "Lunch Only":
                display_df = processed_df[(processed_df["VIP"] != "VIP") & (processed_df["Lunch"] == "LUNCH")]
            elif filter_col == "VIP + Lunch":
                display_df = processed_df[(processed_df["VIP"] == "VIP") & (processed_df["Lunch"] == "LUNCH")]
            elif filter_col == "No VIP/Lunch":
                display_df = processed_df[(processed_df["VIP"] != "VIP") & (processed_df["Lunch"] != "LUNCH")]
            else:
                display_df = processed_df
            
            st.dataframe(display_df, use_container_width=True, height=400)
            st.caption(f"Showing {len(display_df)} of {len(processed_df)} attendees")

    except Exception as e:
        st.error(f"❌ Error processing file: {str(e)}")
        st.info("Please ensure your Excel file contains all required columns.")
    else:
        # Initial state - no file uploaded
        st.markdown("""
            # 🎟️ VIP & Lunch Processing Tool
            
            Welcome to the registration insights tool. This application processes your registration data
            to identify VIP and Lunch ticket holders.
            
            ## How it works:
            
            1. **Upload** your RegistrationReport Excel file using the sidebar
            2. **Process** automatically handles multiple attendees per buyer
            3. **Distribute** guest tickets across attendees with same buyer email
            4. **Download** results in CSV or Excel format
            
            ## Key Features:
            
            - ✅ Checks all 6 VIP and Lunch columns
            - ✅ Distributes guest tickets correctly across multiple attendees
            - ✅ Maps entity types from ticket types
            - ✅ Extracts quantities from text values
            - ✅ Provides summary statistics
            - ✅ Export results in multiple formats
            
            **Ready to get started?** Upload your file in the sidebar!
        """)