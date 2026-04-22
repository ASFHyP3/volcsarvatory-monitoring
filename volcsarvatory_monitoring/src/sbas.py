"""Module to find SBAS for a multiburst set."""

from datetime import datetime, timedelta

import asf_search as asf

import pairs
import prepare_multibursts as pm


def first_date_burst(burst_id: str) -> str:
    """Finds the first date for a given burst ID.

    Args:
        burst_id: ID for the burst.

    Returns:
        date: String with the date of the first acquisition.
    """
    results = asf.search(fullBurstID=burst_id)
    dates = sorted([r.properties['stopTime'] for r in results if r.properties['stopTime'] is not None])
    return dates[0].split('T')[0]


def first_date_multiburst(dic: dict) -> str:
    """Finds the first date for a multiburst set.

    Args:
        dic: Dictionary with the mutliburst set.

    Returns:
        date: String with the date of the first acquisition.
    """
    keys = [key for key in dic.keys()]
    burst_id = keys[0] + '_' + dic[keys[0]][0]

    return first_date_burst(burst_id)


def get_season(dic: dict) -> tuple[tuple[datetime, datetime], datetime]:
    """Calculates the optimal season for asf_search using the expected coherence.

    Args:
        dic: Dictionary with the mutliburst set.

    Returns:
        season: Tuple with the season in month-day format.
        bridge: Month-day to bridge multiyear pairs.
    """
    coherence = pairs.get_coherence(dic, num=1)
    keys = [key for key in coherence.keys()]
    start = datetime.now()
    end = datetime.strptime('2014-01-01', '%Y-%m-%d')
    bridges = []
    for days in keys:
        # days = 12
        cohs = [coherence[days][ref] for ref in coherence[days].keys()]
        mincoh = min(cohs)
        maxcoh = max(cohs)
        dates = [
            datetime.strptime(ref, '%Y-%m-%d') for ref in coherence[days].keys() if not coherence[days][ref] == mincoh
        ]
        maxdates = sorted(
            [datetime.strptime(ref, '%Y-%m-%d') for ref in coherence[days].keys() if coherence[days][ref] == maxcoh]
        )
        meandate = maxdates[0] + timedelta(days=int((maxdates[-1] - maxdates[0]).days / 2))
        diffdays = [abs((date - meandate).days) for date in maxdates]
        bridges.append(maxdates[diffdays.index(min(diffdays))])
        if start > min(dates):
            start = min(dates)
        if end < max(dates):
            end = max(dates)

    target = sorted(bridges)[int(len(bridges) / 2) - 1]
    season = (start, end)

    return season, target


def build_sbas_pairs_default(
    dic: dict,
    start: str,
    season: tuple[str, str],
    tbaseline: int,
    target: str,
    bridge: int,
) -> tuple[list, list]:
    """Calculates a default sbas pairs for a multiburst set. The result is the merge of a seasonal sbas and all possible pairs for the current year.

    Args:
        dic: Dictionary with the multiburst set.
        start: Start date for the SBAS.
        season: Tuple of strings in the format month-day to define the season.
        tbaseline: In-season maximum temporal baseline.
        target: String in the format month-day to define the target date to bridge the years.
        bridge: Number of years to bridge.

    Returns:
        refs: Scene names for the reference acqusitions.
        secs: Scene names for the secondary acqusitions.
    """
    multiburst = asf.MultiBurst(dic)
    opts = asf.ASFSearchOptions(
        **{'start': start, 'end': datetime.now().strftime('%Y-%m-%d'), 'season': pm.get_julian_season(season)}
    )

    network = asf.Network(
        multiburst=multiburst,
        perp_baseline=800,
        inseason_temporal_baseline=tbaseline,
        bridge_target_date=target,
        bridge_year_threshold=bridge,
        opts=opts,
    )

    network.connect_components()

    refs, secs = network.get_multi_burst_pair_ids()

    season = ('1-1', '12-31')
    opts = asf.ASFSearchOptions(
        **{
            'start': (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'),
            'end': datetime.now().strftime('%Y-%m-%d'),
            'season': pm.get_julian_season(season),
        }
    )

    network = asf.Network(
        multiburst=multiburst,
        perp_baseline=800,
        inseason_temporal_baseline=144,
        bridge_target_date=datetime.now().strftime('%m-%d'),
        bridge_year_threshold=1,
        opts=opts,
    )

    try:
        network.connect_components()
    except Exception:
        pass

    refs_add, secs_add = network.get_multi_burst_pair_ids()

    pairs = list_pair_dates(refs, secs)
    pairs_add = list_pair_dates(refs_add, secs_add)

    for i, pair in enumerate(pairs_add):
        if pair not in pairs:
            refs.append(refs_add[i])
            secs.append(secs_add[i])
    return refs, secs


def build_custom_sbas_pairs_default(
    dic: dict,
    start: str,
    season: dict,
    tbaseline: int,
    target: str,
    bridge: int,
) -> tuple[list, list]:
    """Calculates an sbas for a multiburst set. It uses the seasons specified by the user.

    Args:
        dic: Dictionary with the multiburst set.
        start: Start date for the SBAS.
        season: Dictionary with tuples of strings in the format month-day to define the season per year.
        tbaseline: In-season maximum temporal baseline.
        target: String in the format month-day to define the target date to bridge the years.
        bridge: Number of years to bridge.

    Returns:
        refs: Scene names for the reference acqusitions.
        secs: Scene names for the secondary acqusitions.
    """
    years = [int(year) for year in season.keys()]

    month_start = season[str(min(years))][0].split('-')[0]
    day_start = season[str(min(years))][0].split('-')[1]

    month_end = season[str(max(years))][1].split('-')[0]
    day_end = season[str(max(years))][1].split('-')[1]

    start_tmp = f'{str(min(years))}-{month_start.zfill(2)}-{day_start.zfill(2)}'
    end_tmp = f'{str(max(years))}-{month_end.zfill(2)}-{day_end.zfill(2)}'

    seasons = [float(season[year][0].replace('-', '.')) for year in season.keys()]
    seasons += [float(season[year][1].replace('-', '.')) for year in season.keys()]
    season_base = (str(min(seasons)).replace('.', '-'), str(max(seasons)).replace('.', '-'))

    multiburst = asf.MultiBurst(dic)

    if start_tmp < start:
        start_tmp = start
    opts = asf.ASFSearchOptions(**{'start': start_tmp, 'end': end_tmp, 'season': pm.get_julian_season(season_base)})

    # Baseline Network without any pairs
    network = asf.Network(
        multiburst=multiburst,
        perp_baseline=800,
        inseason_temporal_baseline=0,
        bridge_target_date=target,
        opts=opts,
    )

    # Loop over seasons, create a network per season and add pairs to baseline network
    for season_yr in season.keys():
        season_tmp = season[season_yr]

        month_start = season_tmp[0].split('-')[0]
        day_start = season_tmp[0].split('-')[1]

        month_end = season_tmp[1].split('-')[0]
        day_end = season_tmp[1].split('-')[1]

        start_yr = f'{season_yr}-{month_start.zfill(2)}-{day_start.zfill(2)}'
        end_yr = f'{season_yr}-{month_end.zfill(2)}-{day_end.zfill(2)}'

        if start_yr < start:
            start_yr = start
        opts = asf.ASFSearchOptions(
            **{'start': start_yr, 'end': end_yr, 'season': pm.get_julian_season(tuple(season[season_yr]))}
        )
        network_yr = asf.Network(
            multiburst=multiburst,
            perp_baseline=800,
            inseason_temporal_baseline=tbaseline,
            bridge_target_date=target,
            opts=opts,
        )
        pairs = [key for key in network_yr.subset_stack.keys()]
        network.add_pairs(pairs)
        for d in network.additional_multiburst_networks:
            d.add_pairs(pairs)

    # Connects network seasons
    network.connect_components(multiyear_temporal_baseline=tbaseline)
    refs, secs = network.get_multi_burst_pair_ids()

    return refs, secs


def get_sbas_pairs(
    dic: dict,
    tbaseline: int | None = None,
    season: dict | tuple[str, str] | None = None,
    target: str | None = None,
    bridge: int | None = None,
) -> tuple[list, list]:
    """Calculates the sbas pairs for a multiburst set.

    Args:
        dic: Dictionary with the multiburst set.
        tbaseline: Temporal in season baseline in days.
        season: Tuple of strings in the format month-day to define the season.
        target: String in the format month-day to define the target date to bridge the years.
        bridge: Number of years to bridge.

    Returns:
        refs: Scene names for the reference acqusitions.
        secs: Scene names for the secondary acqusitions.
    """
    if isinstance(season, tuple):
        if float(season[0].replace('-', '.')) > float(season[1].replace('-', '.')):
            raise ValueError(f'The second date is before the first date in {season}')
    elif isinstance(season, dict):
        for year in season.keys():
            if float(season[year][0].replace('-', '.')) > float(season[year][1].replace('-', '.')):
                raise ValueError(f'The second date is before the first date in {season[year]}')

    start = first_date_multiburst(dic)  # First available acquisition

    if tbaseline is None:
        tbaseline = 48

    if season is None or target is None:
        seasont, targett = get_season(dic)  # Ideal season and target using coherence catalog
        if season is None:
            start_sea = seasont[0].strftime('%m-%d')
            end_sea = seasont[1].strftime('%m-%d')
            season = (start_sea, end_sea)
        if target is None:
            target = targett.strftime('%m-%d')
            if float(target.replace('-', '.')) < float(season[0].replace('-', '.')) or float(
                target.replace('-', '.')
            ) > float(season[1].replace('-', '.')):
                month_avg = str(int((int(season[0].split('-')[0]) + int(season[1].split('-')[0])) / 2))
                day_avg = str(int((int(season[0].split('-')[1]) + int(season[1].split('-')[1])) / 2))
                target = f'{month_avg}-{day_avg}'

    if bridge is None:
        bridge = 1

    if isinstance(season, tuple):
        refs, secs = build_sbas_pairs_default(dic, start, season, tbaseline, target, bridge)
    elif isinstance(season, dict):
        refs, secs = build_custom_sbas_pairs_default(dic, start, season, tbaseline, target, bridge)

    return refs, secs


def list_pair_dates(refs: list[str], secs: list[str]) -> list:
    """Lists dates for lists of reference and secondary scenes.

    Args:
        refs: Scene names for the reference acqusitions.
        secs: Scene names for the secondary acqusitions.

    Returns:
        pairs: List of strings in the format refdate_secdate.
    """
    pairs = []
    for i in range(len(refs)):
        ref_date = refs[i].split('_')[3].split('T')[0]
        sec_date = secs[i].split('_')[3].split('T')[0]
        pairs.append(f'{ref_date}_{sec_date}')
    return pairs
