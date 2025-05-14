from airflow import DAG
from airflow.decorators import task
from airflow.utils.dates import days_ago
from utils.data_scrapper import SECFilingExtractor
from google.oauth2 import service_account
from airflow.providers.google.cloud.hooks.gcs import GCSHook
from utils.hleper import get_gcp_credentials_from_airflow, list_gcs_folders
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from airflow.utils.trigger_rule import TriggerRule


credentials = get_gcp_credentials_from_airflow(conn_id="google_cloud_default")

tickers = list_gcs_folders(bucket_name="clinical_data_may25",credentials=credentials)

def process_ticker_func(ticker):
    extractor = SECFilingExtractor(ticker=ticker,email="tanmayp@gmail.com", output_dir=f"sec_data/{ticker}")
    extractor.process_new_filings_only(
        form_types=["8-K", "10-K", "10-Q"],
        max_workers=2
    )

default_args = {
    'start_date': datetime(2025, 5, 13),
    'retries': 3,
    'retry_delay': timedelta(minutes=2)
}

with DAG("sec_filing_scheduler", schedule_interval="@daily", default_args=default_args, catchup=False) as dag:
    previous_task = None

    for ticker in tickers:
        task = PythonOperator(
            task_id=f"process_{ticker.lower()}",
            python_callable=process_ticker_func,
            op_args=[ticker],
            retries=3,
            retry_delay=timedelta(minutes=10),
            trigger_rule=TriggerRule.ALL_DONE if previous_task else "all_success"
        )

        if previous_task:
            previous_task >> task
        previous_task = task