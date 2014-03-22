

In condor_config.local

~~~
## Add Rocks ClassAD Attributes.
## The rocks_ad.sh script output a list of attributes, e.g.:
## Rocks_VM_Container_NUM = 4
## Rocks_Frontnode = nbcr-224.ucsd.edu
## ...
## The condor startd uses STARTD_CRON to periodically
## update extended ClassAD attributes by using 
## the following settings 
## (once set, run "condor_reconfig -startd")

ROCKSINFO = /opt/condor/bin/rocks_ad.sh
STARTD_CRON_JOBLIST = $(STARTD_CRON_JOBLIST) ROCKSINFO
STARTD_CRON_ROCKSINFO_EXECUTABLE = $(ROCKSINFO)
STARTD_CRON_ROCKSINFO_PERIOD = 10
~~~

In rocks_ad.sh
~~~
The rocks_ad.sh script extracts Rocks related attributes for Condor's ClassAd. Make sure this script is
accessible by condor user. Set the script location in condor_config.local so that STARTD_CRON can add these customized ClassAd attributes to the resources.
~~~
