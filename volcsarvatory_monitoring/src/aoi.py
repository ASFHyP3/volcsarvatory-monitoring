"""Module to add aois to geoparquet."""

import warnings
from datetime import datetime, timedelta
from pathlib import Path

import asf_search as asf
import cartopy
import cartopy.feature as cfeature
import fsspec
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rioxarray as rio  # noqa
import xarray as xr
from scipy.optimize import curve_fit
from shapely.geometry import Polygon


PARQUET_FILE = Path(__file__).parent / 'data' / 'aoi_vol.parquet'

cartopy.config['data_dir'] = '/tmp'
cartopy.config['pre_existing_data_dir'] = '/tmp'
land_50m = cfeature.NaturalEarthFeature('physical', 'land', '10m')
land_polygons_cartopy = list(land_50m.geometries())
land_gdf = gpd.GeoDataFrame(crs='epsg:4326', geometry=land_polygons_cartopy)


def get_aoi() -> gpd.GeoDataFrame:
    """Reads the parquet file with the areas of interest."""
    aoigdf = gpd.read_parquet(f'{PARQUET_FILE}')
    aoigdf = aoigdf.to_crs('EPSG:4326')
    return aoigdf


def add_aoi(id: str, extent: list) -> gpd.GeoDataFrame:
    """Adds or replaces an area of interest in the parquet file.

    Args:
        id: Id for the area of interest.
        extent: List of lon/lat coordinates for the area of interest in the format [minlon, maxlon, minlat, maxlat].

    Returns:
        intersection: Geopandas dataframe with the intersection between the area of interest and the land mask.
    """
    ullon, lrlon, lrlat, ullat = extent
    poly = Polygon([(ullon, ullat, 0), (ullon, lrlat, 0), (lrlon, lrlat, 0), (lrlon, ullat, 0)])
    new_aoi = gpd.GeoDataFrame(
        {'name': [id], 'geometry': [poly], 'bbox': ','.join(str(item) for item in extent), 'mb_ids': ['']},
        crs='EPSG:4326',
    )
    if Path(f'{PARQUET_FILE}').exists():
        aoi_gdf = gpd.read_parquet(f'{PARQUET_FILE}')
        if len(aoi_gdf[aoi_gdf['name'] == id]) > 0:
            if len(aoi_gdf[(aoi_gdf['name'] == id) & (aoi_gdf['bbox'] == ','.join(str(item) for item in extent))]) > 0:
                return aoi_gdf
            else:
                warnings.warn('An AOI with the same ID exists in the dataframe. Replacing...', UserWarning)
                aoi_gdf = aoi_gdf[aoi_gdf['name'] != id]
        aoi_gdf = gpd.GeoDataFrame(pd.concat([aoi_gdf, new_aoi], ignore_index=True))
    else:
        aoi_gdf = new_aoi
    intersection = gpd.overlay(aoi_gdf, land_gdf, how='intersection')
    intersection.to_parquet(f'{PARQUET_FILE}')

    return aoi_gdf


def get_coherence(extent: list) -> dict[datetime, float]:
    """Calculates the expected S1 coherence from an extent.

    Args:
        extent: List of lon/lat coordinates for the area of interest in the format [minlon, maxlon, minlat, maxlat].

    Returns:
        cvalues: Expected coherence values for each season.
    """
    coherence: dict[str, dict] = dict()
    cvalues: dict[datetime, float] = dict()
    num: dict[datetime, int] = dict()
    lons = extent[0:2]
    lats = extent[2::]
    minx, miny, maxx, maxy = min(lons), min(lats), max(lons), max(lats)
    seasons = ['winter', 'spring', 'summer', 'fall']
    nseasons = ['01', '04', '07', '10']
    temporals = [str(i).zfill(2) for i in [6, 12, 18, 24, 36, 48]]
    for temp in temporals:
        coherence[temp] = dict()
        for i, season in enumerate(seasons):
            uri = f's3://asf-search-coh/global_coh_100ppd_11367x4367_Zarrv2/Global_{season}_vv_COH{temp}_100ppd.zarr'
            ds = xr.open_zarr(fsspec.get_mapper(uri, s3={'anon': True}), consolidated=False)
            ds = ds.rio.write_crs('EPSG:4326', inplace=False)
            try:
                subset = ds.rio.clip_box(minx=minx, miny=miny, maxx=maxx, maxy=maxy, allow_one_dimensional_raster=True)
                coherence[temp][season] = subset.coherence.mean().compute().item()
                date = datetime.strptime(f'2019-{nseasons[i]}-01', '%Y-%m-%d')
                if not np.isnan(coherence[temp][season]):
                    if date not in cvalues.keys():
                        cvalues[date] = coherence[temp][season]
                        num[date] = 1
                    else:
                        cvalues[date] += coherence[temp][season]
                        num[date] += 1
            except Exception:
                pass
    for key in cvalues.keys():
        cvalues[key] = cvalues[key] / (100 * num[key])
    plot_coherence(cvalues)
    return cvalues


def normal_curve(x: np.ndarray, amplitude: float, mean: float, std_dev: float, xoff: float, yoff: float) -> np.ndarray:
    """Normal distribution.

    Args:
        x: x coordinates for the normal distribution
        amplitude: scaling parameter
        mean: mean of the normal distribution
        std_dev: standard deviation for the normal distribution
        xoff: offset in the x coordinates
        yoff: offset in the y coordinates

    Returns:
        values: y coordinates for the normal distribution.
    """
    return amplitude * np.exp(-(((x + xoff) - mean) ** 2) / (2 * std_dev**2)) + yoff


def get_season(id: str, extent: list) -> tuple[datetime, tuple]:
    """Calculates the season and target for an AOI.

    Args:
        id: Name of the AOI
        extent: List of lon/lat coordinates for the area of interest in the format [minlon, maxlon, minlat, maxlat].

    Returns:
        target: Date with the expected maximum coherence
        season: Pair of dates with the ideal season for the AOI.
    """
    coherence = get_coherence(extent)
    start = datetime.strptime('2019-01-01', '%Y-%m-%d')
    days = [(date - start).days for date in coherence.keys()]
    days += [days[-1]]
    values = [coherence[key] for key in coherence.keys()]
    values += [values[-1]]
    initial_guess = [max(values), np.mean(days), np.std(days), 0, 0]
    parameters, covariance = curve_fit(normal_curve, days, values, p0=np.array(initial_guess))
    fitted_amp, fitted_mean, fitted_std, fitted_xoff, fitted_yoff = parameters
    target = start + timedelta(days=int(fitted_mean - fitted_xoff))
    portion = 0.34
    ran = int(portion * 365)
    season = (target - timedelta(days=int(ran)), target + timedelta(days=int(ran)))
    all_days = np.arange(0, 366)
    normal = dict()
    normal['values'] = normal_curve(all_days, fitted_amp, fitted_mean, fitted_std, fitted_xoff, fitted_yoff)
    normal['days'] = np.array([start + timedelta(days=int(day)) for day in all_days])
    plot_coherence(coherence, target, season, normal, name=id)

    return target, season


def plot_coherence(
    coherence: dict,
    target: datetime | None = None,
    season: tuple[datetime, datetime] | None = None,
    normal: dict | None = None,
    name: str | None = None,
) -> None:
    """Plot the expected coherence for an AOI.

    Args:
        coherence: Dictionary with the coherence values
        target: Ideal date to bridge the years or components
        season: Ideal SBAS season for the AOI
        normal: Dictionary with the values of the normal distribution
        name: Name of the AOI
    """
    import matplotlib.dates as mdates

    dates = [key for key in coherence.keys()]
    values = [coherence[key] for key in coherence.keys()]
    if season is not None:
        seasont = list(season)
        season0 = datetime.strptime(seasont[0].strftime('2019-%m-%d'), '%Y-%m-%d')
        season1 = datetime.strptime(seasont[1].strftime('2019-%m-%d'), '%Y-%m-%d')
        season = (season0, season1)
    plt.figure(figsize=(4, 3))
    if normal is not None:
        plt.plot(normal['days'], normal['values'])
        plt.axvline(target, color='black', label='Target')  # type: ignore
        plt.axvline(season[0], color='blue', label='Start')  # type: ignore
        plt.axvline(season[1], color='red', label='End')  # type: ignore
    plt.scatter(dates, values, label='Coherence')
    plt.legend()
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    plt.ylabel('Coherence')
    plt.xlabel('Date')
    plt.savefig(f'coherence_{name}.pdf', bbox_inches='tight')


def update_aoi(gdf: gpd.GeoDataFrame) -> None:
    """Update AOI with a new geoparquet."""
    gdf.to_parquet(f'{PARQUET_FILE}')


def load_s1_parquet() -> gpd.GeoDataFrame:
    """Loads parquet file with Sentinel-1 bursts.

    Returns:
        s1_gdf: Geopandas dataframe with Sentinel-1 bursts.
    """
    s3_url = 's3://its-live-data/autorift_parameters/v001/mission_frames_all.parquet'
    fs = fsspec.filesystem('s3', anon=True)
    s1_gdf = gpd.read_parquet(s3_url, filesystem=fs)
    s1_gdf = s1_gdf[(s1_gdf['mission'] == 'S1')]

    return s1_gdf


def get_burst_ids(aoi_id: str | None = None, aoi_file: str | None = None) -> dict:
    """Get the burst ids that intersect the area of interest.

    Args:
        aoi_id: Id for the area of interest. If None all the area of interest are taken.
        aoi_file: Path to the parquet file. If None it takes the parquet file in cache.

    Returns:
        result: Dictionary where the keys are the burst ids and the area of interests overlapping.
    """
    s1_gdf = load_s1_parquet()

    if aoi_file is None:
        aoi_file = f'{PARQUET_FILE}'
    aoi_gdf = gpd.read_parquet(aoi_file)
    if aoi_id is not None:
        aoi_gdf = aoi_gdf[aoi_gdf['name'] == aoi_id]
    bursts_gdf = gpd.sjoin(s1_gdf, aoi_gdf, how='inner', predicate='intersects')
    intersection = gpd.overlay(s1_gdf, aoi_gdf, how='intersection')
    aoi_utm = gpd.sjoin(aoi_gdf, s1_gdf, how='inner', predicate='intersects')

    utmgdf = aoi_gdf.estimate_utm_crs()
    crs = utmgdf._crs.to_epsg()
    bursts_utm = bursts_gdf.to_crs(epsg=crs)
    aoi_utm = aoi_utm.to_crs(epsg=crs)
    intersection_utm = intersection.to_crs(epsg=crs)

    bursts_gdf['area_aoi'] = intersection_utm.area.to_numpy() / aoi_utm.area.to_numpy()
    bursts_gdf['area_burst'] = intersection_utm.area.to_numpy() / bursts_utm.area.to_numpy()

    bursts_gdf = bursts_gdf[(bursts_gdf['area_aoi'] > 0.3) | (bursts_gdf['area_burst'] > 0.05)]
    result = dict()
    for bid in bursts_gdf['id'].unique():
        asf_res = asf.search(fullBurstID=bid)
        if len(asf_res) > 1 or (len(asf_res) == 1 and asf_res[0].properties['stopTime'] is not None):
            burst_gdf_unique = bursts_gdf[bursts_gdf['id'] == bid]['name'].unique()
            if aoi_id is None:
                result[bid] = burst_gdf_unique
            else:
                if aoi_id in burst_gdf_unique:
                    result[bid] = burst_gdf_unique
    return result
