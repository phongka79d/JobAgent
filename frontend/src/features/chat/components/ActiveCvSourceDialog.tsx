/**
 * Active-CV source dialog: exact durable records, partial disclosure, original CV
 * (Plan 12 03A). Local open state only; zero evidence/chunk network fetches.
 */

import {Banner} from '@astryxdesign/core/Banner';
import {Button} from '@astryxdesign/core/Button';
import {Dialog, DialogHeader} from '@astryxdesign/core/Dialog';
import {HStack} from '@astryxdesign/core/HStack';
import {
  Layout,
  LayoutContent,
  LayoutFooter,
} from '@astryxdesign/core/Layout';
import {
  MetadataList,
  MetadataListItem,
} from '@astryxdesign/core/MetadataList';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

import {
  type ActiveCvChunkRecord,
  type ActiveCvEntryRecord,
  type ActiveCvEvidenceBundle,
  type ActiveCvPage,
  type ActiveCvRecord,
} from '../activeCvEvidence';
import {getRetainedCvUrl} from '../../observability/api';

export type ActiveCvSourceDialogProps = {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  evidence: ActiveCvEvidenceBundle;
};

export const ACTIVE_CV_SOURCE_DIALOG_TITLE = 'Nguồn từ CV' as const;
export const ACTIVE_CV_SOURCE_DIALOG_SUBTITLE =
  'Bằng chứng Agent đã đọc cho câu trả lời này.' as const;
export const ACTIVE_CV_OPEN_ORIGINAL_LABEL = 'Mở CV gốc' as const;
export const ACTIVE_CV_PARTIAL_NOTICE =
  'Bằng chứng một phần: một số trang hoặc bản ghi bị cắt ngắn, hoặc còn trang Agent chưa đọc.' as const;

/** True when any page/record discloses truncation or additional pages. */
export function evidenceIsPartial(evidence: ActiveCvEvidenceBundle): boolean {
  for (const page of evidence.pages) {
    if (page.truncated || page.has_more) {
      return true;
    }
    for (const record of page.records) {
      if (record.record_truncated === true) {
        return true;
      }
    }
  }
  return false;
}

function isEntryRecord(record: ActiveCvRecord): record is ActiveCvEntryRecord {
  return record.kind === 'entry' || record.kind === 'entry_match';
}

function isChunkRecord(record: ActiveCvRecord): record is ActiveCvChunkRecord {
  return record.kind === 'chunk' || record.kind === 'chunk_match';
}

function openOriginalCv(attachmentId: string): void {
  window.open(
    getRetainedCvUrl(attachmentId),
    '_blank',
    'noopener,noreferrer',
  );
}

function EntryRecordView({record}: {record: ActiveCvEntryRecord}) {
  const metaItems: {label: string; value: string}[] = [];
  if (record.title) {
    metaItems.push({label: 'Title', value: record.title});
  }
  if (record.subtitle) {
    metaItems.push({label: 'Subtitle', value: record.subtitle});
  }
  if (record.date_text) {
    metaItems.push({label: 'Date', value: record.date_text});
  }
  if (record.location) {
    metaItems.push({label: 'Location', value: record.location});
  }
  if (record.source_chunk_ordinals.length > 0) {
    metaItems.push({
      label: 'Source chunks',
      value: record.source_chunk_ordinals.join(', '),
    });
  }

  return (
    <VStack gap={1} data-testid="jobagent-active-cv-entry-record">
      {metaItems.length > 0 ? (
        <MetadataList columns="single" label={{position: 'start'}}>
          {metaItems.map((item) => (
            <MetadataListItem key={item.label} label={item.label}>
              {item.value}
            </MetadataListItem>
          ))}
        </MetadataList>
      ) : null}
      <Text type="body" as="p" data-testid="jobagent-active-cv-entry-body">
        {record.body}
      </Text>
      {record.bullets.length > 0
        ? record.bullets.map((bullet, idx) => (
            <Text
              key={`bullet-${idx}`}
              type="supporting"
              as="p"
              data-testid="jobagent-active-cv-entry-bullet"
            >
              • {bullet}
            </Text>
          ))
        : null}
      {record.kind === 'entry_match' && record.excerpt !== undefined ? (
        <Text type="supporting" color="secondary" as="p">
          Excerpt: {record.excerpt}
        </Text>
      ) : null}
      {record.record_truncated === true ? (
        <Text type="supporting" color="secondary" as="p">
          Record truncated
        </Text>
      ) : null}
    </VStack>
  );
}

function ChunkRecordView({record}: {record: ActiveCvChunkRecord}) {
  return (
    <VStack gap={1} data-testid="jobagent-active-cv-chunk-record">
      <MetadataList columns="single" label={{position: 'start'}}>
        <MetadataListItem label="Chunk ordinal">
          {String(record.ordinal)}
        </MetadataListItem>
      </MetadataList>
      <Text type="body" as="p" data-testid="jobagent-active-cv-chunk-text">
        {record.text}
      </Text>
      {record.kind === 'chunk_match' && record.excerpt !== undefined ? (
        <Text type="supporting" color="secondary" as="p">
          Excerpt: {record.excerpt}
        </Text>
      ) : null}
      {record.record_truncated === true ? (
        <Text type="supporting" color="secondary" as="p">
          Record truncated
        </Text>
      ) : null}
    </VStack>
  );
}

function RecordView({record}: {record: ActiveCvRecord}) {
  if (isEntryRecord(record)) {
    return <EntryRecordView record={record} />;
  }
  if (isChunkRecord(record)) {
    return <ChunkRecordView record={record} />;
  }
  return null;
}

function PageView({page, pageIndex}: {page: ActiveCvPage; pageIndex: number}) {
  return (
    <VStack
      gap={2}
      data-testid="jobagent-active-cv-evidence-page"
      data-page-index={String(pageIndex)}
    >
      <Text type="label" as="p">
        Page {pageIndex + 1}
        {page.mode ? ` · ${page.mode}` : ''}
        {page.truncated || page.has_more ? ' · partial' : ''}
      </Text>
      {page.records.map((record, recordIndex) => (
        <VStack
          key={`p${pageIndex}-r${recordIndex}`}
          gap={1}
          data-testid="jobagent-active-cv-evidence-record"
          data-record-index={String(recordIndex)}
        >
          <RecordView record={record} />
        </VStack>
      ))}
    </VStack>
  );
}

/**
 * Modal listing every selected page/record in durable order without dedup,
 * with partial-evidence notice and Mở CV gốc for the answer attachment.
 */
export function ActiveCvSourceDialog({
  isOpen,
  onOpenChange,
  evidence,
}: ActiveCvSourceDialogProps) {
  const partial = evidenceIsPartial(evidence);

  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      purpose="info"
      width={520}
      maxHeight="75vh"
      data-testid="jobagent-active-cv-source-dialog"
    >
      <Layout
        height="auto"
        header={
          <DialogHeader
            title={ACTIVE_CV_SOURCE_DIALOG_TITLE}
            subtitle={ACTIVE_CV_SOURCE_DIALOG_SUBTITLE}
            onOpenChange={onOpenChange}
          />
        }
        content={
          <LayoutContent label="Active CV evidence">
            <VStack gap={3}>
              {partial ? (
                <Banner
                  status="warning"
                  title={ACTIVE_CV_PARTIAL_NOTICE}
                  data-testid="jobagent-active-cv-partial-notice"
                />
              ) : null}
              {evidence.pages.map((page, pageIndex) => (
                <PageView
                  key={`page-${pageIndex}`}
                  page={page}
                  pageIndex={pageIndex}
                />
              ))}
            </VStack>
          </LayoutContent>
        }
        footer={
          <LayoutFooter hasDivider>
            <HStack gap={2} hAlign="end">
              <Button
                label={ACTIVE_CV_OPEN_ORIGINAL_LABEL}
                variant="primary"
                data-testid="jobagent-active-cv-open-original"
                onClick={() => {
                  openOriginalCv(evidence.attachment_id);
                }}
              />
              <Button
                label="Đóng"
                variant="secondary"
                data-testid="jobagent-active-cv-close"
                onClick={() => {
                  onOpenChange(false);
                }}
              />
            </HStack>
          </LayoutFooter>
        }
      />
    </Dialog>
  );
}
