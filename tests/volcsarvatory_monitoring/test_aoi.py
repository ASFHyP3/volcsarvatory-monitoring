from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import Polygon

import aoi


def test_add_aoi() -> None:
    bbox = [-176.25, -175.92, 51.95, 52.14]
    gdf = aoi.add_aoi('test', bbox)

    assert aoi.PARQUET_FILE.exists()
    assert 'test' in gdf['name'].values

    aoi.PARQUET_FILE.unlink()


def test_get_aoi() -> None:
    bbox = [-176.25, -175.92, 51.95, 52.14]
    gdf = aoi.add_aoi('test', bbox)
    gdf = aoi.get_aoi()

    assert 'test' in gdf['name'].values
    aoi.PARQUET_FILE.unlink()


@patch('aoi.load_s1_parquet')
@patch('aoi.asf.search')
def test_get_burst_ids(mock_asf_search, mock_load, asf_product_factory, asf_stack_factory):
    scene_name = 'S1_077634_IW1_20251003T154900_VV_657C-BURST'
    full_burst_id = '037_077634_IW1'

    max_pair_seperation_in_days = 48
    expected_stacks = asf_stack_factory(
        scene_name, full_burst_id, days_separation=range(0, max_pair_seperation_in_days + 1, 6)
    )
    mock_asf_search.side_effect = [*expected_stacks]

    bbox = [-176.25, -175.92, 51.95, 52.14]
    gdf = aoi.add_aoi('test', bbox)

    assert not gdf.empty

    ullon, lrlon, lrlat, ullat = bbox
    poly = Polygon([(ullon, ullat, 0), (ullon, lrlat, 0), (lrlon, lrlat, 0), (lrlon, ullat, 0)])
    s1_gdf = gpd.GeoDataFrame({'id': ['037_077634_IW1'], 'geometry': [poly]}, crs='EPSG:4326')
    mock_load.return_value = s1_gdf

    burst_dic = aoi.get_burst_ids()

    assert '037_077634_IW1' in burst_dic.keys()
    assert 'test' in burst_dic['037_077634_IW1']
    aoi.PARQUET_FILE.unlink()
