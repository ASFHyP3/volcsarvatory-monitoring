"""Module to find SBAS for a multiburst set."""

import time
from datetime import datetime, timedelta

import asf_search as asf
import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

import prepare_multibursts as pm


def first_date_burst(burst_id: str, start: str | None = None) -> str:
    """Finds the first date for a given burst ID.

    Args:
        burst_id: ID for the burst.
        start: Start date of the Stack.

    Returns:
        date: String with the date of the first acquisition.
    """
    if start is not None:
        results = asf.search(fullBurstID=burst_id, start=start, polarization=asf.POLARIZATION.VV)
    else:
        results = asf.search(fullBurstID=burst_id, polarization=asf.POLARIZATION.VV)
    dates = sorted([r.properties['stopTime'] for r in results if r.properties['stopTime'] is not None])
    return dates[0].split('T')[0]


def first_date_multiburst(dic: dict, start: str | None = None) -> str:
    """Finds the first date for a multiburst set.

    Args:
        dic: Dictionary with the mutliburst set.
        start: Start date of the Stack.

    Returns:
        date: String with the date of the first acquisition.
    """
    keys = [key for key in dic.keys()]
    burst_id = keys[0] + '_' + dic[keys[0]][0]

    if start is not None:
        return first_date_burst(burst_id, start)
    else:
        return first_date_burst(burst_id)


def check_available_acquisitions(
    dic: dict,
    start: str,
    end: str,
) -> bool:
    """Check if there are acquisitions for a particular multiburst set.

    Args:
        dic: Dictionary with the multiburst set.
        start: Start date for the SBAS.
        end: End date for the SBAS.

    Returns:
        check: True if there are acquisitions for all the bursts, False otherwise
    """
    for frame in dic.keys():
        for swath in dic[frame]:
            bid = f'{frame}_{swath}'
            res = asf.search(fullBurstID=bid, start=start, end=end, polarization=asf.POLARIZATION.VV)
            if len(res) == 0:
                return False  # No images in the last year
    return True


def get_multi_stack(
    dic: dict,
    start: str,
    end: str,
    season: tuple[str, str],
) -> pd.DataFrame:
    """Finds the stack of burst associated with a multiburst set.

    Args:
        dic: Dictionary with the multiburst set
        start: Start date of the stack.
        end: End date of the stack.
        season: Season pair of dates in month-day format

    Returns:
        all_burst_stacks: Stack from union of multiple burst stacks
    """
    burst_stacks = []
    first_date = first_date_multiburst(dic)
    end_date = (datetime.strptime(first_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    tot_bursts = sum([len(dic[key]) for key in dic.keys()])
    for key in dic.keys():
        burst_ids = [f'{key}_{swath}' for swath in dic[key]]
        for bid in burst_ids:
            ref = asf.search(
                fullBurstID=bid,
                start=first_date,
                end=end_date,
                polarization=asf.POLARIZATION.VV,
            )
            stack = asf.search(
                fullBurstID=bid,
                start=start,
                end=end,
                season=pm.get_julian_season(season),
                polarization=asf.POLARIZATION.VV,
            )
            stack += ref
            print(ref[-1].properties['sceneName'])
            stack = asf.baseline.calculate_perpendicular_baselines(ref[-1].properties['sceneName'], stack)
            stack = gpd.GeoDataFrame.from_features(stack.geojson())
            stack = stack[stack['sceneName'] != ref[-1].properties['sceneName']]
            burst_stacks.append(stack)
    all_burst_stacks: pd.DataFrame = pd.concat(burst_stacks)
    groups = list(set(all_burst_stacks['orbit']))
    for group in groups:
        bursts_group = len(all_burst_stacks[all_burst_stacks['orbit'] == group])
        if bursts_group < tot_bursts:
            all_burst_stacks = all_burst_stacks[all_burst_stacks['orbit'] != group]
    all_burst_stacks.sort_values(by='stopTime')
    bids = [elem['fullBurstID'] for elem in all_burst_stacks['burst']]
    all_burst_stacks['fullBurstID'] = bids
    return all_burst_stacks


def get_target_dates(comp: list[datetime], bridge_target: str, tbaseline: int) -> list[list]:
    """Finds the dates around a bridge_target for given stack.

    Args:
        comp: Set of dates for the stack.
        bridge_target: target month and day to find the dates.
        tbaseline: In-season maximum temporal baseline.

    Returns:
        dates_target: Dates to connect different components.
    """
    years = list(set([date.strftime('%Y') for date in comp]))
    dates_target = []
    for year in years:
        target = datetime.strptime(f'{year}-{bridge_target}', '%Y-%m-%d')
        s = [date for date in comp if abs((date - target).days) <= tbaseline]
        if len(s) > 0:
            dates_target.append(s)
    return dates_target


def closest_sets(sub1: list[list], sub2: list[list]) -> tuple[int, int]:
    """Finds the pair of sets that are closest to each other.

    Args:
        sub1: Sets of dates around the bridge_date for the first stack
        sub2: Sets of dates around the bridge_date for the second stack
    Returns:
        index1: Index of the first subset
        index2: Index of the second dataset
    """
    medians1 = [s[len(s) // 2] for s in sub1]
    medians2 = [s[len(s) // 2] for s in sub2]
    minimum = 10000
    for i, median1 in enumerate(medians1):
        for j, median2 in enumerate(medians2):
            if abs((median1 - median2).days) < minimum:
                minimum = abs((median1 - median2).days)
                index1 = i
                index2 = j
    return index1, index2


def connect_components(network: nx.Graph, bridge_date: str | None, tbaseline: int) -> list[tuple]:
    """Connect different components in SBAS network.

    Args:
        network: Graph with the InSAR pairs.
        bridge_date: Ideal month-day to connect the components
        tbaseline: In-season maximum temporal baseline.

    Returns:
        pairs: List with the dates of the InSAR pairs.
    """
    components = [network.subgraph(c).copy() for c in nx.connected_components(network)]
    dates_components = []
    for component in components:
        dates = sorted(list(set([key for key in component.nodes])))
        dates_components.append(dates)
    # Get the median date on each network
    mids = [dates_component[len(dates_component) // 2] for dates_component in dates_components]

    # Finds the network pairs to be connected (not insar pairs!)
    cons = []
    for i, mid in enumerate(mids[0:-1]):
        difs = [abs((mid - midt).days) for j, midt in enumerate(mids[i + 1 : :])]
        cons.append((i, int(np.argmin(difs) + i + 1)))

    # Loop over the network pairs and find the insar pairs
    pairs = []
    for con in cons:
        sub1 = dates_components[con[0]]
        sub2 = dates_components[con[1]]

        # Ideally the connection is made with the bridge_target
        if bridge_date is None:
            target1 = sub1[len(sub1) // 2]
            target2 = sub2[len(sub2) // 2]
        else:
            target1 = bridge_date
            target2 = bridge_date
        target_dates1 = get_target_dates(sub1, bridge_target=target1, tbaseline=tbaseline)

        # In case the first stack does not have dates around it, change the bridge_date
        if len(target_dates1) == 0:
            bridge_target = mids[con[0]].strftime('%m-%d')
            target_dates1 = get_target_dates(sub1, bridge_target=bridge_target, tbaseline=tbaseline)
            target_dates2 = get_target_dates(sub2, bridge_target=bridge_target, tbaseline=tbaseline)
        else:
            target_dates2 = get_target_dates(sub2, bridge_target=target2, tbaseline=tbaseline)

        # In case the second stack does not have dates around it, change the bridge_date
        if len(target_dates2) == 0:
            bridge_target = mids[con[1]].strftime('%m-%d')
            target_dates2 = get_target_dates(sub2, bridge_target=bridge_target, tbaseline=tbaseline)
            temp = get_target_dates(sub1, bridge_target=bridge_target, tbaseline=tbaseline)

            # In case the first stack has dates around it, change the bridge_date
            if len(temp) > 0:
                target_dates1 = temp

        index1, index2 = closest_sets(target_dates1, target_dates2)
        target_dates1 = target_dates1[index1]
        target_dates2 = target_dates2[index2]
        for i, date1 in enumerate(target_dates1):
            for date2 in target_dates2[i::]:
                if date1 < date2:
                    pairs.append((date1, date2))
                else:
                    pairs.append((date2, date1))
    return pairs


def get_network(pairs: dict) -> nx.Graph:
    """Creates a network from pairs dictionary.

    Args:
        pairs: Dictionary with the multiburst pairs.

    Returns:
        G: Graph that represents the SBAS.
    """
    G: nx.Graph = nx.Graph()
    for key in pairs.keys():
        ref_date = key.split('_')[0]
        sec_date = key.split('_')[1]
        tref = datetime.strptime(ref_date, '%Y%m%d')
        tsec = datetime.strptime(sec_date, '%Y%m%d')
        G.add_edge(tref, tsec)

    return G


def plot_network(pairs: dict) -> None:
    """Plot a SBAS network.

    Args:
        pairs: Dictionary with the multiburst pairs.

    Returns:
        pairs: Dictionary with the additional multiburst pairs.
    """
    tacqs, pacqs = [], []
    plt.figure(figsize=(5, 2))
    for key in pairs.keys():
        ref_date = key.split('_')[0]
        sec_date = key.split('_')[1]
        tref = datetime.strptime(ref_date, '%Y%m%d')
        tsec = datetime.strptime(sec_date, '%Y%m%d')
        pref = pairs[key]['pbaselines'][0]
        psec = pairs[key]['pbaselines'][1]
        plt.plot([tref, tsec], [pref, psec], c='C0', lw=0.1, zorder=2)  # type: ignore
        if tref not in tacqs:
            tacqs.append(tref)
            pacqs.append(pref)
        if tsec not in tacqs:
            tacqs.append(tsec)
            pacqs.append(psec)

    plt.scatter(tacqs, pacqs, c='C1', s=1, zorder=2)  # type: ignore
    plt.xlabel('Date')
    plt.ylabel('Perp. baseline')
    plt.savefig('network.pdf', bbox_inches='tight')


def connect_network(pairs: dict, target: str | None, tbaseline: int) -> dict[str, dict]:
    """Connects an unconnected SBAS network.

    Args:
        pairs: Dictionary with the multiburst pairs.
        target: String in the format month-day to define the target date to bridge the years.
        tbaseline: Temporal in season baseline in days.

    Returns:
        pairs: Dictionary with the additional multiburst pairs.
    """
    G = get_network(pairs)
    if nx.number_connected_components(G) > 1:
        pairs_add = connect_components(G, bridge_date=target, tbaseline=tbaseline)
        for apair in pairs_add:
            tref, tsec = apair
            stref = apair[0].strftime('%Y%m%d')
            stsec = apair[1].strftime('%Y%m%d')
            key = f'{stref}_{stsec}'
            for cur_key in pairs.keys():
                if stref in cur_key:
                    break
            pairs[key] = dict()
            pairs[key]['refs'] = pairs[cur_key]['refs'].copy()
            pairs[key]['pbaselines'] = [pairs[cur_key]['pbaselines'][0]]
            for cur_key in pairs.keys():
                if stsec in cur_key:
                    break
            pairs[key]['secs'] = pairs[cur_key]['secs'].copy()
            pairs[key]['pbaselines'].append(pairs[cur_key]['pbaselines'][1])
    return pairs


def build_sbas_pairs(
    dic: dict,
    start: str,
    end: str,
    season: tuple[str, str],
    tbaseline: int,
    target: str | None,
    bridge: int,
) -> dict[str, dict]:
    """Calculates a default sbas pairs for a multiburst set. The result is the merge of a seasonal sbas and all possible pairs for the current year.

    Args:
        dic: Dictionary with the multiburst set.
        start: Start date for the SBAS.
        end: End date for the SBAS.
        season: Tuple of strings in the format month-day to define the season.
        tbaseline: In-season maximum temporal baseline.
        target: String in the format month-day to define the target date to bridge the years.
        bridge: Number of years to bridge.

    Returns:
        pairs: Dictionary with the reference and secondary acquisitions.
    """
    ini = time.time()
    stack = get_multi_stack(dic, start, end, season)
    fin = time.time()
    print('Time to get multi stack', fin - ini)
    ugids = stack['orbit'].unique().tolist()
    pairs = dict()
    tacqs, pacqs = [], []
    ini = time.time()
    for i, sec_gid in enumerate(ugids[0:-1]):
        for ref_gid in ugids[i + 1 : :]:
            refs = stack[stack['orbit'] == ref_gid]
            secs = stack[stack['orbit'] == sec_gid]
            pairs_gid = pd.merge(refs, secs, on='fullBurstID', how='inner', suffixes=('_ref', '_sec'))
            pairs_gid['diff'] = (
                pd.to_datetime(pairs_gid['stopTime_sec']) - pd.to_datetime(pairs_gid['stopTime_ref'])
            ).dt.days

            mask = np.logical_or(pairs_gid['diff'] % 365 < tbaseline, (pairs_gid['diff'] + tbaseline) % 365 < tbaseline)
            mask = np.logical_and(mask, (pairs_gid['diff'] - tbaseline) / 365 < (bridge))

            valid = pairs_gid[mask]
            pair = dict()
            pair['refs'] = list(valid['sceneName_ref'])
            pair['secs'] = list(valid['sceneName_sec'])
            if len(pair['refs']) > 0:
                ref_date = list(pd.to_datetime(pairs_gid['stopTime_ref']).dt.strftime('%Y%m%d'))[0]
                sec_date = list(pd.to_datetime(pairs_gid['stopTime_sec']).dt.strftime('%Y%m%d'))[0]
                key = f'{ref_date}_{sec_date}'
                pref = float(np.mean(pairs_gid['perpendicularBaseline_ref']))
                psec = float(np.mean(pairs_gid['perpendicularBaseline_sec']))
                pair['pbaselines'] = [pref, psec]
                pairs[key] = pair
                tref = datetime.strptime(ref_date, '%Y%m%d')
                tsec = datetime.strptime(sec_date, '%Y%m%d')
                if tref not in tacqs:
                    tacqs.append(tref)
                    pacqs.append(pref)
                if tsec not in tacqs:
                    tacqs.append(tsec)
                    pacqs.append(psec)
    fin = time.time()
    print('Time to get pairs', fin - ini)

    pairs = connect_network(pairs, target, tbaseline=tbaseline)

    return pairs


def build_sbas_pairs_default(
    dic: dict,
    start: str,
    season: tuple[str, str],
    tbaseline: int,
    target: str | None,
    bridge: int,
) -> dict[str, dict]:
    """Calculates a default sbas pairs for a multiburst set. The result is the merge of a seasonal sbas and all possible pairs for the current year.

    Args:
        dic: Dictionary with the multiburst set.
        start: Start date for the SBAS.
        season: Tuple of strings in the format month-day to define the season.
        tbaseline: In-season maximum temporal baseline.
        target: String in the format month-day to define the target date to bridge the years.
        bridge: Number of years to bridge.

    Returns:
        pairs: Dictionary with the reference and secondary acquisitions.
    """
    end = datetime.now()
    start_date = datetime.strptime(start, '%Y-%m-%d')
    start_last = end - timedelta(days=365)
    years = int((end - start_date).days / 365) + 1
    startt = start_date
    pairs: dict[str, dict] = {}
    isend = False
    for year in range(years):
        endt = startt + timedelta(days=int(365 * bridge + tbaseline))
        if endt > end:
            endt = end
            isend = True
        print(f'Getting pairs between {startt.strftime("%Y-%m-%d")} and {endt.strftime("%Y-%m-%d")}')
        pairs_add = build_sbas_pairs(
            dic, startt.strftime('%Y-%m-%d'), endt.strftime('%Y-%m-%d'), season, tbaseline, target, bridge
        )
        startt = startt + timedelta(days=365)
        for i, pair in enumerate(pairs_add.keys()):
            if pair not in pairs.keys():
                pairs[pair] = pairs_add[pair]
        if isend:
            break

    if check_available_acquisitions(dic, start_last.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')):
        season = (start_last.strftime('%m-%d'), end.strftime('%m-%d'))
        tbaseline = 144
        target = end.strftime('%m-%d')
        bridge = 0
        pairs_add = build_sbas_pairs(
            dic,
            start_last.strftime('%Y-%m-%d'),
            end.strftime('%Y-%m-%d'),
            season=('1-1', '12-31'),
            tbaseline=tbaseline,
            target=target,
            bridge=bridge,
        )
        for i, pair in enumerate(pairs_add.keys()):
            if pair not in pairs.keys():
                pairs[pair] = pairs_add[pair]
    pairs = connect_network(pairs, target, tbaseline=tbaseline)

    return pairs


def build_sbas_pairs_custom(
    dic: dict,
    start: str,
    season: dict,
    tbaseline: int,
    target: str | None,
    bridge: int,
) -> dict[str, dict]:
    """Calculates an sbas for a multiburst set. It uses the seasons specified by the user.

    Args:
        dic: Dictionary with the multiburst set.
        start: Start date for the SBAS.
        season: Dictionary with tuples of strings in the format month-day to define the season per year.
        tbaseline: In-season maximum temporal baseline.
        target: String in the format month-day to define the target date to bridge the years.
        bridge: Number of years to bridge.

    Returns:
        dpairs: Dictionary with the reference and secondary acquisitions.
    """
    pairs: dict[str, dict] = dict()
    for season_yr in season.keys():
        season_tmp = season[season_yr]

        month_start = season_tmp[0].split('-')[0]
        day_start = season_tmp[0].split('-')[1]

        month_end = season_tmp[1].split('-')[0]
        day_end = season_tmp[1].split('-')[1]

        start_yr = f'{season_yr}-{month_start.zfill(2)}-{day_start.zfill(2)}'
        end_yr = f'{season_yr}-{month_end.zfill(2)}-{day_end.zfill(2)}'
        if check_available_acquisitions(dic, start_yr, end_yr):
            pairs = pairs | build_sbas_pairs(dic, start_yr, end_yr, season_tmp, tbaseline, target, bridge)

    pairs = connect_network(pairs, target=target, tbaseline=tbaseline)

    return pairs


def get_sbas_pairs(
    dic: dict,
    tbaseline: int | None = None,
    season: dict | tuple[str, str] | None = None,
    target: str | None = None,
    bridge: int | None = None,
) -> dict[str, dict]:
    """Calculates the sbas pairs for a multiburst set.

    Args:
        dic: Dictionary with the multiburst set.
        tbaseline: Temporal in season baseline in days.
        season: Tuple of strings in the format month-day to define the season.
        target: String in the format month-day to define the target date to bridge the years.
        bridge: Number of years to bridge.

    Returns:
        pairs: Dictionary with the reference and secondary acquisitions.
    """
    start = first_date_multiburst(dic)  # First available acquisition

    if bridge is None:
        bridge = 1
    if tbaseline is None:
        tbaseline = 48

    if isinstance(season, tuple):
        pairs = build_sbas_pairs_default(dic, start, season, tbaseline, target, bridge)
    elif isinstance(season, dict):
        pairs = build_sbas_pairs_custom(dic, start, season, tbaseline, target, bridge)
    plot_network(pairs)

    return pairs


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
