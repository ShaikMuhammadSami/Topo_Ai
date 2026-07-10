"use client";

import React, { useMemo, useState } from "react";
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  NodeMouseHandler,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import type { BlastRadiusResponse, BlastRadiusEntity } from "@/lib/topo-types";

type BlastGraphProps = {
  data: BlastRadiusResponse | null;
  onSelectEntity?: (entity: BlastRadiusEntity) => void;
};

export function BlastRadiusGraph({ data, onSelectEntity }: BlastGraphProps) {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  const nodes: Node[] = useMemo(() => {
    if (!data) return [];

return data.affected_entities.map((e, idx) => ({
  id: e.entity_id,
  data: { label: e.entity_name },
  position: { x: idx * 180, y: e.distance * 120 },
  sourcePosition: Position.Right,
  targetPosition: Position.Left,
  style: {
    border: "2px solid",
    borderColor:
      selectedNode === e.entity_id ? "blue" : "#000",
    padding: 10,
    borderRadius: 8,
    background: "#fff",
    minWidth: 140,
    textAlign: "center",
  },
}));
  }, [data, selectedNode]);

  const edges: Edge[] = useMemo(() => {
    if (!data) return [];

    const result: Edge[] = [];
    data.dependency_paths.forEach((p, idx) => {
      for (let i = 0; i < p.path.length - 1; i++) {
        result.push({
          id: `edge-${idx}-${i}`,
          source: p.path[i],
          target: p.path[i + 1],
          animated: true,
          style: { stroke: "#555" },
        });
      }
    });
    return result;
  }, [data]);

  const handleNodeClick: NodeMouseHandler = (_event, node) => {
    setSelectedNode(node.id);
    if (onSelectEntity && data) {
      const entity = data.affected_entities.find((e) => e.entity_id === node.id);
      if (entity) onSelectEntity(entity);
    }
  };

  if (!data) return <div>No blast radius data available</div>;

  return (
    <div className="w-full h-[500px] rounded-md border border-border bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        onNodeClick={handleNodeClick}
        zoomOnScroll
        panOnScroll
      >
        <Background />
        <MiniMap
          nodeColor={(node) => {
            const entity = data.affected_entities.find((e) => e.entity_id === node.id);
            if (!entity) return "#eee";
            switch (entity.impact) {
              case "direct":
                return "red";
              case "dependent":
                return "yellow";
              case "indirect":
                return "orange";
              case "potential":
                return "blue";
              default:
                return "#ccc";
            }
          }}
        />
        <Controls />
      </ReactFlow>
    </div>
  );
}