import datetime as dt
import json
from copy import deepcopy
from pathlib import Path

import pytest
from asf_search.ASFProduct import ASFProduct
from asf_search.ASFSearchResults import ASFSearchResults
from dateutil.parser import parse as date_parser


@pytest.fixture
def asf_stack_factory(asf_product_factory):
    def create_asf_burst_stacks(
        scene_name: str,
        full_burst_id: str,  # track is not easily derived from scene name
        days_separation: range = range(0, 13, 6),
    ) -> list[ASFSearchResults]:
        _, _, _, start_time, polarization, _ = scene_name.split('_')
        start_times = [date_parser(start_time) - dt.timedelta(days=ii) for ii in days_separation]
        scene_names = [scene_name.replace(start_time, st.strftime('%Y%m%dT%H%M%S')) for st in start_times]

        stacks = []
        fbid = full_burst_id
        burst_ids = [
            f'{fbid.split("_")[0]}_{str(int(fbid.split("_")[1]) + i).zfill(6)}_{fbid.split("_")[2]}' for i in range(3)
        ]
        for burst_id in burst_ids:
            stack = ASFSearchResults()
            stack.data = [
                asf_product_factory(sn, burst_id, polarization, st) for sn, st in zip(scene_names, start_times)
            ]
            stacks.append(stack)

        return stacks

    return create_asf_burst_stacks


@pytest.fixture
def asf_product_factory():
    def create_asf_product(
        scene_name: str,
        full_burst_id: str,
        polarization: str,
        start_time: str | dt.datetime,
    ) -> ASFProduct:
        if isinstance(start_time, str):
            start_time = date_parser(start_time)

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=dt.UTC)

        start_time = start_time.isoformat(timespec='seconds')

        product = ASFProduct()
        product.baseline = {'stateVectors': {'positions': {}}}
        product.properties.update(
            {
                'sceneName': scene_name,
                'startTime': start_time,
                'stopTime': start_time,
                'polarization': polarization,
                'burst': {'fullBurstID': full_burst_id},
            }
        )

        date_str = f'{scene_name.split("_")[3]}_{scene_name.split("_")[3]}'
        product.umm = {'InputGranules': [f'S1A_IW_SLC__1SDV_{date_str}_000000_000000_0000-SLC']}
        return deepcopy(product)

    return create_asf_product


@pytest.fixture(scope='session')
def sentinel1_burst_message():
    example = Path(__file__).parent / 'integration' / 'sentinel1-burst-valid.json'
    return json.loads(example.read_text())
