import datetime as dt
from copy import deepcopy

import pytest
from asf_search.ASFProduct import ASFProduct
from dateutil.parser import parse as date_parser


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
        product.properties.update(
            {
                'sceneName': scene_name,
                'startTime': start_time,
                'polarization': polarization,
                'burst': {'fullBurstID': full_burst_id},
            }
        )

        date_str = f'{scene_name.split("_")[3]}_{scene_name.split("_")[3]}'
        product.umm = {'InputGranules': [f'S1A_IW_SLC__1SDV_{date_str}_000000_000000_0000-SLC']}
        return deepcopy(product)

    return create_asf_product
