'''
Created on Mar 01, 2014

@author: yuanluo
'''

import json
import subprocess
import re

condor_bin='/opt/condor/bin'

def printTest(name):
     print 'Hello', name

def condorCLI(args,format):
    if args[0] == "condor_status":
        condor_status(format)
    if args[0] == "condor_q":
        condor_q(format)
    if args[0] == "condor_history":
        condor_history(format)
    if args[0] == "condor_submit":
        condor_submit(args,format)
def condor_status(format):
    p = subprocess.Popen([condor_bin+"/condor_status","-wide"], stdout=subprocess.PIPE)
    out, err = p.communicate()
    images = __text2dict__( out, filter="slot", columns = ["Name", "OpSys", "Arch", "State", "Activity", "LoadAv", "Mem","ActivityTime"]   )
    if format=="json":
        print json.dumps( images )
    else:
        print out

def condor_q(format):
    p = subprocess.Popen([condor_bin+"/condor_q","-wide"], stdout=subprocess.PIPE)
    out, err = p.communicate()
    images = __text2dict__( out, filter="/", columns = ["ID", "OWNER", "SUBMITTED", "RUN_TIME", "ST", "PRI", "SIZE","CMD"]   )
    if format=="json":
        print json.dumps( images )
    else:
        print out
        
def condor_history(format):
    p = subprocess.Popen([condor_bin+"/condor_history","-wide"], stdout=subprocess.PIPE)
    out, err = p.communicate()
    images = __text2dict__( out, filter="/", columns = ["ID", "OWNER", "SUBMITTED", "RUN_TIME", "COMPLETED","CMD"]   )
    if format=="json":
        print json.dumps( images )
    else:
        print out

def condor_submit(args, format):
    p = subprocess.Popen([condor_bin+"/condor_submit",args[1]], stdout=subprocess.PIPE)
    out, err = p.communicate()
    images = __text2dict__( out, filter="submitted", columns = ["number_of_jobs", "", "", "", "","cluster"]   )
    if format=="json":
        print json.dumps( images )
    else:
        print out
    
def __text2dict__( text, **kwargs ):
  values_line = 1
  lines = text.split("\n")
  columns = re.split( '\s+', lines[0].strip() )
  if kwargs.has_key("filter"):
    lines = filter( lambda x: re.search( kwargs["filter"], x), lines )
    values_line = 0
  if kwargs.has_key("columns"):
    columns = kwargs["columns"]
  data = {}
  if len(columns) > 0 and len(lines[1:]) > 0:
    __line2dict__( data, columns, filter(None, lines), 0, values_line, 0 )
  return data

def __line2dict__( data, columns, lines, col_i, row_i, iter ):
  prev_key = None
  while row_i < len(lines):
    fields = re.split( '[\s:]+', lines[row_i].strip(), maxsplit=len(columns)-1 )
    if col_i > 0 and fields[col_i-1]:
      return row_i
    elif fields[col_i] == '':
      data[prev_key][columns[col_i+1]] = {}
      row_i = __line2dict__( data[prev_key][columns[col_i+1]], columns, lines, col_i+1, row_i, iter+1 )
    else:
      data[fields[col_i]] = {}
      prev_key = fields[col_i]
      for k in range(col_i+1, len(columns)): 
        if not( re.match( "^\-+$", fields[k]) ):
            data[fields[col_i]][columns[k]] = fields[k]
      row_i = row_i + 1

  return row_i   