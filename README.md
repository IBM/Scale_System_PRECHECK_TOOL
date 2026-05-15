# IBM Storage Scale System Upgrade Pre-check Tool

## Overview

The upgrade_precheck tool is a standalone utility that performs comprehensive health checks on IBM Storage Scale System clusters. It can be run at any point in time to validate system health by checking critical components, configurations, and hardware health across all cluster nodes. While particularly useful before upgrades to ensure system readiness, it serves as a general health assessment tool for ongoing cluster monitoring and maintenance.

### High-Level Checks Performed

The tool executes the following health checks:

1. **GNR Health Check (gnrhealthcheck)**
   - Validates GNR health status
   - Checks for enclosure and component issues
   - Ensures hardware components are functioning properly

2. **System HAL Check (system_check)** **
   - Verifies system Hardware Abstraction Layer (HAL) health
   - Runs `/opt/ibm/ess/hal/bin/system_check -c all`
   - Validates system-level hardware components

3. **Node Type and OS Version Validation**
   - Validates node types across the cluster
   - Checks OS version compatibility (especially for s6k nodes)
   - Ensures s6k nodes are running at least RedHat 9.4

4. **Storage Quick Check (essstoragequickcheck)**
   - Runs comprehensive storage validation on IO nodes
   - Checks storage adapters, enclosures, and drives
   - Validates storage configuration and health

5. **Storage Firmware Check**
   - Verifies firmware versions on IO nodes
   - Checks enclosure firmware level
   - Uses `mmlsfirmware` command for validation

6. **Firewall Status and Port Check**
   - Validates firewall configuration on all cluster nodes
   - Checks that required ports are open for cluster communication
   - Verifies ports for SSH, GPFS, GUI, monitoring, and other services

7. **Network Verification (mmnetverify)**
   - Validates network configuration and connectivity
   - Checks communication between all cluster nodes
   - Runs `mmnetverify -N all` to verify network health

8. **Node Health Check (mmhealth)**
   - Checks overall health of all cluster nodes
   - Identifies unhealthy components (DEGRADED, FAILED, CHECKING states)
   - Runs `mmhealth node show --unhealthy -a`

### Check Results

Each check returns one of the following statuses:
- **✓ HEALTHY**: Component is functioning properly, no action required
- **⚠ WARNING**: Minor issues detected, should be addressed but not blocking
- **✗ CRITICAL**: Serious issues found, must be resolved before upgrade
- **⚠ ERROR**: Check failed to execute properly

The tool generates a comprehensive report showing:
- Summary of all checks with pass/fail status
- Detailed resolution guidance for any issues found
- Time estimates for resolving problems
- Whether the system can proceed with upgrade

## Prerequisites

- Requires Python 3.10 or newer to run this tool
- The precheck tool (upgrade_precheck.py) needs to be downloaded to utilityBareMetal.
- Ensure sshpass is installed on the utilityBareMetal node.

  ```shell
  $ yum install -y sshpass
  ```

## Pre-check Tool Execution

**Important Note:** If you have an **EMS P9** or **BYOE with RHEL 8.8**, you must run the PRECHECK tool with **python3.11** instead of the default Python version.

  ```shell
  $  chmod +x upgrade_precheck.py
  $  python3.11 upgrade_precheck.py
  ```

For other configurations, you can run the tool directly:

 ```shell
  $  chmod +x upgrade_precheck.py
  $  ./upgrade_precheck.py
  ```

## Sample Pre-check execution snippet**

```shell
$ chmod +x upgrade_precheck.py
[root@utility1-vm1 ~]# ./upgrade_precheck.py
Enter the EMS SSH hostname: ems_vm1
Enter the SSH username (default root):
Enter the SSH password (leave blank for key-based auth):

SYSTEM DETAILS
========================================================================================================================
System Information (uname -a):
Linux ems1.esstest.net 4.18.0-553.79.1.el8_10.ppc64le #1 SMP Fri Oct 3 10:59:22 EDT 2025 ppc64le ppc64le ppc64le GNU/Linux

Architecture: ppc64le
System Model: 5105-22E

------------------------------------------------------------------------------------------------------------------------
mmlscluster output:
------------------------------------------------------------------------------------------------------------------------
GPFS cluster information
========================
  GPFS cluster name:         ems1cluster.esstest.net
  GPFS cluster id:           1445326092509196240
  GPFS UID domain:           ems1cluster.esstest.net
  Remote shell command:      /usr/bin/ssh
  Remote file copy command:  /usr/bin/scp
  Repository type:           CCR

 Node  Daemon node name             IP address   Admin node name              Designation
------------------------------------------------------------------------------------------
   1   essio11-hs.esstest.net  172.0.10.51  essio11-hs.esstest.net  quorum-manager-perfmon
   2   essio12-hs.esstest.net  172.0.10.52  essio12-hs.esstest.net  quorum-manager-perfmon
   3   ems1-hs.esstest.net     172.0.10.53  ems1-hs.esstest.net     quorum-perfmon
   4   proto11-hs.esstest.net  172.0.10.54  proto11-hs.esstest.net  perfmon

========================================================================================================================
2025-11-12 01:51:17,531 - INFO - Detected system architecture: ppc64le
2025-11-12 01:51:17,691 - INFO - Detected system model: 5105-22E
2025-11-12 01:51:17,691 - INFO - Detected ESS 5000 system (ppc64le, model: 5105-22E)
2025-11-12 01:51:18,064 - INFO - Extracted 4 nodes from mmlscluster: essio11, essio12, ems1, proto11
2025-11-12 01:51:18,064 - INFO - Skipping SystemHALCheckHealthChecker for ESS 5000 system
2025-11-12 01:51:18,064 - INFO - Registered checker: ESS GNR Health (gnrhealthcheck)
2025-11-12 01:51:18,064 - INFO - Registered checker: ESS Storage Quick Check
2025-11-12 01:51:18,064 - INFO - Registered checker: ESS Network (mmnetverify)
2025-11-12 01:51:18,064 - INFO - Registered checker: ESS Node Health (mmhealth)
Starting comprehensive system health check...
================================================================================
[1/4] Checking ESS GNR Health (gnrhealthcheck)... ✗
[2/4] Checking ESS Storage Quick Check... ✓
[3/4] Checking ESS Network (mmnetverify)... ✓
[4/4] Checking ESS Node Health (mmhealth)... ✗

================================================================================
Health check completed!

========================================================================================================================
SYSTEM HEALTH CHECK REPORT
========================================================================================================================
Generated: 2025-11-12 01:52:54

SUMMARY:
  ✓ Healthy: 2    ⚠ Warning: 0    ✗ Critical: 2    ⚠ Error: 0

COMPONENT HEALTH STATUS
========================================================================================================================
COMPONENT                           STATUS       MESSAGE                                  CAN UPGRADE  TIME TO RESOLVE
------------------------------------------------------------------------------------------------------------------------
ESS GNR Health (gnrhealthcheck)     ✗ CRITICAL   gnrhealthcheck found enclosure/compon... NO           Immediate action required.
ESS Storage Quick Check             ✓ HEALTHY    All storage checks passed successfully   YES          N/A
ESS Network (mmnetverify)           ✓ HEALTHY    mmnetverify completed successfully.      NO           N/A
ESS Node Health (mmhealth)          ✗ CRITICAL   mmhealth found unhealthy components o... NO           Immediate action required.
------------------------------------------------------------------------------------------------------------------------

DETAILED RESOLUTION GUIDE
========================================================================================================================

🚨 CRITICAL ISSUES (IMMEDIATE ACTION REQUIRED)
------------------------------------------------------------
• ESS GNR Health (gnrhealthcheck)
  Problem: gnrhealthcheck found enclosure/component issues or failed.
  Solution: Check gnrhealthcheck output for enclosure/component problems and resolve hardware issues.
  Time: Immediate action required.

• ESS Node Health (mmhealth)
  Problem: mmhealth found unhealthy components or failed.
  Solution: Check mmhealth output for component issues and resolve them. (Command executed: /usr/lpp/mmfs/bin/mmhealth node show --unhealthy -a)
  Time: Immediate action required.


SYSTEM DETAILS
========================================================================================================================

Report saved to: health_report_9.11.138.22_2025-11-12_01-51-12.log
```
