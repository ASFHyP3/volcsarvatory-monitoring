# VolcSARvatory Monitoring

The VolcSARvatory monitoring stack provides the AWS architecture to support low-latency production of InSAR pairs and timeseries from Sentinel-1 burst products.

## Architecture overview
VolcSARvatory monitoring processes InSAR pairs and time series for multiburst sets that overlap with Areas of Interest (AOIs) defined by the user in the [aoi.yaml](https://github.com/ASFHyP3/volcsarvatory-monitoring/blob/develop/aoi.yaml) file. To add a new AOI, prepare a pull request modifying this file and adding a unique ID (e.g., `GSitkin`) and define a bounding box for the AOI (minlon, maxlon, minlat, maxlat):
```shell
GSitkin:
  AOI:
  - -176.25
  - -175.92
  - 51.95
  - 52.14
  temporal_baseline:
  season:
  target_date:
  bridge_years:
  resolution:
```
The rest of the parameters are used to build a two-year window SBAS network. If the user does not define them, VolcSARvatory monitoring will choose the most optimal parameters.

VolcSARvatory Monitoring uses a pub-sub model. Data provider publish new scene messages to a SNS Topic for each new scene added to the dataset. The SNS Topic for Sentinel-1 data is described in this page:
* Sentinel-1: <https://github.com/ASFHyP3/CMR-notifier>

VolcSARvatory Monitoring subscribes to these messages and collects them in an SQS Queue. An AWS Lambda function consumes messages from the SQS Queue and:
* determines if the scene in the message should be processed
* builds InSAR pairs from an SBAS network
* ensures these pairs haven't already been processed
* submits the scene pairs to HyP3 for processing
* publish a SNS notification for a new product available in the bucket
* process a time series if there is a new InSAR pair in the bucket and there are not pending/running jobs

## Development

### Development environment setup

To create a development environment, run:
```shell
conda env update -f environment.yml
conda activate volcsarvatory-monitoring
```

A `Makefile` has been provided to run some common development steps:
* `make tests` runs the PyTest test suite.

Review the `Makefile` for a complete list of commands.

### Environment variables

Many parts of this stack are controlled by environment variables. Below is a non-exhaustive list of some environment variables that you may want to set.
* `HYP3_API`: The HyP3 deployment to which jobs will be submitted, e.g. https://hyp3-volcsarvatory.asf.alaska.edu.
* `EARTHDATA_USERNAME`: Earthdata Login username for the account which will submit jobs to HyP3. In the production stack, this should the VolcSARvatory operational user; in the test stack, this should be the team testing user.
* `EARTHDATA_PASSWORD`: Earthdata Login password for the account which will submit jobs to HyP3.
* `JOBS_TABLE_NAME` The jobs table name for the DynamoDB database associated with the HyP3 deployment jobs are submitted to.
* `PUBLISH_BUCKET` The bucket where the products are stored.

 Refer to [`tests/cfg.env`](tests/cfg.env) for a complete list of environment variables.

### Running the Lambda functions locally

The Lambda functions can be run locally from the command line, or by calling the appropriate function in the Python console.

> [!NOTE]
> To call the functions in the python console, you'll need to add all the `src` directories to your `PYTHONPATH`. With PyCharm, you can accomplish this by marking all such directories as "Sources Root" and enabling the "Add source roots to PYTHONPATH" Python Console setting.

#### volcsarvatory_monitoring

To build the multiburst sets from the AOI file:
```shell
cp aoi.yaml volcsarvatory_monitoring/src/data/
python volcsarvatory_monitoring/src/main.py
```
