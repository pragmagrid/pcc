Here is the basic configuration to add node into your pool. 

~~~
##  Read access.  Machines listed as allow (and/or not listed as deny)
##  can view the status of your pool, but cannot join your pool 
##  or run jobs.
##  NOTE: By default, without these entries customized, you
##  are granting read access to the whole world.  You may want to
##  restrict that to hosts in your domain.  If possible, please also
##  grant read access to "*.cs.wisc.edu", so the Condor developers
##  will be able to view the status of your pool and more easily help
##  you install, configure or debug your Condor installation.
##  It is important to have this defined.

ALLOW_READ = nbcr-224.ucsd.edu, 129.79.49.186,129-79-49-186.dhcp-bl.indiana.edu, vm-container-0-2

##  Write access.  Machines listed here can join your pool, submit
##  jobs, etc.  Note: Any machine which has WRITE access must
##  also be granted READ access.  Granting WRITE access below does
##  not also automatically grant READ access; you must change
##  ALLOW_READ above as well.
##
##  You must set this to something else before Condor will run.
##  This most simple option is:
##    ALLOW_WRITE = *
##  but note that this will allow anyone to submit jobs or add
##  machines to your pool and is a serious security risk.

ALLOW_WRITE = nbcr-224.ucsd.edu, 129.79.49.186,129-79-49-186.dhcp-bl.indiana.edu, vm-container-0-2

# Grant machines to access to ADVERTISE_MASTER and ADVERTISE_STARTD
ALLOW_ADVERTISE_MASTER = $(ALLOW_WRITE), pragma8.cs.indiana.edu
ALLOW_ADVERTISE_STARTD = $(ALLOW_WRITE), pragma8.cs.indiana.edu
ALLOW_ADVERTISE_SCHEDD = $(ALLOW_WRITE), pragma8.cs.indiana.edu


## HTCondor uses user nobody if the value of the UID_DOMAIN configuration variable of the submitting and executing machines
## are different or if STARTER_ALLOW_RUNAS_OWNER is false or if the job ClassAd contains RunAsOwner=False. Under Windows, 
## HTCondor by default runs jobs under a dynamically created local account that exists for the duration of the job, but it 
## can optionally run the job as the user account that owns the job if STARTER_ALLOW_RUNAS_OWNER is True and the job contains 
## RunAsOwner=True.

##  If your site needs to use UID_DOMAIN settings (defined above) that
##  are not real Internet domains that match the hostnames, you can
##  tell Condor to trust whatever UID_DOMAIN a submit machine gives to
##  the execute machine and just make sure the two strings match.  The
##  default for this setting is False, since it is more secure this
##  way.
## Set this value to true so that all domains can be specified as "PRAGMA" in local configuration files. 
TRUST_UID_DOMAIN = True 
##  honor the run_as_owner option from the condor submit file.
##
STARTER_ALLOW_RUNAS_OWNER = TRUE
~~~
