from airflow.hooks.base import BaseHook
from google.oauth2 import service_account
import json
from google.cloud import storage
   
def get_gcp_credentials_from_airflow(conn_id="google_cloud_default"):
        conn = BaseHook.get_connection(conn_id)
        keyfile_dict = json.loads(conn.extra_dejson["keyfile_dict"])
        return service_account.Credentials.from_service_account_info(keyfile_dict)


def list_gcs_folders(bucket_name, credentials):
    """List folders in a GCS bucket."""
    client = storage.Client(credentials=credentials)


    blobs = client.list_blobs(bucket_name, delimiter="/")
    _ = list(blobs) 
    ls = list(blobs.prefixes)
    available_tickers = [path.rstrip('/') for path in ls]
    return available_tickers



