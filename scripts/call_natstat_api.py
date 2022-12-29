import logging
import sys
import time
import httpx
import json
from datetime import date
from google.cloud import storage
from dotenv import load_dotenv
import os

load_dotenv()

NETSTAT_API_URL = 'https://api.natstat.com/v1/playerperfs/NBA/'

PARAMS = {
    'key': os.getenv('NATSTAT_API_KEY'),
    'format': 'json',
    'start': '2010-10-26',
    'max': 1000
}

def setup_logging():
    logFormatter = logging.Formatter(
        "%(asctime)s [%(threadName)s] [%(levelname)s]  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z"
    )
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.INFO)


    file_name = 'natstat-api-calls.log'
    fileHandler = logging.FileHandler(file_name)
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    return rootLogger

def write_to_gcs(project, bucket_name, blob_name, data):
    """Write and read a blob from GCS using file-like IO"""
    storage_client = storage.Client(project=project)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    # Mode can be specified as wb/rb for bytes mode.
    # See: https://docs.python.org/3/library/io.html
    with blob.open("w") as f:
        json.dump(data, f)


def call_natstat_api(client: httpx.Client, url: str):
    """Call the natstat API and return the response"""
    r = client.get(url, timeout=60.0)
    return r


def call_natstat_api_with_pagination(client: httpx.Client, url: str, logger: logging.Logger) -> dict:
    """Call the natstat API and return the response"""
    
    logger.info(f'Calling natstat API with url: {url}')

    requests_made = 0
    response_time_start = time.time()
    r = call_natstat_api(client=client, url=url)
    requests_made += 1
    response_metadata = r.json()['meta']
    current_page = int(response_metadata['Page'])
    total_pages = int(response_metadata['Total_Pages'])
    logger.info(f'{r.status_code} response for page {current_page}/{total_pages} took: {time.time() - response_time_start} seconds')

    padded_current_page = str(current_page).zfill(5)
    padded_total_pages = str(total_pages).zfill(5)
    file_name = f'playerperfs/{date.today()}-{padded_current_page}-of-{padded_total_pages}.json'
    # Write the response to GCS
    write_to_gcs(
        project='ozymandias',
        bucket_name='natstat-nba-data', 
        blob_name=file_name, 
        data=r.json()
    )

    return r.json()

def main():
    logger = setup_logging()
    current_page = 1
    total_pages = 0
    next_page_url = NETSTAT_API_URL
    global_start_time = time.time()

    while current_page != total_pages and next_page_url is not None:
        with httpx.Client(params=PARAMS) as client:
            response = call_natstat_api_with_pagination(client=client, url=next_page_url, logger=logger)
            response_metadata = response['meta']
            current_page = int(response_metadata['Page'])
            total_pages = int(response_metadata['Total_Pages'])
            # Get the next page
            next_page_url = response_metadata.get('Next_Page')


    logger.info(f'Total time taken: {time.time() - global_start_time} seconds')


if __name__ == '__main__':
    main()