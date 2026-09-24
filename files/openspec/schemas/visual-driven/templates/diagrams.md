## Diagram needed?

<!-- YES or NO. A visual concern exists when the change affects navigation/routing
     flow, a state machine, data flow, infrastructure topology, or a data schema.
     If NO, add a one-line reason below and STOP - do not add any other sections. -->

YES

<!-- If NO, replace the line above with: NO - <one-line reason> -->

## Placement

<!-- REQUIRED for a YES gate. One row per diagram this change touches. It tells the
     archive merge exactly which Source of Truth file to change, and how. It is
     never merged itself.

     Source of Truth file: a path under openspec/, e.g. specs/architecture/diagrams.md
     (cross-cutting) or specs/<capability>/diagrams.md (capability-owned).
     Ownership: a diagram belongs to the capability whose behaviour it shows. If
     this change CREATES a capability, its new flows go in that capability's own
     diagrams.md - and if an existing diagram now belongs there, move it.

     Why here: REQUIRED when the row adds or moves a diagram INTO
     specs/architecture/diagrams.md - say which capabilities it spans. Leave it
     empty for every other row.

     Action:
       update                 - replace the section. Before copied from that file.
       add                    - new diagram, appended (file created if needed). No Before.
       move from <old file>   - delete from <old file>, add to this file.
                                Before copied from <old file>.
       remove                 - delete the section (and the file if nothing is left).
                                Before copied from that file. NO After section. -->

| Stable name | Source of Truth file | Action | Why here |
|---|---|---|---|
| <Stable Name> | specs/<capability>/diagrams.md | update | |

## Before State

<!-- Verbatim copy of each `## <Stable Name>` section whose row is update, move or
     remove, as `### <Stable Name>`. Copy from the file the row names (for a move,
     from the old file). Nothing else. -->

## After State

<!-- One `### <Stable Name>` section per update, add or move row: a short
     description, then a ```mermaid block. Follow docs/MERMAID_RULES.md.
     Removed diagrams have no After section.
     Diagram type by concern:
     - sequenceDiagram  -> navigation and routing flows
     - stateDiagram-v2  -> state machines (BLoC/Cubit, Redux, XState, workflow states)
     - flowchart        -> infrastructure and system topology
     - erDiagram        -> data schemas -->

<!-- If implementation later deviates from the proposed After State, add a
     top-level `## Deviations` section (a sibling of Before/After State, NOT a
     merge target) recording: what was proposed, what was built, and why. Do NOT
     keep a parallel "expected" diagram. See docs/VSDD.md "Deviations". -->
