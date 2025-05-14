from airflow import DAG
from airflow.decorators import task
from utils.data_scrapper import SECFilingExtractor
from utils.hleper import get_gcp_credentials_from_airflow, list_gcs_folders
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from airflow.utils.trigger_rule import TriggerRule


credentials = get_gcp_credentials_from_airflow(conn_id="google_cloud_default")

#get all the available tickers from the gcs bucket
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

#run each dag but one at a time
with DAG("sec_filing_scheduler", schedule_interval="@daily", default_args=default_args, catchup=False, max_active_tasks=1) as dag:
    for ticker in tickers:
        task = PythonOperator(
            task_id=f"process_{ticker.lower()}",
            python_callable=process_ticker_func,
            op_args=[ticker],
            retries=2,
            retry_delay=timedelta(minutes=0.5),
        )
