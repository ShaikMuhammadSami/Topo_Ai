from topo_agent.tetragon_parser import (
    TetragonAggregator,
)


def test_process_connect_is_aggregated(
) -> None:
    aggregator = TetragonAggregator()

    aggregator.ingest(
        {
            "time":
                "2026-07-19T10:00:00+00:00",
            "process_connect": {
                "process": {
                    "exec_id":
                        "exec-one",
                    "pid": 100,
                    "binary":
                        "/usr/bin/curl",
                    "pod": {
                        "namespace":
                            "dedupe-demo",
                        "name":
                            "dedupe-proof",
                        "uid":
                            "pod-uid-one",
                        "container": {
                            "container_id":
                                "containerd://"
                                "abcdef123456",
                        },
                    },
                },
                "destination": {
                    "address":
                        "10.96.0.10",
                    "port": 53,
                },
                "protocol": "udp",
                "dns_name":
                    "orders-api."
                    "dedupe-demo."
                    "svc.cluster.local",
            },
        }
    )

    result = aggregator.build_batch(
        sensor_id="sensor-one",
        node_name="node-one",
        cluster_name="test-cluster",
        version="0.3.0",
        buffered_batch_count=0,
        source_file=(
            "/var/log/tetragon/"
            "tetragon.log"
        ),
        source_file_offset=100,
        heartbeat_interval_seconds=30,
    )

    assert result is not None

    assert len(
        result["dependencies"]
    ) == 1

    dependency = (
        result["dependencies"][0]
    )

    assert (
        dependency["source"]
        ["namespace"]
        == "dedupe-demo"
    )

    assert (
        dependency["destination"]
        ["port"]
        == 53
    )

    assert (
        dependency["destination"]
        ["name"]
        == (
            "orders-api."
            "dedupe-demo."
            "svc.cluster.local"
        )
    )


def test_process_lifecycle_is_aggregated(
) -> None:
    aggregator = TetragonAggregator()

    aggregator.ingest(
        {
            "time":
                "2026-07-19T10:00:00+00:00",
            "process_exec": {
                "process": {
                    "exec_id":
                        "exec-two",
                    "pid": 200,
                    "binary":
                        "/app/server",
                }
            },
        }
    )

    aggregator.ingest(
        {
            "time":
                "2026-07-19T10:00:10+00:00",
            "process_exit": {
                "process": {
                    "exec_id":
                        "exec-two",
                    "pid": 200,
                    "binary":
                        "/app/server",
                },
                "status": 1,
            },
        }
    )

    result = aggregator.build_batch(
        sensor_id="sensor-one",
        node_name="node-one",
        cluster_name="test-cluster",
        version="0.3.0",
        buffered_batch_count=0,
        source_file="tetragon.log",
        source_file_offset=200,
        heartbeat_interval_seconds=30,
    )

    assert result is not None
    assert len(result["processes"]) == 1

    process = result["processes"][0]

    assert process["exec_count"] == 1
    assert process["exit_count"] == 1