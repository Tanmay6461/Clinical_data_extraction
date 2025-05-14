from google.cloud import storage
from dotenv import load_dotenv
import os 
import json
from datetime import timedelta
import json
from io import BytesIO
from google.cloud import secretmanager

load_dotenv()

BUCKET_NAME = os.getenv("GCP_BUCKET_NAME")


def get_gcp_credentials():
    """
    Fetches GCP credentials from Google Secret Manager.
    """
    client = secretmanager.SecretManagerServiceClient()
    secret_name = "gcp-service-account-key"
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"

    # Access the secret version
    response = client.access_secret_version(request={"name": name})
    return json.loads(response.payload.data.decode("UTF-8"))



def upload_file(file_data, filename, content_type, credentials):
    try:
        client = storage.Client(credentials=credentials)
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        file_data.seek(0)
        blob.upload_from_file(file_data, content_type=content_type)
        return 1
    except:
        return -1
    

def read_json_from_gcs(bucket_name, blob_path, credentials):
    client = storage.Client(credentials=credentials)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        return set()

    data = blob.download_as_text()
    return set(json.loads(data))



def write_json_to_gcs(bucket_name, blob_path, data, credentials):
    client = storage.Client(credentials=credentials)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    blob.upload_from_string(
        data=json.dumps(sorted(list(data)), indent=2),
        content_type="application/json"
    )


def blob_exists(bucket_name, blob_path, credentials):
    client = storage.Client(credentials=credentials)
    bucket = client.bucket(bucket_name)
    return bucket.blob(blob_path).exists()

def load_json_from_gcs(bucket_name, blob_path, credentials):
    client = storage.Client(credentials=credentials)
    blob = client.bucket(bucket_name).blob(blob_path)
    return json.loads(blob.download_as_text())


