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
    """Health checker for ESS Storage Quick check."""
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
        return "ESS Storage Quick Check"

    @property
    def description(self) -> str:
        return (
            f"Runs the ESS Storage Quick Check script "
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


class MMNetVerifyHealthChecker(HealthChecker):
    """Health checker for mmnetverify network verification."""

    def __init__(self, execution_context: Optional[ExecutionContext] = None):
        # Always use SSH context unless explicitly overridden
        if execution_context is None:
            execution_context = ExecutionContext(context_type='ssh')
        super().__init__(execution_context)

    @property
    def component_name(self) -> str:
        return "ESS Network (mmnetverify)"

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
        return "ESS GNR Health (gnrhealthcheck)"

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
    """Health checker for ESS nodes."""
    def __init__(self, execution_context: Optional[ExecutionContext] = None):
        # Default using ssh unless specified
        if execution_context is None:
            execution_context = ExecutionContext(context_type='ssh')
        super().__init__(execution_context)

    @property
    def component_name(self) -> str:
        return "ESS Node Health (mmhealth)"

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
        return "ESS System HAL Check (system_check)"

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

    def get_cluster_nodes(self, ssh_context: ExecutionContext) -> List[str]:
        """Parse mmlscluster output to extract all node names"""
        try:
            executor = RemoteExecutor(ssh_context)
            result = executor.execute_command("mmlscluster", timeout=30)
            output = result.get('stdout', '')
            
            nodes = []
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
                        nodes.append(short_name)
                
                # Stop if we hit an empty line after starting node section
                if in_node_section and not line.strip():
                    break
            
            logging.info("Extracted %d nodes from mmlscluster: %s", len(nodes), ', '.join(nodes))
            return nodes
            
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to parse mmlscluster output: %s", e)
            return []

    def detect_system_architecture(self, ssh_context: ExecutionContext) -> str:
        """Detect system architecture using uname -m"""
        try:
            executor = RemoteExecutor(ssh_context)
            result = executor.execute_command("uname -m", timeout=10)
            arch = result.get('stdout', '').strip()
            self.system_arch = arch
            logging.info("Detected system architecture: %s", arch)
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
            logging.info("Detected system model: %s", model)
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
            logging.info("Detected system model: %s", model)
            return model
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to detect system model: %s", e)
            return ""

    def is_ess_5000(self, ssh_context: ExecutionContext) -> bool:
        """Check if the system is ESS 5000 (ppc64le with model 5105-22E)"""
        arch = self.detect_system_architecture(ssh_context)
        
        # Only check model if architecture is ppc64le
        if arch == "ppc64le":
            model = self.detect_system_model(ssh_context)
            # Check if model starts with 5105-22E (ESS 5000)
            if model.startswith("5105-22E"):
                logging.info("Detected ESS 5000 system (ppc64le, model: %s)", model)
                return True
        
        return False

    def is_ems_BYOE(self, ssh_context: ExecutionContext) -> bool:
        """Check if the system is ESS BYOE (x86 with model EMSVM)"""
        arch = self.detect_system_architecture(ssh_context)

        # Only check model if architecture is ppc64le
        if arch == "x86_64":
            model = self.detect_system_model_x86(ssh_context)
            # Check if model is EMSVM (EMS BYOE)
            if model == "EMSVM":
                logging.info("Detected ESS BYOE system (x86_64, model: %s)", model)
                return True

        return False

    def register_checker(self, checker: HealthChecker):
        """Register a health checker"""
        if checker.enabled:
            self.checkers.append(checker)
            logging.info("Registered checker: %s", checker.component_name)

    def register_default_checkers(self, ssh_context):
        """Register all default health checkers, conditionally skipping SystemHALCheckHealthChecker for ESS 5000."""
        # Check if this is an ESS 5000 system
        is_ess5000 = self.is_ess_5000(ssh_context)
       
        # Check if this is an BYOE system
        is_BYOE = self.is_ems_BYOE(ssh_context)

        # Only add SystemHALCheckHealthChecker if NOT ESS 5000 or NOT BYOE
        hal_check = True
        if is_ess5000 or is_BYOE:
            hal_check = False
        
        # Get cluster nodes for essstoragequickcheck
        cluster_nodes = self.get_cluster_nodes(ssh_context)
        
        default_checkers = [
            GNRHealthChecker(ssh_context),
            ESSStorageQuickCheckHealthChecker(ssh_context, node_list=cluster_nodes),
        ]
        
        # Only add SystemHALCheckHealthChecker if NOT ESS 5000 or NOT BYOE
        if hal_check:
            default_checkers.insert(1, SystemHALCheckHealthChecker(ssh_context))
            logging.info("SystemHALCheckHealthChecker registered")
        else:
            logging.info("Skipping SystemHALCheckHealthChecker for ESS 5000 system")
        
        for checker in default_checkers:
            self.register_checker(checker)

    def run_all_checks(self) -> List[HealthCheckResult]:
        """Run all registered health checks"""
        self.results = []

        print("Starting comprehensive system health check...")
        print("=" * 80)

        for i, checker in enumerate(self.checkers, 1):
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
                        logging.debug("Detected: ESS 5000 - SystemHALCheckHealthChecker will be skipped")
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
