import streamlit as st
import requests
import pandas as pd

API_BASE_URL = "https://fastapi-clinical-data-982882644329.us-central1.run.app"

st.set_page_config(page_title="Drug Filing Summary", layout="wide")
st.title("🧪 Drug Pipeline Summary Dashboard")

ticker = st.text_input("Enter Ticker Symbol (e.g. STOK):").upper()

if st.button("Run & Summarize"):
    if ticker:
        with st.spinner("Triggering pipeline..."):
            try:
                # Step 1: Trigger the pipeline
                check_response = requests.post(f"{API_BASE_URL}/check_filling/{ticker}")
                check_data = check_response.json()

                if isinstance(check_data, dict) and check_data.get("status_code") == 500:
                    st.error(f"❌ Pipeline failed: {check_data.get('error', 'Unknown error')}")
                elif check_data is False:
                    st.info("ℹ️ No new filings found. Proceeding to summary...")

                # Step 2: Trigger summarization
                st.spinner("Summarizing extracted drug data...")
                summary_response = requests.post(f"{API_BASE_URL}/check_filling/{ticker}")
                summary_data = summary_response.json()

                if summary_data.get("status_code") != 200:
                    st.error(f"❌ Summarization failed: {summary_data.get('error', 'No summary available')}")
                else:
                    summary = summary_data["summary"]
                    rows = []

                    for drug, fields in summary.items():
                        row = {"Drug": drug}
                        for key in [
                            "mechanism_of_action", "target", "indication", "preclinical_data",
                            "clinical_trials", "upcoming_milestones", "references", "aliases"
                        ]:
                            value = fields.get(key, [])
                            row[key.replace("_", " ").capitalize()] = "\n".join(value) if isinstance(value, list) else value
                        rows.append(row)

                    df = pd.DataFrame(rows)
                    st.success("✅ Summary extracted successfully.")
                    st.dataframe(df, use_container_width=True)

            except Exception as e:
                st.error(f"❌ Request failed: {str(e)}")
    else:
        st.warning("⚠️ Please enter a ticker symbol.")
