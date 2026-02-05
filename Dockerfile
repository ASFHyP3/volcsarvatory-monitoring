FROM public.ecr.aws/lambda/python:3.12

COPY requirements-volcsarvatory_monitoring.txt ${LAMBDA_TASK_ROOT}

RUN dnf -y install git

RUN pip install -r requirements-volcsarvatory_monitoring.txt

COPY volcsarvatory_monitoring/src ${LAMBDA_TASK_ROOT}

COPY aoi.yaml ${LAMBDA_TASK_ROOT}/data/aoi.yaml

RUN python ${LAMBDA_TASK_ROOT}/main.py

# NOTE: handler set as CMD by  parameter override outside of the Dockerfile
# CMD [ "lambda_function.handler" ]
