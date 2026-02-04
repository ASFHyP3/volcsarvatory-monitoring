import prepare_multibursts as pm


def test_get_julian_season() -> None:
    season = ('1-1', '12-31')
    start_day, end_day = pm.get_julian_season(season)

    assert start_day == 1
    assert end_day == 365


def test_get_multibursts() -> None:
    burst_ids = ['110_234430_IW3', '037_077633_IW1', '037_077634_IW1']
    mbs = pm.get_multibursts(burst_ids)
    keys = [key for mb in mbs for key in mb.multiburst_dict.keys()]
    bids = [bid[0:10] for bid in burst_ids]
    all_dic = {k: e for mb in mbs for k, e in mb.multiburst_dict.items()}
    print(all_dic)

    assert all(burst_id in keys for burst_id in bids)
    assert 'IW3' in all_dic['110_234430']
    assert 'IW1' in all_dic['037_077633']
    assert 'IW1' in all_dic['037_077634']


def test_split_count() -> None:
    mb_dic = {f'000_{str(i).zfill(6)}': ('IW1', 'IW2', 'IW3') for i in range(11)}
    mbs = pm.split_count(mb_dic)

    assert len(mbs) == 2


def test_split_vertically() -> None:
    mb_dic = {
        '000_000001': ('IW1', 'IW2', 'IW3'),
        '000_000003': ('IW1', 'IW2', 'IW3'),
        '000_000005': ('IW1', 'IW2', 'IW3'),
        '000_000006': ('IW1', 'IW2'),
    }
    mbs = pm.split_vertical_multiburst(mb_dic)

    assert len(mbs) == 3


def test_fill_holes() -> None:
    mb_dic = {
        '000_000001': ('IW1', 'IW2', 'IW3'),
        '000_000002': ('IW1', 'IW3'),
        '000_000003': ('IW2',),
        '000_000004': ('IW2', 'IW3'),
    }
    mb_dic = pm.fill_holes(mb_dic)

    assert 'IW2' in mb_dic['000_000002']
    assert 'IW3' in mb_dic['000_000003']


def test_get_ranges() -> None:
    mb_dic = {
        '000_000001': ('IW1', 'IW3'),
        '000_000002': ('IW1', 'IW3'),
        '000_000003': ('IW2', 'IW3'),
        '000_000004': ('IW1', 'IW2', 'IW3'),
    }
    ranges, ids = pm.get_ranges(mb_dic)
    ids1 = ['000_000001', '000_000002', '000_000004']
    ids2 = ['000_000003', '000_000004']
    ids3 = ['000_000001', '000_000002', '000_000003', '000_000004']
    ranges1 = (1, 4)
    ranges2 = (3, 4)
    ranges3 = (1, 4)

    assert ids['IW1'] == ids1
    assert ids['IW2'] == ids2
    assert ids['IW3'] == ids3
    assert ranges['IW1'] == ranges1
    assert ranges['IW2'] == ranges2
    assert ranges['IW3'] == ranges3


def test_complete_sides():
    mb_dic = {
        '000_000001': ('IW2', 'IW3'),
        '000_000002': ('IW2', 'IW3'),
        '000_000003': ('IW2', 'IW3'),
        '000_000004': ('IW1', 'IW2'),
        '000_000005': ('IW1', 'IW2'),
    }
    mb_dics = pm.complete_sides(mb_dic)

    assert 'IW3' in mb_dics[0]['000_000004']
    assert 'IW1' in mb_dics[0]['000_000003']
    assert 'IW1' in mb_dics[0]['000_000002']


def test_split_horizontal():
    mb_dic = {
        '000_000001': ('IW2', 'IW3'),
        '000_000002': ('IW1', 'IW2', 'IW3'),
        '000_000003': ('IW1', 'IW2', 'IW3'),
        '000_000004': ('IW1', 'IW2', 'IW3'),
        '000_000005': ('IW2', 'IW3'),
    }
    mbs = pm.split_horizontal_multiburst(mb_dic)

    assert len(mbs) == 1

    mb_dic = {
        '000_000001': ('IW2', 'IW3'),
        '000_000002': ('IW2', 'IW3'),
        '000_000003': ('IW2', 'IW3'),
        '000_000004': ('IW1', 'IW2', 'IW3'),
        '000_000005': ('IW1', 'IW2', 'IW3'),
    }
    mbs = pm.split_horizontal_multiburst(mb_dic)

    assert len(mbs) == 2

    mb_dic = {
        '000_000001': ('IW1', 'IW2'),
        '000_000002': ('IW1', 'IW2'),
        '000_000003': ('IW1', 'IW2', 'IW3'),
        '000_000004': ('IW1', 'IW2', 'IW3'),
        '000_000005': ('IW1', 'IW2', 'IW3'),
    }
    mbs = pm.split_horizontal_multiburst(mb_dic)

    assert len(mbs) == 2

    mb_dic = {
        '000_000001': ('IW2', 'IW3'),
        '000_000002': ('IW2', 'IW3'),
        '000_000003': ('IW2', 'IW3'),
        '000_000004': ('IW1', 'IW2'),
        '000_000005': ('IW1', 'IW2'),
    }
    mbs = pm.split_horizontal_multiburst(mb_dic)

    assert len(mbs) == 3


def test_split_multiburst():
    mb_dic = {
        '000_000001': ('IW2',),
        '000_000002': ('IW2',),
        '000_000003': ('IW1', 'IW3'),
        '000_000004': ('IW1',),
        '000_000005': ('IW2', 'IW3'),
    }
    mbs = pm.split_multiburst(mb_dic)

    assert len(mbs) == 1
    assert mbs[0]['000_000002'] == ('IW1', 'IW2', 'IW3')
    assert mbs[0]['000_000003'] == ('IW1', 'IW2', 'IW3')
    assert mbs[0]['000_000005'] == ('IW2', 'IW3')
