"""volcsarvatory-monitoring processing for HyP3."""

import json
import logging
import os
import random
import subprocess
import zipfile
from pathlib import Path

import asf_search as asf
import boto3

from hyp3_query import list_pending_running_jobs_parameters, submit_jobs
from s1burst import MULTIBURST_JSON, create_aux_jsons, prepare_pairs, submit_pairs_burst
from timeseries import submit_timeseries


log = logging.getLogger('volcsarvatory_monitoring')
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


def check_id(product_id: str) -> bool:
    """Check if the ID qualifies for processing.

    Args:
        product_id: ID for a S1 product.

    Returns:
        qualifies: The product ID corresponds to a S1 burst.
    """
    if product_id.startswith('S1_') and 'BURST' in product_id:
        if '_VV_' in product_id or '_HH_' in product_id:
            return True
    return False


def product_id_from_message(message: dict) -> str:
    """Return a scene product ID from an SQS message.

    Args:
        message: SQS message as received from supported satellite missions (Sentinel-1).

    Returns:
        product_id: the product ID of a scene
    """
    # See `tests/integration/*-valid.json` for example messages
    match message:
        case {'granule_ur': product_id} if check_id(product_id):
            return product_id
        case _:
            raise ValueError(f'Unable to determine product ID from message {message}')


def product_mbid_from_message(message: dict) -> str:
    """Return a multiburst ID from an SQS message.

    Args:
        message: SQS message as received from updates in stack monitoring.

    Returns:
        mb_id: Multiburst ID.
    """
    # See `tests/integration/*-valid.json` for example messages
    match message:
        case {'mb_id': mb_id} if 'INT' in mb_id:
            return mb_id
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


def get_secret(key: str) -> str:
    """Retrieves the secret from AWS Secrets Manager.

    Args:
        key: key in AWS Secrets Manager.

    Returns:
        secret_key: value of the secret key
    """
    client = boto3.client('secretsmanager')
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
    key_file_path = Path('/tmp/ssh_key.pem')
    if not key_file_path.parent.exists():
        key_file_path.parent.mkdir(parents=True)
    fd = os.open(str(key_file_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o400)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(private_key_str)

        bucket_name = os.environ.get('PUBLISH_BUCKET')
        product_path = '/tmp' / Path(product)
        product_path.parent.mkdir(parents=True)
        s3 = boto3.client('s3')
        s3.download_file(bucket_name, product, str(product_path))
        with zipfile.ZipFile(str(product_path), mode='r') as archive:
            archive.extractall(str(product_path.parent))
        product_path.unlink()
        ssh_opts = [
            '-i',
            str(key_file_path),
            '-r',
        ]
        remote = 'geodesy@apps.avo.alaska.edu'
        remote_base = '/shared/data/geodesy/overlay-test'
        dest = f'{remote}:{remote_base}/insar/'
        try:
            subprocess.run(
                ['scp', *ssh_opts, str(product_path.parent.parent), dest],
                check=True,
            )
        finally:
            # Always clean up the extracted products directory
            subprocess.run(
                ['rm', '-rf', str(product_path.parent.parent)],
                check=False,
            )
    finally:
        # Ensure the SSH key file is removed even if an error occurs
        if key_file_path.exists():
            key_file_path.unlink()


def publish_sns_multiburst(mb_id: str) -> None:
    """Publish message in SNS topic for a new multiburst id.

    Args:
        mb_id: Multiburst ID.
    """
    client = boto3.client('sns')
    message = {'mb_id': f'{mb_id}'}
    _ = client.publish(
        TargetArn=os.environ['AOI_TOPIC_ARN'],
        Message=json.dumps(message),
    )


def lambda_handler(event: dict, context: object) -> dict:
    """Landsat processing lambda function.

    Accepts an event with SQS records for newly ingested S1-burst and processes each scene.

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
            body = json.loads(record['body'])
            message = body['Message']
            if 'New AOI' in message or 'New Test' in message:
                mb_ids = json.loads(MULTIBURST_JSON.read_text())
                keys = [key for key in mb_ids.keys()]
                if 'New Test' in message:
                    keys = random.sample(keys, 3)
                for mb_id in keys:
                    publish_sns_multiburst(mb_id)
            else:
                message = json.loads(message)
                mb_id = product_mbid_from_message(message)
                log.log(logging.INFO, f'Finding InSAR pairs for {mb_id}')
                jobs = prepare_pairs([mb_id])
                if len(jobs) > 0:
                    _ = submit_jobs(jobs)
                    log.log(logging.INFO, f'Jobs submitted for {mb_id}: {len(jobs)}')
        except Exception:
            log.exception(f'Could not process message {record["messageId"]}')
            batch_item_failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': batch_item_failures}


def lambda_bucket_handler(event: dict, context: object) -> dict:
    """Bucket notification processing lambda function.

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
                    pending = list_pending_running_jobs_parameters(job_type='VOLCSARVATORY_MINTPY', name=mbid)
                    if len(pending) > 0:
                        pass
                    else:
                        submit_timeseries([mbid])
        except Exception:
            log.exception(f'Could not process message {record["messageId"]}')
            batch_item_failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': batch_item_failures}


def main() -> None:
    """HyP3 entrypoint for volcsarvatory_monitoring."""
    create_aux_jsons()


if __name__ == '__main__':
    main()
