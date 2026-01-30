"""Module to create auxiliary files and submit jobs to HyP3."""

import json
import logging
import os
from pathlib import Path

import asf_search as asf
import boto3
import geopandas as gpd
import hyp3_sdk as sdk
import ruamel.yaml as yaml
from asf_search.ASFProduct import ASFProduct

import aoi
import pairs
import prepare_multibursts as pm
import sbas


log = logging.getLogger('volcsarvatory_monitoring')
log.setLevel(os.environ.get('LOGGING_LEVEL', 'INFO'))

AOI = Path(__file__).parent / 'data' / 'aoi.yaml'

MULTIBURST_JSON = Path(__file__).parent / 'data' / 'multiburst.json'

PARQUET_DIR = Path(__file__).parent / 'data'

SENTINEL1_BURSTS_TO_PROCESS = Path(__file__).parent / 'data' / 'sentinel1_tiles_to_process.json'


def create_aux_jsons() -> None:
    """Finds overlapping burst(s) for given bounding box(es)."""
    yamlo = yaml.YAML(typ='rt')
    aois = yamlo.load(AOI.read_text())
    aoi_gdf, mb_dics = update_aoi_multibursts(aois)
    aoi.update_aoi(aoi_gdf)

    with MULTIBURST_JSON.open('w') as json_file:
        json.dump(mb_dics, json_file)

    update_burst_json()


def update_aoi_multibursts(aois: dict) -> tuple[gpd.GeoDataFrame, dict]:
    """Updates geoparquet for the AOIs and finds multiburst sets.

    Args:
        aois: Dictionary with the AOIs.

    Returns:
        aoi_gdf: Geoparquet with the AOIs intersecting land masks.
        mb_ids: multiburst ids for the multiburst sets.
    """
    aoi_ids = [key for key in aois]
    mb_dics: dict[str, dict] = dict()
    for id in aoi_ids:
        aoi_gdf = aoi.add_aoi(id, extent=aois[id]['AOI'])
        mb_dic = get_multibursts(aois, id)
        mb_ids = [key for key in mb_dic]
        aoi_gdf.loc[aoi_gdf['name'] == id, 'mb_ids'] = ','.join(mb_ids)
        mb_dics |= mb_dic
        print(f'Multibursts for {id}: {",".join(mb_ids)}')

    return aoi_gdf, mb_dics


def get_multibursts(aois: dict, id: str) -> dict:
    """Finds multiburst sets for an AOI.

    Args:
        aois: Dictionary with the AOIs.
        id: id for the AOI

    Returns:
        mb_dic: Dictionary with the multiburst sets.
    """
    burst_dict = aoi.get_burst_ids(aoi_id=id)
    burst_ids = [bid for bid in burst_dict.keys()]
    multibursts = pm.get_multibursts(burst_ids)
    mb_dic: dict[str, dict] = dict()
    resolution = aois[id]['resolution']
    for multiburst in multibursts:
        dic = multiburst.multiburst_dict
        mb_id = get_mbid(dic, resolution)
        mb_dic[mb_id] = dict()
        mb_dic[mb_id]['mb_set'] = dic
        mb_dic[mb_id]['temporal_baseline'] = aois[id]['temporal_baseline']
        mb_dic[mb_id]['season'] = aois[id]['season']
        mb_dic[mb_id]['target_date'] = aois[id]['target_date']
        mb_dic[mb_id]['bridge_years'] = aois[id]['bridge_years']
        mb_dic[mb_id]['resolution'] = resolution

    return mb_dic


def list_pairs_s3(mb_id: str) -> list[str]:
    """Lists pairs found in the s3 bucket.

    Args:
        mb_id: Multiburst ID.

    Returns:
        pairs: List of strings with pair dates.
    """
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(os.environ.get('PUBLISH_BUCKET'))

    # Use filter to apply a prefix; handles pagination automatically
    prefix = f'multiburst_products/{mb_id}'
    objects = bucket.objects.filter(Prefix=prefix)
    keys = [obj.key.split('IW')[1] for obj in objects]
    pairs = ['_'.join(key.split('_')[1:3]) for key in keys]

    return pairs


def get_mbid(dic: dict, resolution: str | None) -> str:
    """Finds the name for a multiburst set and given resolution.

    Args:
        dic: Dictionary with multiburst set.
        resolution: Resolution for the InSAR products [5x1, 10x2, 20x4].

    Returns:
        resolution: Resolution of the InSAR product [5x1, 10x2, 20x4].
    """
    keys = [key for key in dic.keys()]
    iw1s = [int(key.split('_')[1]) for key in keys if 'IW1' in dic[key]]
    iw2s = [int(key.split('_')[1]) for key in keys if 'IW2' in dic[key]]
    iw3s = [int(key.split('_')[1]) for key in keys if 'IW3' in dic[key]]
    iw1 = '000000'
    iw2 = '000000'
    iw3 = '000000'

    if resolution is None:
        res = '80'
    else:
        res = str(int(int(resolution.split('x')[0]) * int(resolution.split('x')[1]))).zfill(2)
    if len(iw1s) > 0:
        iw1 = str(min(iw1s)).zfill(6)
    if len(iw2s) > 0:
        iw2 = str(min(iw2s)).zfill(6)
    if len(iw3s) > 0:
        iw3 = str(min(iw3s)).zfill(6)
    path = keys[0].split('_')[0]
    swath1 = str(len(iw1s)).zfill(2)
    swath2 = str(len(iw2s)).zfill(2)
    swath3 = str(len(iw3s)).zfill(2)
    mb_id = f'{path}_{iw1}n{swath1}_{iw2}n{swath2}_{iw3}n{swath3}_INT{res}'

    return mb_id


def get_multibursts_ids(burst_id: str) -> list[str]:
    """Finds multiburst ids for the sets that contain a given burst id.

    Args:
        burst_id: ID for the burst.

    Returns:
        mb_ids: IDs for the multiburst sets that contain the given burst.
    """
    burst_dic = json.loads(MULTIBURST_JSON.read_text())
    path = burst_id.split('_')[0]
    frame = burst_id.split('_')[1]
    swath = burst_id.split('_')[-1]
    keys = [key for key in burst_dic.keys() if path in key]

    mb_ids = [mb_id for mb_id in keys if swath in burst_dic[mb_id]['mb_set'][f'{path}_{frame}']]
    return mb_ids


def deduplicate_pairs(
    multiburst_dict: dict,
    resolution: str | None,
    tbaseline: int | None,
    season: tuple[str, str] | None,
    target: str | None,
    bridge: int | None,
) -> tuple[list[str], list[str]]:
    """Deduplicates the pairs that have been already archived in the s3 bucket.

    Args:
        multiburst_dict: Dictionary with the multiburst set.
        resolution: Resolution of the multiburst products valid options are [5x1, 10x2, 20x4].
        tbaseline: Temporal in season baseline in days.
        season: Tuple of strings in the format month-day to define the season.
        target: String in the format month-day to define the target date to bridge the years.
        bridge: Number of years to bridge.

    Returns:
        refs: Deduplicated reference scenes.
        secs: Deduplicated secondary scenes.
    """
    refs, secs = [], []
    refst, secst = sbas.get_sbas_pairs(multiburst_dict, tbaseline, season, target, bridge)
    mb_id = get_mbid(multiburst_dict, resolution)
    pairst = sbas.list_pair_dates(refst, secst)
    bucket_pairs = list_pairs_s3(mb_id)
    for i, pair in enumerate(pairst):
        if pair not in bucket_pairs:
            refs.append(refst[i])
            secs.append(secst[i])

    return refs, secs


def submit_pairs_burst(burst_id: str) -> list[dict]:
    """Submit multiburst jobs for multiburst sets that contain a given burst.

    Args:
        burst_id: ID for the burst.

    Returns:
        jobs: Submitted multiburst jobs.
    """
    mb_ids = get_multibursts_ids(burst_id)
    jobs = submit_pairs(mb_ids)

    return jobs


def submit_pairs(mb_ids: list[str]) -> list[dict]:
    """Submit multiburst jobs for multiburst sets.

    Args:
        mb_ids: IDs for the multiburst sets.

    Returns:
        jobs: Submitted multiburst jobs.
    """
    hyp3 = sdk.HyP3(
        os.environ.get('HYP3_API'),
        username=os.environ.get('EARTHDATA_USERNAME'),
        password=os.environ.get('EARTHDATA_PASSWORD'),
    )
    mbs_dic = json.loads(MULTIBURST_JSON.read_text())

    insar_jobs = []
    for mb_id in mb_ids:
        mb_set = mbs_dic[mb_id]['mb_set']
        tbaseline = mbs_dic[mb_id]['temporal_baseline']
        season = mbs_dic[mb_id]['season']
        target = mbs_dic[mb_id]['target_date']
        bridge = mbs_dic[mb_id]['bridge_years']
        resolution = mbs_dic[mb_id]['resolution']
        refs, secs = deduplicate_pairs(mb_set, resolution, tbaseline, season, target, bridge)

        insar_jobs += pairs.prepare_multiburst_jobs(refs, secs, mb_id, hyp3, looks=resolution, apply_water_mask=True)

    jobs = pairs.submit_jobs(insar_jobs, hyp3)
    return jobs


def initial_run() -> list[dict]:
    """Initial run for the deployment."""
    create_aux_jsons()

    burst_dic = json.loads(MULTIBURST_JSON.read_text())
    mb_ids = [key for key in burst_dic.keys()]
    jobs = submit_pairs(mb_ids)

    return jobs


def update_burst_json() -> None:
    """Updates the json that contains burst id to be processed."""
    burst_dic = json.loads(MULTIBURST_JSON.read_text())
    burst_ids = []
    for mb_id in burst_dic.keys():
        for key in burst_dic[mb_id]['mb_set']:
            for swath in burst_dic[mb_id]['mb_set'][key]:
                burst_ids.append(f'{key}_{swath}')

    with SENTINEL1_BURSTS_TO_PROCESS.open('w') as json_file:
        json.dump(burst_ids, json_file)


def product_qualifies_for_sentinel1_processing(product: ASFProduct, log_level: int = logging.DEBUG) -> bool:
    """Check if a Sentinel-1 Burst product qualifies for processing."""
    burst_id = product.properties['burst']['fullBurstID']
    bursts = json.loads(SENTINEL1_BURSTS_TO_PROCESS.read_text())
    if burst_id not in bursts:
        log.log(log_level, f'{burst_id} disqualifies for processing because it is not from a burst containing land-ice')
        return False

    if (polarization := product.properties['polarization']) not in [asf.constants.VV, asf.constants.HH]:
        log.log(log_level, f'{burst_id} disqualifies for processing because it has a {polarization} polarization')
        return False

    log.log(log_level, f'{burst_id} qualifies for processing')
    return True
