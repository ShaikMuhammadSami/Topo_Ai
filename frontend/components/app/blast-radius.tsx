"use client";

import React from "react";
import type { BlastRadiusResponse } from "@/lib/topo-types";

type BlastRadiusProps = {
  data: BlastRadiusResponse | null;
};

export function BlastRadius({ data }: BlastRadiusProps) {
  if (!data) return <div>No blast radius data</div>;

  return (
    <section className="rounded-md border border-border bg-background p-4 space-y-4">
      <h3 className="font-bold text-lg">Blast Radius</h3>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
        <div>Direct: {data.direct_impact_count}</div>
        <div>Indirect: {data.indirect_impact_count}</div>
        <div>Potential: {data.potential_impact_count}</div>
        <div>Total: {data.affected_entity_count}</div>
      </div>

      <table className="w-full text-left border-collapse border border-border mt-2">
        <thead>
          <tr className="bg-card/30">
            <th className="px-2 py-1 border">Entity Name</th>
            <th className="px-2 py-1 border">Kind</th>
            <th className="px-2 py-1 border">Namespace</th>
            <th className="px-2 py-1 border">Distance</th>
            <th className="px-2 py-1 border">Impact</th>
            <th className="px-2 py-1 border">Score</th>
            <th className="px-2 py-1 border">Relationship</th>
          </tr>
        </thead>
        <tbody>
          {data.affected_entities.map((entity) => (
            <tr key={entity.entity_id}>
              <td className="px-2 py-1 border">{entity.entity_name}</td>
              <td className="px-2 py-1 border">{entity.entity_kind}</td>
              <td className="px-2 py-1 border">{entity.namespace ?? "—"}</td>
              <td className="px-2 py-1 border">{entity.distance}</td>
              <td className="px-2 py-1 border">{entity.impact}</td>
              <td className="px-2 py-1 border">{entity.impact_score}</td>
              <td className="px-2 py-1 border">{entity.relationship ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}