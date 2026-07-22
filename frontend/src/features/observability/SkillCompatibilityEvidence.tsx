import {HStack} from '@astryxdesign/core/HStack';
import {List, ListItem} from '@astryxdesign/core/List';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import type {
  SkillCompatibilityItem,
  SkillMapMatchType,
} from '../jobs/types';

export const SKILL_MATCH_PRESENTATION: Record<
  SkillMapMatchType,
  {
    label: string;
    variant: 'success' | 'accent' | 'error' | 'warning' | 'neutral';
  }
> = {
  direct: {label: 'Khớp chính xác', variant: 'success'},
  related: {label: 'Liên quan', variant: 'accent'},
  missing_required: {label: 'Thiếu bắt buộc', variant: 'error'},
  missing_preferred: {label: 'Ưu tiên chưa có', variant: 'warning'},
  candidate_only: {label: 'Kỹ năng bổ sung', variant: 'neutral'},
};

const REQUIREMENT_LABEL = {
  required: 'Bắt buộc trong JD',
  preferred: 'Ưu tiên trong JD',
  none: 'Chỉ có trong CV',
} as const;

type SkillCompatibilityEvidenceProps = {
  item: SkillCompatibilityItem;
};

function EvidenceList({
  header,
  evidence,
  emptyLabel,
}: {
  header: string;
  evidence: readonly string[];
  emptyLabel: string;
}) {
  return (
    <List density="compact" hasDividers header={header}>
      {evidence.length > 0 ? (
        evidence.map((entry, index) => (
          <ListItem key={`${header}-${index}`} label={entry} />
        ))
      ) : (
        <ListItem label={emptyLabel} />
      )}
    </List>
  );
}

export function SkillCompatibilityEvidence({
  item,
}: SkillCompatibilityEvidenceProps) {
  const presentation = SKILL_MATCH_PRESENTATION[item.match_type];
  const candidate = item.candidate_skill;
  const job = item.job_skill;

  return (
    <section
      className="jobagent-skill-map-evidence"
      data-testid="jobagent-skill-map-evidence"
      aria-label="Bằng chứng kỹ năng đang chọn"
    >
      <VStack gap={2} width="100%">
        <Text type="large">Chi tiết kỹ năng</Text>
        <HStack gap={1} align="center">
          <StatusDot
            variant={presentation.variant}
            label={presentation.label}
          />
          <Text type="label">{presentation.label}</Text>
        </HStack>
        <Text type="supporting" color="secondary">
          {REQUIREMENT_LABEL[item.requirement]}
        </Text>
        {candidate ? (
          <Text type="body">CV: {candidate.display_name}</Text>
        ) : null}
        {job ? <Text type="body">JD: {job.display_name}</Text> : null}
        <EvidenceList
          header="Bằng chứng từ CV"
          evidence={candidate?.evidence ?? []}
          emptyLabel="Không có kỹ năng CV được ghép với yêu cầu này."
        />
        <EvidenceList
          header="Bằng chứng từ JD"
          evidence={job?.evidence ?? []}
          emptyLabel="Mục này không có kỹ năng JD tương ứng."
        />
      </VStack>
    </section>
  );
}
