FROM condaforge/mambaforge:latest

# For opencontainers label definitions, see:
#    https://github.com/opencontainers/image-spec/blob/master/annotations.md
LABEL org.opencontainers.image.title="HyP3 volcsarvatory-monitoring "
LABEL org.opencontainers.image.description="Monitoring stack for InSAR deformation time series"
LABEL org.opencontainers.image.vendor="Alaska Satellite Facility"
LABEL org.opencontainers.image.authors="username_for_github_actions <email_for@github_actions.com>"
LABEL org.opencontainers.image.licenses="BSD-3-Clause"
LABEL org.opencontainers.image.url="https://github.com/ASFHyP3/volcsarvatory-monitoring"
LABEL org.opencontainers.image.source="https://github.com/ASFHyP3/volcsarvatory-monitoring"
LABEL org.opencontainers.image.documentation="https://hyp3-docs.asf.alaska.edu"

# Dynamic lables to define at build time via `docker build --label`
# LABEL org.opencontainers.image.created=""
# LABEL org.opencontainers.image.version=""
# LABEL org.opencontainers.image.revision=""

ARG DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=true

RUN apt-get update && apt-get install -y --no-install-recommends unzip vim && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ARG CONDA_UID=1000
ARG CONDA_GID=1000

RUN groupadd -g "${CONDA_GID}" --system conda && \
    useradd -l -u "${CONDA_UID}" -g "${CONDA_GID}" --system -d /home/conda -m  -s /bin/bash conda && \
    chown -R conda:conda /opt && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> /home/conda/.profile && \
    echo "conda activate base" >> /home/conda/.profile


USER ${CONDA_UID}
SHELL ["/bin/bash", "-l", "-c"]
WORKDIR /home/conda/

COPY --chown=${CONDA_UID}:${CONDA_GID} . /volcsarvatory-monitoring/

RUN mamba env create -f /volcsarvatory-monitoring/environment.yml && \
    conda clean -afy && \
    conda activate volcsarvatory-monitoring && \
    sed -i 's/conda activate base/conda activate volcsarvatory-monitoring/g' /home/conda/.profile && \
    python -m pip install --no-cache-dir /volcsarvatory-monitoring

ENTRYPOINT ["/volcsarvatory-monitoring/src/volcsarvatory_monitoring/etc/entrypoint.sh"]
CMD ["-h"]
