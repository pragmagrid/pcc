condor rocks patch
==========
This condor patch enables condor to submit vm universe jobs via rocks. A sample submit script and configuration file can be found in the test directory.

We have integrated HTCondor with the pragma_boot and Rocks commands. HTCondor can start and control virtual clusters from its Virtual Machine universe. The condor_vm-gahp enables the VM Universe feature of HTCondor. The stock VM Universe code uses xen/kvm/vmware to start and control VMs under HTCondor's Startd. The integration is done by modifying the HTCondor source code of the condor_schedd, condor_startd, and condor_starter daemons, and the condor_vm-gahp.

HTCondor does not have plugin mechanism to plug in new GAHP service. We decided to change the existing VM GAHP code that enabled new vm_type, the rocks type.  A sample HTCondor submission script is shown below:
~~~
universe                            = vm
executable                          = lifemapper
log                                 = simple.condor.log
vm_type                             = rocks
rocks_job_dir                       = /path/to/the/job/dir
rocks_should_transfer_files         = NO
queue
~~~
Different tools can be plugin directly under the rocks vm_type by supplying a separate configuration file with vmconf extension during the HTCondor job submission. The tools are advertised by condor_startd daemons in the corresponding execution nodes using the customized ClassAd attributes. Here is a sample vmconf file:
~~~
executable     = pragma_boot
basepath       = /opt/pragma_boot/vm-images
key            = ~/.ssh/id_rsa.pub
num_cores      = 2
vcname         = lifemapper
logfile        = pragma_boot.log
~~~
Here's how it works:

1. submit a sample vm job to condor
~~~
condor_submit /<path>/samplejob.sub
~~~
2. query status
~~~
condor_q <cluster>
~~~
3. The log file on the execute node
~~~
less /<local.dir>/log/StarteLOG.<slot_name>
~~~
