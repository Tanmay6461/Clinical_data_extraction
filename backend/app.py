from fastapi import FastAPI
from utils.data_scrapper import SECFilingExtractor
from google.cloud import storage
from google.oauth2 import service_account
import json
from io import BytesIO
from utils.litellm.helper import prompt_summarize_drug_data
from utils.litellm.llm import llm, llmGpt
import os 
from gcp.cloud_storage import upload_file, blob_exists, load_json_from_gcs, get_gcp_credentials
from dotenv import load_dotenv
import logging
from openai import OpenAI


logging.basicConfig(
    format="%(name)s %(message)s",
    level=logging.INFO
)

load_dotenv()
app = FastAPI()

# cred_path   = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
# credentials = service_account.Credentials.from_service_account_file(cred_path)
secrets_json = get_gcp_credentials()
credentials = service_account.Credentials.from_service_account_info(secrets_json)

bucket_name = os.getenv("GCP_BUCKET_NAME")
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

@app.get("/summary/{ticker}")
def summarize_filing(ticker: str):
    os.environ["LITELLM_VERBOSE"] = "False"
    ticker = ticker.upper()
    drug_blob_path = f"{ticker}/{ticker}_drug_facts.json"
    summary_path = f"{ticker}/{ticker}_summary.json"

    # Step 1: If summary already exists, return it
    if blob_exists(bucket_name, summary_path, credentials):
        try:
            json_data = load_json_from_gcs(bucket_name, summary_path, credentials)
            return {"status_code": 200, "summary": json_data}
        except Exception as e:
            return {"status_code": 400, "error": f"Failed to load summary: {str(e)}"}

    # Step 2: If drug data doesn't exist, run the pipeline
    if not blob_exists(bucket_name, drug_blob_path, credentials):
        try:
            extractor = SECFilingExtractor(ticker, email="fxddrdhcgh@gmail.com", output_dir=f"sec_data/{ticker}")
            extractor.process_new_filings_only(form_types=["8-K", "10-K", "10-Q"], max_workers=35)
        except Exception as e:
            return {"status_code": 500, "error": f"Extraction failed: {str(e)}"}

    # Step 3: Summarize the drug data
    try:
        print("summarizing drug data...")
        json_data = load_json_from_gcs(bucket_name, drug_blob_path, credentials)
        prompt = prompt_summarize_drug_data.format(json_blob=json.dumps(json_data, indent=2))
        # response = llm(model="vertex_ai/gemini-2.5-flash-preview-04-17", prompt=prompt)
        response = llmGpt(model="gpt-4.1-mini", prompt=prompt, client=client)
        
        raw_response = response['response'].strip()
        if raw_response.startswith("```json"):
            raw_response = raw_response.removeprefix("```json").removesuffix("```").strip()
        elif raw_response.startswith("```"):
            raw_response = raw_response.removeprefix("```").removesuffix("```").strip()

        summary= json.loads(raw_response)
        # Save the summary to GCS for caching
        summary_bytes = BytesIO(json.dumps(summary, indent=2).encode("utf-8"))
        upload_file(summary_bytes, summary_path, "application/json", credentials)
        return {"status_code": 200, "summary": summary}
    except Exception as e:
        return {"status_code": 500, "error": f"Summarization failed: {str(e)}"}
