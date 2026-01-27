#!/bin/bash --login
set -e
conda activate hyp3-volcsarvatory-monitoring
exec python -um hyp3_volcsarvatory_monitoring "$@"
