"""Module that handles jobs in HyP3."""

import os

import hyp3_sdk as sdk


def get_hyp3_instance() -> sdk.HyP3:
    """Get an instance for the HyP3 sdk.

    Returns:
        hyp3: HyP3 sdk instance.
    """
    hyp3 = sdk.HyP3(
        os.environ.get('HYP3_API'),
        username=os.environ.get('EARTHDATA_USERNAME'),
        password=os.environ.get('EARTHDATA_PASSWORD'),
    )
    return hyp3


def submit_jobs(jobs: list[dict]) -> list[dict]:
    """Submit jobs for multiburst sets.

    Args:
        jobs: List of jobs to be submitted

    Returns:
        jobs: Filtered and submitted jobs.
    """
    job_params = list_pending_running_jobs_parameters(jobs[0]['job_type'])
    jobs = [job for job in jobs if job['job_parameters'] not in job_params]
    jobs = submit_split_jobs(jobs)

    return jobs


def list_pending_running_jobs_parameters(job_type: str) -> list[dict]:
    """List jobs that are pending or running.

    Args:
        job_type: Name of the job type to submit.

    Returns:
        jobs_params: List with the parameters of the jobs submitted.
    """
    hyp3 = get_hyp3_instance()
    jobs = hyp3.find_jobs(job_type=job_type, status_code='PENDING')
    jobs += hyp3.find_jobs(job_type=job_type, status_code='RUNNING')
    jobs_params = [job.to_dict()['job_parameters'] for job in jobs]

    return jobs_params


def wait_jobs(jobs: list[dict]) -> None:
    """Wait for jobs to be finished.

    Args:
        jobs: List of submitted jobs.
    """
    hyp3 = get_hyp3_instance()
    for job in jobs:
        hyp3.watch(job)


def submit_split_jobs(jobs: list[dict]) -> list[dict]:
    """Submits prepared multiburst jobs.

    Args:
        jobs: Prepared multiburst jobs.

    Returns:
        jobs: List of submitted batches.
    """
    hyp3 = get_hyp3_instance()
    batches = int(len(jobs) / 100) + 1
    sub_jobs = []
    for batch in range(batches):
        ini = batch * 100
        if batch == batches - 1:
            fin = batch * 100 + len(jobs) % 100
        else:
            fin = (batch + 1) * 100
        sub_jobs += hyp3.submit_prepared_jobs(jobs[ini:fin])

    return sub_jobs
