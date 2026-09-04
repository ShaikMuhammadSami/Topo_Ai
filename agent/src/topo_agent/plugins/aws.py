from __future__ import annotations

import logging
import os
from datetime import (
    date,
    datetime,
)
from pathlib import Path
from typing import Any
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    ProfileNotFound,
)

from topo_agent import __version__
from topo_agent.aws_cache import (
    AwsInventoryCache,
)
from topo_agent.config import (
    AgentConfig,
    agent_home,
)
from topo_agent.plugin import (
    PluginCollectionResult,
    PluginDiagnostic,
)
from topo_agent.security import safe_exception_message


LOGGER = logging.getLogger(
    "topo-agent.aws"
)


INVENTORY_KEYS = (
    "aws_regions",
    "aws_vpcs",
    "aws_subnets",
    "aws_route_tables",
    "aws_security_groups",
    "aws_instances",
    "aws_eks_clusters",
    "aws_eks_nodegroups",
    "aws_load_balancers",
    "aws_target_groups",
    "aws_target_health",
    "aws_rds_instances",
    "aws_lambda_functions",
)


def _json_value(
    value: Any,
) -> Any:
    if isinstance(
        value,
        (datetime, date),
    ):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _json_value(item)
            for item in value
        ]

    return value


def _tags(
    values: Any,
) -> dict[str, str]:
    if isinstance(values, dict):
        return {
            str(key): str(value)
            for key, value
            in values.items()
        }

    if not isinstance(values, list):
        return {}

    result: dict[str, str] = {}

    for item in values:
        if not isinstance(item, dict):
            continue

        key = item.get("Key")
        value = item.get("Value")

        if key is not None:
            result[str(key)] = (
                str(value)
                if value is not None
                else ""
            )

    return result


def _name(
    tags: dict[str, str],
    fallback: str,
) -> str:
    return (
        tags.get("Name")
        or fallback
    )


def _chunks(
    values: list[str],
    size: int,
) -> list[list[str]]:
    return [
        values[index:index + size]
        for index
        in range(
            0,
            len(values),
            size,
        )
    ]


def _empty_inventory(
) -> dict[str, list[dict]]:
    return {
        key: []
        for key in INVENTORY_KEYS
    }


def _resource(
    *,
    account_id: str,
    region: str,
    resource_type: str,
    resource_id: str,
    name: str,
    arn: str | None = None,
    status: str | None = None,
    tags: dict[str, str] | None = None,
    vpc_id: str | None = None,
    subnet_ids:
        list[str] | None = None,
    properties:
        dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "provider": "aws",
        "account_id": account_id,
        "region": region,
        "resource_type":
            resource_type,
        "resource_id": resource_id,
        "name": name,
        "arn": arn,
        "status": status,
        "tags": tags or {},
        "vpc_id": vpc_id,
        "subnet_ids":
            subnet_ids or [],
        "properties": _json_value(
            properties or {}
        ),
    }


class AwsSessionFactory:
    def __init__(
        self,
        config: AgentConfig,
    ) -> None:
        self.config = config

        self.sdk_config = Config(
            retries={
                "max_attempts": max(
                    config
                    .aws_api_max_attempts,
                    1,
                ),
                "mode": "standard",
            },
            user_agent_extra=(
                f"topo-agent/"
                f"{__version__}"
            ),
        )

        base_arguments: dict[
            str,
            Any,
        ] = {}

        if config.aws_profile:
            base_arguments[
                "profile_name"
            ] = config.aws_profile

        self.base_session = (
            boto3.Session(
                **base_arguments
            )
        )

        self.session = (
            self._assumed_session()
            if config.aws_role_arn
            else self.base_session
        )

    def _assumed_session(
        self,
    ) -> boto3.Session:
        arguments: dict[
            str,
            Any,
        ] = {
            "RoleArn":
                self.config
                .aws_role_arn,
            "RoleSessionName":
                self.config
                .aws_role_session_name,
        }

        if self.config.aws_external_id:
            arguments["ExternalId"] = (
                self.config
                .aws_external_id
            )

        sts = self.base_session.client(
            "sts",
            config=self.sdk_config,
        )

        response = sts.assume_role(
            **arguments
        )

        credentials = response[
            "Credentials"
        ]

        return boto3.Session(
            aws_access_key_id=(
                credentials[
                    "AccessKeyId"
                ]
            ),
            aws_secret_access_key=(
                credentials[
                    "SecretAccessKey"
                ]
            ),
            aws_session_token=(
                credentials[
                    "SessionToken"
                ]
            ),
            region_name=(
                self.base_session
                .region_name
            ),
        )

    def client(
        self,
        service_name: str,
        *,
        region: str | None = None,
    ):
        return self.session.client(
            service_name,
            region_name=region,
            config=self.sdk_config,
        )


class AwsPlugin:
    name = "aws"
    version = __version__

    capabilities = (
        "aws.identity",
        "aws.regions",
        "aws.vpc",
        "aws.subnets",
        "aws.route_tables",
        "aws.security_groups",
        "aws.ec2",
        "aws.eks",
        "aws.elbv2",
        "aws.rds",
        "aws.lambda",
        "aws.tags",
    )

    def __init__(
        self,
        config: AgentConfig,
    ) -> None:
        self.config = config

        self.factory = AwsSessionFactory(
            config
        )

        self.cache = AwsInventoryCache(
            (
                agent_home()
                / "cache"
                / "aws"
            ),
            ttl_seconds=(
                config
                .aws_cache_ttl_seconds
            ),
        )

    def close(
        self,
    ) -> None:
        return None

    def _identity(
        self,
    ) -> dict[str, str]:
        sts = self.factory.client(
            "sts"
        )

        result = (
            sts.get_caller_identity()
        )

        return {
            "account_id": str(
                result["Account"]
            ),
            "principal_arn": str(
                result["Arn"]
            ),
            "user_id": str(
                result["UserId"]
            ),
        }

    def _regions(
        self,
    ) -> list[str]:
        if self.config.aws_regions:
            return sorted(
                set(
                    self.config
                    .aws_regions
                )
            )

        if (
            self.config
            .aws_discover_regions
        ):
            initial_region = (
                self.factory
                .session.region_name
                or os.getenv(
                    "AWS_REGION"
                )
                or os.getenv(
                    "AWS_DEFAULT_REGION"
                )
                or "us-east-1"
            )

            ec2 = self.factory.client(
                "ec2",
                region=initial_region,
            )

            response = (
                ec2.describe_regions(
                    AllRegions=False
                )
            )

            values = [
                str(item["RegionName"])
                for item in response.get(
                    "Regions",
                    [],
                )
                if item.get(
                    "RegionName"
                )
            ]

            if values:
                return sorted(
                    set(values)
                )

        configured_region = (
            self.factory.session.region_name
            or os.getenv("AWS_REGION")
            or os.getenv(
                "AWS_DEFAULT_REGION"
            )
        )

        if configured_region:
            return [configured_region]

        return ["us-east-1"]

    def doctor(
        self,
    ) -> PluginDiagnostic:
        try:
            identity = self._identity()
            regions = self._regions()

        except (
            NoCredentialsError,
            ProfileNotFound,
            BotoCoreError,
            ClientError,
        ) as exc:
            return PluginDiagnostic(
                name=self.name,
                status="failed",
                message=safe_exception_message(exc, "AWS discovery failed"),
                capabilities=list(
                    self.capabilities
                ),
            )

        return PluginDiagnostic(
            name=self.name,
            status="available",
            capabilities=list(
                self.capabilities
            ),
            details={
                **identity,
                "regions": regions,
                "profile": (
                    self.config.aws_profile
                ),
                "assume_role": bool(
                    self.config
                    .aws_role_arn
                ),
                "credential_method":
                    "aws-sdk-provider-chain",
            },
        )

    def _ec2_inventory(
        self,
        *,
        account_id: str,
        region: str,
    ) -> dict[str, list[dict]]:
        client = self.factory.client(
            "ec2",
            region=region,
        )

        result = _empty_inventory()

        for page in client.get_paginator(
            "describe_vpcs"
        ).paginate():
            for value in page.get(
                "Vpcs",
                [],
            ):
                tags = _tags(
                    value.get("Tags")
                )

                vpc_id = str(
                    value["VpcId"]
                )

                result[
                    "aws_vpcs"
                ].append(
                    _resource(
                        account_id=(
                            account_id
                        ),
                        region=region,
                        resource_type=(
                            "aws_vpc"
                        ),
                        resource_id=vpc_id,
                        name=_name(
                            tags,
                            vpc_id,
                        ),
                        status=value.get(
                            "State"
                        ),
                        tags=tags,
                        vpc_id=vpc_id,
                        properties={
                            "cidr_block":
                                value.get(
                                    "CidrBlock"
                                ),
                            "is_default":
                                value.get(
                                    "IsDefault"
                                ),
                            "dhcp_options_id":
                                value.get(
                                    "DhcpOptionsId"
                                ),
                            "ipv6_cidr_blocks":
                                value.get(
                                    "Ipv6CidrBlockAssociationSet",
                                    [],
                                ),
                        },
                    )
                )

        for page in client.get_paginator(
            "describe_subnets"
        ).paginate():
            for value in page.get(
                "Subnets",
                [],
            ):
                tags = _tags(
                    value.get("Tags")
                )

                subnet_id = str(
                    value["SubnetId"]
                )

                result[
                    "aws_subnets"
                ].append(
                    _resource(
                        account_id=(
                            account_id
                        ),
                        region=region,
                        resource_type=(
                            "aws_subnet"
                        ),
                        resource_id=(
                            subnet_id
                        ),
                        name=_name(
                            tags,
                            subnet_id,
                        ),
                        status=value.get(
                            "State"
                        ),
                        tags=tags,
                        vpc_id=value.get(
                            "VpcId"
                        ),
                        subnet_ids=[
                            subnet_id
                        ],
                        properties={
                            "availability_zone":
                                value.get(
                                    "AvailabilityZone"
                                ),
                            "cidr_block":
                                value.get(
                                    "CidrBlock"
                                ),
                            "available_ip_count":
                                value.get(
                                    "AvailableIpAddressCount"
                                ),
                            "map_public_ip":
                                value.get(
                                    "MapPublicIpOnLaunch"
                                ),
                            "owner_id":
                                value.get(
                                    "OwnerId"
                                ),
                        },
                    )
                )

        for page in client.get_paginator(
            "describe_route_tables"
        ).paginate():
            for value in page.get(
                "RouteTables",
                [],
            ):
                tags = _tags(
                    value.get("Tags")
                )

                resource_id = str(
                    value[
                        "RouteTableId"
                    ]
                )

                subnet_ids = [
                    str(
                        association[
                            "SubnetId"
                        ]
                    )
                    for association in (
                        value.get(
                            "Associations",
                            [],
                        )
                    )
                    if association.get(
                        "SubnetId"
                    )
                ]

                result[
                    "aws_route_tables"
                ].append(
                    _resource(
                        account_id=(
                            account_id
                        ),
                        region=region,
                        resource_type=(
                            "aws_route_table"
                        ),
                        resource_id=(
                            resource_id
                        ),
                        name=_name(
                            tags,
                            resource_id,
                        ),
                        tags=tags,
                        vpc_id=value.get(
                            "VpcId"
                        ),
                        subnet_ids=(
                            subnet_ids
                        ),
                        properties={
                            "routes":
                                value.get(
                                    "Routes",
                                    [],
                                ),
                            "associations":
                                value.get(
                                    "Associations",
                                    [],
                                ),
                        },
                    )
                )

        for page in client.get_paginator(
            "describe_security_groups"
        ).paginate():
            for value in page.get(
                "SecurityGroups",
                [],
            ):
                tags = _tags(
                    value.get("Tags")
                )

                resource_id = str(
                    value["GroupId"]
                )

                result[
                    "aws_security_groups"
                ].append(
                    _resource(
                        account_id=(
                            account_id
                        ),
                        region=region,
                        resource_type=(
                            "aws_security_group"
                        ),
                        resource_id=(
                            resource_id
                        ),
                        name=(
                            value.get(
                                "GroupName"
                            )
                            or resource_id
                        ),
                        tags=tags,
                        vpc_id=value.get(
                            "VpcId"
                        ),
                        properties={
                            "description":
                                value.get(
                                    "Description"
                                ),
                            "ingress":
                                value.get(
                                    "IpPermissions",
                                    [],
                                ),
                            "egress":
                                value.get(
                                    "IpPermissionsEgress",
                                    [],
                                ),
                        },
                    )
                )

        for page in client.get_paginator(
            "describe_instances"
        ).paginate():
            for reservation in page.get(
                "Reservations",
                [],
            ):
                for value in reservation.get(
                    "Instances",
                    [],
                ):
                    tags = _tags(
                        value.get("Tags")
                    )

                    resource_id = str(
                        value[
                            "InstanceId"
                        ]
                    )

                    security_group_ids = [
                        str(item["GroupId"])
                        for item in value.get(
                            "SecurityGroups",
                            [],
                        )
                        if item.get(
                            "GroupId"
                        )
                    ]

                    result[
                        "aws_instances"
                    ].append(
                        _resource(
                            account_id=(
                                account_id
                            ),
                            region=region,
                            resource_type=(
                                "aws_ec2_instance"
                            ),
                            resource_id=(
                                resource_id
                            ),
                            name=_name(
                                tags,
                                resource_id,
                            ),
                            status=(
                                value.get(
                                    "State",
                                    {},
                                ).get(
                                    "Name"
                                )
                            ),
                            tags=tags,
                            vpc_id=value.get(
                                "VpcId"
                            ),
                            subnet_ids=[
                                str(
                                    value[
                                        "SubnetId"
                                    ]
                                )
                            ]
                            if value.get(
                                "SubnetId"
                            )
                            else [],
                            properties={
                                "instance_type":
                                    value.get(
                                        "InstanceType"
                                    ),
                                "availability_zone":
                                    value.get(
                                        "Placement",
                                        {},
                                    ).get(
                                        "AvailabilityZone"
                                    ),
                                "private_ip":
                                    value.get(
                                        "PrivateIpAddress"
                                    ),
                                "private_dns":
                                    value.get(
                                        "PrivateDnsName"
                                    ),
                                "public_ip":
                                    value.get(
                                        "PublicIpAddress"
                                    ),
                                "platform_details":
                                    value.get(
                                        "PlatformDetails"
                                    ),
                                "architecture":
                                    value.get(
                                        "Architecture"
                                    ),
                                "image_id":
                                    value.get(
                                        "ImageId"
                                    ),
                                "security_group_ids":
                                    security_group_ids,
                            },
                        )
                    )

        return result

    def _eks_inventory(
        self,
        *,
        account_id: str,
        region: str,
    ) -> dict[str, list[dict]]:
        client = self.factory.client(
            "eks",
            region=region,
        )

        result = _empty_inventory()

        cluster_names: list[str] = []

        for page in client.get_paginator(
            "list_clusters"
        ).paginate():
            cluster_names.extend(
                str(item)
                for item in page.get(
                    "clusters",
                    []
                )
            )

        for cluster_name in cluster_names:
            cluster = client.describe_cluster(
                name=cluster_name
            )["cluster"]

            resources = cluster.get(
                "resourcesVpcConfig",
                {},
            )

            cluster_arn = str(
                cluster["arn"]
            )

            security_group_ids = [
                str(item)
                for item in resources.get(
                    "securityGroupIds",
                    [],
                )
            ]

            cluster_security_group = (
                resources.get(
                    "clusterSecurityGroupId"
                )
            )

            if cluster_security_group:
                security_group_ids.append(
                    str(
                        cluster_security_group
                    )
                )

            result[
                "aws_eks_clusters"
            ].append(
                _resource(
                    account_id=account_id,
                    region=region,
                    resource_type=(
                        "aws_eks_cluster"
                    ),
                    resource_id=(
                        cluster_name
                    ),
                    name=cluster_name,
                    arn=cluster_arn,
                    status=cluster.get(
                        "status"
                    ),
                    tags=_tags(
                        cluster.get("tags")
                    ),
                    vpc_id=resources.get(
                        "vpcId"
                    ),
                    subnet_ids=[
                        str(item)
                        for item in (
                            resources.get(
                                "subnetIds",
                                [],
                            )
                        )
                    ],
                    properties={
                        "version":
                            cluster.get(
                                "version"
                            ),
                        "endpoint":
                            cluster.get(
                                "endpoint"
                            ),
                        "role_arn":
                            cluster.get(
                                "roleArn"
                            ),
                        "platform_version":
                            cluster.get(
                                "platformVersion"
                            ),
                        "security_group_ids":
                            sorted(
                                set(
                                    security_group_ids
                                )
                            ),
                        "identity":
                            cluster.get(
                                "identity",
                                {},
                            ),
                    },
                )
            )

            nodegroup_names: list[str] = []

            paginator = (
                client.get_paginator(
                    "list_nodegroups"
                )
            )

            for page in paginator.paginate(
                clusterName=cluster_name
            ):
                nodegroup_names.extend(
                    str(item)
                    for item in page.get(
                        "nodegroups",
                        [],
                    )
                )

            for nodegroup_name in (
                nodegroup_names
            ):
                nodegroup = (
                    client.describe_nodegroup(
                        clusterName=(
                            cluster_name
                        ),
                        nodegroupName=(
                            nodegroup_name
                        ),
                    )["nodegroup"]
                )

                result[
                    "aws_eks_nodegroups"
                ].append(
                    _resource(
                        account_id=(
                            account_id
                        ),
                        region=region,
                        resource_type=(
                            "aws_eks_nodegroup"
                        ),
                        resource_id=(
                            f"{cluster_name}/"
                            f"{nodegroup_name}"
                        ),
                        name=nodegroup_name,
                        arn=nodegroup.get(
                            "nodegroupArn"
                        ),
                        status=nodegroup.get(
                            "status"
                        ),
                        tags=_tags(
                            nodegroup.get(
                                "tags"
                            )
                        ),
                        subnet_ids=[
                            str(item)
                            for item in (
                                nodegroup.get(
                                    "subnets",
                                    [],
                                )
                            )
                        ],
                        properties={
                            "cluster_name":
                                cluster_name,
                            "node_role":
                                nodegroup.get(
                                    "nodeRole"
                                ),
                            "instance_types":
                                nodegroup.get(
                                    "instanceTypes",
                                    [],
                                ),
                            "ami_type":
                                nodegroup.get(
                                    "amiType"
                                ),
                            "capacity_type":
                                nodegroup.get(
                                    "capacityType"
                                ),
                            "scaling_config":
                                nodegroup.get(
                                    "scalingConfig",
                                    {},
                                ),
                            "resources":
                                nodegroup.get(
                                    "resources",
                                    {},
                                ),
                        },
                    )
                )

        return result

    def _load_balancer_tags(
        self,
        client,
        arns: list[str],
    ) -> dict[str, dict[str, str]]:
        result: dict[
            str,
            dict[str, str],
        ] = {}

        for batch in _chunks(
            arns,
            20,
        ):
            response = (
                client.describe_tags(
                    ResourceArns=batch
                )
            )

            for item in response.get(
                "TagDescriptions",
                [],
            ):
                arn = item.get(
                    "ResourceArn"
                )

                if arn:
                    result[str(arn)] = (
                        _tags(
                            item.get("Tags")
                        )
                    )

        return result

    def _elbv2_inventory(
        self,
        *,
        account_id: str,
        region: str,
    ) -> dict[str, list[dict]]:
        client = self.factory.client(
            "elbv2",
            region=region,
        )

        result = _empty_inventory()

        load_balancers: list[
            dict[str, Any]
        ] = []

        for page in client.get_paginator(
            "describe_load_balancers"
        ).paginate():
            load_balancers.extend(
                page.get(
                    "LoadBalancers",
                    [],
                )
            )

        load_balancer_tags = (
            self._load_balancer_tags(
                client,
                [
                    str(item[
                        "LoadBalancerArn"
                    ])
                    for item in load_balancers
                ],
            )
            if load_balancers
            else {}
        )

        for value in load_balancers:
            arn = str(
                value[
                    "LoadBalancerArn"
                ]
            )

            tags = (
                load_balancer_tags.get(
                    arn,
                    {},
                )
            )

            subnet_ids = [
                str(
                    item["SubnetId"]
                )
                for item in value.get(
                    "AvailabilityZones",
                    [],
                )
                if item.get("SubnetId")
            ]

            result[
                "aws_load_balancers"
            ].append(
                _resource(
                    account_id=account_id,
                    region=region,
                    resource_type=(
                        "aws_load_balancer"
                    ),
                    resource_id=arn,
                    name=str(
                        value.get(
                            "LoadBalancerName"
                        )
                        or arn
                    ),
                    arn=arn,
                    status=(
                        value.get(
                            "State",
                            {},
                        ).get("Code")
                    ),
                    tags=tags,
                    vpc_id=value.get(
                        "VpcId"
                    ),
                    subnet_ids=subnet_ids,
                    properties={
                        "dns_name":
                            value.get(
                                "DNSName"
                            ),
                        "scheme":
                            value.get(
                                "Scheme"
                            ),
                        "type":
                            value.get(
                                "Type"
                            ),
                        "ip_address_type":
                            value.get(
                                "IpAddressType"
                            ),
                        "security_group_ids":
                            value.get(
                                "SecurityGroups",
                                [],
                            ),
                    },
                )
            )

        target_groups: list[
            dict[str, Any]
        ] = []

        for page in client.get_paginator(
            "describe_target_groups"
        ).paginate():
            target_groups.extend(
                page.get(
                    "TargetGroups",
                    [],
                )
            )

        target_group_tags = (
            self._load_balancer_tags(
                client,
                [
                    str(item[
                        "TargetGroupArn"
                    ])
                    for item in target_groups
                ],
            )
            if target_groups
            else {}
        )

        for value in target_groups:
            arn = str(
                value["TargetGroupArn"]
            )

            result[
                "aws_target_groups"
            ].append(
                _resource(
                    account_id=account_id,
                    region=region,
                    resource_type=(
                        "aws_target_group"
                    ),
                    resource_id=arn,
                    name=str(
                        value.get(
                            "TargetGroupName"
                        )
                        or arn
                    ),
                    arn=arn,
                    tags=(
                        target_group_tags
                        .get(arn, {})
                    ),
                    vpc_id=value.get(
                        "VpcId"
                    ),
                    properties={
                        "protocol":
                            value.get(
                                "Protocol"
                            ),
                        "port":
                            value.get(
                                "Port"
                            ),
                        "protocol_version":
                            value.get(
                                "ProtocolVersion"
                            ),
                        "target_type":
                            value.get(
                                "TargetType"
                            ),
                        "load_balancer_arns":
                            value.get(
                                "LoadBalancerArns",
                                [],
                            ),
                        "health_check":
                            {
                                "protocol":
                                    value.get(
                                        "HealthCheckProtocol"
                                    ),
                                "port":
                                    value.get(
                                        "HealthCheckPort"
                                    ),
                                "path":
                                    value.get(
                                        "HealthCheckPath"
                                    ),
                            },
                    },
                )
            )

            health = (
                client
                .describe_target_health(
                    TargetGroupArn=arn
                )
            )

            for description in (
                health.get(
                    "TargetHealthDescriptions",
                    [],
                )
            ):
                target = description.get(
                    "Target",
                    {},
                )

                target_health = (
                    description.get(
                        "TargetHealth",
                        {},
                    )
                )

                target_id = str(
                    target.get("Id")
                    or "unknown"
                )

                target_port = (
                    target.get("Port")
                )

                resource_id = (
                    f"{arn}|"
                    f"{target_id}|"
                    f"{target_port}"
                )

                result[
                    "aws_target_health"
                ].append(
                    _resource(
                        account_id=(
                            account_id
                        ),
                        region=region,
                        resource_type=(
                            "aws_target_health"
                        ),
                        resource_id=(
                            resource_id
                        ),
                        name=target_id,
                        status=(
                            target_health.get(
                                "State"
                            )
                        ),
                        properties={
                            "target_group_arn":
                                arn,
                            "target_id":
                                target_id,
                            "target_port":
                                target_port,
                            "availability_zone":
                                target.get(
                                    "AvailabilityZone"
                                ),
                            "reason":
                                target_health.get(
                                    "Reason"
                                ),
                            "description":
                                target_health.get(
                                    "Description"
                                ),
                        },
                    )
                )

        return result

    def _rds_inventory(
        self,
        *,
        account_id: str,
        region: str,
    ) -> dict[str, list[dict]]:
        client = self.factory.client(
            "rds",
            region=region,
        )

        result = _empty_inventory()

        for page in client.get_paginator(
            "describe_db_instances"
        ).paginate():
            for value in page.get(
                "DBInstances",
                [],
            ):
                arn = value.get(
                    "DBInstanceArn"
                )

                tags: dict[
                    str,
                    str,
                ] = {}

                if arn:
                    tags = _tags(
                        client
                        .list_tags_for_resource(
                            ResourceName=arn
                        )
                        .get(
                            "TagList",
                            [],
                        )
                    )

                subnet_group = value.get(
                    "DBSubnetGroup",
                    {},
                )

                subnet_ids = [
                    str(
                        item.get(
                            "SubnetIdentifier"
                        )
                    )
                    for item in (
                        subnet_group.get(
                            "Subnets",
                            [],
                        )
                    )
                    if item.get(
                        "SubnetIdentifier"
                    )
                ]

                security_group_ids = [
                    str(
                        item.get(
                            "VpcSecurityGroupId"
                        )
                    )
                    for item in (
                        value.get(
                            "VpcSecurityGroups",
                            [],
                        )
                    )
                    if item.get(
                        "VpcSecurityGroupId"
                    )
                ]

                endpoint = value.get(
                    "Endpoint",
                    {},
                )

                resource_id = str(
                    value[
                        "DBInstanceIdentifier"
                    ]
                )

                result[
                    "aws_rds_instances"
                ].append(
                    _resource(
                        account_id=(
                            account_id
                        ),
                        region=region,
                        resource_type=(
                            "aws_rds_instance"
                        ),
                        resource_id=(
                            resource_id
                        ),
                        name=_name(
                            tags,
                            resource_id,
                        ),
                        arn=(
                            str(arn)
                            if arn
                            else None
                        ),
                        status=value.get(
                            "DBInstanceStatus"
                        ),
                        tags=tags,
                        vpc_id=(
                            subnet_group.get(
                                "VpcId"
                            )
                        ),
                        subnet_ids=(
                            subnet_ids
                        ),
                        properties={
                            "engine":
                                value.get(
                                    "Engine"
                                ),
                            "engine_version":
                                value.get(
                                    "EngineVersion"
                                ),
                            "instance_class":
                                value.get(
                                    "DBInstanceClass"
                                ),
                            "multi_az":
                                value.get(
                                    "MultiAZ"
                                ),
                            "publicly_accessible":
                                value.get(
                                    "PubliclyAccessible"
                                ),
                            "endpoint_address":
                                endpoint.get(
                                    "Address"
                                ),
                            "endpoint_port":
                                endpoint.get(
                                    "Port"
                                ),
                            "security_group_ids":
                                security_group_ids,
                        },
                    )
                )

        return result

    def _lambda_inventory(
        self,
        *,
        account_id: str,
        region: str,
    ) -> dict[str, list[dict]]:
        client = self.factory.client(
            "lambda",
            region=region,
        )

        result = _empty_inventory()

        for page in client.get_paginator(
            "list_functions"
        ).paginate():
            for value in page.get(
                "Functions",
                [],
            ):
                arn = str(
                    value[
                        "FunctionArn"
                    ]
                )

                tags = _tags(
                    client.list_tags(
                        Resource=arn
                    ).get(
                        "Tags",
                        {},
                    )
                )

                vpc_config = value.get(
                    "VpcConfig",
                    {},
                )

                function_name = str(
                    value[
                        "FunctionName"
                    ]
                )

                result[
                    "aws_lambda_functions"
                ].append(
                    _resource(
                        account_id=(
                            account_id
                        ),
                        region=region,
                        resource_type=(
                            "aws_lambda_function"
                        ),
                        resource_id=(
                            function_name
                        ),
                        name=_name(
                            tags,
                            function_name,
                        ),
                        arn=arn,
                        status=value.get(
                            "State"
                        ),
                        tags=tags,
                        vpc_id=vpc_config.get(
                            "VpcId"
                        ),
                        subnet_ids=[
                            str(item)
                            for item in (
                                vpc_config.get(
                                    "SubnetIds",
                                    [],
                                )
                            )
                        ],
                        properties={
                            "runtime":
                                value.get(
                                    "Runtime"
                                ),
                            "handler":
                                value.get(
                                    "Handler"
                                ),
                            "role_arn":
                                value.get(
                                    "Role"
                                ),
                            "memory_size":
                                value.get(
                                    "MemorySize"
                                ),
                            "timeout":
                                value.get(
                                    "Timeout"
                                ),
                            "package_type":
                                value.get(
                                    "PackageType"
                                ),
                            "architectures":
                                value.get(
                                    "Architectures",
                                    [],
                                ),
                            "security_group_ids":
                                vpc_config.get(
                                    "SecurityGroupIds",
                                    [],
                                ),
                        },
                    )
                )

        return result

    @staticmethod
    def _merge(
        destination:
            dict[str, list[dict]],
        source:
            dict[str, list[dict]],
    ) -> None:
        for key, values in (
            source.items()
        ):
            destination.setdefault(
                key,
                [],
            )

            destination[key].extend(
                values
            )

    def _collect_region(
        self,
        *,
        account_id: str,
        region: str,
    ) -> tuple[
        dict[str, list[dict]],
        list[str],
    ]:
        cached = self.cache.load(
            account_id=account_id,
            region=region,
        )

        if cached is not None:
            inventory = cached[
                "inventory"
            ]

            inventory.setdefault(
                "aws_regions",
                [],
            )

            inventory[
                "aws_regions"
            ].append(
                _resource(
                    account_id=(
                        account_id
                    ),
                    region=region,
                    resource_type=(
                        "aws_region"
                    ),
                    resource_id=region,
                    name=region,
                    status="enabled",
                    properties={
                        "cached": True,
                        "cache_age_seconds":
                            cached[
                                "age_seconds"
                            ],
                    },
                )
            )

            return inventory, []

        inventory = _empty_inventory()

        inventory[
            "aws_regions"
        ].append(
            _resource(
                account_id=account_id,
                region=region,
                resource_type=(
                    "aws_region"
                ),
                resource_id=region,
                name=region,
                status="enabled",
            )
        )

        errors: list[str] = []

        collectors = (
            (
                "ec2",
                self._ec2_inventory,
            ),
            (
                "eks",
                self._eks_inventory,
            ),
            (
                "elbv2",
                self._elbv2_inventory,
            ),
            (
                "rds",
                self._rds_inventory,
            ),
            (
                "lambda",
                self._lambda_inventory,
            ),
        )

        successful_collectors = 0

        for (
            service_name,
            collector,
        ) in collectors:
            try:
                service_inventory = (
                    collector(
                        account_id=(
                            account_id
                        ),
                        region=region,
                    )
                )

                self._merge(
                    inventory,
                    service_inventory,
                )

                successful_collectors += 1

            except (
                ClientError,
                BotoCoreError,
            ) as exc:
                errors.append(
                    safe_exception_message(
                        exc,
                        f"AWS service collection failed for {region}/{service_name}",
                    )
                )

                LOGGER.warning(
                    "AWS service collection "
                    "failed for %s/%s: %s",
                    region,
                    service_name,
                    type(exc).__name__,
                )

        if successful_collectors:
            self.cache.save(
                account_id=account_id,
                region=region,
                inventory=inventory,
            )

            return inventory, errors

        stale = self.cache.load(
            account_id=account_id,
            region=region,
            allow_stale=True,
        )

        if stale is not None:
            errors.append(
                f"{region}: using stale "
                "AWS inventory cache"
            )

            return (
                stale["inventory"],
                errors,
            )

        return inventory, errors

    def collect(
        self,
    ) -> PluginCollectionResult:
        identity = self._identity()

        account_id = identity[
            "account_id"
        ]

        regions = self._regions()

        inventory = _empty_inventory()

        inventory["aws_accounts"] = [
            {
                "provider": "aws",
                "account_id":
                    account_id,
                "resource_type":
                    "aws_account",
                "resource_id":
                    account_id,
                "name": account_id,
                "arn": (
                    f"arn:aws:iam::"
                    f"{account_id}:root"
                ),
                "status": "available",
                "tags": {},
                "region": "global",
                "vpc_id": None,
                "subnet_ids": [],
                "properties": {
                    "principal_arn":
                        identity[
                            "principal_arn"
                        ],
                    "user_id":
                        identity[
                            "user_id"
                        ],
                },
            }
        ]

        errors: list[str] = []

        region_status: list[
            dict[str, Any]
        ] = []

        for region in regions:
            region_inventory, (
                region_errors
            ) = self._collect_region(
                account_id=account_id,
                region=region,
            )

            self._merge(
                inventory,
                region_inventory,
            )

            errors.extend(
                region_errors
            )

            region_status.append(
                {
                    "region": region,
                    "status": (
                        "partial"
                        if region_errors
                        else "success"
                    ),
                    "errors":
                        region_errors,
                }
            )

        resource_count = sum(
            len(values)
            for key, values
            in inventory.items()
            if key != "aws_accounts"
        )

        return PluginCollectionResult(
            plugin_name=self.name,
            status=(
                "partial"
                if errors
                else "success"
            ),
            inventory=inventory,
            capabilities=list(
                self.capabilities
            ),
            errors=errors,
            metadata={
                "provider": "aws",
                "account_id":
                    account_id,
                "principal_arn":
                    identity[
                        "principal_arn"
                    ],
                "regions": regions,
                "region_status":
                    region_status,
                "resource_count":
                    resource_count,
                "collection_id":
                    (
                        "aws-collection:"
                        + uuid4().hex
                    ),
            },
        )
