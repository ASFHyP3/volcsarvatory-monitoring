from unittest.mock import patch

import sbas


@patch('sbas.asf.search')
def test_first_date_burst(mock_asf_search, asf_product_factory, asf_stack_factory):
    scene_name = 'S1_234430_IW1_20251003T154900_VV_657C-BURST'
    full_burst_id = '110_234430_IW3'

    max_pair_seperation_in_days = 48
    expected_stacks = asf_stack_factory(
        scene_name, full_burst_id, days_separation=range(0, max_pair_seperation_in_days + 1, 6)
    )
    mock_asf_search.side_effect = [*expected_stacks]
    burst_id = '110_234430_IW3'

    date = sbas.first_date_burst(burst_id)

    assert date == '2025-08-16'


@patch('sbas.asf.search')
def test_first_date_multiburst(mock_asf_search, asf_product_factory, asf_stack_factory):
    scene_name = 'S1_234430_IW1_20251003T154900_VV_657C-BURST'
    full_burst_id = '110_234430_IW1'

    max_pair_seperation_in_days = 48
    expected_stacks = asf_stack_factory(
        scene_name, full_burst_id, days_separation=range(0, max_pair_seperation_in_days + 1, 6)
    )
    mock_asf_search.side_effect = [*expected_stacks]
    mb_dic = {'110_234430': ('IW1', 'IW2', 'IW3')}

    date = sbas.first_date_multiburst(mb_dic)

    assert date == '2025-08-16'


def test_list_pair_dates() -> None:
    refs = [
        'S1_000001_IW1_00000000T000000_VV_0001-BURST',
        'S1_000002_IW1_00000000T000000_VV_0001-BURST',
        'S1_000001_IW1_00000001T000000_VV_0001-BURST',
        'S1_000002_IW1_00000001T000000_VV_0001-BURST',
    ]
    secs = [
        'S1_000001_IW1_00000001T000000_VV_0001-BURST',
        'S1_000002_IW1_00000001T000000_VV_0001-BURST',
        'S1_000001_IW1_00000003T000000_VV_0001-BURST',
        'S1_000002_IW1_00000003T000000_VV_0001-BURST',
    ]

    pairs = sbas.list_pair_dates(refs, secs)

    assert pairs == ['00000000_00000001', '00000000_00000001', '00000001_00000003', '00000001_00000003']
