from datetime import timedelta
from unittest.mock import MagicMock, patch

import pairs


@patch('pairs.asf.Pair')
@patch('pairs.asf.search')
def test_get_coherence(mock_asf_search, mock_pair, asf_product_factory, asf_stack_factory) -> None:
    scene_name = 'S1_247728_IW1_20251003T154900_VV_657C-BURST'
    full_burst_id = '116_247728_IW1'

    max_pair_seperation_in_days = 48
    expected_stacks = asf_stack_factory(
        scene_name, full_burst_id, days_separation=range(0, max_pair_seperation_in_days + 1, 6)
    )
    mock_asf_search.side_effect = [*expected_stacks]
    pair_instance = MagicMock()
    pair_instance.temporal_baseline = timedelta(days=6)
    pair_instance.estimate_s1_mean_coherence.return_value = 0

    mock_pair.return_value = pair_instance

    mb_dic = {'116_247728': ('IW1', 'IW2', 'IW3')}
    coh = pairs.get_coherence(mb_dic)

    assert 6 in coh.keys()


def test_prepare_multiburst_jobs() -> None:
    dpairs: dict[str, dict] = dict()
    dpairs['00000000_00000001'] = dict()
    dpairs['00000000_00000001']['refs'] = [
        'S1_000001_IW1_00000000T000000_VV_0001-BURST',
        'S1_000002_IW1_00000000T000000_VV_0001-BURST',
    ]
    dpairs['00000000_00000001']['secs'] = [
        'S1_000001_IW1_00000001T000000_VV_0001-BURST',
        'S1_000002_IW1_00000001T000000_VV_0001-BURST',
    ]
    dpairs['00000001_00000003'] = dict()
    dpairs['00000001_00000003']['refs'] = [
        'S1_000001_IW1_00000001T000000_VV_0001-BURST',
        'S1_000002_IW1_00000001T000000_VV_0001-BURST',
    ]
    dpairs['00000001_00000003']['secs'] = [
        'S1_000001_IW1_00000003T000000_VV_0001-BURST',
        'S1_000002_IW1_00000003T000000_VV_0001-BURST',
    ]
    jobs = pairs.prepare_multiburst_jobs(dpairs, 'test job')

    assert len(jobs) == 2
    assert len(jobs[0]['job_parameters']['reference']) == 2
    assert len(jobs[1]['job_parameters']['secondary']) == 2
