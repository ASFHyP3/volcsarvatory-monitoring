"""Module to prepare InSAR pairs for HyP3."""

import os
import random
from copy import deepcopy

import asf_search as asf


MULTIBURST_JOB_TEMPLATE = {
    'job_type': 'INSAR_ISCE_MULTI_BURST',
    'job_parameters': {
        'apply_water_mask': True,
    },
}


def get_coherence(multiburst_dict: dict, num: int = 1) -> dict:
    """Estimates the mean coherence for random burst(s) pairs in a multiburst set.

    Args:
        multiburst_dict: Dictionary where the keys are the burst ids and the elements the swaths.
        num: Number of burst(s) to estimate the mean coherence.

    Returns:
        coherence: Dictionary where the keys are the number of days between the pairs and the
                   elements are dictionaries where the keys are the reference dates.
    """
    coherence: dict[int, dict] = dict()
    burst_ids = []
    for bid in multiburst_dict.keys():
        for swath in multiburst_dict[bid]:
            burst_ids.append(bid + '_' + swath)

    bids = random.sample(burst_ids, num)

    for bid in bids:
        prods = asf.search(fullBurstID=bid, start='2019-12-01', end='2021-02-01', polarization=asf.POLARIZATION.VV)[
            ::-1
        ]
        if len(prods) == 0:
            results = asf.search(fullBurstID=bid, polarization=asf.POLARIZATION.VV)
            start_date = results[-1].properties['stopTime'].split('T')[0]
            end_year = str(int(start_date.split('-')[0]) + 1)
            end_month = start_date.split('-')[1]
            end_day = start_date.split('-')[2]
            end_date = f'{end_year}-{end_month}-{end_day}'
            prods = asf.search(fullBurstID=bid, start=start_date, end=end_date, polarization=asf.POLARIZATION.VV)[::-1]
        for i, ref in enumerate(prods[0:-1]):
            for sec in prods[i + 1 : :]:
                pair = asf.Pair(ref, sec)
                temporal_baseline = pair.temporal_baseline.days
                if temporal_baseline in [6, 12, 18, 24, 36, 48]:
                    ref_date = ref.properties['stopTime'].split('T')[0]
                    mean_coherence = pair.estimate_s1_mean_coherence() / num
                    if temporal_baseline not in coherence.keys():
                        coherence[temporal_baseline] = dict()
                    else:
                        if ref_date in coherence[temporal_baseline].keys():
                            coherence[temporal_baseline][ref_date] += mean_coherence
                        else:
                            coherence[temporal_baseline][ref_date] = mean_coherence
    return coherence


def prepare_multiburst_jobs(
    pairs: dict,
    project_name: str,
    looks: str | None = None,
    apply_water_mask: bool = True,
) -> list[dict]:
    """Prepares the multiburst jobs from the pairs returned by an SBAS network.

    Args:
        pairs: Dictionary with the reference and secondary acquisitions.
        hyp3: Instance of HyP3 where the user has been logged in.
        project_name: Name of the project in HyP3.
        looks: Multilooking in the final products.
        apply_water_mask: If true it applies a water mask in the HyP3 processing.

    Returns:
        insar_jobs: List with prepared jobs for HyP3
    """
    if looks is None:
        looks = '20x4'

    insar_jobs = []
    for pair in pairs.keys():
        prepared_job: dict = deepcopy(MULTIBURST_JOB_TEMPLATE)
        prepared_job['name'] = project_name
        prepared_job['job_parameters']['reference'] = pairs[pair]['refs']
        prepared_job['job_parameters']['secondary'] = pairs[pair]['secs']
        prepared_job['job_parameters']['looks'] = looks
        prepared_job['job_parameters']['apply_water_mask'] = apply_water_mask
        insar_jobs.append(prepared_job)

    for job in insar_jobs:
        job['job_parameters']['publish_bucket'] = os.environ.get('PUBLISH_BUCKET')
        job['job_parameters']['publish_prefix'] = f'multiburst_products/{project_name}'

    return insar_jobs
