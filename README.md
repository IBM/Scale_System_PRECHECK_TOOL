# IBM Storage Scale System Upgrade Pre-check Tool

## Prerequisites

- Requires Python 3.10 or newer to run this tool
- The precheck tool (upgrade_precheck.py) needs to be downloaded to utilityBareMetal.
- Ensure sshpass is installed on the utilityBareMetal node.

  ```shell
  $ yum install -y sshpass
  ```

## Pre-check Tool Execution

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
