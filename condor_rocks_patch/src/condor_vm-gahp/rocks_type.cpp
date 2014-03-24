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
 *  File:			rocks_type.cpp
 *  Description: 	Inplement rocks type that defined in rocks_type.h for vm universe.
 *
 *  Modified by Yuan Luo, Indiana University (yuanluo@indiana.edu)
 *  @version 0.0.1
 *  @update 03/24/14
 *  **************************************************************
*/


#include "condor_common.h"
#include "condor_config.h"
#include "condor_string.h"
#include "string_list.h"
#include "condor_attributes.h"
#include "condor_classad.h"
#include "MyString.h"
#include "util_lib_proto.h"
#include "stat_wrapper.h"
#include "vmgahp_common.h"
#include "vmgahp_error_codes.h"
#include "condor_vm_universe_types.h"
#include "rocks_type.h"
#include "../condor_privsep/condor_privsep.h"

#define ROCKS_TMP_FILE "rocks_status.condor"
#define ROCKS_TMP_TEMPLATE		"rocks_vm_XXXXXX"
#define ROCKS_TMP_CONFIG_SUFFIX	"_condor.vmconf"
#define ROCKS_VMCONF_FILE_PERM	0770
#define ROCKS_IMG_FILE_PERM	0660

#define ROCKS_LOCAL_SETTINGS_PARAM "ROCKS_LOCAL_SETTINGS_FILE"
#define ROCKS_LOCAL_SETTINGS_START_MARKER "### Start local parameters ###"
#define ROCKS_LOCAL_SETTINGS_END_MARKER "### End local parameters ###"

#define ROCKS_MONOLITHICSPARSE_IMG_SEEK_BYTE	512
#define ROCKS_MONOLITHICSPARSE_IMG_DESCRIPTOR_SIZE	800

#define ROCKS_SNAPSHOT_PARENTFILE_HINT "parentFileNameHint"

extern uid_t job_user_uid;
extern MyString workingdir;



RocksType::RocksType(const char* prog_for_script, const char* scriptname,
	const char* workingpath, ClassAd* ad) : 
	VMType(prog_for_script, scriptname, workingpath, ad)
{
	m_vmtype = CONDOR_VM_UNIVERSE_ROCKS;

	//m_cputime_before_suspend = 0;
	m_need_snapshot = false;
	m_restart_with_ckpt = false;
	m_rocks_transfer = false;
	m_rocks_snapshot_disk = false;

	// delete lock files
	deleteLockFiles();
}

RocksType::~RocksType()
{
	Shutdown();

	if( getVMStatus() != VM_STOPPED ) {
		// To make sure the process for VM exits.
		killVM();
	}
	setVMStatus(VM_STOPPED);
}

void
RocksType::Config()
{
	// Nothing to do
}

void
RocksType::adjustConfigDiskPath()
{

}

void
RocksType::deleteLockFiles()
{
	// Delete unnecessary files such as lock files
#define ROCKS_WRITELOCK_SUFFIX	".WRITELOCK"
#define ROCKS_READLOCK_SUFFIX	".READLOCK"

	const char *tmp_file = NULL;
	m_initial_working_files.rewind();
	while( (tmp_file = m_initial_working_files.next()) != NULL ) {
		if( has_suffix(tmp_file, ROCKS_WRITELOCK_SUFFIX) ||
			has_suffix(tmp_file, ROCKS_READLOCK_SUFFIX)) {
			IGNORE_RETURN unlink(tmp_file);
			m_initial_working_files.deleteCurrent();
		}else if( has_suffix(tmp_file, ".img") ) {
			// modify permission for img files
			IGNORE_RETURN chmod(tmp_file, ROCKS_IMG_FILE_PERM);
		}
	}

	// delete entries for these lock files
	m_transfer_intermediate_files.rewind();
	while( (tmp_file = m_transfer_intermediate_files.next()) != NULL ) {
		if( has_suffix(tmp_file, ROCKS_WRITELOCK_SUFFIX) ||
			has_suffix(tmp_file, ROCKS_READLOCK_SUFFIX)) {
			m_transfer_intermediate_files.deleteCurrent();
		}
	}
	m_transfer_input_files.rewind();
	while( (tmp_file = m_transfer_input_files.next()) != NULL ) {
		if( has_suffix(tmp_file, ROCKS_WRITELOCK_SUFFIX) ||
			has_suffix(tmp_file, ROCKS_READLOCK_SUFFIX)) {
			m_transfer_input_files.deleteCurrent();
		}
	}
}

bool 
RocksType::findCkptConfig(MyString &vmconfig)
{
	if( m_transfer_intermediate_files.isEmpty()) {
		return false;
	}

	int file_length = 0;
	int config_length = strlen(ROCKS_TMP_TEMPLATE) +
		strlen(ROCKS_TMP_CONFIG_SUFFIX); // rocks_vm_XXXXX_condor.vmconf
	char *tmp_file = NULL;
	const char *tmp_base = NULL;
	m_transfer_intermediate_files.rewind();
	while( (tmp_file = m_transfer_intermediate_files.next()) != NULL ) {
		tmp_base = condor_basename(tmp_file);
		file_length = strlen(tmp_base);
		if( (file_length == config_length ) && 
				has_suffix(tmp_file, ROCKS_TMP_CONFIG_SUFFIX) ) {
			// file has the ending suffix of "_condor.vmconf"
			// This is the vm config file for checkpointed files
			if( check_vm_read_access_file(tmp_file) ) {
				vmconfig = tmp_file;
				return true;
			}else {
				vmprintf(D_ALWAYS, "Cannot read the rocks config file "
						"for checkpointed files\n");
				return false;
			}
		}
	}
	return false;
}

bool 
RocksType::adjustCkptConfig(const char* vmconfig)
{
	return true;
}


static bool starts_with(const char * str, const char * pre)
{
	size_t cp = strlen(pre);
	if (cp <= 0)
		return false;

	size_t cs = strlen(str);
	if (cs < cp)
		return false;

	for (size_t ix = 0; ix < cp; ++ix) {
		if (str[ix] != pre[ix]) {
			return false;
		}
	}
	return true;
}

static bool starts_with_ignore_case(const char * str, const char * pre)
{
	size_t cp = strlen(pre);
	if (cp <= 0)
		return false;

	size_t cs = strlen(str);
	if (cs < cp)
		return false;

	for (size_t ix = 0; ix < cp; ++ix) {
		if (str[ix] != pre[ix]) {
			if (_tolower(str[ix]) != _tolower(pre[ix]))
				return false;
		}
	}
	return true;
}

bool
RocksType::readVMCONFfile(const char *filename, const char *dirpath)
{
	return true;

}


bool
RocksType::Unregister()
{
	//vmprintf(D_FULLDEBUG, "Inside RocksType::Unregister\n");
	vmprintf(D_ALWAYS, "Inside RocksType::Unregister\n");

	if( (m_scriptname.Length() == 0) ||
		(m_configfile.Length() == 0)) {
		vmprintf(D_ALWAYS, "RocksType::Unregister(): m_scriptname.Length()=%d, m_configfile.Length()=%d\n", m_scriptname.Length(), m_configfile.Length());
		return false;
	}

	ArgList systemcmd;
	systemcmd.AppendArg(m_prog_for_script);
	systemcmd.AppendArg(m_scriptname);
	systemcmd.AppendArg("unregister");
	systemcmd.AppendArg(m_configfile);

	int result = systemCommand(systemcmd, m_file_owner);
	if( result != 0 ) {
		return false;
	}
	return true;
}

bool
RocksType::Snapshot()
{
	vmprintf(D_FULLDEBUG, "Inside RocksType::Snapshot\n");
	vmprintf(D_ALWAYS, "Inside RocksType::Snapshot\n");

	if( (m_scriptname.Length() == 0) ||
		(m_configfile.Length() == 0)) {
		vmprintf(D_ALWAYS, "RocksType::Snapshot(): m_scriptname.Length()=%d, m_configfile.Length()=%d\n", m_scriptname.Length(), m_configfile.Length());

		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}

	StringList cmd_out;

	ArgList systemcmd;
	systemcmd.AppendArg(m_prog_for_script);
	systemcmd.AppendArg(m_scriptname);
	systemcmd.AppendArg("snapshot");
	systemcmd.AppendArg(m_configfile);

	int result = systemCommand(systemcmd, m_file_owner, &cmd_out);
	if( result != 0 ) {
		char *temp = cmd_out.print_to_delimed_string("/");
		m_result_msg = temp;
		free( temp );
		return false;
	}

#if defined(LINUX)	
	// To avoid lazy-write behavior to disk
	sync();
#endif

	return true;
}

bool 
RocksType::Start()
{
	//vmprintf(D_FULLDEBUG, "Inside RocksType::Start\n");
	vmprintf(D_ALWAYS, "Inside RocksType::Start\n");

	if( (m_scriptname.Length() == 0) ||
		(m_configfile.Length() == 0)) {
		vmprintf(D_ALWAYS, "RocksType::Start(): m_scriptname.Length()=%d, m_configfile.Length()=%d\n", m_scriptname.Length(), m_configfile.Length());

		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}

	if( getVMStatus() != VM_STOPPED ) {
		m_result_msg = VMGAHP_ERR_VM_INVALID_OPERATION;
		return false;
	}
		
	if( m_restart_with_ckpt ) {
		m_restart_with_ckpt = false;
		m_need_snapshot = false;
		bool res = Start();
		if( res ) {
			vmprintf(D_ALWAYS, "Succeeded to restart with checkpointed files\n");
			return true;
		}else {
			// Failed to restart with checkpointed files
			vmprintf(D_ALWAYS, "Failed to restart with checkpointed files\n");
			vmprintf(D_ALWAYS, "So, we will try to create a new configuration file\n");

			deleteNonTransferredFiles();
			m_configfile = "";
			m_restart_with_ckpt = false;

			if( CreateConfigFile() == false ) {
				vmprintf(D_ALWAYS, "Failed to create a new configuration files\n");
				return false;
			}

			// Succeeded to create a configuration file
			// Keep going..
		}
	}


	if( m_need_snapshot ) {
		if( Snapshot() == false ) {
			Unregister();
			return false;
		}
	}

	StringList cmd_out;

	ArgList systemcmd;
	systemcmd.AppendArg(m_prog_for_script);
	systemcmd.AppendArg(m_scriptname);
	systemcmd.AppendArg("start");
	systemcmd.AppendArg(m_configfile);

	int result = systemCommand(systemcmd, m_file_owner, &cmd_out);
	if( result != 0 ) {
		Unregister();
		char *temp = cmd_out.print_to_delimed_string("/");
		m_result_msg = temp;
		free( temp );
		return false;
	}

	// Got Pid result
	m_vm_pid = 0;
	cmd_out.rewind();
	const char *pid_line;
	while ( (pid_line = cmd_out.next()) ) {
		if ( sscanf( pid_line, "PID=%d", &m_vm_pid ) == 1 ) {
			if ( m_vm_pid <= 0 ) {
				m_vm_pid = 0;
			}
			break;
		}
	}

	setVMStatus(VM_RUNNING);
	m_start_time.getTime();
    //m_cpu_time = 0;
	return true;
}

bool
RocksType::ShutdownFast()
{
	static bool sent_signal = false;
	vmprintf(D_FULLDEBUG, "Inside RocksType::ShutdownFast\n");

	bool ret = false;
	if( m_vm_pid > 0 && daemonCore ) {
		if( !sent_signal ) {
			vmprintf(D_FULLDEBUG, "Sending Kill signal to process(pid=%d)\n", m_vm_pid);
			ret = daemonCore->Send_Signal(m_vm_pid, SIGKILL);
			if( ret ) {
				// success to send signal
				m_vm_pid = 0;
				sleep(1);
			}
			sent_signal = true;
		}
	}
	return ret;
}

bool
RocksType::ShutdownGraceful()
{
	vmprintf(D_FULLDEBUG, "Inside RocksType::ShutdownGraceful\n");

	ArgList systemcmd;
	systemcmd.AppendArg(m_prog_for_script);
	systemcmd.AppendArg(m_scriptname);
	systemcmd.AppendArg("stop");
	systemcmd.AppendArg(m_configfile);

	int result = systemCommand(systemcmd, m_file_owner);
	if( result != 0 ) {
		return false; 
	}

	m_vm_pid = 0;
	setVMStatus(VM_STOPPED);
	return true;
}


bool
RocksType::Shutdown()
{
	vmprintf(D_FULLDEBUG, "Inside RocksType::Shutdown\n");

#if !defined(WIN32)
	if (privsep_enabled()) {
		if (!privsep_chown_dir(get_condor_uid(),
		                       job_user_uid,
		                       workingdir.Value()))
		{
			m_result_msg = VMGAHP_ERR_CRITICAL;
			return false;
		}
		m_file_owner = PRIV_CONDOR;
	}
#endif

	if( (m_scriptname.Length() == 0) ||
			(m_configfile.Length() == 0)) {
		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}

	if( getVMStatus() == VM_STOPPED ) {
		if( m_self_shutdown ) {
			if( m_rocks_transfer && m_rocks_snapshot_disk
					&& !m_vm_no_output_vm ) {
				// The path of parent disk in a snapshot disk 
				// used basename because all parent disk files 
				// were transferred. So we need to replace 
				// the path with the path on submit machine.
				priv_state old_priv = set_user_priv();
				adjustConfigDiskPath();
				set_priv( old_priv );
			}
			Unregister();

			if( m_vm_no_output_vm ) {
				// A job user doesn't want to get back VM files.
				// So we will delete all files in working directory.
				m_delete_working_files = true;
				m_is_checkpointed = false;
			}
		}
		// We here set m_self_shutdown to false
		// So, above functions will not be called twice
		m_self_shutdown = false;
		return true;
	}

	if( getVMStatus() == VM_SUSPENDED ) {
		// Unregistering ...
		Unregister();
	}
	
	// If a VM is soft suspended, resume it first.
	ResumeFromSoftSuspend();

	if( getVMStatus() == VM_RUNNING ) {
		if( ShutdownGraceful() == false ) {
			vmprintf(D_ALWAYS, "ShutdownGraceful failed ..\n");
			// We failed to stop a running VM gracefully.
			// So we will try to destroy the VM forcedly.
			if( killVM() == false ) {
				vmprintf(D_ALWAYS, "killVM failed ..\n");
				// We failed again. So final step is 
				// to try kill process for VM directly.
				ShutdownFast();
				Unregister();
			}
		}
		// Now we don't need to keep working files any more
		m_delete_working_files = true;
		m_is_checkpointed = false;
	}
	
	m_vm_pid = 0;
	setVMStatus(VM_STOPPED);
	m_stop_time.getTime();
	return true;
}

bool
RocksType::Checkpoint()
{

	vmprintf(D_FULLDEBUG, "Inside RocksType::Checkpoint\n");

	if( (m_scriptname.Length() == 0) ||
		(m_configfile.Length() == 0)) {
		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}

	if( getVMStatus() == VM_STOPPED ) {
		vmprintf(D_ALWAYS, "Checkpoint is called for a stopped VM\n");
		m_result_msg = VMGAHP_ERR_VM_INVALID_OPERATION;
		return false;
	}

	if( !m_vm_checkpoint ) {
		vmprintf(D_ALWAYS, "Checkpoint is not supported.\n");
		m_result_msg = VMGAHP_ERR_VM_NO_SUPPORT_CHECKPOINT;
		return false;
	}

	// If a VM is soft suspended, resume it first.
	ResumeFromSoftSuspend();

	// This function cause a running VM to be suspended.
	if( createCkptFiles() == false ) { 
		m_result_msg = VMGAHP_ERR_VM_CANNOT_CREATE_CKPT_FILES;
		vmprintf(D_ALWAYS, "failed to create checkpoint files\n");
		return false;
	}

	// VM is suspended for checkpoint.
	// so there is no process for VM.
	m_vm_pid = 0;

	return true;

}

bool
RocksType::ResumeFromSoftSuspend()
{
	vmprintf(D_FULLDEBUG, "Inside RocksType::ResumeFromSoftSuspend\n");
	if( m_is_soft_suspended ) {
		if( m_vm_pid > 0 ) {
			// Send SIGCONT to a process for VM
			if( daemonCore->Send_Signal(m_vm_pid, SIGCONT) == false ) {
				// Sending SIGCONT failed
				vmprintf(D_ALWAYS, "Sending SIGCONT to process[%d] failed in "
						"RocksType::ResumeFromSoftSuspend\n", m_vm_pid);
				return false;
			}
		}
		m_is_soft_suspended = false;
	}
	return true;
}

bool 
RocksType::SoftSuspend()
{
	vmprintf(D_FULLDEBUG, "Inside RocksType::SoftSuspend\n");

	if( m_is_soft_suspended ) {
		return true;
	}

	if( getVMStatus() != VM_RUNNING ) {
		m_result_msg = VMGAHP_ERR_VM_INVALID_OPERATION;
		return false;
	}

	if( m_vm_pid > 0 ) {
		// Send SIGSTOP to a process for VM
		if( daemonCore->Send_Signal(m_vm_pid, SIGSTOP) ) {
			m_is_soft_suspended = true;
			return true;
		}
	}

	// Failed to suspend a VM softly.
	// Instead of soft suspend, we use hard suspend.
	vmprintf(D_ALWAYS, "SoftSuspend failed, so try hard Suspend instead!.\n");
	return Suspend();
}

bool 
RocksType::Suspend()
{
	vmprintf(D_FULLDEBUG, "Inside RocksType::Suspend\n");

	if( (m_scriptname.Length() == 0) ||
		(m_configfile.Length() == 0)) {
		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}

	if( getVMStatus() == VM_SUSPENDED ) {
		return true;
	}

	if( getVMStatus() != VM_RUNNING ) {
		m_result_msg = VMGAHP_ERR_VM_INVALID_OPERATION;
		return false;
	}

	// If a VM is soft suspended, resume it first.
	ResumeFromSoftSuspend();

	StringList cmd_out;

	ArgList systemcmd;
	systemcmd.AppendArg(m_prog_for_script);
	systemcmd.AppendArg(m_scriptname);
	systemcmd.AppendArg("suspend");
	systemcmd.AppendArg(m_configfile);

	int result = systemCommand(systemcmd, m_file_owner, &cmd_out);
	if( result != 0 ) {
		char *temp = cmd_out.print_to_delimed_string("/");
		m_result_msg = temp;
		free( temp );
		return false;
	}

	// Suspend succeeds. So there is no process for VM.
	m_vm_pid = 0;
	setVMStatus(VM_SUSPENDED);
	//m_cputime_before_suspend += m_cpu_time;
	//m_cpu_time = 0;
	return true;
}

bool 
RocksType::Resume()
{
	vmprintf(D_FULLDEBUG, "Inside RocksType::Resume\n");

	if( (m_scriptname.Length() == 0) ||
		(m_configfile.Length() == 0)) {
		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}

	// If a VM is soft suspended, resume it first.
	ResumeFromSoftSuspend();

	if( getVMStatus() == VM_RUNNING ) {
		return true;
	}

	if( getVMStatus() != VM_SUSPENDED ) {
		m_result_msg = VMGAHP_ERR_VM_INVALID_OPERATION;
		return false;
	}

	m_is_checkpointed = false;

	StringList cmd_out;

	ArgList systemcmd;
	systemcmd.AppendArg(m_prog_for_script);
	systemcmd.AppendArg(m_scriptname);
	systemcmd.AppendArg("resume");
	systemcmd.AppendArg(m_configfile);

	int result = systemCommand(systemcmd, m_file_owner, &cmd_out);
	if( result != 0 ) {
		char *temp = cmd_out.print_to_delimed_string("/");
		m_result_msg = temp;
		free( temp );
		return false;
	}

	// Got Pid result
	m_vm_pid = 0;
	cmd_out.rewind();
	const char *pid_line;
	while ( (pid_line = cmd_out.next()) ) {
		if ( sscanf( pid_line, "PID=%d", &m_vm_pid ) == 1 ) {
			if ( m_vm_pid <= 0 ) {
				m_vm_pid = 0;
			}
			break;
		}
	}

	setVMStatus(VM_RUNNING);
	return true;
}

bool
RocksType::Status()
{
	vmprintf(D_FULLDEBUG, "Inside RocksType::Status\n");

	if( (m_scriptname.Length() == 0) ||
			(m_configfile.Length() == 0)) {
		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}

	if( m_is_soft_suspended ) {
		// If a VM is softly suspended, 
		// we cannot get info about the VM by using script
		m_result_msg = VMGAHP_STATUS_COMMAND_STATUS;
		m_result_msg += "=";
		m_result_msg += "SoftSuspended";
		return true;
	}

	// Check the last time when we executed status.
	// If the time is in 10 seconds before current time, 
	// We will not execute status again.
	// Maybe this case may happen when it took long time 
	// to execute the last status.
	UtcTime cur_time;
	long diff_seconds = 0;

	cur_time.getTime();
	diff_seconds = cur_time.seconds() - m_last_status_time.seconds();

	if( (diff_seconds < 10) && !m_last_status_result.IsEmpty() ) {
		m_result_msg = m_last_status_result;
		return true;
	}

	StringList cmd_out;

	ArgList systemcmd;
	systemcmd.AppendArg(m_prog_for_script);
	systemcmd.AppendArg(m_scriptname);
	if( m_vm_networking ) {
		systemcmd.AppendArg("getvminfo");
	}else {
		systemcmd.AppendArg("status");
	}
	systemcmd.AppendArg(m_configfile);

	int result = systemCommand(systemcmd, m_file_owner, &cmd_out);
	if( result != 0 ) {
		char *temp = cmd_out.print_to_delimed_string("/");
		m_result_msg = temp;
		free( temp );
		return false;
	}

	// Got result
	const char *next_line;
	MyString one_line;
	MyString name;
	MyString value;

	MyString vm_status;
	int vm_pid = 0;
	float cputime = 0;
	cmd_out.rewind();
	while( (next_line = cmd_out.next()) != NULL ) {
		one_line = next_line;
		one_line.trim();

		if( one_line.Length() == 0 ) {
			continue;
		}

		if( one_line[0] == '#' ) {
			/* Skip over comments */
			continue;
		}

		parse_param_string(one_line.Value(), name, value, true);
		if( !name.Length() || !value.Length() ) {
			continue;
		}
		
		if( !strcasecmp(name.Value(), VMGAHP_STATUS_COMMAND_CPUTIME)) {
			cputime = (float)strtod(value.Value(), (char **)NULL);
			if( cputime <= 0 ) {
				cputime = 0;
			}
			continue;
		}

		if( !strcasecmp(name.Value(), VMGAHP_STATUS_COMMAND_STATUS)) {
			vm_status = value;
			continue;
		}
		if( !strcasecmp(name.Value(), VMGAHP_STATUS_COMMAND_PID) ) {
			vm_pid = (int)strtol(value.Value(), (char **)NULL, 10);
			if( vm_pid <= 0 ) {
				vm_pid = 0;
			}
			continue;
		}
		if( m_vm_networking ) {
			if( !strcasecmp(name.Value(), VMGAHP_STATUS_COMMAND_MAC) ) {
				m_vm_mac = value;
				continue;
			}
			if( !strcasecmp(name.Value(), VMGAHP_STATUS_COMMAND_IP) ) {
				m_vm_ip = value;
				continue;
			}
		}
	}

	if( !vm_status.Length() ) {
		m_result_msg = VMGAHP_ERR_CRITICAL;
		return false;
	}

	m_result_msg = "";

	if( m_vm_networking ) {
		if( m_vm_mac.IsEmpty() == false ) {
			if( m_result_msg.IsEmpty() == false ) {
				m_result_msg += " ";
			}
			m_result_msg += VMGAHP_STATUS_COMMAND_MAC;
			m_result_msg += "=";
			m_result_msg += m_vm_mac;
		}

		if( m_vm_ip.IsEmpty() == false ) {
			if( m_result_msg.IsEmpty() == false ) {
				m_result_msg += " ";
			}
			m_result_msg += VMGAHP_STATUS_COMMAND_IP;
			m_result_msg += "=";
			m_result_msg += m_vm_ip;
		}
	}

	if( m_result_msg.IsEmpty() == false ) {
		m_result_msg += " ";
	}

	m_result_msg += VMGAHP_STATUS_COMMAND_STATUS;
	m_result_msg += "=";

	if( strcasecmp(vm_status.Value(), "Running") == 0 ) {
		setVMStatus(VM_RUNNING);

		if( !vm_pid ) {
			// Retry to get pid
			getPIDofVM(vm_pid);
		}
		m_vm_pid = vm_pid;

		m_result_msg += "Running";
		m_result_msg += " ";

		m_result_msg += VMGAHP_STATUS_COMMAND_PID;
		m_result_msg += "=";
		m_result_msg += m_vm_pid;
		if( cputime > 0 ) {
			// Update vm running time
			m_cpu_time = cputime;

			m_result_msg += " ";
			m_result_msg += VMGAHP_STATUS_COMMAND_CPUTIME;
			m_result_msg += "=";
			m_result_msg += m_cpu_time;
			//m_result_msg += (double)(m_cpu_time + m_cputime_before_suspend);
		}

		return true;

	}else if( strcasecmp(vm_status.Value(), "Suspended") == 0 ) {
		// VM is suspended
		setVMStatus(VM_SUSPENDED);
		m_vm_pid = 0;
		m_result_msg += "Suspended";
		return true;
	}else if( strcasecmp(vm_status.Value(), "Stopped") == 0 ) {
		// VM is stopped
		m_vm_pid = 0;

		if( getVMStatus() == VM_SUSPENDED ) {
			m_result_msg += "Suspended";
			return true;
		}

		if( getVMStatus() == VM_RUNNING ) {
			m_self_shutdown = true;
		}

		m_result_msg += "Stopped";
		if( getVMStatus() != VM_STOPPED ) {
			setVMStatus(VM_STOPPED);
			m_stop_time.getTime();
		}
		return true;
	}else {
		// Woops, something is wrong
		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}
	return true;
}

bool 
RocksType::getPIDofVM(int &vm_pid)
{
	vmprintf(D_FULLDEBUG, "Inside RocksType::getPIDofVM\n");

	vm_pid = 0;

	if( (m_scriptname.Length() == 0) ||
		(m_configfile.Length() == 0)) {
		return false;
	}

	if( getVMStatus() != VM_RUNNING ) {
		return false;
	}

	StringList cmd_out;

	ArgList systemcmd;
	systemcmd.AppendArg(m_prog_for_script);
	systemcmd.AppendArg(m_scriptname);
	systemcmd.AppendArg("getpid");
	systemcmd.AppendArg(m_configfile);

	int result = systemCommand(systemcmd, m_file_owner, &cmd_out);
	if( result != 0 ) {
		return false;
	}

	// Got Pid result
	cmd_out.rewind();
	const char *pid_line;
	while ( (pid_line = cmd_out.next()) ) {
		if ( sscanf( pid_line, "PID=%d", &m_vm_pid ) == 1 ) {
			if ( m_vm_pid <= 0 ) {
				m_vm_pid = 0;
			}
			return true;
		}
	}
	return false;
}

bool
RocksType::CreateConfigFile()
{
	MyString tmp_config_name;

	m_result_msg = "";

	// Read common parameters for VM
	// and create the name of this VM
	if( parseCommonParamFromClassAd() == false ) {
		return false;
	}

	// Read the flag about transferring rocks files
	m_rocks_transfer = false;
	m_classAd.LookupBool(VMPARAM_ROCKS_TRANSFER, m_rocks_transfer);

	// Read the flag about snapshot disk
	m_rocks_snapshot_disk = true;
	m_classAd.LookupBool(VMPARAM_ROCKS_SNAPSHOTDISK, m_rocks_snapshot_disk);

	// Read the directory where rocks files are on a submit machine
	m_rocks_dir = "";
	m_classAd.LookupString(VMPARAM_ROCKS_DIR, m_rocks_dir);
	m_rocks_dir.trim();

	// Read the parameter of rocks vmconf file
	if( m_classAd.LookupString(VMPARAM_ROCKS_VMCONF_FILE, m_rocks_vmconf) != 1 ) {
		vmprintf(D_ALWAYS, "%s cannot be found in job classAd\n", 
							VMPARAM_ROCKS_VMCONF_FILE);
		m_result_msg = VMGAHP_ERR_JOBCLASSAD_NO_ROCKS_VMCONF_PARAM;
		return false;
	}
	m_rocks_vmconf.trim();

	// Read the parameter of rocks imgs
	if( m_classAd.LookupString(VMPARAM_ROCKS_IMG_FILES, m_rocks_img) == 1 ) {
		m_rocks_img.trim();
	}

	if( !m_rocks_transfer ) {
		// we use a shared filesystem
		// So we always use snapshot disks
		m_need_snapshot = true;
	}else {
		// Disk files are transferred 
		m_need_snapshot = m_rocks_snapshot_disk;
	}

	// Check whether this is re-starting after vacating or periodic checkpointing 
	if( m_transfer_intermediate_files.isEmpty() == false) {
		// We have checkpointed files
		// So, we don't need to create vm config file
		// Find the vm config file for checkpointed files
		MyString ckpt_config_file;
		if( findCkptConfig(ckpt_config_file) == false ) {
			vmprintf(D_ALWAYS, "Checkpoint files exist but "
					"cannot find the config file for them\n");
			// Delete all non-transferred files from submit machine
			deleteNonTransferredFiles();
			m_restart_with_ckpt = false;
		}else {
			// We found a valid vm configuration file with checkpointed files
			// Now, we need to adjust the configuration file, if necessary.
			if( adjustCkptConfig(ckpt_config_file.Value()) == false ) {
				vmprintf(D_ALWAYS, "Failed to adjust vm config file(%s) for ckpt files "
						"in RocksType::CreateConfigFile()\n",
						ckpt_config_file.Value());
				deleteNonTransferredFiles();
				m_restart_with_ckpt = false;
			}else {
				m_configfile = ckpt_config_file;
				m_need_snapshot = false;
				m_restart_with_ckpt = true;
				vmprintf(D_ALWAYS, "Found checkpointed files, "
						"so we start using them\n");
				return true;
			}
		}
	}

	// Create vm config file
	if( createTempFile(ROCKS_TMP_TEMPLATE, ROCKS_TMP_CONFIG_SUFFIX,
				tmp_config_name) == false ) {
		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}

	// Change file permission
	int retval = chmod(tmp_config_name.Value(), ROCKS_VMCONF_FILE_PERM);
	if( retval < 0 ) {
		vmprintf(D_ALWAYS, "Failed to chmod %s in "
				"RocksType::CreateConfigFile()\n", tmp_config_name.Value());
		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}

	// Read transferred rocks_vmconf file
	MyString ori_vmconf_file;
	ori_vmconf_file.formatstr("%s%c%s",m_workingpath.Value(),
			DIR_DELIM_CHAR, m_rocks_vmconf.Value());

	if( readVMCONFfile(ori_vmconf_file.Value(), m_rocks_dir.Value())
			== false ) {
		IGNORE_RETURN unlink(tmp_config_name.Value());
		return false;
	}

	// Add memsize to m_configVars
	MyString tmp_line;
	tmp_line.formatstr("memsize = \"%d\"", m_vm_mem);
	m_configVars.append(tmp_line.Value());

	// Add displyName to m_configVars
	tmp_line.formatstr("displayName = \"%s\"", m_vm_name.Value());
	m_configVars.append(tmp_line.Value());

	// Add networking parameters to m_configVars
	if( m_vm_networking ) {
		MyString networking_type;
		MyString tmp_string; 
		MyString tmp_string2;

		tmp_string2 = m_vm_networking_type;
		tmp_string2.upper_case();

		tmp_string.formatstr("ROCKS_%s_NETWORKING_TYPE", tmp_string2.Value());

		char *net_type = param(tmp_string.Value());
		if( net_type ) {
			networking_type = delete_quotation_marks(net_type);
			free(net_type);
		}else {
			net_type = param("ROCKS_NETWORKING_TYPE");
			if( net_type ) {
				networking_type = delete_quotation_marks(net_type);
				free(net_type);
			}else {
				// default networking type is bridge
				networking_type = "bridge";
			}
		}

		m_configVars.append("ethernet0.present = \"TRUE\"");
		tmp_line.formatstr("ethernet0.connectionType = \"%s\"", 
				networking_type.Value());
		m_configVars.append(tmp_line.Value());
        if (!m_vm_job_mac.IsEmpty())
        {
            vmprintf(D_FULLDEBUG, "mac address is %s\n", m_vm_job_mac.Value());
            m_configVars.append("ethernet0.addressType = \"static\"");
            tmp_line.formatstr("ethernet0.address = \"%s\"", m_vm_job_mac.Value());
            m_configVars.append(tmp_line.Value());
            //**********************************************************************
            // LIMITATION: the mac address has to be in the range
            // 00:50:56:00:00:00 - 00:50:56:3F:FF:FF
            // This is a rocks limitation and I can't find a way to circumvent it.
            //**********************************************************************
        } else {
    		m_configVars.append("ethernet0.addressType = \"generated\"");
        }
	}

	// Add uuid option
	m_configVars.append("uuid.action = \"keep\"");

	// Don't create lock file for disks
	m_configVars.append("disk.locking = \"FALSE\"");

	FILE *config_fp = safe_fopen_wrapper_follow(tmp_config_name.Value(), "w");
	if( !config_fp ) {
		vmprintf(D_ALWAYS, "failed to safe_fopen_wrapper rocks config file "
				"with write mode: safe_fopen_wrapper_follow(%s) returns %s\n", 
				tmp_config_name.Value(), strerror(errno));

		IGNORE_RETURN unlink(tmp_config_name.Value());
		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}

	// write config parameters
	m_configVars.rewind();
	char *oneline = NULL;
	while( (oneline = m_configVars.next()) != NULL ) {
		if( fprintf(config_fp, "%s\n", oneline) < 0 ) {
			vmprintf(D_ALWAYS, "failed to fprintf in CreateConfigFile(%s:%s)\n",
					tmp_config_name.Value(), strerror(errno));

			fclose(config_fp);
			IGNORE_RETURN unlink(tmp_config_name.Value());
			m_result_msg = VMGAHP_ERR_INTERNAL;
			return false;
		}
	}

	if (!write_local_settings_from_file(config_fp,
	                                    ROCKS_LOCAL_SETTINGS_PARAM,
	                                    ROCKS_LOCAL_SETTINGS_START_MARKER,
	                                    ROCKS_LOCAL_SETTINGS_END_MARKER))
	{
		vmprintf(D_ALWAYS,
		         "failed to add local settings in CreateConfigFile\n");
		fclose(config_fp);
		IGNORE_RETURN unlink(tmp_config_name.Value());
		m_result_msg = VMGAHP_ERR_INTERNAL;
		return false;
	}

	fclose(config_fp);
	config_fp = NULL;

	if( m_use_script_to_create_config ) {
		// We will call the script program 
		// to create a configuration file for VM

		if( createConfigUsingScript(tmp_config_name.Value()) == false ) {
			IGNORE_RETURN unlink(tmp_config_name.Value());
			m_result_msg = VMGAHP_ERR_CRITICAL;
			return false;
		}
	}

	// set vm config file
	m_configfile = tmp_config_name;
	return true;
}


bool
RocksType::createCkptFiles()
{

	vmprintf(D_FULLDEBUG, "Inside RocksType::createCkptFiles\n");

	// This function will suspend a running VM.
	if( getVMStatus() == VM_STOPPED ) {
		vmprintf(D_ALWAYS, "createCkptFiles is called for a stopped VM\n");
		return false;
	}

	if( getVMStatus() == VM_RUNNING ) {
		if( Suspend() == false ) {
			return false;
		}
	}

	if( getVMStatus() == VM_SUSPENDED ) {
		char *tmp_file = NULL;
		StringList ckpt_files;
		struct utimbuf timewrap;
		time_t current_time;

		find_all_files_in_dir(m_workingpath.Value(), ckpt_files, true);

		ckpt_files.rewind();
		while( (tmp_file = ckpt_files.next()) != NULL ) {
			// In some systems such as Linux, mtime may not be updated 
			// after changes to files via mmap. For example, 
			// the mtime of Rocks vmem file is not updated
			// even after changes, because Rocks uses the file via mmap.
			// So we manually update mtimes of some files.
			if( !has_suffix(tmp_file, ".img") &&
					!has_suffix(tmp_file, ".iso") &&
					!has_suffix(tmp_file, ".log") &&
					!has_suffix(tmp_file, ROCKS_WRITELOCK_SUFFIX ) &&
					!has_suffix(tmp_file, ROCKS_READLOCK_SUFFIX ) &&
					strcmp(condor_basename(tmp_file), m_rocks_vmconf.Value())) {
				// We update mtime and atime of all files 
				// except img, iso, log, lock files, cdrom file, and
				// the original vmconf file.
				current_time = time(NULL);
				timewrap.actime = current_time;
				timewrap.modtime = current_time;
				utime(tmp_file, &timewrap);
			}
		}

		// checkpoint succeeds
		m_is_checkpointed = true;
		return true;
	}
	return false;

}


bool 
RocksType::checkRocksParams(VMGahpConfig* config)
{
	char *config_value = NULL;
	MyString fixedvalue;

	if( !config ) {
		return false;
	}

	// find perl program
	config_value = param("ROCKS_PERL");
	if( !config_value ) {
		vmprintf(D_ALWAYS,
		         "\nERROR: 'ROCKS_PERL' not in configuration\n");
		return false;
	}
	fixedvalue = delete_quotation_marks(config_value);
	free(config_value);
	config->m_prog_for_script = fixedvalue;

	// find script program for Rocks
	config_value = param("ROCKS_SCRIPT");
	if( !config_value ) {
		vmprintf(D_ALWAYS,
		         "\nERROR: 'ROCKS_SCRIPT' not in configuration\n");
		return false;
	}
	fixedvalue = delete_quotation_marks(config_value);
	free(config_value);

#if !defined(WIN32)
	struct stat sbuf;
	if( stat(fixedvalue.Value(), &sbuf ) < 0 ) {
		vmprintf(D_ALWAYS, "\nERROR: Failed to access the script "
				"program for Rocks:(%s:%s)\n", fixedvalue.Value(),
				strerror(errno));
		return false;
	}

	// Other writable bit
	if( sbuf.st_mode & S_IWOTH ) {
		vmprintf(D_ALWAYS, "\nFile Permission Error: "
				"other writable bit is not allowed for \"%s\" "
				"due to security issues.\n", fixedvalue.Value());
		return false;
	}

	// Other readable bit
	if( !(sbuf.st_mode & S_IROTH) ) {
		vmprintf(D_ALWAYS, "\nFile Permission Error: "
				"\"%s\" must be readable by anybody, because script program "
				"will be executed with user permission.\n", fixedvalue.Value());
		return false;
	}
#endif

	// Can read script program?
	if( check_vm_read_access_file(fixedvalue.Value()) == false ) {
		return false;
	}
	config->m_vm_script = fixedvalue;

	return true;
}

bool 
RocksType::testRocks(VMGahpConfig* config)
{
	if( !config ) {
		return false;
	}

	if( RocksType::checkRocksParams(config) == false ) {
		return false;
	}

	ArgList systemcmd;
	systemcmd.AppendArg(config->m_prog_for_script);
	systemcmd.AppendArg(config->m_vm_script);
	systemcmd.AppendArg("check");

	int result = systemCommand(systemcmd, PRIV_USER);
	if( result != 0 ) {
		vmprintf( D_ALWAYS, "Rocks script check failed:\n" );
		return false;
	}

	return true;
}

bool 
RocksType::killVM()
{
	vmprintf(D_FULLDEBUG, "Inside RocksType::killVM\n");

	if( (m_scriptname.Length() == 0) ||
			(m_configfile.Length() == 0)) {
		return false;
	}

	// If a VM is soft suspended, resume it first.
	ResumeFromSoftSuspend();

	return killVMFast(m_prog_for_script.Value(), m_scriptname.Value(), 
			m_configfile.Value());
}

bool 
RocksType::killVMFast(const char* prog_for_script, const char* script,
		const char* matchstring, bool is_root /*false*/)
{
	vmprintf(D_FULLDEBUG, "Inside RocksType::killVMFast\n");

	if( !script || (script[0] == '\0') ||
			!matchstring || (matchstring[0] == '\0') ) {
		return false;
	}

	ArgList systemcmd;
	systemcmd.AppendArg(prog_for_script);
	systemcmd.AppendArg(script);
	systemcmd.AppendArg("killvm");
	systemcmd.AppendArg(matchstring);

	int result = systemCommand(systemcmd, is_root ? PRIV_ROOT : PRIV_USER);
	if( result != 0 ) {
		return false;
	}
	return true;
}
