#!/bin/bash
##
## This script extracts Rocks related attributes 
## for Condor's ClassAd. Make sure this script is
## accessible by condor user. Set the script location 
## in condor_config.local so that STARTD_CRON can 
## add these customized ClassAd attributes to the resources.
##

## TODO: Implement rocks info extraction script.
echo "ROCKS_HOSTNAME = $(/bin/hostname)"
