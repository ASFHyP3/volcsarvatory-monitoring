#!/bin/bash --login
set -e
conda activate volcsarvatory-monitoring
exec python -um volcsarvatory_monitoring "$@"
