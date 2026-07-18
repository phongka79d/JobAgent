import {Icon} from '@astryxdesign/core/Icon';
import {Tab, TabList} from '@astryxdesign/core/TabList';
import {Tooltip} from '@astryxdesign/core/Tooltip';

import {OBSERVABILITY_TABS} from './observabilityTabs';
import type {ObservabilityTabId} from './types';

const TAB_FIT_STYLE = {
  width: '100%',
  maxWidth: '100%',
  minWidth: 0,
} as const;

const VERTICAL_TAB_LIST_STYLE = {
  ...TAB_FIT_STYLE,
  flexDirection: 'column',
} as const;

// Astryx 0.1.4 defaults undefined to "Tabs"; remove when the component supports presentational composition.
const OMITTED_ARIA_LABEL = null as unknown as string;

export function ObservabilityTabList({
  value,
  isCollapsed,
  onChange,
}: {
  value: ObservabilityTabId;
  isCollapsed: boolean;
  onChange: (value: ObservabilityTabId) => void;
}) {
  return (
    <div
      className="jobagent-obs-tab-rail"
      role="tablist"
      aria-label="Observability inspector"
      aria-orientation="vertical"
    >
      <TabList
        role="presentation"
        aria-label={OMITTED_ARIA_LABEL}
        value={value}
        onChange={(next) => {
          const tab = OBSERVABILITY_TABS.find((item) => item.id === next);
          if (tab) onChange(tab.id);
        }}
        orientation="vertical"
        size="sm"
        style={VERTICAL_TAB_LIST_STYLE}
      >
        {OBSERVABILITY_TABS.map((tab) => (
          <Tab
            key={tab.id}
            value={tab.id}
            label={tab.label}
            isLabelHidden={isCollapsed}
            role="tab"
            aria-selected={value === tab.id}
            aria-controls={
              isCollapsed ? undefined : `jobagent-obs-panel-${tab.id}`
            }
            style={TAB_FIT_STYLE}
            icon={
              isCollapsed ? (
                <Tooltip content={tab.label} placement="end">
                  <Icon icon={tab.icon} size="sm" />
                </Tooltip>
              ) : (
                <Icon icon={tab.icon} size="sm" />
              )
            }
            id={`jobagent-obs-tab-${tab.id}`}
            data-testid={`jobagent-obs-tab-${tab.id}`}
          />
        ))}
      </TabList>
    </div>
  );
}
