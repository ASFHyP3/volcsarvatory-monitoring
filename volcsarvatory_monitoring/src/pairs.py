"""Module to prepare InSAR pairs for HyP3."""

import os
from copy import deepcopy


MULTIBURST_JOB_TEMPLATE = {
    'job_type': 'INSAR_ISCE_MULTI_BURST',
    'job_parameters': {
        'apply_water_mask': True,
    },
}


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
