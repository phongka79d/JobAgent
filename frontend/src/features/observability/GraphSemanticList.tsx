import {Collapsible} from '@astryxdesign/core/Collapsible';
import {List, ListItem} from '@astryxdesign/core/List';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {GraphSnapshot} from './types';

type GraphSemanticListProps = {
  snapshot: GraphSnapshot;
};

export function GraphSemanticList({snapshot}: GraphSemanticListProps) {
  return (
    <Collapsible trigger="Graph data" defaultIsOpen={false}>
      <VStack gap={2} width="100%">
        <Text type="supporting" color="secondary">
          Server projection: {snapshot.omitted_node_count} omitted nodes and{' '}
          {snapshot.omitted_edge_count} omitted relationships.
        </Text>

        <section data-testid="jobagent-obs-graph-jobs">
          <List density="compact" hasDividers header="Candidate and jobs">
            {snapshot.candidate ? (
              <ListItem
                label="Candidate"
                description={`${snapshot.candidate.id} · revision ${snapshot.candidate.revision}`}
              />
            ) : null}
            {snapshot.jobs.map((job) => (
              <ListItem
                key={job.id}
                label={job.title || job.id}
                description={[job.id, job.company, `revision ${job.revision}`]
                  .filter(Boolean)
                  .join(' · ')}
              />
            ))}
            {!snapshot.candidate && snapshot.jobs.length === 0 ? (
              <ListItem label="No candidate or jobs in snapshot" />
            ) : null}
          </List>
        </section>

        <section data-testid="jobagent-obs-graph-skills">
          <List density="compact" hasDividers header="Skills">
            {snapshot.skills.length > 0 ? (
              snapshot.skills.map((skill) => (
                <ListItem
                  key={skill.canonical_name}
                  label={skill.canonical_name}
                />
              ))
            ) : (
              <ListItem label="No skills in snapshot" />
            )}
          </List>
        </section>

        <section data-testid="jobagent-obs-graph-edges">
          <List density="compact" hasDividers header="Relationships">
            {snapshot.edges.length > 0 ? (
              snapshot.edges.map((edge, index) => (
                <ListItem
                  key={`${edge.type}-${edge.source_id}-${edge.target_id}-${index}`}
                  label={`${edge.source_id} —${edge.type}→ ${edge.target_id}`}
                />
              ))
            ) : (
              <ListItem label="No relationships in snapshot" />
            )}
          </List>
        </section>
      </VStack>
    </Collapsible>
  );
}
