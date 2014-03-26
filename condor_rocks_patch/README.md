vc-manager
==========
This condor patch enables condor to submit vm universe jobs via rocks. A sample submit script and configuration file can be found in the test directory.

Note: the real rocks command (pragma_boot) is not integrated at this moment. The condor vm gahp calls a fake script that simulates rocks command. The VM status is manipulated by manually write job status to a file.

Here's how it works:
1. submit a sample vm job to condor
~~~
condor_submit /<path>/samplejob.sub
~~~
2. query status
~~~
condor_q <cluster>
~~~
3. Manually change VM status
~~~
echo "Running" > /<path>/status.txt
echo "Suspended" > /<path>/status.txt
echo "Stopped" > /<path>/status.txt
~~~
4. query status to see change
~~~
condor_q <cluster>
~~~
5. take a look at the log file
~~~
tail -f /<local.dir>/log/StarteLOG.<slot_name>
~~~
