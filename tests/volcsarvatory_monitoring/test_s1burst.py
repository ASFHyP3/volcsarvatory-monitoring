import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import responses

import s1burst


def test_get_mbid():
    mb_dic = {
        '000_000001': ('IW1',),
        '000_000002': ('IW1', 'IW2'),
        '000_000003': ('IW1', 'IW2', 'IW3'),
        '000_000004': ('IW1',),
    }

    mb_id = s1burst.get_mbid(mb_dic, resolution=None)

    assert mb_id == '000_000001n04_000002n02_000003n01_INT80'

    mb_id = s1burst.get_mbid(mb_dic, resolution='5x1')

    assert mb_id == '000_000001n04_000002n02_000003n01_INT05'


@responses.activate
@patch('s1burst.aoi.get_burst_ids')
def test_get_multibursts(mock_burst_ids):
    mock_url = 'https://cmr.earthdata.nasa.gov/search/granules.umm_json'

    responses.add(
        responses.GET,
        mock_url,
        body=json.dumps(json.loads((Path(__file__).parent / 'data' / 'multiburst_valid.json').read_text())),
        status=200,
        content_type='application/json',
    )
    mock_burst_ids.return_value = {'000_000001_IW1': ['test']}

    aoi_dic = {
        'test': {
            'resolution': '20x4',
            'season': ('1-1', '12-31'),
            'temporal_baseline': 48,
            'target_date': '6-1',
            'bridge_years': 1,
        }
    }

    mb_dic = s1burst.get_multibursts(aoi_dic, 'test')
    key = '000_000001n01_000000n00_000000n00_INT80'

    assert key in mb_dic.keys()
    assert 'mb_set' in mb_dic[key].keys()


@patch('s1burst.get_multibursts')
def test_update_aoi_multibursts(mock_multibursts):
    bbox = [-176.25, -175.92, 51.95, 52.14]
    aoi_dic = {'test': {'AOI': bbox}, 'test1': {'AOI': bbox}}
    mb_dic1: dict[str, dict] = {
        '000_000001n01_000000n00_000000n00_INT80': {'mb_set': {}},
        '000_000002n01_000000n00_000000n00_INT80': {'mb_set': {}},
    }
    mb_dic2: dict[str, dict] = {
        '000_000003n01_000000n00_000000n00_INT80': {'mb_set': {}},
        '000_000004n01_000000n00_000000n00_INT80': {'mb_set': {}},
    }
    mock_multibursts.side_effect = [mb_dic1, mb_dic2]
    aoi_gdf, mb_dics = s1burst.update_aoi_multibursts(aoi_dic)

    assert not (aoi_gdf[aoi_gdf['name'] == 'test'].empty or aoi_gdf[aoi_gdf['name'] == 'test1'].empty)
    assert '000_000003n01_000000n00_000000n00_INT80' in mb_dics
    assert len(mb_dics) == 4
    s1burst.aoi.PARQUET_FILE.unlink()


def test_list_bursts() -> None:
    mb_set = {
        '000_000001': ('IW1',),
        '000_000002': ('IW2',),
    }
    mb_dic = {'000_000001n01_000000n00_000000n00_INT80': {'mb_set': mb_set}}
    burst_ids = s1burst.list_bursts(mb_dic)

    assert '000_000001_IW1' in burst_ids
    assert '000_000002_IW2' in burst_ids


@patch('s1burst.list_s3_objects')
def test_list_pairs_s3(mock_s3_objects) -> None:
    mb_id = '000_000000s1n00_000000s2n00_344433s3n01_INT80'
    list_objs = [
        f'multiburst_products/{mb_id}/S1_161_000000s1n00-000000s2n00-344433s3n01_IW_20210313_20210406_VV_INT80_0000.zip',
        f'multiburst_products/{mb_id}/S1_161_000000s1n00-000000s2n00-344433s3n01_IW_20210313_20210407_VV_INT80_0000.zip',
        f'multiburst_products/{mb_id}/S1_161_000000s1n00-000000s2n00-344433s3n01_IW_20210314_20210406_VV_INT80_0000.zip',
    ]
    mock_s3_objects.return_value = list_objs
    expected = ['20210313_20210406', '20210313_20210407', '20210314_20210406']

    list_pairs = s1burst.list_pairs_s3(mb_id)
    print(list_pairs)

    assert expected == list_pairs


def test_get_multibursts_ids():
    mb_dic = {
        '000_000001n01_000000n00_000000n00_INT80': {'mb_set': {'000_000001': ('IW1',)}},
        '000_000002n01_000000n00_000000n00_INT80': {'mb_set': {'000_000002': ('IW1',)}},
    }
    with s1burst.MULTIBURST_JSON.open('w') as json_file:
        json.dump(mb_dic, json_file)
    mb_ids = s1burst.get_multibursts_ids('000_000001_IW1')

    assert '000_000001n01_000000n00_000000n00_INT80' in mb_ids

    s1burst.MULTIBURST_JSON.unlink()


@patch('s1burst.list_s3_objects')
@patch('s1burst.sbas.get_sbas_pairs')
def test_deduplicate_pairs(mock_sbas_pairs, mock_s3_objects) -> None:
    mb_dic = {
        '000_000001': ('IW1',),
        '000_000002': ('IW1',),
    }

    resolution = '20x4'
    mb_id = s1burst.get_mbid(mb_dic, resolution=resolution)

    refs = [
        'S1_000001_IW1_00000000T000000_VV_0001-BURST',
        'S1_000001_IW1_00000001T000000_VV_0001-BURST',
        'S1_000002_IW1_00000000T000000_VV_0001-BURST',
        'S1_000002_IW1_00000001T000000_VV_0001-BURST',
    ]

    secs = [
        'S1_000001_IW1_00000001T000000_VV_0001-BURST',
        'S1_000001_IW1_00000003T000000_VV_0001-BURST',
        'S1_000002_IW1_00000001T000000_VV_0001-BURST',
        'S1_000002_IW1_00000003T000000_VV_0001-BURST',
    ]
    list_objs = [
        f'multiburst_products/{mb_id}/S1_{"-".join(mb_id.split("_")[0:-1])}_IW_00000000_00000001_VV_INT80_0000.zip'
    ]
    mock_s3_objects.return_value = list_objs

    mock_sbas_pairs.return_value = (refs, secs)

    refs_out, secs_out = s1burst.deduplicate_pairs(mb_dic, resolution, None, None, None, None)
    print(refs_out)
    refs_exp = [
        'S1_000001_IW1_00000001T000000_VV_0001-BURST',
        'S1_000002_IW1_00000001T000000_VV_0001-BURST',
    ]

    secs_exp = [
        'S1_000001_IW1_00000003T000000_VV_0001-BURST',
        'S1_000002_IW1_00000003T000000_VV_0001-BURST',
    ]

    assert refs_out == refs_exp
    assert secs_out == secs_exp


@patch('s1burst.deduplicate_pairs')
def test_prepare_pairs(mock_deduplicate) -> None:
    mb_dic = {
        '000_000001n02_000000n00_000000n00_INT80': {
            'mb_set': {'000_000001': ('IW1',), '000_000002': ('IW1',)},
            'temporal_baseline': None,
            'season': None,
            'target_date': None,
            'bridge_years': None,
            'resolution': None,
        }
    }
    with s1burst.MULTIBURST_JSON.open('w') as json_file:
        json.dump(mb_dic, json_file)

    mb_ids = [key for key in mb_dic.keys()]

    refs = [
        'S1_000001_IW1_00000000T000000_VV_0001-BURST',
        'S1_000001_IW1_00000001T000000_VV_0001-BURST',
        'S1_000002_IW1_00000000T000000_VV_0001-BURST',
        'S1_000002_IW1_00000001T000000_VV_0001-BURST',
    ]

    secs = [
        'S1_000001_IW1_00000001T000000_VV_0001-BURST',
        'S1_000001_IW1_00000003T000000_VV_0001-BURST',
        'S1_000002_IW1_00000001T000000_VV_0001-BURST',
        'S1_000002_IW1_00000003T000000_VV_0001-BURST',
    ]

    mock_deduplicate.return_value = (refs, secs)

    jobs = s1burst.prepare_pairs(mb_ids)

    assert len(jobs) == 2
    assert 'job_type' in jobs[0].keys()
    assert jobs[0]['job_type'] == 'INSAR_ISCE_MULTI_BURST'
    assert jobs[0]['job_parameters']['reference'] == [
        'S1_000001_IW1_00000000T000000_VV_0001-BURST',
        'S1_000002_IW1_00000000T000000_VV_0001-BURST',
    ]

    s1burst.MULTIBURST_JSON.unlink()


def test_product_qualifies_sentinel1_processing(asf_product_factory) -> None:
    scene_name = 'S1_125344_IW1_20251003T154900_VV_657C-BURST'
    full_burst_id = '059_125344_IW1'
    polarization = 'VV'
    start_time = '2025-10-03T15:49:00+00:00'
    good_product = asf_product_factory(scene_name, full_burst_id, polarization, start_time)

    assert s1burst.product_qualifies_for_sentinel1_processing(good_product)

    product = deepcopy(good_product)
    product.properties['burst']['fullBurstID'] = 'foobar'
    assert not s1burst.product_qualifies_for_sentinel1_processing(product)

    product = deepcopy(good_product)
    product.properties['polarization'] = 'HH'
    assert s1burst.product_qualifies_for_sentinel1_processing(product)

    product = deepcopy(good_product)
    product.properties['polarization'] = 'HV'
    assert not s1burst.product_qualifies_for_sentinel1_processing(product)
