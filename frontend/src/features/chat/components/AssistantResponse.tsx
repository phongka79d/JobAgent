/**
 * Assistant-only Astryx Markdown + exact-one active-CV Nguồn citation (Plan 12 03A).
 * Display-only transform: never mutates message.content, history, or reducer state.
 */

import {useCallback, useMemo, useState, type MouseEvent} from 'react';
import {Citation} from '@astryxdesign/core/Citation';
import type {CitationSource} from '@astryxdesign/core/Citation';
import {Markdown} from '@astryxdesign/core/Markdown';
import {VStack} from '@astryxdesign/core/VStack';

import type {ActiveCvEvidenceBundle} from '../activeCvEvidence';
import {ActiveCvSourceDialog} from './ActiveCvSourceDialog';

/** Reserved source id for Markdown sources map — never shown as raw text when wired. */
export const ACTIVE_CV_CITATION_SOURCE_ID = 'jobagent-nguon' as const;
export const ACTIVE_CV_CITATION_LABEL = 'Nguồn' as const;
export const ACTIVE_CV_CITATION_MARKER =
  `[${ACTIVE_CV_CITATION_SOURCE_ID}]` as const;

/** Internal hash target so Citation renders as an activatable link without navigation. */
const CITATION_HREF = '#jobagent-active-cv-source';

export type AssistantResponseProps = {
  content: string;
  isStreaming?: boolean;
  /** Same-row durable evidence from activeCvEvidenceForTools; null = no citation. */
  evidence: ActiveCvEvidenceBundle | null;
};

/**
 * Insert exactly one reserved citation marker after the first safe lead paragraph.
 * Safe = first non-empty prose block outside fences that is not a heading, list,
 * blockquote, table, or thematic break. Falls back to post-body placement when
 * no safe lead exists. Presentation-only — never writes to stored content.
 */
export function placeActiveCvCitationMarker(content: string): {
  displayContent: string;
  placement: 'inline' | 'fallback';
} {
  // Defensive: strip accidental reserved markers so they never appear twice/raw.
  const cleaned = content.split(ACTIVE_CV_CITATION_MARKER).join('');
  if (cleaned.trim() === '') {
    return {displayContent: cleaned, placement: 'fallback'};
  }

  const lines = cleaned.split('\n');
  let inFence = false;
  let i = 0;

  const isFenceLine = (trimmed: string): boolean => trimmed.startsWith('```');

  const isUnsafeBlockStart = (trimmed: string): boolean =>
    /^#{1,6}(\s|$)/.test(trimmed) ||
    /^([-*+]|\d+\.)\s+/.test(trimmed) ||
    /^>\s?/.test(trimmed) ||
    /^\|/.test(trimmed) ||
    /^-{3,}\s*$/.test(trimmed) ||
    /^\*{3,}\s*$/.test(trimmed);

  while (i < lines.length) {
    const trimmed = lines[i].trim();

    if (isFenceLine(trimmed)) {
      inFence = !inFence;
      i += 1;
      continue;
    }
    if (inFence) {
      i += 1;
      continue;
    }
    if (trimmed === '') {
      i += 1;
      continue;
    }

    if (isUnsafeBlockStart(trimmed)) {
      // Skip this block until a blank line (or EOF).
      while (i < lines.length && lines[i].trim() !== '') {
        const t = lines[i].trim();
        if (isFenceLine(t)) {
          inFence = !inFence;
        }
        i += 1;
      }
      continue;
    }

    // Safe lead paragraph: consume until blank line, fence, or EOF.
    while (i < lines.length) {
      const t = lines[i].trim();
      if (t === '' || isFenceLine(t)) {
        break;
      }
      i += 1;
    }
    const lastIdx = i - 1;
    if (lastIdx < 0) {
      break;
    }
    lines[lastIdx] = `${lines[lastIdx]}${ACTIVE_CV_CITATION_MARKER}`;
    return {displayContent: lines.join('\n'), placement: 'inline'};
  }

  return {displayContent: cleaned, placement: 'fallback'};
}

type CitationChipProps = {
  source: CitationSource;
  number: number;
  variant: 'label' | 'number';
  onActivate: () => void;
};

function NguonCitationChip({
  source,
  number,
  variant,
  onActivate,
}: CitationChipProps) {
  const handleClick = (event: MouseEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    onActivate();
  };

  return (
    <Citation
      source={{
        title: source.title ?? ACTIVE_CV_CITATION_LABEL,
        url: CITATION_HREF,
      }}
      number={number}
      variant={variant}
      data-testid="jobagent-active-cv-citation"
      onClick={handleClick}
    />
  );
}

/**
 * Renders assistant prose via public Astryx Markdown (compact, heading 4,
 * streaming). When evidence is present, shows exactly one Nguồn citation that
 * opens ActiveCvSourceDialog.
 */
export function AssistantResponse({
  content,
  isStreaming = false,
  evidence,
}: AssistantResponseProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const hasEvidence = evidence !== null && evidence.pages.length > 0;

  const placement = useMemo(() => {
    if (!hasEvidence) {
      return {
        displayContent: content,
        placement: 'fallback' as const,
      };
    }
    return placeActiveCvCitationMarker(content);
  }, [content, hasEvidence]);

  const openDialog = useCallback(() => {
    setDialogOpen(true);
  }, []);

  const sources = useMemo(() => {
    if (!hasEvidence || placement.placement !== 'inline') {
      return undefined;
    }
    return {
      [ACTIVE_CV_CITATION_SOURCE_ID]: {
        title: ACTIVE_CV_CITATION_LABEL,
        url: CITATION_HREF,
      },
    };
  }, [hasEvidence, placement.placement]);

  const citationComponent = useMemo(() => {
    if (!hasEvidence) {
      return undefined;
    }
    function BoundCitation(props: {
      source: CitationSource;
      number: number;
      variant: 'label' | 'number';
    }) {
      return (
        <NguonCitationChip
          source={props.source}
          number={props.number}
          variant={props.variant}
          onActivate={openDialog}
        />
      );
    }
    return BoundCitation;
  }, [hasEvidence, openDialog]);

  const showFallbackCitation =
    hasEvidence && placement.placement === 'fallback';

  return (
    <VStack gap={1} data-testid="jobagent-assistant-response">
      <Markdown
        density="compact"
        headingLevelStart={4}
        isStreaming={isStreaming}
        sources={sources}
        citationStyle="label"
        components={
          citationComponent ? {citation: citationComponent} : undefined
        }
        data-testid="jobagent-assistant-markdown"
      >
        {placement.displayContent}
      </Markdown>
      {showFallbackCitation ? (
        <NguonCitationChip
          source={{title: ACTIVE_CV_CITATION_LABEL, url: CITATION_HREF}}
          number={1}
          variant="label"
          onActivate={openDialog}
        />
      ) : null}
      {hasEvidence && evidence ? (
        <ActiveCvSourceDialog
          isOpen={dialogOpen}
          onOpenChange={setDialogOpen}
          evidence={evidence}
        />
      ) : null}
    </VStack>
  );
}
