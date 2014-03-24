/***************************************************************
 *
 * Copyright (C) 1990-2007, Condor Team, Computer Sciences Department,
 * University of Wisconsin-Madison, WI.
 * 
 * Licensed under the Apache License, Version 2.0 (the "License"); you
 * may not use this file except in compliance with the License.  You may
 * obtain a copy of the License at
 * 
 *    http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 ***************************************************************/

/*****************************************************************
 *  Project:		Personal Cloud Controller
 *  				In addition to submit VM jobs to XEN, KVM, and VMWARE, Condor can
 *  				submit VM jobs to rocks-based interface, such as rocks command, and
 *  				pragma_boot command.
 *
 *  File:			rocks_type.h
 *  Description: 	Defines rocks type and operations for vm universe.
 *
 *  Modified by Yuan Luo, Indiana University (yuanluo@indiana.edu)
 *  @version 0.0.1
 *  @update 03/24/14
 *  **************************************************************
*/

#ifndef ROCKS_TYPE_H
#define ROCKS_TYPE_H

#include "condor_classad.h"
#include "MyString.h"
#include "simplelist.h"
#include "gahp_common.h"
#include "vmgahp.h"
#include "vm_type.h"

class RocksType : public VMType
{
public:
	static bool checkRocksParams(VMGahpConfig* config);
	static bool testRocks(VMGahpConfig* config);
	static bool killVMFast(const char* prog_for_script, const char* script, 
			const char* matchstring, bool is_root = false);

	RocksType(const char* prog_for_script, const char* scriptname,
			const char* workingpath, ClassAd* ad);

	virtual ~RocksType();

	virtual void Config();

	virtual bool Start();

	virtual bool Shutdown();

	virtual bool SoftSuspend();

	virtual bool Suspend();

	virtual bool Resume();

	virtual bool Checkpoint();

	virtual bool Status();

	virtual bool CreateConfigFile();
	
	virtual bool killVM();

private:
	void deleteLockFiles();
	bool createCkptFiles();
	bool CombineDisks();
	void adjustConfigDiskPath();
	bool adjustCkptConfig(const char* vmconfig);
	bool Snapshot();
	bool Unregister();
	bool ShutdownFast();
	bool ShutdownGraceful();
	bool ResumeFromSoftSuspend();
	bool getPIDofVM(int &vm_pid);

	bool findCkptConfig(MyString &vmconfig);
	bool readVMCONFfile(const char *filename, const char *dirpath);

	StringList m_configVars;

	bool m_need_snapshot;
	bool m_restart_with_ckpt;
	bool m_rocks_transfer;
	bool m_rocks_snapshot_disk;

	MyString m_rocks_dir;
	MyString m_rocks_vmconf;
	MyString m_rocks_img;
};
#endif
