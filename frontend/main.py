import streamlit as st
import requests
import pandas as pd

API_BASE_URL = "https://fastapi-clinical-data-982882644329.us-central1.run.app"

st.set_page_config(page_title="Drug Summary Table", layout="wide")
st.title("🧬 Drug Summary Table")

ticker = st.text_input("Enter Ticker Symbol (e.g. WVE):").upper()

if st.button("Get Summary") and ticker:
    with st.spinner("Fetching summary..."):
        try:
            res = requests.get(f"{API_BASE_URL}/summary/{ticker}")
            data = res.json()

            if data["status_code"] == 200:
                summary = data["summary"]
                rows = []

                for drug, fields in summary.items():
                    row = {"Drug": drug}
                    for key in ["mechanism_of_action", "target","indication", "preclinical_data", "clinical_trials",
                                "upcoming_milestones", "references", "aliases"]:
                        value = fields.get(key, [])
                        if isinstance(value, list):
                            row[key.replace("_", " ").capitalize()] = "\n".join(value)
                        else:
                            row[key.replace("_", " ").capitalize()] = value
                    rows.append(row)

                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True)
            else:
                st.error(data.get("error", "API returned an error."))

        except Exception as e:
            st.error(f"Request failed: {str(e)}")
