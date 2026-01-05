"""
Stage: TigerBeetle Validation.

Validates TigerBeetle cluster configuration for:
- Node count is odd (required for Raft consensus)
- Sufficient node count for production HA
- EBS volume IOPS meets requirements
- No public access to TigerBeetle ports
- Security group rules are properly configured
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import (
    STAGE_TIGERBEETLE,
    Finding,
    FindingSeverity,
)
from .base import PreflightStage

# TigerBeetle minimum requirements
MIN_PROD_NODES = 3
MIN_DEV_NODES = 1
MIN_IOPS = 5000  # Minimum IOPS for acceptable performance
RECOMMENDED_IOPS = 10000
TIGERBEETLE_CLIENT_PORT = 3000
TIGERBEETLE_REPLICATION_PORT = 3001


class TigerBeetleStage(PreflightStage):
    """
    TigerBeetle cluster validation stage.

    Validates that the TigerBeetle cluster configuration meets
    requirements for production deployment.
    """

    @property
    def name(self) -> str:
        return STAGE_TIGERBEETLE

    def should_skip(self) -> tuple[bool, str | None]:
        """Check if TigerBeetle validation should be skipped."""
        skip, reason = super().should_skip()
        if skip:
            return skip, reason

        # Skip if no synth output
        if not self.context.synth_output_dir:
            return True, "No synth output available"

        if not self.context.synth_output_dir.exists():
            return True, "Synth output directory does not exist"

        # Skip if no TigerBeetle template
        if not self._has_tigerbeetle_template():
            return True, "No TigerBeetle stack in deployment"

        return False, None

    def _has_tigerbeetle_template(self) -> bool:
        """Check if TigerBeetle template exists in synth output."""
        synth_dir = self.context.synth_output_dir
        if not synth_dir:
            return False

        # Look for TigerBeetle template
        for template_file in synth_dir.glob("*.template.json"):
            if "tigerbeetle" in template_file.name.lower():
                return True

        # Also check manifest for TigerBeetle stack
        manifest_file = synth_dir / "manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file) as f:
                    manifest = json.load(f)
                for artifact in manifest.get("artifacts", {}).values():
                    if "tigerbeetle" in artifact.get("displayName", "").lower():
                        return True
            except (json.JSONDecodeError, KeyError):
                pass

        return False

    def _execute(self) -> None:
        """Execute TigerBeetle validation checks."""
        synth_dir = self.context.synth_output_dir
        if not synth_dir:
            return

        # Find TigerBeetle template
        template_data = self._load_tigerbeetle_template(synth_dir)
        if not template_data:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.INFO,
                    code="TB_NO_TEMPLATE",
                    message="TigerBeetle template not found in synth output",
                )
            )
            return

        # Run validation checks
        self._check_node_count(template_data)
        self._check_volume_iops(template_data)
        self._check_security_groups(template_data)
        self._check_network_isolation(template_data)

    def _load_tigerbeetle_template(self, synth_dir: Path) -> dict[str, Any] | None:
        """Load TigerBeetle CloudFormation template."""
        for template_file in synth_dir.glob("*.template.json"):
            if "tigerbeetle" in template_file.name.lower():
                try:
                    with open(template_file) as f:
                        data: dict[str, Any] = json.load(f)
                        return data
                except json.JSONDecodeError:
                    self.add_finding(
                        Finding(
                            severity=FindingSeverity.HIGH,
                            code="TB_TEMPLATE_INVALID",
                            message=f"Invalid JSON in TigerBeetle template: {template_file.name}",
                            file_path=str(template_file),
                        )
                    )
                    return None
        return None

    def _check_node_count(self, template: dict[str, Any]) -> None:
        """Validate TigerBeetle node count is odd for Raft consensus."""
        resources = template.get("Resources", {})

        for resource_id, resource in resources.items():
            if resource.get("Type") != "AWS::AutoScaling::AutoScalingGroup":
                continue

            props = resource.get("Properties", {})
            min_size = props.get("MinSize", 0)
            desired = props.get("DesiredCapacity", min_size)

            # Use int conversion for CloudFormation intrinsic functions
            if isinstance(desired, dict):
                # Intrinsic function - can't validate statically
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.INFO,
                        code="TB_DYNAMIC_SIZE",
                        message="TigerBeetle node count uses dynamic value, cannot validate statically",
                        resource=resource_id,
                    )
                )
                continue

            try:
                node_count = int(desired)
            except (ValueError, TypeError):
                continue

            # Check if odd (required for Raft)
            if node_count > 1 and node_count % 2 == 0:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.CRITICAL,
                        code="TB_EVEN_NODE_COUNT",
                        message=f"TigerBeetle node count ({node_count}) must be odd for Raft consensus",
                        resource=resource_id,
                        remediation="Use 1, 3, or 5 nodes. Even counts cannot achieve consensus quorum.",
                    )
                )

            # Check production requirements
            is_prod = self._is_production_environment()
            if is_prod and node_count < MIN_PROD_NODES:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.HIGH,
                        code="TB_INSUFFICIENT_NODES_PROD",
                        message=f"Production environment has only {node_count} TigerBeetle node(s)",
                        resource=resource_id,
                        remediation=f"Use at least {MIN_PROD_NODES} nodes for production high availability.",
                    )
                )
            elif not is_prod and node_count >= 1:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.INFO,
                        code="TB_NODE_COUNT_OK",
                        message=f"TigerBeetle configured with {node_count} node(s)",
                        resource=resource_id,
                    )
                )

    def _check_volume_iops(self, template: dict[str, Any]) -> None:
        """Validate EBS volume IOPS meets TigerBeetle requirements."""
        resources = template.get("Resources", {})

        for resource_id, resource in resources.items():
            if resource.get("Type") != "AWS::EC2::LaunchTemplate":
                continue

            props = resource.get("Properties", {})
            launch_data = props.get("LaunchTemplateData", {})
            block_devices = launch_data.get("BlockDeviceMappings", [])

            for device in block_devices:
                ebs = device.get("Ebs", {})
                iops = ebs.get("Iops")
                volume_type = ebs.get("VolumeType", "")
                device_name = device.get("DeviceName", "unknown")

                # Skip root volumes
                if device_name in ["/dev/xvda", "/dev/sda1"]:
                    continue

                if iops is None:
                    # No IOPS specified - might be using default
                    if volume_type == "gp3":
                        self.add_finding(
                            Finding(
                                severity=FindingSeverity.WARN,
                                code="TB_DEFAULT_IOPS",
                                message="TigerBeetle data volume using default gp3 IOPS (3000)",
                                resource=resource_id,
                                remediation=f"Consider increasing IOPS to {RECOMMENDED_IOPS} for optimal performance.",
                            )
                        )
                    continue

                try:
                    iops_value = int(iops)
                except (ValueError, TypeError):
                    continue

                if iops_value < MIN_IOPS:
                    self.add_finding(
                        Finding(
                            severity=FindingSeverity.HIGH,
                            code="TB_LOW_IOPS",
                            message=f"TigerBeetle data volume IOPS ({iops_value}) below minimum ({MIN_IOPS})",
                            resource=resource_id,
                            remediation=f"Increase IOPS to at least {MIN_IOPS}, recommended {RECOMMENDED_IOPS}.",
                        )
                    )
                elif iops_value < RECOMMENDED_IOPS:
                    self.add_finding(
                        Finding(
                            severity=FindingSeverity.WARN,
                            code="TB_SUBOPTIMAL_IOPS",
                            message=f"TigerBeetle data volume IOPS ({iops_value}) below recommended ({RECOMMENDED_IOPS})",
                            resource=resource_id,
                        )
                    )
                else:
                    self.add_finding(
                        Finding(
                            severity=FindingSeverity.INFO,
                            code="TB_IOPS_OK",
                            message=f"TigerBeetle data volume IOPS ({iops_value}) meets requirements",
                            resource=resource_id,
                        )
                    )

    def _check_security_groups(self, template: dict[str, Any]) -> None:
        """Validate TigerBeetle security group configuration."""
        resources = template.get("Resources", {})

        for resource_id, resource in resources.items():
            if resource.get("Type") != "AWS::EC2::SecurityGroup":
                continue

            # Check if this is the TigerBeetle security group
            props = resource.get("Properties", {})
            description = props.get("GroupDescription", "")
            if (
                "tigerbeetle" not in description.lower()
                and "tigerbeetle" not in resource_id.lower()
            ):
                continue

            ingress_rules = props.get("SecurityGroupIngress", [])

            has_client_port = False
            has_replication_port = False

            for rule in ingress_rules:
                from_port = rule.get("FromPort")
                to_port = rule.get("ToPort")

                if from_port == TIGERBEETLE_CLIENT_PORT or to_port == TIGERBEETLE_CLIENT_PORT:
                    has_client_port = True
                if (
                    from_port == TIGERBEETLE_REPLICATION_PORT
                    or to_port == TIGERBEETLE_REPLICATION_PORT
                ):
                    has_replication_port = True

            if not has_client_port:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.WARN,
                        code="TB_NO_CLIENT_PORT",
                        message=f"Security group missing port {TIGERBEETLE_CLIENT_PORT} (client)",
                        resource=resource_id,
                    )
                )

            if not has_replication_port:
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.WARN,
                        code="TB_NO_REPLICATION_PORT",
                        message=f"Security group missing port {TIGERBEETLE_REPLICATION_PORT} (replication)",
                        resource=resource_id,
                    )
                )

    def _check_network_isolation(self, template: dict[str, Any]) -> None:
        """Validate TigerBeetle is not publicly accessible."""
        resources = template.get("Resources", {})

        for resource_id, resource in resources.items():
            if resource.get("Type") != "AWS::EC2::SecurityGroup":
                continue

            props = resource.get("Properties", {})
            description = props.get("GroupDescription", "")
            if (
                "tigerbeetle" not in description.lower()
                and "tigerbeetle" not in resource_id.lower()
            ):
                continue

            ingress_rules = props.get("SecurityGroupIngress", [])

            for rule in ingress_rules:
                cidr = rule.get("CidrIp", "")
                cidr_ipv6 = rule.get("CidrIpv6", "")
                from_port = rule.get("FromPort")

                # Check for public access to TigerBeetle ports
                is_public = cidr == "0.0.0.0/0" or cidr_ipv6 == "::/0"
                is_tigerbeetle_port = from_port in [
                    TIGERBEETLE_CLIENT_PORT,
                    TIGERBEETLE_REPLICATION_PORT,
                ]

                if is_public and is_tigerbeetle_port:
                    self.add_finding(
                        Finding(
                            severity=FindingSeverity.CRITICAL,
                            code="TB_PUBLIC_ACCESS",
                            message=f"TigerBeetle port {from_port} is publicly accessible",
                            resource=resource_id,
                            remediation="Restrict access to VPC CIDR or specific security groups only.",
                        )
                    )

    def _is_production_environment(self) -> bool:
        """Check if this is a production environment."""
        env_indicators = ["prod", "production", "live"]
        region = self.context.region.lower() if self.context.region else ""
        app_name = self.context.app_name.lower() if self.context.app_name else ""

        # Check context hints
        for indicator in env_indicators:
            if indicator in region or indicator in app_name:
                return True

        # Default to assuming production for safety
        return False
