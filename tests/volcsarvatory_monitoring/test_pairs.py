import pairs


def test_prepare_multiburst_jobs() -> None:
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
    jobs = pairs.prepare_multiburst_jobs(refs, secs, 'test job')

    assert len(jobs) == 2
    assert len(jobs[0]['job_parameters']['reference']) == 2
    assert len(jobs[1]['job_parameters']['secondary']) == 2
