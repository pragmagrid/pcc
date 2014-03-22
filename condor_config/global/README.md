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
ALLOW_ADVERTISE_MASTER = $(ALLOW_WRITE), 129.79.49.186,129-79-49-186.dhcp-bl.indiana.edu
ALLOW_ADVERTISE_STARTD = $(ALLOW_WRITE), 129.79.49.186,129-79-49-186.dhcp-bl.indiana.edu
~~~
