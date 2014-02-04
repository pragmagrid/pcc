#! /usr/bin/env python
    
import sys

version = '1.0'
    
class VCManager:
  """
  vc-manager - a wrapper program for managing virtual clusters
    
  A prototype of a virtual cluster manager for PRAGMA that emphasizes user
  controllability.   This will integrate existing PRAGMA components (just Rocks
  to start) into Condor to leverage Condor's scheduling, fault tolerance, and
  monitoring features.  The prototype will provide basic capabilities such as
  1) create a pool, 2) manage a pool (add/delete/describe resources), 3) submit
  a virtual cluster request as a workflow DAG, instantiate the virtual cluster
  on Rocks via a custom gahp (Condor) plugin, and 4) shut it down and save
  images/data.  This was also serve as the PRAGMA 26 demo.

  Note, the Condor pool administration commands are modeled after Rocks and try
  to follow the conventions there (i.e., add, list, remove) whereas the user
  commands are modeled after PBS (i.e., qsub, qdel, qstat).
    
    add pool {name}
      Create a new personal condor pool.  
        
    add resource {pool} {name} {file}
      Add a resource described in file to the named Condor pool.  May want to
      consider (3.2.9 Dynamic Deployment) as a way to easily add new resources.

    help
      Display help for vc-manager.py

    list pool
      List the Condor pools (will probably be just 1 for this prototype).

    list resource {pool}
      List the resources in the specified pool.

    qchkpt {pool} {cluster} 
      Snapshot a running virtual cluster. 

    qdel {pool} {cluster} 
      Delete a cluster job

    qstat {pool} [cluster] 
      List the clusters in the Condor pool (i.e., condor_status) and each
      cluster's status (i.e., queued, starting, running, saved). 

    qsub {pool} {file} 
      Submit a cluster job to Condor as a DAG workflow.
        
    remove pool {name}
      Delete the specified pool.

    remove resource {pool} {resource}
      Delete a resource from the specified pool.
   """   

  def __init__(self, argv):
    """Class constructor; pass the sys.argv as the parameter."""

    if len(argv) < 1:
      print self.__doc__
      sys.exit(0)
    
    # Use python introspection to call appropriate function based on command.
    # First looks for single command functions (e.g., command 'qstat' calls
    # function 'qstat').   Then looks for double command functions (e.g.,
    # command 'add pool' calls function 'addPool') and then triple commands
    # (e.g., toBeAdded)
    for numwords in range(1,4):
      if numwords > len(argv): # don't continue if we run out of args to try
        break
      # create a potential function name out of provided args
      arg_function = argv[0];
      for i in range(1, numwords):
        arg_function = arg_function + argv[i].capitalize()
      # look at functions in this class and look for a match
      for function in dir(VCManager):
        if arg_function == function:
          sys.exit( getattr(self, function)(argv[numwords:]) )

    # otherwise we error out
    sys.stderr.write("Unknown command '" + " ".join(argv) + "'.  ")
    sys.stderr.write("Re-run with 'help' for more information.\n")
    sys.exit(1)
       

  def addPool(self, argv):
    """Create a new personal condor pool."""
    if len(argv) <= 0:
      sys.stderr.write("Pool name missing\n");
      sys.stderr.write("Usage:  add pool {name} \n");
      sys.exit(1)
      
    print "Created new pool " + argv[0]

  def help(self, argv):
    """Display help for vc-manager.py"""

    print self.__doc__

  def qstat(self, argv):
    """List the clusters in the Condor pool."""

    print "table indicating virtual cluster status"

VCManager(sys.argv[1:]) # trim off program name
