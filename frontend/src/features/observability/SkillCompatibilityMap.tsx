import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {HStack} from '@astryxdesign/core/HStack';
import {List, ListItem} from '@astryxdesign/core/List';
import {Skeleton} from '@astryxdesign/core/Skeleton';
import {StatusDot} from '@astryxdesign/core/StatusDot';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {useState} from 'react';

import type {CachedResource} from '../jobs/savedJobsState';
import type {
  SelectedJobSkillMap,
  SkillCompatibilityItem,
  SkillMapMatchType,
} from '../jobs/types';
import {formatObservabilityDateTime} from './observabilityFormat';
import {
  SKILL_MATCH_PRESENTATION,
  SkillCompatibilityEvidence,
} from './SkillCompatibilityEvidence';

const FILTER_ORDER: readonly SkillMapMatchType[] = [
  'direct',
  'related',
  'missing_required',
  'missing_preferred',
  'candidate_only',
];

type SkillCompatibilityMapProps = {
  selectedJobId: string | null;
  resource: CachedResource<SelectedJobSkillMap> | null;
};

function MapLoading() {
  return (
    <VStack
      gap={2}
      width="100%"
      data-testid="jobagent-skill-map-loading"
      aria-live="polite"
    >
      <Text type="supporting">Đang tải bản đồ kỹ năng…</Text>
      <Skeleton width="65%" height="var(--spacing-3)" radius={1} />
      <Skeleton width="100%" height="var(--spacing-8)" radius={2} index={1} />
    </VStack>
  );
}

function itemLabel(item: SkillCompatibilityItem): string {
  return (
    item.job_skill?.display_name ??
    item.candidate_skill?.display_name ??
    SKILL_MATCH_PRESENTATION[item.match_type].label
  );
}

function itemDescription(item: SkillCompatibilityItem): string {
  const candidate = item.candidate_skill?.display_name;
  const job = item.job_skill?.display_name;
  if (candidate && job && candidate !== job) {
    return `${candidate} → ${job}`;
  }
  if (item.requirement === 'required') return 'Yêu cầu bắt buộc';
  if (item.requirement === 'preferred') return 'Yêu cầu ưu tiên';
  return 'Kỹ năng bổ sung trong CV';
}

function statusMessage(map: SelectedJobSkillMap) {
  if (map.status === 'ready') return null;
  return (
    <Banner
      status={map.status === 'stale' ? 'warning' : 'error'}
      title={
        map.status === 'stale'
          ? 'Bản đồ cần được xây dựng lại'
          : 'Không thể đọc bản đồ lúc này'
      }
      description={[map.summary, map.rebuild_instruction]
        .filter(Boolean)
        .join(' ')}
      container="card"
      data-testid={`jobagent-skill-map-status-${map.status}`}
    />
  );
}

export function SkillCompatibilityMap({
  selectedJobId,
  resource,
}: SkillCompatibilityMapProps) {
  const [filter, setFilter] = useState<SkillMapMatchType | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);

  if (!selectedJobId) {
    return (
      <EmptyState
        title="Chưa chọn JD"
        description="Chọn một JD trong danh sách đã lưu để xem độ phù hợp với CV đang hoạt động."
        isCompact
      />
    );
  }
  if (!resource || (resource.phase === 'loading' && !resource.data)) {
    return <MapLoading />;
  }
  if (resource.phase === 'error' && !resource.data && resource.error) {
    if (resource.error.code === 'ACTIVE_PROFILE_REQUIRED') {
      return (
        <EmptyState
          title="Chưa có CV đang hoạt động"
          description="Lưu và kích hoạt một hồ sơ CV trước khi xem bản đồ kỹ năng."
          isCompact
        />
      );
    }
    return (
      <Banner
        status="error"
        title="Không thể tải bản đồ kỹ năng"
        description={resource.error.summary}
        container="card"
        data-testid="jobagent-skill-map-error"
      />
    );
  }

  const map = resource.data;
  if (!map) return <MapLoading />;
  const filtered = map.items
    .map((entry, index) => ({entry, index}))
    .filter(({entry}) => filter === null || entry.match_type === filter);
  const selected =
    filtered.find(({index}) => index === selectedIndex) ?? filtered[0] ?? null;

  return (
    <VStack gap={3} width="100%">
      {resource.phase === 'loading' ? (
        <Text type="supporting" color="secondary" aria-live="polite">
          Đang cập nhật, dữ liệu an toàn gần nhất vẫn được hiển thị.
        </Text>
      ) : null}
      {resource.phase === 'error' && resource.error ? (
        <Banner
          status="error"
          title="Lần cập nhật gần nhất thất bại"
          description={resource.error.summary}
          container="card"
          data-testid="jobagent-skill-map-refresh-error"
        />
      ) : null}
      <Text type="body">{map.summary}</Text>
      <Text type="supporting" color="secondary">
        Kiểm tra lúc {formatObservabilityDateTime(map.checked_at)}
      </Text>
      {statusMessage(map)}

      {map.candidate && map.job ? (
        <section
          className="jobagent-skill-map-anchors"
          aria-label="CV và JD đang so sánh"
        >
          <article className="jobagent-skill-map-anchor">
            <VStack gap={1} width="100%">
              <Text type="label" color="secondary">
                CV đang hoạt động
              </Text>
              <Text type="large">
                {map.candidate.current_title ?? 'Hồ sơ ứng viên'}
              </Text>
            </VStack>
          </article>
          <article className="jobagent-skill-map-anchor">
            <VStack gap={1} width="100%">
              <Text type="label" color="secondary">
                JD đã chọn
              </Text>
              <Text type="large">{map.job.title ?? 'JD chưa có tiêu đề'}</Text>
              {map.job.company ? (
                <Text type="supporting" color="secondary">
                  {map.job.company}
                </Text>
              ) : null}
            </VStack>
          </article>
        </section>
      ) : null}

      {map.status === 'ready' ? (
        <VStack gap={3} width="100%">
          <HStack
            gap={1}
            wrap="wrap"
            className="jobagent-skill-map-filters"
            aria-label="Lọc theo trạng thái kỹ năng"
          >
            {FILTER_ORDER.map((matchType) => {
              const presentation = SKILL_MATCH_PRESENTATION[matchType];
              const label = `${presentation.label} (${map.counts[matchType]})`;
              const active = filter === matchType;
              return (
                <Button
                  key={matchType}
                  label={label}
                  size="sm"
                  variant={active ? 'primary' : 'ghost'}
                  aria-pressed={active}
                  onClick={() => setFilter(active ? null : matchType)}
                />
              );
            })}
          </HStack>

          {filtered.length === 0 ? (
            <EmptyState
              title="Không có kỹ năng trong bộ lọc này"
              description="Chọn lại bộ lọc đang bật để xem tất cả kết quả."
              isCompact
            />
          ) : (
            <section className="jobagent-skill-map-layout">
              <section
                className="jobagent-skill-map-items"
                data-testid="jobagent-skill-map-items"
              >
                <List density="compact" hasDividers header="Kỹ năng theo trạng thái">
                  {filtered.map(({entry, index}) => {
                    const presentation =
                      SKILL_MATCH_PRESENTATION[entry.match_type];
                    return (
                      <ListItem
                        key={`${entry.match_type}-${index}`}
                        label={itemLabel(entry)}
                        description={itemDescription(entry)}
                        startContent={
                          <HStack gap={1} align="center">
                            <StatusDot
                              variant={presentation.variant}
                              label={presentation.label}
                            />
                            <Text type="supporting">{presentation.label}</Text>
                          </HStack>
                        }
                        isSelected={selected?.index === index}
                        onClick={() => setSelectedIndex(index)}
                      />
                    );
                  })}
                </List>
              </section>
              {selected ? (
                <SkillCompatibilityEvidence item={selected.entry} />
              ) : null}
            </section>
          )}
        </VStack>
      ) : null}
    </VStack>
  );
}
