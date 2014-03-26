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
 *  File:			condor_vm_universe_types.h
 *  Modification: 	add attributes for rocks
 *
 *  Modified by Yuan Luo, Indiana University (yuanluo@indiana.edu)
 *  @version 0.0.1
 *  @update 03/24/14
 *  **************************************************************
*/

#ifndef CONDOR_VM_UNIVERSE_TYPES_H_INCLUDE
#define CONDOR_VM_UNIVERSE_TYPES_H_INCLUDE

#define CONDOR_VM_UNIVERSE_XEN "xen"
#define CONDOR_VM_UNIVERSE_VMWARE "vmware"
#define CONDOR_VM_UNIVERSE_KVM "kvm"
#define CONDOR_VM_UNIVERSE_ROCKS "rocks"

#define VM_CKPT_FILE_EXTENSION	".cckpt"
#define VM_AVAIL_UNLIMITED_NUM	10000

#define VM_UNIV_ARGUMENT_FILE	"condor.arg"

/* Running modes for VM GAHP Server */
#define VMGAHP_TEST_MODE 0
#define VMGAHP_IO_MODE 1		/* Deprecated */
#define VMGAHP_WORKER_MODE 2	/* Deprecated */
#define VMGAHP_STANDALONE_MODE 3
#define VMGAHP_KILL_MODE 4
#define VMGAHP_MODE_MAX 5

/* Parameters in a result of VM GAHP STATUS command  */
#define VMGAHP_STATUS_COMMAND_STATUS	"STATUS"
#define VMGAHP_STATUS_COMMAND_PID		"PID"
#define VMGAHP_STATUS_COMMAND_MAC		"MAC"
#define VMGAHP_STATUS_COMMAND_IP		"IP"
#define VMGAHP_STATUS_COMMAND_CPUTIME	"CPUTIME"
#define VMGAHP_STATUS_COMMAND_CPUUTILIZATION	"CPUUTILIZATION"

/* Parameters for Xen kernel */
#define XEN_KERNEL_INCLUDED		"included"
#define XEN_KERNEL_HW_VT		"vmx"

/* ClassAd Attributes for KVM && Xen */
#define VMPARAM_VM_DISK         "VMPARAM_vm_Disk"

/* ClassAd Attributes for Xen */
#define VMPARAM_XEN_KERNEL			"VMPARAM_Xen_Kernel"
#define VMPARAM_XEN_INITRD			"VMPARAM_Xen_Initrd"
#define VMPARAM_XEN_ROOT			"VMPARAM_Xen_Root"
#define VMPARAM_XEN_KERNEL_PARAMS	"VMPARAM_Xen_Kernel_Params"
#define VMPARAM_XEN_BOOTLOADER		"VMPARAM_Xen_Bootloader"

/* ClassAd Attributes for VMware */
#define VMPARAM_VMWARE_TRANSFER		"VMPARAM_VMware_Transfer"
#define VMPARAM_VMWARE_SNAPSHOTDISK "VMPARAM_VMware_SnapshotDisk"
#define VMPARAM_VMWARE_DIR			"VMPARAM_VMware_Dir"
#define VMPARAM_VMWARE_VMX_FILE		"VMPARAM_VMware_VMX_File"
#define VMPARAM_VMWARE_VMDK_FILES	"VMPARAM_VMware_VMDK_Files"

/* ClassAd Attributes for Rocks */
#define VMPARAM_ROCKS_TRANSFER		"VMPARAM_Rocks_Transfer"
#define VMPARAM_ROCKS_SNAPSHOTDISK	"VMPARAM_Rocks_SnapshotDisk"
#define VMPARAM_ROCKS_JOB_DIR			"VMPARAM_Rocks_Job_Dir"
#define VMPARAM_ROCKS_VMCONF_FILE	"VMPARAM_Rocks_VMCONF_File"
#define VMPARAM_ROCKS_IMG_FILES		"VMPARAM_Rocks_IMG_Files"

/* Extra ClassAd Attributes for VM */
#define VMPARAM_NO_OUTPUT_VM			"VMPARAM_No_Output_VM"
#define VMPARAM_BRIDGE_INTERFACE        "VMPARAM_Bridge_Interface"

#endif

