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
