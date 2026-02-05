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


def get_sbas_pairs(
    dic: dict,
    tbaseline: int | None = None,
    season: tuple[str, str] | None = None,
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
    start = first_date_multiburst(dic)
    if tbaseline is None:
        tbaseline = 48
    if season is None or target is None:
        seasont, targett = get_season(dic)
        if season is None:
            start_sea = seasont[0].strftime('%m-%d')
            end_sea = seasont[1].strftime('%m-%d')
            season = (start_sea, end_sea)
        if target is None:
            target = targett.strftime('%m-%d')
            if target < season[0] or target > season[1]:
                target = None

    if bridge is None:
        bridge = 1

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
