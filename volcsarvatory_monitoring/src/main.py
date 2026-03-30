"""volcsarvatory-monitoring processing for HyP3."""

import json
import logging
import os
import subprocess
from pathlib import Path

import asf_search as asf
import boto3

from hyp3_query import list_pending_running_jobs_parameters
from s1burst import MULTIBURST_JSON, create_aux_jsons, initial_run, submit_pairs_burst
from timeseries import list_mbids_bucket, submit_timeseries


log = logging.getLogger('its_live_monitoring')
log.setLevel(os.environ.get('LOGGING_LEVEL', 'INFO'))


def get_burst_id(scene: str) -> str:
    """Return the burst ID from a scene name.

    Args:
        scene: Scene burst name.

    Returns:
        burst_id: the burst ID of a scene
    """
    results = asf.granule_search(scene)

    if len(results) == 0:
        raise ValueError(f'Sentinel-1 Burst {scene} could not be found')

    return results[0].properties['burst']['fullBurstID']


def product_id_from_message(message: dict) -> str:
    """Return a scene product ID from an SQS message.

    Args:
        message: SQS message as received from supported satellite missions (Sentinel-1).

    Returns:
        product_id: the product ID of a scene
    """
    # See `tests/integration/*-valid.json` for example messages
    match message:
        case {'granule_ur': product_id} if product_id.startswith('S1'):
            return product_id
        case _:
            raise ValueError(f'Unable to determine product ID from message {message}')


def check_multiburst_product(message: dict) -> bool:
    """Check if file in bucket is a multiburst product.

    Args:
        message: SQS message as received from supported satellite missions (Sentinel-1).

    Returns:
        product_id: the product ID of a scene
    """
    # See `tests/integration/*-valid.json` for example messages
    key = get_product(message)
    return 'multiburst_products' in key


def product_mbid_from_bucket(message: dict) -> str:
    """Return a multiburst product ID from an SQS message.

    Args:
        message: SQS message as received from supported satellite missions (Sentinel-1).

    Returns:
        product_id: the product ID of a scene
    """
    # See `tests/integration/*-valid.json` for example messages
    key = get_product(message)
    return key.split('/')[1]


def get_product(message: dict) -> str:
    """Return a multiburst product ID from an SQS message.

    Args:
        message: SQS message as received from supported satellite missions (Sentinel-1).

    Returns:
        product_id: the key of a scene
    """
    # See `tests/integration/*-valid.json` for example messages
    records = message['Records']
    if len(records) == 0:
        raise ValueError(f'Unable to determine product ID from message {message}')
    else:
        key = records[0]['s3']['object']['key']
        return key


def lambda_handler(event: dict, context: object) -> dict:
    """Landsat processing lambda function.

    Accepts an event with SQS records for newly ingested Landsat scenes and processes each scene.

    Args:
        event: The event dictionary that contains the parameters sent when this function is invoked.
        context: The context in which is function is called.

    Returns:
        AWS SQS batchItemFailures JSON response including messages that failed to be processed
    """
    batch_item_failures = []
    for record in event['Records']:
        try:
            body = json.loads(record['body'])
            message = json.loads(body['Message'])
            product_id = product_id_from_message(message)
            burst_id = get_burst_id(product_id)
            submit_pairs_burst(burst_id)
        except Exception:
            log.exception(f'Could not process message {record["messageId"]}')
            batch_item_failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': batch_item_failures}


def lambda_aoi_handler(event: dict, context: object) -> dict:
    """Landsat processing lambda function.

    Accepts an event with SQS records for newly ingested Landsat scenes and processes each scene.

    Args:
        event: The event dictionary that contains the parameters sent when this function is invoked.
        context: The context in which is function is called.

    Returns:
        AWS SQS batchItemFailures JSON response including messages that failed to be processed
    """
    batch_item_failures = []
    for record in event['Records']:
        try:
            jobs = initial_run()
            mb_ids = json.loads(MULTIBURST_JSON.read_text())
            mb_ids_pending = [job['name'] for job in jobs]
            mb_ids_bucket = list_mbids_bucket()
            mb_ids_missing = list(set(mb_ids).difference(set(mb_ids_bucket)))
            mb_ids_missing = list(set(mb_ids_missing).difference(set(mb_ids_pending)))
            submit_timeseries(mb_ids_missing)
        except Exception:
            log.exception(f'Could not process message {record["messageId"]}')
            batch_item_failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': batch_item_failures}


def get_secret(key: str) -> str:
    """Retrieves the secret from AWS Secrets Manager.

    Args:
        secret_name: secret name in AWS Secrets Manager.

    Returns:
        secret_key: value of the secret key
    """
    try:
        access_key_id = os.environ['AWS_ACCESS_KEY_ID']
        access_key_secret = os.environ['AWS_SECRET_ACCESS_KEY']
    except KeyError:
        raise ValueError(
            'Please provide S3 Bucket upload access key credentials via the '
            'AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables'
        )
    client = boto3.client('secretsmanager', aws_access_key_id=access_key_id, aws_secret_access_key=access_key_secret, region_name=os.environ['AWS_REGION'])
    private_key_str = ''
    secret_name = 'hyp3-volcsarvatory'
    try:
        response = client.get_secret_value(SecretId=secret_name)
        if key in response:
            private_key_str = response[key]
        # Handle binary secrets if needed
    except Exception as e:
        print(f'Error retrieving secret: {e}')
        raise e
    return private_key_str


def transfer_file(product: str) -> None:
    """Transfer file from s3 bucket to AVO server.

    Args:
        product: key for file in s3 bucket.
    """
    private_key_str = get_secret('SSH_KEY')
    key_file_path = '/tmp/ssh_key.pem'
    with Path(key_file_path).open('w') as f:
        f.write(private_key_str)
    # Change permissions as required by SSH (read-only for the owner)
    Path(key_file_path).chmod(0o400)

    bucket_name = os.environ.get('PUBLISH_BUCKET')
    s3 = boto3.client('s3')
    s3.download_file(bucket_name, product, product)
    ssh_opts = [
        '-i',
        '/tmp/ssh_key.pem',
        '-o',
        'BatchMode=yes',
        '-o',
        'IdentitiesOnly=yes',
        '-o',
        'ControlMaster=auto',
        '-o',
        'ControlPersist=10m',
        '-o',
        'ControlPath=~/.ssh/cm-%r@%h:%p',
    ]
    remote = 'geodesy@apps.avo.alaska.edu'
    remote_base = '/shared/data/geodesy/overlay-test'
    dest = f'{remote}:{remote_base}/insar/{product}'
    subprocess.run(['scp', *ssh_opts, product, dest], check=True)


def lambda_bucket_handler(event: dict, context: object) -> dict:
    """Landsat processing lambda function.

    Accepts an event with SQS records for newly ingested Landsat scenes and processes each scene.

    Args:
        event: The event dictionary that contains the parameters sent when this function is invoked.
        context: The context in which is function is called.

    Returns:
        AWS SQS batchItemFailures JSON response including messages that failed to be processed
    """
    batch_item_failures = []
    for record in event['Records']:
        try:
            body = json.loads(record['body'])
            message = json.loads(body['Message'])
            if check_multiburst_product(message):
                mbid = product_mbid_from_bucket(message)
                pending = list_pending_running_jobs_parameters(job_type='INSAR_ISCE_MULTI_BURST', name=mbid)
                if len(pending) > 0:
                    pass
                else:
                    submit_timeseries([mbid])
            product = get_product(message)
            transfer_file(product)
        except Exception:
            log.exception(f'Could not process message {record["messageId"]}')
            batch_item_failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': batch_item_failures}


def main() -> None:
    """HyP3 entrypoint for volcsarvatory_monitoring."""
    create_aux_jsons()


if __name__ == '__main__':
    main()
