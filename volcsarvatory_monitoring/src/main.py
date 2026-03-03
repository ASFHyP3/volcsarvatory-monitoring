"""volcsarvatory-monitoring processing for HyP3."""

import json
import logging
import os

import asf_search as asf

from hyp3_query import list_pending_running_jobs_parameters
from s1burst import create_aux_jsons, initial_run, submit_pairs_burst
from timeseries import submit_timeseries


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


def product_mbid_from_bucket(message: dict) -> str:
    """Return a multiburst product ID from an SQS message.

    Args:
        message: SQS message as received from supported satellite missions (Sentinel-1).

    Returns:
        product_id: the product ID of a scene
    """
    # See `tests/integration/*-valid.json` for example messages
    records = message['Records']
    if len(records) == 0:
        raise ValueError(f'Unable to determine product ID from message {message}')
    else:
        key = records[0]['s3']['object']['key']
        return key.split('/')[1]


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
        except Exception:
            log.exception(f'Could not process message {record["messageId"]}')
            batch_item_failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': batch_item_failures}


def lambda_mintpy_handler(event: dict, context: object) -> dict:
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
            mbid = product_mbid_from_bucket(message)
            pending = list_pending_running_jobs_parameters(job_type='INSAR_ISCE_MULTI_BURST', name=mbid)
            if len(pending) > 0:
                pass
            else:
                submit_timeseries([mb_id])
        except Exception:
            log.exception(f'Could not process message {record["messageId"]}')
            batch_item_failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': batch_item_failures}


def main() -> None:
    """HyP3 entrypoint for volcsarvatory_monitoring."""
    create_aux_jsons()


if __name__ == '__main__':
    main()
