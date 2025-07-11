import requests
import streamlit as st
import threading
import logging
import re
import os
import json
from openai import OpenAI

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load API key securely
API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# US State code to full name mapping
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

# Load SOP content
SOP_FILE_PATH = "/mnt/data/Address-type-SOP.txt"
with open(SOP_FILE_PATH, "r", encoding="utf-8") as f:
    FULL_SOP_TEXT = f.read()

def extract_po_box(address):
    match = re.search(r'\bP(?:\.?\s*)?O(?:\.?\s*)?BOX\s*(\d+)', address, re.IGNORECASE)
    if match:
        return match.group(1)
    match_alt = re.search(r'\b(\d{3,})\s*,?\s*P(?:\.?\s*)?O(?:\.?\s*)?BOX\b', address, re.IGNORECASE)
    if match_alt:
        return match_alt.group(1)
    return ""

def classify_address_type(address, place_name, description):
    prompt = f"""
You are an Amazon Address Validation specialist. Follow the below official SOP carefully to classify the address type.

=== SOP START ===
{FULL_SOP_TEXT}
=== SOP END ===

Now based on the SOP, classify the address:

Address: {address}
Place Name: {place_name}
Map Tags: {description}

Return only this JSON:
{{
  "type": "<Residential | Commercial | FQA | FFS | Mixed | PO Box | Incomplete>",
  "reason": "<Explain using the SOP criteria>"
}}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a professional trained on Amazon Address Validation SOP."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error during AI classification: {e}"

def parse_address_google(address, api_key):
    po_box_number = extract_po_box(address)
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] != "OK":
            logging.error(f"Google API returned error: {data['status']}")
            return {"Error": f"Google API error: {data['status']}"}

        components = data["results"][0]["address_components"]
        place_name = data["results"][0].get("formatted_address", "")
        description = data["results"][0].get("types", [])

        result = {
            "PO Box Number": po_box_number,
            "Building Number": "",
            "Unit/Suite/Apt": "",
            "Street Name": "",
            "Neighborhood": "",
            "City": "",
            "State": "",
            "State Full Form": "",
            "Zip Code": "",
            "Country": "",
            "Address Type": "",
            "Classification Reason": ""
        }

        for comp in components:
            types = comp["types"]
            if "street_number" in types:
                result["Building Number"] = comp["long_name"]
            elif "route" in types:
                result["Street Name"] = comp["long_name"]
            elif "subpremise" in types:
                result["Unit/Suite/Apt"] = comp["long_name"]
            elif "neighborhood" in types:
                result["Neighborhood"] = comp["long_name"]
            elif "locality" in types:
                result["City"] = comp["long_name"]
            elif "administrative_area_level_1" in types:
                state_short = comp["short_name"]
                full_name = US_STATE_NAMES.get(state_short, state_short)
                result["State"] = state_short
                result["State Full Form"] = full_name
            elif "postal_code" in types:
                result["Zip Code"] = comp["long_name"]
            elif "country" in types:
                result["Country"] = comp["long_name"]

        ai_response = classify_address_type(address, place_name, ", ".join(description))
        if ai_response.startswith("{"):
            parsed = json.loads(ai_response)
            result["Address Type"] = parsed.get("type", "")
            result["Classification Reason"] = parsed.get("reason", "")
        else:
            result["Address Type"] = "LLM Error"
            result["Classification Reason"] = ai_response

        return result

    except Exception as e:
        logging.exception("Exception occurred while parsing address")
        return {"Error": str(e)}

# Streamlit UI
st.set_page_config(page_title="Professional Address Parser", page_icon="favicon.ico")
st.title("Professional Address Parser")
address_input = st.text_input("Enter Address")
if st.button("Go"):
    if not address_input:
        st.warning("Please enter an address.")
    else:
        with st.spinner("Parsing..."):
            result = parse_address_google(address_input, API_KEY)
            if "Error" in result:
                st.error(result["Error"])
            else:
                for key, value in result.items():
                    if value:
                        st.text(f"{key:<22}: {value}")
