"""volcsarvatory-monitoring processing for HyP3."""

import json
import logging
import os

from s1burst import create_aux_jsons, submit_pairs_burst


log = logging.getLogger('its_live_monitoring')
log.setLevel(os.environ.get('LOGGING_LEVEL', 'INFO'))


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
            submit_pairs_burst(product_id)
        except Exception:
            log.exception(f'Could not process message {record["messageId"]}')
            batch_item_failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': batch_item_failures}


def main() -> None:
    """HyP3 entrypoint for volcsarvatory_monitoring."""
    create_aux_jsons()


if __name__ == '__main__':
    main()
