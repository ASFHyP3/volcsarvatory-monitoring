"""Module to prepare InSAR pairs for HyP3."""

import os
import random
from copy import deepcopy

import asf_search as asf
import hyp3_sdk as sdk


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
        for i, ref in enumerate(prods[0:-1]):
            for sec in prods[i + 1 : :]:
                pair = asf.Pair(ref, sec)
                if pair.temporal_baseline.days in [6, 12, 18, 24, 36, 48]:
                    ref_date = ref.properties['stopTime'].split('T')[0]
                    if pair.temporal_baseline.days not in coherence.keys():
                        coherence[pair.temporal_baseline.days] = dict()
                    else:
                        if ref_date in coherence[pair.temporal_baseline.days].keys():
                            coherence[pair.temporal_baseline.days][ref_date] += pair.estimate_s1_mean_coherence() / num
                        else:
                            coherence[pair.temporal_baseline.days][ref_date] = pair.estimate_s1_mean_coherence() / num
    return coherence


def prepare_multiburst_jobs(
    refs: list[str],
    secs: list[str],
    project_name: str,
    looks: str | None = None,
    apply_water_mask: bool = True,
) -> list[dict]:
    """Prepares the multiburst jobs from the pairs returned by an SBAS network.

    Args:
        refs: Reference scene ids.
        secs: Secondary scene ids.
        hyp3: Instance of HyP3 where the user has been logged in.
        project_name: Name of the project in HyP3.
        looks: Multilooking in the final products.
        apply_water_mask: If true it applies a water mask in the HyP3 processing.

    Returns:
        insar_jobs: List with prepared jobs for HyP3
    """
    insar_jobs = []
    bursts = [ref[0:13] for ref in refs]
    ubursts = list(set(bursts))
    lenburst = int(len(refs) / len(ubursts))
    if looks is None:
        looks = '20x4'

    for i in range(lenburst):
        prepared_job: dict = deepcopy(MULTIBURST_JOB_TEMPLATE)
        ref = [refs[i + j * lenburst] for j in range(len(ubursts))]
        sec = [secs[i + j * lenburst] for j in range(len(ubursts))]
        prepared_job['name'] = project_name
        prepared_job['job_parameters']['reference'] = ref
        prepared_job['job_parameters']['secondary'] = sec
        prepared_job['job_parameters']['looks'] = looks
        prepared_job['job_parameters']['apply_water_mask'] = apply_water_mask
        insar_jobs.append(prepared_job)

    for job in insar_jobs:
        job['job_parameters']['publish_bucket'] = os.environ.get('PUBLISH_BUCKET')

    return insar_jobs


def submit_jobs(insar_jobs: list[dict], hyp3: sdk.HyP3) -> list[dict]:
    """Submits prepared multiburst jobs.

    Args:
        insar_jobs: Prepared multiburst jobs.
        hyp3: Instance of HyP3 where the user has been logged in.

    Returns:
        jobs: List of submitted batches.
    """
    batches = int(len(insar_jobs) / 100) + 1
    jobs = []
    for batch in range(batches):
        ini = batch * 100
        if batch == batches - 1:
            fin = batch * 100 + len(insar_jobs) % 100
        else:
            fin = (batch + 1) * 100
        jobs += hyp3.submit_prepared_jobs(insar_jobs[ini:fin])

    return jobs
