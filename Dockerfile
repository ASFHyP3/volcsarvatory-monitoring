FROM public.ecr.aws/lambda/python:3.12

COPY requirements-volcsarvatory_monitoring.txt ${LAMBDA_TASK_ROOT}

RUN pip install -r  requirements-volcsarvatory_monitoring.txt

COPY aoi.yaml volcsarvatory_monitoring/src/data/aoi.yaml

RUN python volcsarvatory_monitoring/src/main.py

COPY volcsarvatory_monitoring/src ${LAMBDA_TASK_ROOT}

# NOTE: handler set as CMD by  parameter override outside of the Dockerfile
# CMD [ "lambda_function.handler" ]
