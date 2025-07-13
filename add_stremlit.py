import streamlit as st
import requests
import logging
import re
import openai
import os

# === CONFIGURATION ===
API_KEY = "YOUR_GOOGLE_API_KEY"
OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
SOP_FILE_PATH = "Address-type-SOP.txt"

openai.api_key = OPENAI_API_KEY

US_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia"
}

# === LOGGING ===
logging.basicConfig(level=logging.INFO)

def extract_po_box(address):
    match = re.search(r'\bP(?:\.?\s*)?O(?:\.?\s*)?BOX\s*(\d+)', address, re.IGNORECASE)
    if match:
        return match.group(1)
    match_alt = re.search(r'\b(\d{3,})\s*,?\s*P(?:\.?\s*)?O(?:\.?\s*)?BOX\b', address, re.IGNORECASE)
    if match_alt:
        return match_alt.group(1)
    return ""

def parse_address_google(address, api_key):
    po_box_number = extract_po_box(address)
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] != "OK":
            return {"Error": f"Google API error: {data['status']}"}

        components = data["results"][0]["address_components"]

        result = {
            "PO Box Number": po_box_number,
            "Building Number": "",
            "Unit/Suite/Apt": "",
            "Street Name": "",
            "City": "",
            "State": "",
            "State Full Form": "",
            "Zip Code": "",
            "Country": ""
        }

        for comp in components:
            types = comp["types"]
            if "street_number" in types:
                result["Building Number"] = comp["long_name"]
            elif "route" in types:
                result["Street Name"] = comp["long_name"]
            elif "subpremise" in types:
                result["Unit/Suite/Apt"] = comp["long_name"]
            elif "neighborhood" in types and not result["City"]:
                result["City"] = comp["long_name"]
            elif "locality" in types and not result["City"]:
                result["City"] = comp["long_name"]
            elif "administrative_area_level_1" in types:
                result["State"] = comp["short_name"]
                result["State Full Form"] = US_STATE_NAMES.get(comp["short_name"], comp["short_name"])
            elif "postal_code" in types:
                result["Zip Code"] = comp["long_name"]
            elif "country" in types:
                result["Country"] = comp["long_name"]

        return result
    except Exception as e:
        logging.exception("Exception occurred while parsing address")
        return {"Error": str(e)}

def classify_address_type_llm(address_data, sop_text):
    prompt = f"""
You are a professional address type classifier working at Amazon. Using the SOP guidelines below, classify the address into one of the following types:
- Residential
- Commercial
- Mixed
- FQA
- FFS
- Vacant

SOP:
{sop_text}

Now classify the following address:
{address_data}

Return:
Address Type: <One of the above>
Reason: <Concise reason based on SOP>
"""
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = completion.choices[0].message.content
        if "Address Type:" in reply:
            address_type = reply.split("Address Type:")[1].split("Reason:")[0].strip()
            reason = reply.split("Reason:")[-1].strip()
            return address_type, reason
        else:
            return "LLM Error", reply
    except Exception as e:
        return "LLM Error", str(e)

# === STREAMLIT UI ===
st.set_page_config(page_title="Professional Address Parser", layout="wide")
st.title("Professional Address Parser")

address_input = st.text_input("Enter Address")
if st.button("Go") and address_input:
    # Parse address components
    data = parse_address_google(address_input, API_KEY)

    # Load SOP and AI classify
    if "Error" not in data:
        with open(SOP_FILE_PATH, "r", encoding="utf-8") as f:
            sop_text = f.read()
        address_type, reason = classify_address_type_llm(data, sop_text)
        data["Address Type"] = address_type
        data["Classification Reason"] = reason

    # Show results
    for key, val in data.items():
        if val:
            st.markdown(f"**{key}** : {val}")

    # Embed Google Map (right side)
    col1, col2 = st.columns([2, 3])
    with col2:
        if address_input:
            map_url = f"https://www.google.com/maps?q={address_input.replace(' ', '+')}&output=embed"
            st.components.v1.iframe(map_url, height=400)

        # Embed Google search below map
        search_url = f"https://www.google.com/search?q={address_input.replace(' ', '+')}"
        st.components.v1.iframe(search_url, height=600)
