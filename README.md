# 🧬 SEC Drug Pipeline
This project automates the extraction, canonicalization, and summarization of drug development pipelines from SEC filings using LLMs and cloud infrastructure.


### use WVE or ALNY for demo since this data is already stored.(Due to limited credits)
- API - https://fastapi-clinical-data-982882644329.us-central1.run.app/docs#/default/summarize_filing_summary__ticker__get
- UI - https://clinical-data.streamlit.app/

## 📌 Overview

- Extracts 8-K, 10-K, and 10-Q filings from the SEC EDGAR system for a given ticker
- Parses and chunks textual sections using form-type-specific strategies
- Uses an LLM (OpenAI / Gemini) to identify **drug development programs** from raw text
- Canonicalizes drug names via alias grouping and merges scattered mentions
- Validates the final schema and uploads structured drug facts to Google Cloud Storage
- Summarizes the extracted drug data into clinically meaningful insights using a second LLM stage
- Exposes APIs for triggering extraction and retrieving structured summaries

---

## 🧪 Key Features

- **Form-Aware Parsing**: Custom logic for 8-K, 10-K, and 10-Q section extraction
- **Chunked LLM Processing**: Auto-chunks long documents to avoid token overflows
- **Alias Grouping via LLM**: Maps drug aliases (e.g., "ALN-TTR02", "patisiran", "ONPATTRO") to a canonical name
- **Schema Validation**: Ensures final output conforms to a strict drug facts schema
- **GCS Integration**: Uploads both raw and summarized JSON to Google Cloud buckets
- **Streamlit UI**: Lets users input a ticker and view structured summaries in a searchable table
- **FastAPI Backend**: Powers secure, scalable LLM-based APIs with summarization-on-demand

---

## 📁 Key Components

| Component                     | Description                                                                 |
|------------------------------|-----------------------------------------------------------------------------|
| `process_filing`             | Extracts drug programs from one filing using chunked LLM calls              |
| `process_all_filings`        | Coordinates threaded processing of multiple filings and handles aggregation |
| `group_and_merge_drug_aliases` | Uses LLM to canonicalize drug names and resolve aliases                     |
| `merge_all_drug_data`        | Merges extracted facts across all alias variants into a unified structure   |
| `summarize_filing` (FastAPI) | API to trigger summarization; checks cache, extracts if needed, then summarizes |
