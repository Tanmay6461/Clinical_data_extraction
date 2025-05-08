from google.cloud import storage
from dotenv import load_dotenv
import os 
import json
from datetime import timedelta


load_dotenv()

BUCKET_NAME = os.getenv("GCP_BUCKET_NAME")

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
    

    

# def get_gcp_credentials():
#     """
#     Fetches GCP credentials from Google Secret Manager.
#     """
#     client = secretmanager.SecretManagerServiceClient()
#     secret_name = "gcp-service-account-key"
#     project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
#     name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"

#     # Access the secret version
#     response = client.access_secret_version(request={"name": name})
#     return json.loads(response.payload.data.decode("UTF-8"))



# def generate_signed_url(bucket_name, object_name, credentials):
#     try:
#         client = storage.Client(credentials=credentials)
#         bucket = client.bucket(bucket_name)
#         blob = bucket.blob(object_name)

#         url = blob.generate_signed_url(
#             expiration=timedelta(hours=24),
#             method='GET'
#         )
#         return url
#     except:
#         -1
