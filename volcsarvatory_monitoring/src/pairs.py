"""Module to prepare InSAR pairs for HyP3."""

import json
import os
import random
from pathlib import Path

import asf_search as asf
import hyp3_sdk as sdk


PROCESSING_JSON = Path(__file__).parent / 'data' / 'processing.json'


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
    hyp3: sdk.HyP3,
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

    for i in range(lenburst):
        ref = [refs[i + j * lenburst] for j in range(len(ubursts))]
        sec = [secs[i + j * lenburst] for j in range(len(ubursts))]
        insar_jobs.append(hyp3.prepare_insar_isce_multi_burst_job(ref, sec, name=project_name, apply_water_mask=True))

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
    if PROCESSING_JSON.exists():
        processing = json.loads(PROCESSING_JSON.read_text())
    else:
        processing = []
    batches = int(len(insar_jobs) / 100) + 1
    jobs = []
    newjobs = []
    for batch in range(batches):
        ini = batch * 100
        if batch == batches - 1:
            fin = batch * 100 + len(insar_jobs) % 100
        else:
            fin = (batch + 1) * 100
        jobs_def = [job for job in insar_jobs[ini:fin] if job['name'] not in processing]
        names_def = [job['name'] for job in jobs_def]
        # hyp3.submit_prepared_jobs(jobs_def)
        newjobs += names_def
        jobs += jobs_def
    processing += newjobs

    with PROCESSING_JSON.open('w') as json_file:
        json.dump(sorted(list(set(processing))), json_file)

    return jobs
