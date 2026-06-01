#!/usr/bin/env python3
"""
Version: 1.0.0
"""

import getpass
import time
import subprocess
import logging
import shlex
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from enum import Enum
from datetime import datetime
import sys


class HealthStatus(Enum):
    """Health check status levels"""
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"


class ResolutionLevel(Enum):
    """Resolution difficulty levels"""
    EASY = "EASY"
    MODERATE = "MODERATE"
    ADVANCED = "ADVANCED"
    PROFESSIONAL = "PROFESSIONAL"


@dataclass
class ExecutionContext:
    """Defines where and how to execute commands"""
    context_type: str  # 'local', 'ssh'
    name: str = "local"
    host: Optional[str] = None
    port: int = 22
    username: Optional[str] = None
    password: Optional[str] = None
    key_file: Optional[str] = None
    command_prefix: Optional[str] = None


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    component: str
    status: HealthStatus
    message: str
    details: Dict[str, Any]
    resolution: str
    time_to_resolve: str
    can_upgrade: bool
    execution_context: Optional[str] = None
    upgrade_info: Optional[str] = None
    timestamp: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


# Global constants for IO node types
IO_NODE_TYPES = ["p9io", "p8io", "ess3k", "ess3200", "ess3500", "s6k"]


def get_node_type(full_node_name: str, executor: 'RemoteExecutor') -> Optional[str]:
    """
    Get the node type for a given node using essgetconfig command.
    
    Args:
        full_node_name: The full daemon node name (e.g., ess3500rw1a-hs.esstest.net)
        executor: RemoteExecutor instance to execute the command
        
    Returns:
        The node type string if found, None otherwise
    """
    try:
        cmd = f"essgetconfig -N {full_node_name}"
        result = executor.execute_command(cmd, timeout=30)
        output = result.get('stdout', '')
        
        # Parse the JSON-like output to extract nodeType
        for line in output.splitlines():
            if '"nodeType":' in line:
                # Extract the value between quotes after "nodeType":
                node_type = line.split('"nodeType":')[1].strip().strip('",')
                logging.debug("Node %s has type: %s", full_node_name, node_type)
                return node_type
                
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.warning("Failed to get node type for %s: %s", full_node_name, e)
    
    return None


def filter_io_nodes(nodes: Dict[str, str], executor: 'RemoteExecutor') -> List[str]:
    """
    Filter nodes to return only IO nodes.
    
    Args:
        nodes: Dictionary mapping short node names to full daemon node names
        executor: RemoteExecutor instance to execute commands
        
    Returns:
        List of short node names that are IO nodes
    """
    io_nodes = []
    
    for short_name, full_name in nodes.items():
        node_type = get_node_type(full_name, executor)
        if node_type and node_type in IO_NODE_TYPES:
            io_nodes.append(short_name)
            logging.debug("Node %s (%s) identified as IO node (type: %s)", short_name, full_name, node_type)
        else:
            logging.debug("Node %s (%s) is not an IO node (type: %s)", short_name, full_name, node_type)
    
    logging.info("Filtered %d IO nodes from %d total nodes", len(io_nodes), len(nodes))
    return io_nodes


class RemoteExecutor:
    """Handles remote command execution for different contexts"""

    def __init__(self, context: ExecutionContext):
        self.context = context

    def execute_command(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute command based on context"""
        try:
            if self.context.context_type == 'local':
                return self._execute_local(command, timeout)
            if self.context.context_type == 'ssh':
                return self._execute_ssh(command, timeout)
            raise ValueError(f"Unknown context type: {self.context.context_type}")
        except Exception as e:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'error': str(e)
            }

    def _execute_local(self, command: str, timeout: int) -> Dict[str, Any]:
        """Execute command locally"""
        try:
            if self.context.command_prefix:
                command = f"{self.context.command_prefix} {command}"

            result = subprocess.run(
                shlex.split(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=timeout,
                check=False
            )

            return {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'error': None
            }
        except subprocess.TimeoutExpired:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': 'Command timed out',
                'error': 'Command timed out'
            }
        except Exception as e:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'error': str(e)
            }

    def _execute_ssh(self, command: str, timeout: int) -> Dict[str, Any]:
        """Execute command via SSH"""
        if not self.context.host:
            raise ValueError("Host required for SSH execution")

        try:
            # Build SSH command
            ssh_cmd_parts = []

            # Use sshpass for password authentication, or ssh with key file
            if self.context.password:
                ssh_cmd_parts.extend(['sshpass', '-p', self.context.password])

            # Add SSH command
            ssh_cmd_parts.extend([
                'ssh',
                '-o', 'StrictHostKeyChecking=no',
                '-p', str(self.context.port)
            ])

            # Add key file if specified
            if self.context.key_file:
                ssh_cmd_parts.extend(['-i', self.context.key_file])

            # Add user@host
            ssh_cmd_parts.append(f"{self.context.username}@{self.context.host}")

            # Add the command to execute
            ssh_cmd_parts.append(command)

            # Execute the command
            result = subprocess.run(
                ssh_cmd_parts,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=timeout,
                check=False
            )

            return {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'error': None
            }

        except subprocess.TimeoutExpired:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': 'SSH command timed out',
                'error': 'SSH command timed out'
            }
        except Exception as e:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'error': str(e)
            }

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        pass


class HealthChecker:
    """Base class for health checkers"""

    def __init__(self, execution_context: Optional[ExecutionContext] = None):
        self.execution_context = execution_context or ExecutionContext(context_type='local')
        self.executor = None

    @property
    def component_name(self) -> str:
        """Name of the component being checked"""
        raise NotImplementedError("Subclasses must implement component_name")

    @property
    def description(self) -> str:
        """Description of what this checker does"""
        raise NotImplementedError("Subclasses must implement description")

    @property
    def enabled(self) -> bool:
        """Whether this checker is enabled (override to disable)"""
        return True

    def check_health(self) -> HealthCheckResult:
        """Perform the health check"""
        raise NotImplementedError("Subclasses must implement check_health")

    def _get_executor(self) -> RemoteExecutor:
        """Get or create executor for this checker"""
        if not self.executor:
            self.executor = RemoteExecutor(self.execution_context)
        return self.executor

    def _execute_command(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute command using configured executor"""
        executor = self._get_executor()
        return executor.execute_command(command, timeout)

    def _safe_execute(
        self, func, default_result: Optional[HealthCheckResult] = None
    ) -> HealthCheckResult:
        """Safely execute a function with error handling"""
        try:
            result = func()
            if result is None:
                raise ValueError("Health check function returned None")
            return result
        except Exception as e:
            logging.error("Error in health check: %s", e)
            if default_result is not None:
                return default_result
            # Return a default error result
            return HealthCheckResult(
                component="Unknown",
                status=HealthStatus.ERROR,
                message=f"Health check failed: {str(e)}",
                details={"error": str(e)},
                resolution="Check logs for details",
                time_to_resolve="Unknown",
                can_upgrade=False
            )


class ESSStorageQuickCheckHealthChecker(HealthChecker):
    """Health checker for Storage Scale System Storage Quick check."""
    def __init__(
        self,
        execution_context: Optional[ExecutionContext] = None,
        script_path="/opt/ibm/ess/tools/bin/essstoragequickcheck",
        node_list: Optional[List[str]] = None
    ):
        super().__init__(execution_context)
        self.script_path = script_path
        self.node_list = node_list or []

    @property
    def component_name(self) -> str:
        return "Storage Scale System Storage Quick Check"

    @property
    def description(self) -> str:
        return (
            f"Runs the Storage Scale System Storage Quick Check script "
            f"({self.script_path}) across all cluster nodes and parses its output."
        )

    def check_health(self) -> HealthCheckResult:
        # Build command with node list
        if self.node_list:
            node_str = ','.join(self.node_list)
            cmd = f"{self.script_path} -N {node_str}"
        else:
            cmd = self.script_path
        
        result = self._execute_command(cmd, timeout=300)  # Increased timeout for multiple nodes
        output = result.get('stdout', '')
        error = result.get('stderr', '')
        rc = result.get('returncode', -1)
        
        # Filter SSH warnings from stderr
        if error:
            filtered_err_lines = []
            for line in error.splitlines():
                # Skip SSH host key warnings
                if not ("Permanently added" in line and "to the list of known hosts" in line):
                    filtered_err_lines.append(line)
            error = '\n'.join(filtered_err_lines).strip()
        
        # Parse output for errors and warnings
        errors = []
        warnings = []
        info_lines = []
        
        for line in output.splitlines():
            # Temporary workaround to not consider non ess nodes
            if "Invalid node in the list" in line:
                    continue
            if "[ERROR]" in line:
                errors.append(line)
            elif "[WARNING]" in line or "WARNING" in line:
                warnings.append(line)
            elif "[INFO]" in line:
                info_lines.append(line)
        
        # Determine status based on findings
        if errors or "essstoragequickcheck detected error" in output:
            status = HealthStatus.CRITICAL
            message = f"Found {len(errors)} error(s) in storage check"
        elif warnings:
            status = HealthStatus.WARNING
            message = f"Found {len(warnings)} warning(s) in storage check"
        elif rc == 0 and "essstoragequickcheck passed successfully" in output:
            status = HealthStatus.HEALTHY
            message = "All storage checks passed successfully"
        else:
            status = HealthStatus.ERROR
            message = error or "Unknown error during storage check"
        
        details = {
            "stdout": output,
            "errors": errors,
            "warnings": warnings,
            "stderr": error,
            "returncode": rc,
            "command": cmd,
            "nodes_checked": self.node_list
        }
        
        # Build resolution message
        if errors:
            resolution = (
                "Critical storage issues detected. Review the following:\n"
                + "\n".join(f"  - {err}" for err in errors[:5])  # Show only first 5 errors
            )
        elif warnings:
            resolution = (
                "Storage warnings detected. Review the following:\n"
                + "\n".join(f"  - {warn}" for warn in warnings[:5])  # Show only first 5 warnings
            )
        else:
            resolution = "No action required."
        
        return HealthCheckResult(
            component=self.component_name,
            status=status,
            message=message,
            details=details,
            resolution=resolution + f"\n(Command executed: {cmd})",
            time_to_resolve="5-30 minutes" if warnings or errors else "N/A",
            can_upgrade=status == HealthStatus.HEALTHY
        )

class StorageFirmwareHealthChecker(HealthChecker):
    """Health checker for storage firmware (adapters, enclosures, drives) on IO nodes."""
    
    def __init__(
        self,
        execution_context: Optional[ExecutionContext] = None,
        node_list: Optional[List[str]] = None,
        approved_items: Optional[Dict[str, Dict[str, str]]] = None
    ):
        super().__init__(execution_context)
        self.node_list = node_list or []
        # Default approved firmware lists (can be overridden)
        self.approved_items = approved_items or {
            #"adapter": {},
            "enclosure": {},
            #"drive": {}
        }

    @property
    def component_name(self) -> str:
        return "Storage Firmware Check"

    @property
    def description(self) -> str:
        return (
            "Checks adapter, enclosure and drive firmware versions on IO nodes "
            "using mmlsfirmware command."
        )

    def check_health(self) -> HealthCheckResult:
        """Check storage firmware on all IO nodes"""
        if not self.node_list:
            return HealthCheckResult(
                component=self.component_name,
                status=HealthStatus.WARNING,
                message="No IO nodes found to check",
                details={"nodes": []},
                resolution="Ensure IO nodes are properly configured in the cluster",
                time_to_resolve="N/A",
                can_upgrade=True
            )

        all_errors = []
        all_warnings = []
        all_ok = []
        nodes_checked = []
        nodes_failed = []
        total_error_count = 0
        total_warning_count = 0

        for node in self.node_list:
            #logging.info("Checking storage firmware on node: %s", node)
            node_result = self._check_node_firmware(node)
            
            if node_result["status"] == "error":
                nodes_failed.append(node)
                all_errors.extend(node_result["errors"])
                total_error_count += node_result.get("error_count", len(node_result["errors"]))
            else:
                nodes_checked.append(node)
                all_errors.extend(node_result["errors"])
                all_warnings.extend(node_result["warnings"])
                all_ok.extend(node_result["ok"])
                total_error_count += node_result.get("error_count", 0)
                total_warning_count += node_result.get("warning_count", 0)

        # Determine overall status
        if all_errors:
            status = HealthStatus.CRITICAL
            message = f"Found {total_error_count} firmware error(s) across {len(nodes_checked)} node(s)"
            can_upgrade = False
        elif all_warnings:
            status = HealthStatus.WARNING
            message = f"Found {total_warning_count} firmware warning(s) across {len(nodes_checked)} node(s)"
            can_upgrade = True
        elif nodes_checked:
            status = HealthStatus.HEALTHY
            message = f"All storage firmware checks passed on {len(nodes_checked)} node(s)"
            can_upgrade = True
        else:
            status = HealthStatus.ERROR
            message = f"Failed to check firmware on all {len(nodes_failed)} node(s)"
            can_upgrade = False

        details = {
            "nodes_checked": nodes_checked,
            "nodes_failed": nodes_failed,
            "total_errors": total_error_count,
            "total_warnings": total_warning_count,
            "errors": all_errors[:10],  # Limit to first 10
            "warnings": all_warnings[:10],  # Limit to first 10
            "ok_items": all_ok[:10]  # Limit to first 10
        }

        # Build resolution message with firmware information
        resolution_parts = []
        
        if all_errors:
            resolution_parts.append("Critical firmware issues detected:")
            resolution_parts.extend(f"  - {err}" for err in all_errors)
            resolution_parts.append("\nUpdate firmware to approved versions before upgrade.")
        
        if all_warnings:
            if resolution_parts:
                resolution_parts.append("")
            resolution_parts.append("Firmware warnings detected:")
            resolution_parts.extend(f"  - {warn}" for warn in all_warnings)
            resolution_parts.append("\nReview and consider updating firmware.")
        
        if not resolution_parts:
            resolution = "No firmware information available."
        else:
            resolution = "\n".join(resolution_parts)

        return HealthCheckResult(
            component=self.component_name,
            status=status,
            message=message,
            details=details,
            resolution=resolution,
            time_to_resolve="30-120 minutes" if all_errors or all_warnings else "N/A",
            can_upgrade=can_upgrade
        )

    def _check_node_firmware(self, node: str) -> Dict[str, Any]:
        """Check firmware on a single node"""
        errors = []
        warnings = []
        ok_items = []
        error_count = 0
        warning_count = 0
        
        # Create a node-specific execution context to run command locally on the node
        node_context = ExecutionContext(
            context_type='ssh',
            name=node,
            host=node,
            port=self.execution_context.port if self.execution_context else 22,
            username=self.execution_context.username if self.execution_context else None,
            password=self.execution_context.password if self.execution_context else None,
            key_file=self.execution_context.key_file if self.execution_context else None
        )
        
        # Build mmlsfirmware command - run locally on the node (no -N option)
        cmd = "/usr/lpp/mmfs/bin/mmlsfirmware --type storage-enclosure -Y"
        
        # Execute command on the specific node
        node_executor = RemoteExecutor(node_context)
        result = node_executor.execute_command(cmd, timeout=120)
        rc = result.get('returncode', -1)
        output = result.get('stdout', '')
        stderr = result.get('stderr', '')
        
        if rc != 0:
            error_msg = f"Node {node}: Failed to run mmlsfirmware (rc={rc})"
            if stderr:
                error_msg += f" - {stderr}"
            return {
                "status": "error",
                "errors": [error_msg],
                "warnings": [],
                "ok": [],
                "error_count": 1,
                "warning_count": 0
            }
        
        # Collect unique items with their firmware info and count
        # Key: (item_type, item_name, item_fw, expected_fw)
        # Value: count
        unique_items = {}
        
        # Parse mmlsfirmware output
        for line in output.splitlines():
            line = line.strip()
            if not line or "HEADER" in line:
                continue
            
            # Parse YAML-like output from mmlsfirmware -Y
            parts = line.split(":")
            if len(parts) < 11:
                continue
            
            item_type = None
            #if "adapter" in line:
            #    item_type = "adapter"
            if "enclosure" in line and "drive" not in line:
                item_type = "enclosure"
            #elif "drive" in line:
            #    item_type = "drive"
            
            if not item_type:
                continue
            
            try:
                item_name = parts[6].strip()
                item_fw = parts[8].strip().replace('cli=', '')
                available_fw = parts[10].strip().replace('cli=', '').lstrip('*')
                
                # Handle URL-encoded characters in enclosure names
                if item_type == "enclosure" and "%" in item_name:
                    item_name = item_name.replace("%2D", "-").replace("%2d", "-")
                
                # Create unique key for this item
                item_key = (item_type, item_name, item_fw, available_fw)
                unique_items[item_key] = unique_items.get(item_key, 0) + 1
                
            except (IndexError, ValueError) as e:
                logging.warning("Failed to parse firmware line: %s - %s", line, e)
                continue
        
        # Now process unique items and generate messages
        for (item_type, item_name, item_fw, available_fw), count in unique_items.items():
            # Compare installed firmware against available firmware from mmlsfirmware
            if available_fw:
                expected_fw = available_fw
                
                # Special handling for enclosures (may have dual firmware)
                if item_type == "enclosure" and "," in item_fw:
                    current_levels = [fw.strip() for fw in item_fw.split(",") if fw.strip()]
                    if current_levels and all(fw == expected_fw for fw in current_levels):
                        ok_items.append(
                            f"Node {node}: OK: {item_type.capitalize()} {item_name} firmware: "
                            f"found {item_fw} expected {expected_fw}, {item_type} count: {count}"
                        )
                    else:
                        errors.append(
                            f"Node {node}: ERROR: {item_type.capitalize()} {item_name} firmware: "
                            f"found {item_fw} expected {expected_fw}, {item_type} count: {count}"
                        )
                        error_count += count
                else:
                    if item_fw == expected_fw:
                        ok_items.append(
                            f"Node {node}: OK: {item_type.capitalize()} {item_name} firmware: "
                            f"found {item_fw} expected {expected_fw}, {item_type} count: {count}"
                        )
                    else:
                        errors.append(
                            f"Node {node}: ERROR: {item_type.capitalize()} {item_name} firmware: "
                            f"found {item_fw} expected {expected_fw}, {item_type} count: {count}"
                        )
                        error_count += count
            else:
                ok_items.append(
                    f"Node {node}: OK: {item_type.capitalize()} {item_name} firmware: "
                    f"found {item_fw}, {item_type} count: {count}"
                )
        
        return {
            "status": "ok",
            "errors": errors,
            "warnings": warnings,
            "ok": ok_items,
            "error_count": error_count,
            "warning_count": warning_count
        }



class MMNetVerifyHealthChecker(HealthChecker):
    """Health checker for mmnetverify network verification."""

    def __init__(self, execution_context: Optional[ExecutionContext] = None):
        # Always use SSH context unless explicitly overridden
        if execution_context is None:
            execution_context = ExecutionContext(context_type='ssh')
        super().__init__(execution_context)

    @property
    def component_name(self) -> str:
        return "Storage Scale System Network (mmnetverify)"

    @property
    def description(self) -> str:
        return "Checks network configuration and communication using mmnetverify."

    def check_health(self) -> HealthCheckResult:
        return self._safe_execute(self._check_mmnetverify)

    def _check_mmnetverify(self) -> HealthCheckResult:
        mmnetverify_path = "/usr/lpp/mmfs/bin/mmnetverify"
        cmd = f"{mmnetverify_path} -N all"
        result = self._execute_command(command=cmd, timeout=60)
        output = result.get('stdout', '')
        error = result.get('stderr', '')
        rc = result.get('returncode', -1)
        details = {"stdout": output, "stderr": error, "returncode": rc}

        # Parse output for issues
        issues = []
        status = HealthStatus.HEALTHY
        message = "mmnetverify completed successfully."
        resolution = "No action required."
        time_to_resolve = "N/A"

        if (rc != 0 or "Issues Found:" in output or
                "Command failed" in output):
            status = HealthStatus.CRITICAL
            message = "mmnetverify found network issues or failed."
            resolution = (
                "Check mmnetverify output for details. "
                "Ensure all nodes are reachable and services are running."
            )
            time_to_resolve = "Immediate action required."
        elif "Fail" in output or "failed" in output:
            status = HealthStatus.WARNING
            message = "mmnetverify reported some failures."
            resolution = "Review mmnetverify output and address reported failures."
            time_to_resolve = "As soon as possible."

        # Optionally, extract specific issues
        for line in output.splitlines():
            if "Fail" in line or "failed" in line or "Error" in line:
                issues.append(line)
        if issues:
            details["issues"] = issues

        return HealthCheckResult(
            component=self.component_name,
            status=status,
            message=message,
            details=details,
            resolution=resolution,
            time_to_resolve=time_to_resolve,
            can_upgrade=False
        )


class GNRHealthChecker(HealthChecker):
    """Health checker for GNR (General Node Recovery) using gnrhealthcheck."""
    def __init__(self, execution_context: Optional[ExecutionContext] = None):
        # Always use ssh context unless explicitly overridden
        if execution_context is None:
            execution_context = ExecutionContext(context_type='ssh')
        super().__init__(execution_context)

    @property
    def component_name(self) -> str:
        return "Storage Scale System GNR Health (gnrhealthcheck)"

    @property
    def description(self) -> str:
        return "Checks GNR health using gnrhealthcheck."

    def check_health(self) -> HealthCheckResult:
        return self._safe_execute(self._check_gnrhealth)

    def _check_gnrhealth(self) -> HealthCheckResult:  # pylint: disable=too-many-locals
        gnrhealth_path = "/usr/lpp/mmfs/bin/gnrhealthcheck"
        result = self._execute_command(gnrhealth_path, timeout=600)
        output = result.get('stdout', '')
        error = result.get('stderr', '')
        rc = result.get('returncode', -1)
        details = {"stdout": output, "stderr": error, "returncode": rc}

        # Parse output for enclosure/component problems
        status = HealthStatus.HEALTHY
        message = "gnrhealthcheck completed successfully."
        resolution = "No action required."
        time_to_resolve = "N/A"
        issues = []
        enclosure_problem = False
        component_problems = []

        for line in output.splitlines():
            if "Found enclosure problems." in line:
                enclosure_problem = True
                issues.append(line)
            line_starts = (
                line.strip().startswith("dimm") or
                line.strip().startswith("esm") or
                line.strip().startswith("fan") or
                line.strip().startswith("tempSensor")
            )
            line_contains = "ABSENT" in line or "NOTAVAIL" in line
            if line_starts and line_contains:
                component_problems.append(line)
            if any(word in line for word in ["ERROR", "Error", "FAILED", "Fail"]):
                issues.append(line)
            if "WARNING" in line or "Warning" in line:
                issues.append(line)

        error_keywords = ["ERROR", "Error", "FAILED", "Fail"]
        has_errors = any(w in output for w in error_keywords)
        if enclosure_problem or component_problems or rc != 0 or has_errors:
            status = HealthStatus.CRITICAL
            message = "gnrhealthcheck found enclosure/component issues or failed."
            resolution = (
                "Check gnrhealthcheck output for enclosure/component "
                "problems and resolve hardware issues."
            )
            time_to_resolve = "Immediate action required."
        elif any(w in output for w in ["WARNING", "Warning"]):
            status = HealthStatus.WARNING
            message = "gnrhealthcheck reported warnings."
            resolution = "Review gnrhealthcheck output and address reported warnings."
            time_to_resolve = "As soon as possible."

        if issues:
            details["issues"] = issues
        if component_problems:
            details["component_problems"] = component_problems

        return HealthCheckResult(
            component=self.component_name,
            status=status,
            message=message,
            details=details,
            resolution=resolution,
            time_to_resolve=time_to_resolve,
            can_upgrade=False
        )


class MMHealthChecker(HealthChecker):
    """Health checker for Storage Scale System nodes."""
    def __init__(self, execution_context: Optional[ExecutionContext] = None):
        # Default using ssh unless specified
        if execution_context is None:
            execution_context = ExecutionContext(context_type='ssh')
        super().__init__(execution_context)

    @property
    def component_name(self) -> str:
        return "Storage Scale System Node Health (mmhealth)"

    @property
    def description(self) -> str:
        return "Checks node health using mmhealth (executed in VM)."

    def check_health(self) -> HealthCheckResult:
        return self._safe_execute(self._check_mmhealth)

    def _check_mmhealth(self) -> HealthCheckResult:  # pylint: disable=too-many-locals
        mmhealth_path = "/usr/lpp/mmfs/bin/mmhealth"
        cmd = f"{mmhealth_path} node show --unhealthy -a"
        result = self._execute_command(cmd, timeout=60)
        output = result.get('stdout', '')
        error = result.get('stderr', '')
        rc = result.get('returncode', -1)
        details = {"stdout": output, "stderr": error, "returncode": rc, "command": cmd}

        # Parse output for unhealthy states and extract component details
        status = HealthStatus.HEALTHY
        message = "All nodes healthy."
        resolution = "No action required."
        time_to_resolve = "N/A"
        issues = []
        unhealthy_components = []
        unhealthy_keywords = ["DEGRADED", "CHECKING", "FAILED", "DEPEND"]
        in_table = False
        for line in output.splitlines():
            if line.strip().startswith("Component") and "Status" in line:
                in_table = True
                continue
            if in_table and line.strip() and not line.startswith("-"):
                # Example: GUI DEGRADED 1 day ago
                # time_not_in_sync(utility1-vm1-hs.gpfs.local),
                # gui_refresh_task_failed
                parts = line.split()
                if len(parts) >= 4:
                    component = parts[0]
                    comp_status = parts[1]
                    # The rest is status change and reasons
                    reasons = " ".join(parts[3:])
                    if comp_status in unhealthy_keywords:
                        unhealthy_components.append({
                            "component": component,
                            "status": comp_status,
                            "reasons": reasons.strip()
                        })
                        issues.append(f"{component}: {comp_status} - {reasons.strip()}")
            if not line.strip():
                in_table = False
        if rc != 0 or unhealthy_components:
            status = HealthStatus.CRITICAL
            message = "mmhealth found unhealthy components or failed."
            resolution = "Check mmhealth output for component issues and resolve them."
            time_to_resolve = "Immediate action required."
        if unhealthy_components:
            details["unhealthy_components"] = unhealthy_components
        if issues:
            details["issues"] = issues
        return HealthCheckResult(
            component=self.component_name,
            status=status,
            message=message,
            details=details,
            resolution=resolution + f" (Command executed: {cmd})",
            time_to_resolve=time_to_resolve,
            can_upgrade=False
        )


class SystemHALCheckHealthChecker(HealthChecker):
    """Health checker for system HAL using system_check."""
    def __init__(self, execution_context: Optional[ExecutionContext] = None):
        # Always use ssh context unless explicitly overridden
        if execution_context is None:
            execution_context = ExecutionContext(context_type='ssh')
        super().__init__(execution_context)

    @property
    def component_name(self) -> str:
        return "Storage Scale System HAL Check (system_check)"

    @property
    def description(self) -> str:
        return (
            "Checks system health using "
            "/opt/ibm/ess/hal/bin/system_check -c all (executed in VM)."
        )

    def check_health(self) -> HealthCheckResult:
        return self._safe_execute(self._check_systemhal)

    def _check_systemhal(self) -> HealthCheckResult:
        system_check_path = "/opt/ibm/ess/hal/bin/system_check"
        cmd = f"{system_check_path} -c all"
        result = self._execute_command(cmd, timeout=120)
        output = result.get('stdout', '')
        error = result.get('stderr', '')
        rc = result.get('returncode', -1)
        details = {"stdout": output, "stderr": error, "returncode": rc}

        # Parse output for errors or failures
        status = HealthStatus.HEALTHY
        message = "system_check completed successfully."
        resolution = "No action required."
        time_to_resolve = "N/A"
        issues = []
        for line in output.splitlines():
            if any(word in line for word in ["ERROR", "Error", "FAILED", "Fail"]):
                issues.append(line)
        if rc != 0 or issues:
            status = HealthStatus.CRITICAL
            message = "system_check found errors or failed."
            resolution = "Check system_check output for details and resolve reported errors."
            time_to_resolve = "Immediate action required."
        if issues:
            details["issues"] = issues
        return HealthCheckResult(
            component=self.component_name,
            status=status,
            message=message,
            details=details,
            resolution=resolution,
            time_to_resolve=time_to_resolve,
            can_upgrade=False
        )

class NodeTypeVersionHealthChecker(HealthChecker):
    """Check node type and OS version compatibility for s6k nodes"""

    def __init__(self, execution_context: ExecutionContext, cluster_nodes: Optional[Dict[str, str]] = None):
        super().__init__(execution_context)
        self.cluster_nodes = cluster_nodes or {}

    @property
    def component_name(self) -> str:
        return "Node Type and OS Version Validation"

    @property
    def description(self) -> str:
        return (
            "Validates that s6k nodes are running compatible RedHat versions. "
            "s6k nodes must be running at least RedHat 9.4 for upgrade compatibility."
        )

    def check_health(self) -> HealthCheckResult:
        """Check node type and OS version compatibility"""
        return self._safe_execute(self._check_node_compatibility)

    def _check_node_compatibility(self) -> HealthCheckResult:
        """Validate s6k nodes are running compatible OS versions"""
        executor = self._get_executor()
        incompatible_nodes = []
        details = {}
        
        try:
            # Use the cluster_nodes passed during initialization
            if not self.cluster_nodes:
                return HealthCheckResult(
                    component=self.component_name,
                    status=HealthStatus.ERROR,
                    message="No cluster nodes provided for validation",
                    details={"error": "cluster_nodes is empty"},
                    resolution="Ensure cluster nodes are properly detected",
                    time_to_resolve="5 minutes",
                    can_upgrade=False,
                    execution_context=self.execution_context.name
                )
            
            # Check each node
            for short_name, full_name in self.cluster_nodes.items():
                # Get node type
                node_type = get_node_type(full_name, executor)
                
                if node_type == "s6k":
                    # Check RedHat version for s6k nodes
                    try:
                        # Get OS release info
                        os_result = executor.execute_command(
                            "cat /etc/redhat-release",
                            timeout=10
                        )
                        os_info = os_result.get('stdout', '').strip()
                        
                        # Extract version number (e.g., "9.2" from "Red Hat Enterprise Linux release 9.2")
                        version = None
                        major_version = None
                        
                        if "release" in os_info:
                            version_part = os_info.split("release")[1].strip().split()[0]
                            version = version_part
                            major_version = version.split('.')[0]
                        
                        details[short_name] = {
                            "node_type": node_type,
                            "os_info": os_info,
                            "version": version,
                            "major_version": major_version
                        }
                        
                        # Check if it's RedHat 9.2 (incompatible version)
                        if major_version == "9" and version == "9.2":
                            incompatible_nodes.append({
                                "node": short_name,
                                "node_type": node_type,
                                "version": version,
                                "os_info": os_info
                            })
                            logging.warning(
                                "Node %s (type: %s) is running incompatible RedHat version %s",
                                short_name, node_type, version
                            )
                        else:
                            logging.debug(
                                "Node %s (type: %s) is running compatible RedHat version %s",
                                short_name, node_type, version
                            )
                    
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        logging.error("Failed to check OS version for node %s: %s", short_name, e)
                        details[short_name] = {
                            "node_type": node_type,
                            "error": str(e)
                        }
            
            # Generate result based on findings
            if incompatible_nodes:
                node_list = "\n".join([
                    f"  - Node: {n['node']}, Type: {n['node_type']}, "
                    f"RedHat Version: {n['version']}"
                    for n in incompatible_nodes
                ])
                
                flash_link = "https://www.ibm.com/support/pages/node/7266332"
                
                return HealthCheckResult(
                    component=self.component_name,
                    status=HealthStatus.CRITICAL,
                    message=(
                        f"Cannot perform this update. Detected {len(incompatible_nodes)} "
                        f"s6k node(s) running incompatible RedHat version 9.2.\n"
                        f"Incompatible nodes:\n{node_list}\n\n"
                        f"⚠️  WARNING ISSUES (MONITOR AND PLAN)\n"
                        f"It is not supported to upgrade from IBM Storage Scale System "
                        f"6.1.9.4, 6.2.0.x, and 6.2.1.x (which run Red Hat Enterprise Linux 9.2) to "
                        f"IBM Storage Scale System 6.2.3.3, 6.2.3.4, 7.0.0.0, and 7.0.0.1 (which run "
                        f"RHEL 9.6). If you have an IBM Storage Scale System 6000 building-block in "
                        f"the cluster with an affected release, (including unaffected nodes such as "
                        f"IBM Storage Scale System 5000) you must perform an intermediate "
                        f"upgrade, which is listed in the upgrade support matrix table.\n\n"
                        f"Any Utility Node running Red Hat Enterprise Linux 9.2 is also impacted.\n\n"
                        f"For more information about this restriction, see:\n"
                        f"Nodes may kernel panic during OS upgrade from RHEL 9.2 to RHEL 9.6\n"
                        f"{flash_link}"
                    ),
                    details={
                        "incompatible_nodes": incompatible_nodes,
                        "all_nodes_checked": details,
                        "flash_link": flash_link
                    },
                    resolution=(
                        "Upgrade all s6k nodes to RedHat 9.4 or later before proceeding "
                        "with the system update. Contact IBM support for assistance."
                    ),
                    time_to_resolve="2-4 hours (OS upgrade required)",
                    can_upgrade=False,
                    execution_context=self.execution_context.name
                )
            
            # All s6k nodes are compatible or no s6k nodes found
            return HealthCheckResult(
                component=self.component_name,
                status=HealthStatus.HEALTHY,
                message="",
                details={"nodes_checked": details},
                resolution="No action required",
                time_to_resolve="N/A",
                can_upgrade=True,
                execution_context=self.execution_context.name
            )
        
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Error checking node compatibility: %s", e)
            return HealthCheckResult(
                component=self.component_name,
                status=HealthStatus.ERROR,
                message=f"Failed to check node compatibility: {str(e)}",
                details={"error": str(e)},
                resolution="Check system logs and ensure mmlscluster command is available",
                time_to_resolve="5-10 minutes",
                can_upgrade=False,
                execution_context=self.execution_context.name
            )


class FirewallHealthChecker(HealthChecker):
    """Health checker for firewall status and required ports on cluster nodes."""
    
    # Common ports required for IBM Spectrum Scale/Storage Scale System
    # Format: (port_or_range, protocol, description)
    # port_or_range can be an integer or a string like "8123-8127"
    REQUIRED_PORTS = [
        # TCP ports
        (22, 'tcp', 'Secure Shell (SSH)'),
        (873, 'tcp', 'rsync port'),
        (1191, 'tcp', 'GPFS daemon and CCR intra‑cluster communication'),
        (4739, 'tcp', 'Zimon'),
        (51001, 'tcp', 'Cross HAL communication'),
        (50052, 'tcp', 'gRPC (Native Rest API)'),
        (46443, 'tcp', 'Native REST API (HTTPS)'),
        (5353, 'tcp', 'mDNS (HAL)'),
        (10080, 'tcp', 'Installation toolkit (http repository)'),
        (20080, 'tcp', 'Storage Scale System repository'),
        (9085, 'tcp', 'Performance monitoring'),
        (9980, 'tcp', 'Performance monitoring'),
        (80, 'tcp', 'HTTP (GUI)'),
        (443, 'tcp', 'HTTPS (GUI)'),
        (4444, 'tcp', 'GUI (localhost)'),
        (657, 'tcp', 'HMC communication'),
        ('60000-61000', 'tcp', 'GPFS ephemeral port range'),
        (9981, 'tcp', 'Performance monitoring collector'),
        (40443, 'tcp', 'GUI'),
        (51000, 'tcp', 'INTERLINK'),
        # UDP ports
        (5353, 'udp', 'mDNS (HAL)'),
        (123, 'udp', 'NTP'),
        (657, 'udp', 'HMC communication'),
        (67, 'udp', 'DHCP'),
        (623, 'udp', 'IPMI'),
    ]
    
    # Ports that should be closed for security (not required for IBM Storage Scale System)
    # These ports are commonly found open but are not in REQUIRED_PORTS
    # Format: (port_or_range, protocol, description)
    CLOSED_PORTS = [
        # TCP ports that can be closed
        (8889, 'tcp', 'Unnecessary port - can be closed'),
        (123, 'tcp', 'NTP TCP (only UDP needed) - can be closed'),
        (8080, 'tcp', 'Alternative HTTP - can be closed'),
        (35357, 'tcp', 'OpenStack Keystone admin - can be closed'),
        (5000, 'tcp', 'OpenStack Keystone - can be closed'),
        (5431, 'tcp', 'PostgreSQL alternative - can be closed'),
        ('6200-6203', 'tcp', 'Unnecessary port range - can be closed'),
        (11211, 'tcp', 'Memcached - can be closed'),
        ('8123-8127', 'tcp', 'Unnecessary port range - can be closed'),
        (9094, 'tcp', 'Unnecessary port - can be closed'),
        (8085, 'tcp', 'Unnecessary port - can be closed'),
        (1500, 'tcp', 'Unnecessary port - can be closed'),
        (5024, 'tcp', 'Unnecessary port - can be closed'),
        (3001, 'tcp', 'Unnecessary port - can be closed'),
        (3002, 'tcp', 'Unnecessary port - can be closed'),
        (67, 'tcp', 'DHCP TCP (only UDP needed) - can be closed'),
        (68, 'tcp', 'DHCP client - can be closed'),
        (69, 'tcp', 'TFTP TCP - can be closed'),
        (514, 'tcp', 'Syslog TCP - can be closed'),
        (782, 'tcp', 'Unnecessary port - can be closed'),
        (4011, 'tcp', 'PXE boot - can be closed'),
        (623, 'tcp', 'IPMI TCP (only UDP needed) - can be closed'),
        (162, 'tcp', 'SNMP trap - can be closed'),
        # UDP ports that can be closed
        (22, 'udp', 'SSH UDP (only TCP needed) - can be closed'),
        (5431, 'udp', 'PostgreSQL alternative UDP - can be closed'),
        (11211, 'udp', 'Memcached UDP - can be closed'),
        (80, 'udp', 'HTTP UDP (only TCP needed) - can be closed'),
        (4739, 'udp', 'Zimon UDP (only TCP needed) - can be closed'),
        (20080, 'udp', 'Repository UDP (only TCP needed) - can be closed'),
        (10080, 'udp', 'Installation toolkit UDP (only TCP needed) - can be closed'),
        (3001, 'udp', 'Unnecessary port - can be closed'),
        (3002, 'udp', 'Unnecessary port - can be closed'),
        (873, 'udp', 'rsync UDP (only TCP needed) - can be closed'),
        (69, 'udp', 'TFTP - can be closed'),
        (514, 'udp', 'Syslog UDP - can be closed'),
        (162, 'udp', 'SNMP trap UDP - can be closed'),
        (7, 'udp', 'Echo service - can be closed'),
    ]
    
    @staticmethod
    def _expand_port_range(port_or_range):
        """Expand port range string to list of individual ports.
        
        Args:
            port_or_range: Either an integer port or a string like "8123-8127"
            
        Returns:
            List of individual port numbers
        """
        if isinstance(port_or_range, int):
            return [port_or_range]
        elif isinstance(port_or_range, str) and '-' in port_or_range:
            start, end = map(int, port_or_range.split('-'))
            return list(range(start, end + 1))
        else:
            return [int(port_or_range)]
    
    def __init__(self, execution_context: Optional[ExecutionContext] = None, node_list: Optional[List[str]] = None):
        # Always use ssh context unless explicitly overridden
        if execution_context is None:
            execution_context = ExecutionContext(context_type='ssh')
        super().__init__(execution_context)
        self.node_list = node_list or []

    @property
    def component_name(self) -> str:
        return "Firewall Status and Port Check"

    @property
    def description(self) -> str:
        return (
            "Checks if firewall is running on cluster nodes and verifies "
            "that required ports are open for IBM Storage System operation."
        )

    def check_health(self) -> HealthCheckResult:
        return self._safe_execute(self._check_firewall)

    def _check_firewall(self) -> HealthCheckResult:
        """Check firewall status and port availability on all cluster nodes."""
        all_results = {}
        overall_status = HealthStatus.HEALTHY
        issues = []
        warnings = []
        
        # If no nodes specified, check local node only
        nodes_to_check = self.node_list if self.node_list else ["localhost"]
        
        for node in nodes_to_check:
            node_results = {
                "firewall_running": False,
                "firewall_service": "unknown",
                "closed_ports": [],
                "open_ports": [],
                "unnecessary_open_ports": [],
                "check_errors": []
            }
            
            # Check firewall status
            firewall_status = self._check_firewall_status(node)
            node_results["firewall_running"] = firewall_status["running"]
            node_results["firewall_service"] = firewall_status["service"]
            
            if firewall_status.get("error"):
                node_results["check_errors"].append(firewall_status["error"])
            
            # If firewall is running, check ports
            if node_results["firewall_running"]:
                port_results = self._check_ports(node, firewall_status["service"])
                node_results["closed_ports"] = port_results["closed"]
                node_results["open_ports"] = port_results["open"]
                
                if port_results.get("error"):
                    node_results["check_errors"].append(port_results["error"])
                
                # Check for unnecessary open ports
                unnecessary_results = self._check_unnecessary_ports(node, firewall_status["service"])
                node_results["unnecessary_open_ports"] = unnecessary_results["unnecessary_open"]
                
                if unnecessary_results.get("error"):
                    node_results["check_errors"].append(unnecessary_results["error"])
                
                # Add warnings for unnecessary open ports
                if node_results["unnecessary_open_ports"]:
                    for port_info in node_results["unnecessary_open_ports"]:
                        warnings.append(
                            f"Node {node}: Unnecessary port {port_info['port']} is open - {port_info['description']}. "
                            f"To close: {port_info['close_command']}"
                        )
                
                # Analyze results for this node
                if node_results["closed_ports"]:
                    overall_status = HealthStatus.CRITICAL
                    issues.append(
                        f"Node {node}: Firewall is blocking required ports: "
                        f"{', '.join(map(str, node_results['closed_ports']))}"
                    )
            else:
                # Firewall not running - this could be intentional
                warnings.append(
                    f"Node {node}: Firewall service ({firewall_status['service']}) is not running. "
                    "This may be intentional in some environments."
                )
            
            all_results[node] = node_results
        
        # Determine overall status and message
        if overall_status == HealthStatus.CRITICAL:
            # Extract node names from issues
            affected_nodes = [node for node in all_results.keys() if all_results[node]["closed_ports"]]
            nodes_str = ", ".join(affected_nodes)
            
            # Collect all unique closed ports across all nodes
            all_closed_ports = set()
            for node in affected_nodes:
                all_closed_ports.update(all_results[node]["closed_ports"])
            
            # Sort and format closed ports for display
            closed_ports_list = sorted(all_closed_ports)
            ports_display = ", ".join(closed_ports_list)
            
            message = f"Firewall is blocking required ports on {len(issues)} node(s): {nodes_str}"
            resolution = (
                f"Open the required ports in the firewall configuration on nodes: {nodes_str}. "
                "Use 'essrun firewall enable' command to open all required ports. "
                f"Blocked ports that need to be opened: {ports_display}"
            )
            time_to_resolve = "15-30 minutes"
            can_upgrade = False
        elif warnings:
            # Check if warnings are about unnecessary ports or firewall not running
            # Only include nodes with unnecessary ports if firewall is actually running
            nodes_with_unnecessary_ports = [node for node in all_results.keys()
                                           if all_results[node]["firewall_running"]
                                           and all_results[node].get("unnecessary_open_ports")]
            nodes_without_firewall = [node for node in all_results.keys()
                                     if not all_results[node]["firewall_running"]]
            
            if overall_status != HealthStatus.WARNING:
                overall_status = HealthStatus.WARNING
            
            if nodes_with_unnecessary_ports and nodes_without_firewall:
                message = (f"Firewall is not running on {len(nodes_without_firewall)} node(s) and "
                          f"{len(nodes_with_unnecessary_ports)} node(s) have unnecessary open ports")
            elif nodes_with_unnecessary_ports:
                nodes_str = ", ".join(nodes_with_unnecessary_ports)
                message = f"Found unnecessary open ports on {len(nodes_with_unnecessary_ports)} node(s): {nodes_str}"
            else:
                nodes_str = ", ".join(nodes_without_firewall)
                message = f"Firewall is not running on {len(nodes_without_firewall)} node(s): {nodes_str}"
            
            resolution = "Review warnings for details. Close unnecessary ports using the provided firewall-cmd commands."
            time_to_resolve = "5-10 minutes"
            can_upgrade = True
        else:
            message = "Firewall configuration is correct on all nodes."
            resolution = "No action required."
            time_to_resolve = "N/A"
            can_upgrade = True
        
        details = {
            "nodes_checked": len(nodes_to_check),
            "node_results": all_results,
            "required_ports": self.REQUIRED_PORTS,
            "closed_ports_list": self.CLOSED_PORTS,
            "issues": issues,
            "warnings": warnings
        }
        
        return HealthCheckResult(
            component=self.component_name,
            status=overall_status,
            message=message,
            details=details,
            resolution=resolution,
            time_to_resolve=time_to_resolve,
            can_upgrade=can_upgrade,
            execution_context=self.execution_context.name
        )
    
    def _check_firewall_status(self, node: str) -> Dict[str, Any]:
        """Check if firewall is running on a specific node."""
        result = {
            "running": False,
            "service": "unknown",
            "error": None
        }
        
        # Build command based on node
        if node == "localhost":
            cmd_prefix = ""
        else:
            cmd_prefix = f"ssh -o StrictHostKeyChecking=no {node} "
        
        # Check for firewalld first (RHEL 7+)
        cmd = f"{cmd_prefix}systemctl is-active firewalld"
        check_result = self._execute_command(cmd, timeout=10)
        
        if check_result.get('returncode') == 0 and 'active' in check_result.get('stdout', '').lower():
            result["running"] = True
            result["service"] = "firewalld"
            return result
        
        # Check for iptables
        cmd = f"{cmd_prefix}systemctl is-active iptables"
        check_result = self._execute_command(cmd, timeout=10)
        
        if check_result.get('returncode') == 0 and 'active' in check_result.get('stdout', '').lower():
            result["running"] = True
            result["service"] = "iptables"
            return result
        
        # Check for ufw (Ubuntu/Debian)
        cmd = f"{cmd_prefix}systemctl is-active ufw"
        check_result = self._execute_command(cmd, timeout=10)
        
        if check_result.get('returncode') == 0 and 'active' in check_result.get('stdout', '').lower():
            result["running"] = True
            result["service"] = "ufw"
            return result
        
        # If none are active, firewall is not running
        result["service"] = "none"
        return result
    
    def _check_unnecessary_ports(self, node: str, firewall_service: str) -> Dict[str, Any]:
        """Check if any unnecessary ports (from CLOSED_PORTS) are open in the firewall."""
        result = {
            "unnecessary_open": [],
            "error": None
        }
        
        # Build command prefix based on node
        if node == "localhost":
            cmd_prefix = ""
        else:
            cmd_prefix = f"ssh -o StrictHostKeyChecking=no {node} "
        
        if firewall_service == "firewalld":
            # Check firewalld rules
            cmd = f"{cmd_prefix}firewall-cmd --list-ports"
            check_result = self._execute_command(cmd, timeout=15)
            
            if check_result.get('returncode') != 0:
                result["error"] = f"Failed to query firewalld: {check_result.get('stderr', '')}"
                return result
            
            open_ports_output = check_result.get('stdout', '')
            
            # Parse open ports (format: "1191/tcp 60000/udp 32767-32769/tcp ...")
            open_ports = set()
            for port_entry in open_ports_output.split():
                if '/' in port_entry:
                    try:
                        port_part, protocol = port_entry.split('/')
                        # Expand port ranges in firewall output
                        ports = self._expand_port_range(port_part)
                        for port_num in ports:
                            open_ports.add((port_num, protocol))
                    except ValueError:
                        pass
            
            # Check each port in CLOSED_PORTS to see if it's unnecessarily open
            for port_or_range, protocol, desc in self.CLOSED_PORTS:
                ports_to_check = self._expand_port_range(port_or_range)
                for port_num in ports_to_check:
                    if (port_num, protocol) in open_ports:
                        result["unnecessary_open"].append({
                            "port": f"{port_or_range}/{protocol}",
                            "description": desc,
                            "close_command": f"firewall-cmd --permanent --remove-port={port_or_range}/{protocol} && firewall-cmd --reload"
                        })
                        break  # Only add once per port_or_range
        
        elif firewall_service == "iptables":
            # Check iptables rules for both TCP and UDP
            open_ports = set()
            
            # Check TCP rules
            cmd = f"{cmd_prefix}iptables -L INPUT -n --line-numbers"
            check_result = self._execute_command(cmd, timeout=15)
            
            if check_result.get('returncode') != 0:
                result["error"] = f"Failed to query iptables: {check_result.get('stderr', '')}"
                return result
            
            iptables_output = check_result.get('stdout', '')
            
            # Parse iptables output to find ACCEPT rules for TCP ports
            for line in iptables_output.splitlines():
                if 'ACCEPT' in line and 'tcp' in line.lower() and 'dpt:' in line:
                    for part in line.split():
                        if part.startswith('dpt:'):
                            try:
                                port_num = int(part.split(':')[1])
                                open_ports.add((port_num, 'tcp'))
                            except (ValueError, IndexError):
                                pass
            
            # Check UDP rules
            cmd = f"{cmd_prefix}iptables -L INPUT -n --line-numbers -t filter"
            check_result = self._execute_command(cmd, timeout=15)
            
            if check_result.get('returncode') == 0:
                iptables_output = check_result.get('stdout', '')
                for line in iptables_output.splitlines():
                    if 'ACCEPT' in line and 'udp' in line.lower() and 'dpt:' in line:
                        for part in line.split():
                            if part.startswith('dpt:'):
                                try:
                                    port_num = int(part.split(':')[1])
                                    open_ports.add((port_num, 'udp'))
                                except (ValueError, IndexError):
                                    pass
            
            # Check each port in CLOSED_PORTS to see if it's unnecessarily open
            for port_or_range, protocol, desc in self.CLOSED_PORTS:
                ports_to_check = self._expand_port_range(port_or_range)
                for port_num in ports_to_check:
                    if (port_num, protocol) in open_ports:
                        result["unnecessary_open"].append({
                            "port": f"{port_or_range}/{protocol}",
                            "description": desc,
                            "close_command": f"iptables -D INPUT -p {protocol} --dport {port_num} -j ACCEPT"
                        })
                        break  # Only add once per port_or_range
        
        elif firewall_service == "ufw":
            # Check ufw status
            cmd = f"{cmd_prefix}ufw status numbered"
            check_result = self._execute_command(cmd, timeout=15)
            
            if check_result.get('returncode') != 0:
                result["error"] = f"Failed to query ufw: {check_result.get('stderr', '')}"
                return result
            
            ufw_output = check_result.get('stdout', '')
            
            # Parse ufw output (format: "22/tcp ALLOW IN")
            open_ports = set()
            for line in ufw_output.splitlines():
                if 'ALLOW' in line:
                    parts = line.split()
                    for part in parts:
                        if '/' in part and any(proto in part.lower() for proto in ['tcp', 'udp']):
                            try:
                                port_proto = part.split('/')
                                if len(port_proto) == 2:
                                    port_num = int(port_proto[0])
                                    protocol = port_proto[1].lower()
                                    open_ports.add((port_num, protocol))
                            except ValueError:
                                pass
            
            # Check each port in CLOSED_PORTS to see if it's unnecessarily open
            for port_or_range, protocol, desc in self.CLOSED_PORTS:
                ports_to_check = self._expand_port_range(port_or_range)
                for port_num in ports_to_check:
                    if (port_num, protocol) in open_ports:
                        result["unnecessary_open"].append({
                            "port": f"{port_or_range}/{protocol}",
                            "description": desc,
                            "close_command": f"ufw delete allow {port_num}/{protocol}"
                        })
                        break  # Only add once per port_or_range
        
        return result
    
    def _check_ports(self, node: str, firewall_service: str) -> Dict[str, Any]:
        """Check if required ports are open in the firewall."""
        result = {
            "open": [],
            "closed": [],
            "error": None
        }
        
        # Build command prefix based on node
        if node == "localhost":
            cmd_prefix = ""
        else:
            cmd_prefix = f"ssh -o StrictHostKeyChecking=no {node} "
        
        if firewall_service == "firewalld":
            # Check firewalld rules
            cmd = f"{cmd_prefix}firewall-cmd --list-ports"
            check_result = self._execute_command(cmd, timeout=15)
            
            if check_result.get('returncode') != 0:
                result["error"] = f"Failed to query firewalld: {check_result.get('stderr', '')}"
                return result
            
            open_ports_output = check_result.get('stdout', '')
            
            # Parse open ports (format: "1191/tcp 60000/udp 32767-32769/tcp ...")
            open_ports = set()
            for port_entry in open_ports_output.split():
                if '/' in port_entry:
                    try:
                        port_part, protocol = port_entry.split('/')
                        # Expand port ranges in firewall output
                        ports = self._expand_port_range(port_part)
                        for port_num in ports:
                            open_ports.add((port_num, protocol))
                    except ValueError:
                        pass
            
            # Check each required port (expand ranges)
            for port_or_range, protocol, desc in self.REQUIRED_PORTS:
                ports_to_check = self._expand_port_range(port_or_range)
                all_open = all((p, protocol) in open_ports for p in ports_to_check)
                
                if all_open:
                    result["open"].append(f"{port_or_range}/{protocol}")
                else:
                    result["closed"].append(f"{port_or_range}/{protocol}")
        
        elif firewall_service == "iptables":
            # Check iptables rules for both TCP and UDP
            open_ports = set()
            
            # Check TCP rules
            cmd = f"{cmd_prefix}iptables -L INPUT -n --line-numbers"
            check_result = self._execute_command(cmd, timeout=15)
            
            if check_result.get('returncode') != 0:
                result["error"] = f"Failed to query iptables: {check_result.get('stderr', '')}"
                return result
            
            iptables_output = check_result.get('stdout', '')
            
            # Parse iptables output to find ACCEPT rules for TCP ports
            for line in iptables_output.splitlines():
                if 'ACCEPT' in line and 'tcp' in line.lower() and 'dpt:' in line:
                    for part in line.split():
                        if part.startswith('dpt:'):
                            try:
                                port_num = int(part.split(':')[1])
                                open_ports.add((port_num, 'tcp'))
                            except (ValueError, IndexError):
                                pass
            
            # Check UDP rules
            cmd = f"{cmd_prefix}iptables -L INPUT -n --line-numbers -t filter"
            check_result = self._execute_command(cmd, timeout=15)
            
            if check_result.get('returncode') == 0:
                iptables_output = check_result.get('stdout', '')
                for line in iptables_output.splitlines():
                    if 'ACCEPT' in line and 'udp' in line.lower() and 'dpt:' in line:
                        for part in line.split():
                            if part.startswith('dpt:'):
                                try:
                                    port_num = int(part.split(':')[1])
                                    open_ports.add((port_num, 'udp'))
                                except (ValueError, IndexError):
                                    pass
            
            # Check each required port (expand ranges)
            for port_or_range, protocol, desc in self.REQUIRED_PORTS:
                ports_to_check = self._expand_port_range(port_or_range)
                all_open = all((p, protocol) in open_ports for p in ports_to_check)
                
                if all_open:
                    result["open"].append(f"{port_or_range}/{protocol}")
                else:
                    result["closed"].append(f"{port_or_range}/{protocol}")
        
        elif firewall_service == "ufw":
            # Check ufw status
            cmd = f"{cmd_prefix}ufw status numbered"
            check_result = self._execute_command(cmd, timeout=15)
            
            if check_result.get('returncode') != 0:
                result["error"] = f"Failed to query ufw: {check_result.get('stderr', '')}"
                return result
            
            ufw_output = check_result.get('stdout', '')
            
            # Parse ufw output (format: "22/tcp ALLOW IN")
            open_ports = set()
            for line in ufw_output.splitlines():
                if 'ALLOW' in line:
                    parts = line.split()
                    for part in parts:
                        if '/' in part and any(proto in part.lower() for proto in ['tcp', 'udp']):
                            try:
                                port_proto = part.split('/')
                                if len(port_proto) == 2:
                                    port_num = int(port_proto[0])
                                    protocol = port_proto[1].lower()
                                    open_ports.add((port_num, protocol))
                            except ValueError:
                                pass
                        elif part.isdigit():
                            # If no protocol specified, assume both tcp and udp
                            port_num = int(part)
                            open_ports.add((port_num, 'tcp'))
                            open_ports.add((port_num, 'udp'))
            
            # Check each required port (expand ranges)
            for port_or_range, protocol, desc in self.REQUIRED_PORTS:
                ports_to_check = self._expand_port_range(port_or_range)
                all_open = all((p, protocol) in open_ports for p in ports_to_check)
                
                if all_open:
                    result["open"].append(f"{port_or_range}/{protocol}")
                else:
                    result["closed"].append(f"{port_or_range}/{protocol}")
        
        return result


class HealthCheckManager:
    """Manages and orchestrates health checks"""

    def __init__(self):
        self.checkers: List[HealthChecker] = []
        self.results: List[HealthCheckResult] = []
        self.system_arch = None
        self.system_model = None
        self.log_filename = None
        self.log_handler = None

    def setup_logging(self, log_filename: str):
        """Setup logging configuration to write to the health report file"""
        self.log_filename = log_filename
        
        # Clear any existing handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # Create file handler for the health report
        self.log_handler = logging.FileHandler(self.log_filename)
        self.log_handler.setLevel(logging.INFO)
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        # Add handlers to root logger
        logging.root.setLevel(logging.INFO)
        logging.root.addHandler(self.log_handler)
        logging.root.addHandler(console_handler)

    def get_cluster_nodes(self, ssh_context: ExecutionContext) -> Dict[str, str]:
        """
        Parse mmlscluster output to extract all node names.
        
        Returns:
            Dictionary mapping short node names to full daemon node names
        """
        try:
            executor = RemoteExecutor(ssh_context)
            result = executor.execute_command("mmlscluster", timeout=30)
            output = result.get('stdout', '')
            
            nodes = {}
            in_node_section = False
            
            for line in output.splitlines():
                # Look for the node table header
                if line.strip().startswith("Node") and "Daemon node name" in line:
                    in_node_section = True
                    continue
                
                # Skip separator lines
                if in_node_section and line.strip().startswith("-"):
                    continue
                
                # Parse node lines
                if in_node_section and line.strip():
                    parts = line.split()
                    if len(parts) >= 2 and parts[0].isdigit():
                        # Extract daemon node name (second column)
                        daemon_node = parts[1]
                        # Remove -hs suffix if present and extract short name
                        short_name = daemon_node.split('-hs.')[0].split('.')[0]
                        nodes[short_name] = daemon_node
                
                # Stop if we hit an empty line after starting node section
                if in_node_section and not line.strip():
                    break
            
            logging.info("Extracted %d nodes from mmlscluster: %s", len(nodes), ', '.join(nodes.keys()))
            return nodes
            
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to parse mmlscluster output: %s", e)
            return {}

    def detect_system_architecture(self, ssh_context: ExecutionContext) -> str:
        """Detect system architecture using uname -m"""
        try:
            executor = RemoteExecutor(ssh_context)
            result = executor.execute_command("uname -m", timeout=10)
            arch = result.get('stdout', '').strip()
            self.system_arch = arch
            hostname = ssh_context.host if ssh_context.host else "localhost"
            logging.debug("Detected system architecture on %s: %s", hostname, arch)
            return arch
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to detect system architecture: %s", e)
            return ""

    def detect_system_model(self, ssh_context: ExecutionContext) -> str:
        """Detect system model from /proc/device-tree/model (for ppc64le)"""
        try:
            executor = RemoteExecutor(ssh_context)
            result = executor.execute_command("cat /proc/device-tree/model", timeout=10)
            model = result.get('stdout', '').strip()
            self.system_model = model
            hostname = ssh_context.host if ssh_context.host else "localhost"
            logging.debug("Detected system model on %s: %s", hostname, model)
            return model
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to detect system model: %s", e)
            return ""

    def detect_system_model_x86(self, ssh_context: ExecutionContext) -> str:
        """Detect system model from dmidecode (for x86)"""
        try:
            executor = RemoteExecutor(ssh_context)
            result = executor.execute_command("dmidecode -s system-product-name", timeout=10)
            model = result.get('stdout', '').strip()
            self.system_model = model
            logging.debug("Detected system model: %s", model)
            return model
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to detect system model: %s", e)
            return ""

    def is_ess_5000(self, ssh_context: ExecutionContext) -> bool:
        """Check if the system is Storage Scale System 5000 (ppc64le with model 5105-22E)"""
        arch = self.detect_system_architecture(ssh_context)
        
        # Only check model if architecture is ppc64le
        if arch == "ppc64le":
            model = self.detect_system_model(ssh_context)
            # Check if model starts with 5105-22E (Storage Scale System 5000)
            if model.startswith("5105-22E"):
                logging.info("Detected Storage Scale System 5000 (ppc64le, model: %s)", model)
                return True
        
        return False

    def is_ems_BYOE(self, ssh_context: ExecutionContext) -> bool:
        """Check if the system is Storage Scale System BYOE (x86 with model EMSVM)"""
        arch = self.detect_system_architecture(ssh_context)

        # Only check model if architecture is ppc64le
        if arch == "x86_64":
            model = self.detect_system_model_x86(ssh_context)
            # Check if model is EMSVM (EMS BYOE)
            if model == "EMSVM":
                logging.info("Detected Storage Scale System BYOE (x86_64, model: %s)", model)
                return True

        return False

    def register_checker(self, checker: HealthChecker):
        """Register a health checker"""
        if checker.enabled:
            self.checkers.append(checker)
            logging.debug("Registered checker: %s", checker.component_name)

    def register_default_checkers(self, ssh_context):
        """Register all default health checkers, conditionally skipping SystemHALCheckHealthChecker for Storage Scale System 5000."""
        # Check if this is a Storage Scale System 5000 system
        is_ess5000 = self.is_ess_5000(ssh_context)
       
        # Check if this is an BYOE system
        is_BYOE = self.is_ems_BYOE(ssh_context)

        # Only add SystemHALCheckHealthChecker if NOT Storage Scale System 5000 or NOT BYOE
        hal_check = True
        if is_ess5000 or is_BYOE:
            hal_check = False
        
        # Get cluster nodes (returns dict of short_name -> full_daemon_name)
        cluster_nodes = self.get_cluster_nodes(ssh_context)
        
        # Filter to get only IO nodes for essstoragequickcheck
        executor = RemoteExecutor(ssh_context)
        io_nodes = filter_io_nodes(cluster_nodes, executor)
        
        # Get list of all short node names for FirewallHealthChecker
        all_node_names = list(cluster_nodes.keys())
        
        logging.info("Total cluster nodes: %d, IO nodes: %d", len(cluster_nodes), len(io_nodes))
        
        default_checkers = [
            GNRHealthChecker(ssh_context),
            NodeTypeVersionHealthChecker(ssh_context, cluster_nodes=cluster_nodes),
            ESSStorageQuickCheckHealthChecker(ssh_context, node_list=io_nodes),
            StorageFirmwareHealthChecker(ssh_context, node_list=io_nodes),
            FirewallHealthChecker(ssh_context, node_list=all_node_names),
        ]
        
        # Only add SystemHALCheckHealthChecker if NOT Storage Scale System 5000 or NOT BYOE
        if hal_check:
            default_checkers.insert(1, SystemHALCheckHealthChecker(ssh_context))
            logging.debug("SystemHALCheckHealthChecker registered")
        else:
            logging.debug("Skipping SystemHALCheckHealthChecker for Storage Scale System 5000")
        
        for checker in default_checkers:
            self.register_checker(checker)

    def run_all_checks(self) -> List[HealthCheckResult]:
        """Run all registered health checks"""
        self.results = []

        print("Starting comprehensive system health check...")
        print("=" * 80)
        print("\n⚠️  SECURITY ADVISORY: IBM Storage Scale System: Vulnerability in Linux kernel crypto")
        print("    subsystem could allow local privilege escalation (CVE-2026-31431, RHEL 8/9)")
        print("    Check if your system is impacted: https://www.ibm.com/support/pages/node/7272714")
        print("=" * 80)

        for i, checker in enumerate(self.checkers, 1):
            if "Storage Firmware" in checker.component_name:
                print(f"[{i}/{len(self.checkers)}] Running storage firmware checks, may take a long time...", end=" ")
            else:
                print(f"[{i}/{len(self.checkers)}] Checking {checker.component_name}...", end=" ")

            start_time = time.time()
            result = checker.check_health()
            end_time = time.time()

            result.details["check_duration_seconds"] = round(end_time - start_time, 2)
            self.results.append(result)

            status_symbol = {
                HealthStatus.HEALTHY: "✓",
                HealthStatus.WARNING: "⚠",
                HealthStatus.CRITICAL: "✗",
                HealthStatus.ERROR: "⚠"
            }
            print(f"{status_symbol[result.status]}")

        print("\n" + "=" * 80)
        print("Health check completed!")

        return self.results

    def generate_report(self, output_format: str = "console") -> str:
        """Generate a comprehensive health report"""
        if not self.results:
            return "No health check results available. Run checks first."
        if output_format == "detailed":
            return self._generate_detailed_report()
        return self._generate_console_report()


    def _generate_console_report(self) -> str:
        # pylint: disable=too-many-locals,too-many-statements
        """Generate console-formatted report with table layout"""
        report = []
        report.append("\n" + "=" * 120)
        report.append("SYSTEM HEALTH CHECK REPORT")
        report.append("=" * 120)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Summary
        healthy = sum(1 for r in self.results if r.status == HealthStatus.HEALTHY)
        warning = sum(1 for r in self.results if r.status == HealthStatus.WARNING)
        critical = sum(1 for r in self.results if r.status == HealthStatus.CRITICAL)
        error = sum(1 for r in self.results if r.status == HealthStatus.ERROR)

        report.append("SUMMARY:")
        report.append(
            f"  ✓ Healthy: {healthy}    ⚠ Warning: {warning}    "
            f"✗ Critical: {critical}    ⚠ Error: {error}"
        )
        report.append("")

        # Table header
        report.append("COMPONENT HEALTH STATUS")
        report.append("=" * 120)

        # Create table with proper spacing
        header = (
            f"{'COMPONENT':<35} {'STATUS':<12} {'MESSAGE':<40} "
            f"{'CAN UPGRADE':<12} {'TIME TO RESOLVE':<20}"
        )
        report.append(header)
        report.append("-" * 120)

        # Table rows
        for result in self.results:
            status_display = {
                HealthStatus.HEALTHY: "✓ HEALTHY",
                HealthStatus.WARNING: "⚠ WARNING",
                HealthStatus.CRITICAL: "✗ CRITICAL",
                HealthStatus.ERROR: "⚠ ERROR"
            }

            # Truncate message if too long
            message = (
                result.message[:37] + "..."
                if len(result.message) > 40
                else result.message
            )
            upgrade_status = "YES" if result.can_upgrade else "NO"
            row = (
                f"{result.component:<35} {status_display[result.status]:<12} "
                f"{message:<40} {upgrade_status:<12} "
                f"{result.time_to_resolve:<20}"
            )
            report.append(row)

        report.append("-" * 120)
        report.append("")

        # Upgrade Matrix Information Banner with colors
        # ANSI color codes
        CYAN = "\033[96m"
        YELLOW = "\033[93m"
        GREEN = "\033[92m"
        BLUE = "\033[94m"
        BOLD = "\033[1m"
        RESET = "\033[0m"
        
        report.append(f"{CYAN}{'=' * 120}{RESET}")
        report.append(f"{BOLD}{YELLOW}📊 STORAGE SCALE UPGRADE MATRIX{RESET}")
        report.append(f"{CYAN}{'=' * 120}{RESET}")
        report.append(f"{BOLD}Planning to upgrade your Storage Scale System cluster?{RESET}")
        report.append("Check the official upgrade path matrix and documentation for supported upgrade routes:")
        report.append("")
        report.append(f"{GREEN}🔗 Upgrade Matrix:{RESET} {BLUE}{BOLD}https://tanso.net/ESS-Upgrade-Path/{RESET}")
        report.append(f"{GREEN}📚 Knowledge Center:{RESET} Refer to Storage Scale System Knowledge Center documentation for upgrade matrix")
        report.append("")
        report.append(f"{BOLD}These resources provide comprehensive information about:{RESET}")
        report.append(f"  {YELLOW}•{RESET} Supported upgrade paths between versions")
        report.append(f"  {YELLOW}•{RESET} Direct and multi-hop upgrade routes")
        report.append(f"  {YELLOW}•{RESET} Version compatibility requirements")
        report.append(f"  {YELLOW}•{RESET} Pre-upgrade and post-upgrade procedures")
        report.append(f"{CYAN}{'=' * 120}{RESET}")
        report.append("")

        # Firmware Information section - always display, grouped by node
        firmware_results = [r for r in self.results if r.component == "Storage Firmware Check"]
        if firmware_results:
            report.append(f"{CYAN}{'=' * 60}{RESET}")
            report.append(f"{BOLD}{YELLOW}📋 FIRMWARE INFORMATION{RESET}")
            report.append(f"{CYAN}{'=' * 60}{RESET}")
            
            # Collect all firmware items grouped by node
            node_firmware = {}
            
            for result in firmware_results:
                # Process ok_items
                if result.details and 'ok_items' in result.details:
                    for item in result.details['ok_items']:
                        # Extract node name from the item string
                        if item.startswith("Node "):
                            parts = item.split(":", 1)
                            if len(parts) == 2:
                                node_name = parts[0].replace("Node ", "").strip()
                                firmware_info = parts[1].strip()
                                if node_name not in node_firmware:
                                    node_firmware[node_name] = []
                                node_firmware[node_name].append(firmware_info)
                
                # Process errors
                if result.details and 'errors' in result.details:
                    for error in result.details['errors']:
                        # Extract node name from the error string
                        if error.startswith("Node "):
                            parts = error.split(":", 1)
                            if len(parts) == 2:
                                node_name = parts[0].replace("Node ", "").strip()
                                firmware_info = parts[1].strip()
                                if node_name not in node_firmware:
                                    node_firmware[node_name] = []
                                node_firmware[node_name].append(firmware_info)
            
            # Display firmware information grouped by node
            for node_name in sorted(node_firmware.keys()):
                report.append(f"Node {node_name}:")
                for firmware_info in node_firmware[node_name]:
                    report.append(f"  {firmware_info}")
                report.append("")

        # Detailed resolution section
        report.append("DETAILED RESOLUTION GUIDE")
        report.append("=" * 120)

        # Group by status for better organization
        critical_issues = [r for r in self.results if r.status == HealthStatus.CRITICAL]
        warning_issues = [r for r in self.results if r.status == HealthStatus.WARNING]
        error_issues = [r for r in self.results if r.status == HealthStatus.ERROR]

        if critical_issues:
            report.append("")
            report.append("🚨 CRITICAL ISSUES (IMMEDIATE ACTION REQUIRED)")
            report.append("-" * 60)
            for result in critical_issues:
                report.append(f"• {result.component}")
                report.append(f"  Problem: {result.message}")
                report.append(f"  Solution: {result.resolution}")
                report.append(f"  Time: {result.time_to_resolve}")
                if result.upgrade_info:
                    report.append(f"  Upgrade: {result.upgrade_info}")
                
                # Add detailed unnecessary ports information for Firewall checks
                if result.component == "Firewall Status and Port Check":
                    if result.details and 'node_results' in result.details:
                        has_unnecessary = False
                        for node_name, node_data in result.details['node_results'].items():
                            if node_data.get('unnecessary_open_ports'):
                                has_unnecessary = True
                                break
                        
                        if has_unnecessary:
                            report.append("")
                            report.append("  " + "=" * 60)
                            report.append("  WARNING: Unnecessary Firewall Ports Open")
                            report.append("  " + "=" * 60)
                            report.append("  The following ports are currently open but are not required for this node type.")
                            report.append("  These ports can be closed for better security.")
                            report.append("")
                            
                            # Collect all unnecessary ports grouped by node and protocol
                            for node_name, node_data in result.details['node_results'].items():
                                unnecessary_ports = node_data.get('unnecessary_open_ports', [])
                                if unnecessary_ports:
                                    # Separate TCP and UDP ports
                                    tcp_ports = []
                                    udp_ports = []
                                    for port_info in unnecessary_ports:
                                        port = port_info['port']
                                        if '/tcp' in port:
                                            tcp_ports.append(port)
                                        elif '/udp' in port:
                                            udp_ports.append(port)
                                    
                                    report.append(f"  Node {node_name}:")
                                    if tcp_ports:
                                        report.append(f"  Unnecessary TCP ports: {', '.join(tcp_ports)}")
                                    if udp_ports:
                                        report.append(f"  Unnecessary UDP ports: {', '.join(udp_ports)}")
                                    report.append("")
                            
                            report.append("  RECOMMENDED ACTION:")
                            report.append("  You can close these ports using the following firewall-cmd commands:")
                            report.append("")
                            report.append("    firewall-cmd --permanent --remove-port=<PORT>")
                            report.append("    firewall-cmd --reload")
                            report.append("")
                            report.append("  Example:")
                            report.append("    firewall-cmd --permanent --remove-port=8889/tcp")
                            report.append("    firewall-cmd --reload")
                
                report.append("")

        if warning_issues:
            report.append("")
            report.append("⚠️  WARNING ISSUES (MONITOR AND PLAN)")
            report.append("-" * 60)
            for result in warning_issues:
                report.append(f"• {result.component}")
                report.append(f"  Problem: {result.message}")
                report.append(f"  Solution: {result.resolution}")
                report.append(f"  Time: {result.time_to_resolve}")
                if result.upgrade_info:
                    report.append(f"  Upgrade: {result.upgrade_info}")
                
                # Add detailed unnecessary ports information for Firewall checks
                if result.component == "Firewall Status and Port Check":
                    if result.details and 'node_results' in result.details:
                        has_unnecessary = False
                        for node_name, node_data in result.details['node_results'].items():
                            if node_data.get('unnecessary_open_ports'):
                                has_unnecessary = True
                                break
                        
                        if has_unnecessary:
                            report.append("")
                            report.append("  " + "=" * 60)
                            report.append("  WARNING: Unnecessary Firewall Ports Open")
                            report.append("  " + "=" * 60)
                            report.append("  The following ports are currently open but are not required for this node type.")
                            report.append("  These ports can be closed for better security.")
                            report.append("")
                            
                            # Collect all unnecessary ports grouped by node and protocol
                            for node_name, node_data in result.details['node_results'].items():
                                unnecessary_ports = node_data.get('unnecessary_open_ports', [])
                                if unnecessary_ports:
                                    # Separate TCP and UDP ports
                                    tcp_ports = []
                                    udp_ports = []
                                    for port_info in unnecessary_ports:
                                        port = port_info['port']
                                        if '/tcp' in port:
                                            tcp_ports.append(port)
                                        elif '/udp' in port:
                                            udp_ports.append(port)
                                    
                                    report.append(f"  Node {node_name}:")
                                    if tcp_ports:
                                        report.append(f"  Unnecessary TCP ports: {', '.join(tcp_ports)}")
                                    if udp_ports:
                                        report.append(f"  Unnecessary UDP ports: {', '.join(udp_ports)}")
                                    report.append("")
                            
                            report.append("  RECOMMENDED ACTION:")
                            report.append("  You can close these ports using the following firewall-cmd commands:")
                            report.append("")
                            report.append("    firewall-cmd --permanent --remove-port=<PORT>")
                            report.append("    firewall-cmd --reload")
                            report.append("")
                            report.append("  Example:")
                            report.append("    firewall-cmd --permanent --remove-port=8889/tcp")
                            report.append("    firewall-cmd --reload")
                
                report.append("")

        if error_issues:
            report.append("")
            report.append("❌ ERROR ISSUES (CHECK SYSTEM)")
            report.append("-" * 60)
            for result in error_issues:
                report.append(f"• {result.component}")
                report.append(f"  Problem: {result.message}")
                report.append(f"  Solution: {result.resolution}")
                report.append(f"  Time: {result.time_to_resolve}")
                report.append("")

        # System details section
        report.append("")
        report.append("SYSTEM DETAILS")
        report.append("=" * 120)

        for result in self.results:
            if result.component == "System Information":
                details = result.details
                report.append(f"Platform: {details.get('platform', 'Unknown')}")
                report.append(f"Architecture: {details.get('architecture', 'Unknown')}")
                report.append(f"Processor: {details.get('processor', 'Unknown')}")
                uptime_days = details.get('uptime_days', 0)
                uptime_hours = details.get('uptime_hours', 0)
                report.append(f"Uptime: {uptime_days} days, {uptime_hours} hours")
                break

        report.append("")
        return "\n".join(report)

    def _generate_detailed_report(self) -> str:
        """Generate detailed plain text report with full command outputs"""
        report = []
        report.append("=" * 120)
        report.append("DETAILED SYSTEM HEALTH CHECK REPORT")
        report.append("=" * 120)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Summary
        healthy = sum(1 for r in self.results if r.status == HealthStatus.HEALTHY)
        warning = sum(1 for r in self.results if r.status == HealthStatus.WARNING)
        critical = sum(1 for r in self.results if r.status == HealthStatus.CRITICAL)
        error = sum(1 for r in self.results if r.status == HealthStatus.ERROR)

        report.append("SUMMARY:")
        report.append(
            f"  ✓ Healthy: {healthy}    ⚠ Warning: {warning}    "
            f"✗ Critical: {critical}    ⚠ Error: {error}"
        )
        report.append("")
        report.append("=" * 120)

        # Detailed results for each component
        for i, result in enumerate(self.results, 1):
            report.append("")
            report.append(f"[{i}] COMPONENT: {result.component}")
            report.append("-" * 120)
            
            status_display = {
                HealthStatus.HEALTHY: "✓ HEALTHY",
                HealthStatus.WARNING: "⚠ WARNING",
                HealthStatus.CRITICAL: "✗ CRITICAL",
                HealthStatus.ERROR: "⚠ ERROR"
            }
            
            report.append(f"Status: {status_display[result.status]}")
            report.append(f"Message: {result.message}")
            report.append(f"Can Upgrade: {'YES' if result.can_upgrade else 'NO'}")
            report.append(f"Time to Resolve: {result.time_to_resolve}")
            report.append(f"Timestamp: {result.timestamp}")
            report.append("")
            
            # Resolution
            report.append("Resolution:")
            report.append(f"  {result.resolution}")
            report.append("")
            
            # Command output details
            if result.details:
                report.append("Details:")
                
                # Show command if available
                if 'command' in result.details:
                    report.append(f"  Command: {result.details['command']}")
                    report.append("")
                
                # Show stdout with preserved formatting
                if 'stdout' in result.details and result.details['stdout']:
                    report.append("  Standard Output:")
                    report.append("  " + "-" * 116)
                    for line in result.details['stdout'].splitlines():
                        # Temporary workaround to not consider non ess nodes
                        if "Invalid node in the list" in line:
                            continue
                        report.append(f"  {line}")
                    report.append("  " + "-" * 116)
                    report.append("")
                
                # Show stderr if present and not empty
                if 'stderr' in result.details and result.details['stderr']:
                    report.append("  Standard Error:")
                    report.append("  " + "-" * 116)
                    for line in result.details['stderr'].splitlines():
                        report.append(f"  {line}")
                    report.append("  " + "-" * 116)
                    report.append("")
                
                # Show return code
                if 'returncode' in result.details:
                    report.append(f"  Return Code: {result.details['returncode']}")
                    report.append("")
                
                # Show issues if present
                if 'issues' in result.details and result.details['issues']:
                    report.append("  Issues Found:")
                    for issue in result.details['issues']:
                        report.append(f"    - {issue}")
                    report.append("")
                
                # Show errors if present
                if 'errors' in result.details and result.details['errors']:
                    report.append("  Errors:")
                    for err in result.details['errors']:
                        report.append(f"    - {err}")
                    report.append("")
                
                # Show warnings if present
                if 'warnings' in result.details and result.details['warnings']:
                    report.append("  Warnings:")
                    for warn in result.details['warnings']:
                        report.append(f"    - {warn}")
                    report.append("")
                
                # Show check duration
                if 'check_duration_seconds' in result.details:
                    report.append(f"  Check Duration: {result.details['check_duration_seconds']} seconds")
                    report.append("")
            
            report.append("=" * 120)

        return "\n".join(report)

    def save_report(self):
        """Append detailed report to the log file that already contains execution logs"""
        if not self.log_filename:
            print("Error: Log filename not set")
            return
        
        # Flush the log handler to ensure all logs are written
        if self.log_handler:
            self.log_handler.flush()
        
        # Generate the detailed report
        report = self.generate_report("detailed")
        
        # Append the detailed report to the existing log file
        with open(self.log_filename, 'a', encoding='utf-8') as f:
            f.write("\n\n")
            f.write(report)
        
        print(f"Report saved to: {self.log_filename}")


def main():
    """Main function to run health checks"""
    # Get SSH details first to create the log filename
    ssh_host = input("Enter the EMS SSH hostname: ")
    if not ssh_host:
        print("SSH host is required.")
        sys.exit(1)
    
    # Create log filename with timestamp
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"health_report_{ssh_host}_{timestamp_str}.log"
    
    # Initialize manager with the log filename
    manager = HealthCheckManager()
    manager.setup_logging(log_filename)
    
    ssh_user = input("Enter the SSH username (default root): ") or "root"
    ssh_pass = getpass.getpass("Enter the SSH password (leave blank for key-based auth): ")
    ssh_context_kwargs: Dict[str, Any] = {
        'context_type': 'ssh',
        'host': ssh_host,
        'username': ssh_user
    }
    if ssh_pass:
        ssh_context_kwargs['password'] = ssh_pass
    ssh_context = ExecutionContext(**ssh_context_kwargs)

    print("\nSYSTEM DETAILS")
    print("=" * 120)
    try:
        executor = RemoteExecutor(ssh_context)
        
        # Get system architecture
        uname_result = executor.execute_command("uname -a", timeout=10)
        uname_out = uname_result.get('stdout', '').strip()
        if uname_out:
            print("System Information (uname -a):")
            print(uname_out)
            print()
        
        # Get architecture
        arch_result = executor.execute_command("uname -m", timeout=10)
        arch = arch_result.get('stdout', '').strip()
        if arch:
            print(f"Architecture: {arch}")
            
            # If ppc64le, get the model
            if arch == "ppc64le":
                model_result = executor.execute_command("cat /proc/device-tree/model", timeout=10)
                model = model_result.get('stdout', '').strip()
                if model:
                    print(f"System Model: {model}")
                    if model.startswith("5105-22E"):
                        logging.debug("Detected: Storage Scale System 5000 - SystemHALCheckHealthChecker will be skipped")
            print()
        
        # Get cluster information
        mmlscluster_result = executor.execute_command("mmlscluster", timeout=30)
        mmlscluster_out = mmlscluster_result.get('stdout', '').strip()
        mmlscluster_err = mmlscluster_result.get('stderr', '').strip()
        
        # Filter out SSH warnings from stderr
        if mmlscluster_err:
            filtered_err_lines = []
            for line in mmlscluster_err.splitlines():
                # Skip SSH host key warnings
                if not ("Permanently added" in line and "to the list of known hosts" in line):
                    filtered_err_lines.append(line)
            mmlscluster_err = '\n'.join(filtered_err_lines).strip()
        
        if mmlscluster_out:
            print()
            print("-" * 120)
            print("mmlscluster output:")
            print("-" * 120)
            print(mmlscluster_out)
        if mmlscluster_err:
            print()
            print("mmlscluster error output:")
            print(mmlscluster_err)
        print()
    except Exception as e:
        print(f"Failed to execute system commands: {e}")
    print("=" * 120)

    # Register checks that can execute on utility
    manager.register_default_checkers(ssh_context)
    # Register checks that can needs to be run from EMS VM
    manager.register_checker(MMNetVerifyHealthChecker(ssh_context))
    manager.register_checker(MMHealthChecker(ssh_context))

    results = manager.run_all_checks()
    print(manager.generate_report())
    manager.save_report()
    critical_issues = sum(1 for r in results if r.status == HealthStatus.CRITICAL)
    if critical_issues > 0:
        sys.exit(1)  # Critical issues found
    else:
        sys.exit(0)  # All good


if __name__ == "__main__":
    main()

