import {useEffect, useRef, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Heading} from '@astryxdesign/core/Heading';
import {HStack} from '@astryxdesign/core/HStack';
import {Section} from '@astryxdesign/core/Section';
import {Text} from '@astryxdesign/core/Text';
import {TextArea} from '@astryxdesign/core/TextArea';
import {TextInput} from '@astryxdesign/core/TextInput';
import {VStack} from '@astryxdesign/core/VStack';

import {TAILORING_COPY} from './copy';
import {tailoringFieldId, tailoringIssueId, tailoringSectionId} from './types';
import type {
  SourceBoundText,
  TailoredFactEvidence,
  TailoredItem,
  TailoredSection,
  TailoringUserIssue,
} from './types';

export type TailoredSectionEditorProps = {
  readonly section: TailoredSection;
  readonly evidence: readonly TailoredFactEvidence[];
  readonly isDisabled: boolean;
  readonly onChange: (section: TailoredSection) => void;
  readonly onAskAi: (sectionId: string, heading: string) => void;
  readonly issues?: readonly TailoringUserIssue[];
  readonly isEvidenceOpen?: boolean;
  readonly evidenceFocusKey?: number;
};

function replaceAt<T>(items: readonly T[], index: number, value: T): readonly T[] {
  return items.map((item, current) => (current === index ? value : item));
}

function moveAt<T>(items: readonly T[], index: number, offset: -1 | 1): readonly T[] {
  const target = index + offset;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

function withText(value: SourceBoundText, text: string): SourceBoundText {
  return {...value, text};
}

function itemLabel(section: TailoredSection, index: number): string {
  return `${section.heading} ${index + 1}`;
}

export function TailoredSectionEditor({
  section,
  evidence,
  isDisabled,
  onChange,
  onAskAi,
  issues = [],
  isEvidenceOpen = false,
  evidenceFocusKey = 0,
}: TailoredSectionEditorProps) {
  const evidenceRef = useRef<HTMLDivElement>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  useEffect(() => {
    if (isEvidenceOpen && evidenceFocusKey > 0) {
      setEvidenceOpen(true);
    }
  }, [evidenceFocusKey, isEvidenceOpen]);
  useEffect(() => {
    if (!evidenceOpen) return;
    const frame = requestAnimationFrame(() => evidenceRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [evidenceFocusKey, evidenceOpen]);
  const fieldStatus = (itemIndex: number, field: TailoringUserIssue['field']) => {
    const messages = issues
      .filter((issue) => issue.item_index === itemIndex && issue.field === field)
      .map((issue) => TAILORING_COPY.issueReasons[issue.reason]);
    if (messages.length === 0) return undefined;
    return {
      type: 'error' as const,
      message: `Needs attention: ${[...new Set(messages)].join(' ')}`,
    };
  };
  const sectionIssueIds = issues.filter((issue) => issue.item_index === null || issue.field === 'section').map(tailoringIssueId).join(' ') || undefined;
  const updateItem = (index: number, item: TailoredItem) => {
    onChange({...section, items: replaceAt(section.items, index, item)});
  };

  return (
    <Section
      id={tailoringSectionId(section.id)}
      tabIndex={-1}
      aria-describedby={sectionIssueIds}
      variant="transparent"
      dividers={['bottom']}
      data-testid={`jobagent-tailored-section-${section.id}`}
    >
      <VStack gap={4}>
        <HStack gap={3} hAlign="between" vAlign="center" wrap="wrap">
          <Heading level={2}>{section.heading}</Heading>
          <Button
            label="Ask AI to revise this section"
            size="sm"
            variant="secondary"
            isDisabled={isDisabled}
            onClick={() => onAskAi(section.id, section.heading)}
          />
        </HStack>

        {section.items.length === 0 ? (
          <Text type="supporting">This section has no content items.</Text>
        ) : null}

        {section.items.map((item, itemIndex) => (
          <Section
            key={item.id}
            variant="muted"
            padding={3}
            data-testid={`jobagent-tailored-item-${item.id}`}
          >
            <VStack gap={3}>
              <HStack gap={2} hAlign="end" wrap="wrap">
                <Button
                  label={`Move item ${itemIndex + 1} up`}
                  size="sm"
                  variant="ghost"
                  isDisabled={isDisabled || itemIndex === 0}
                  onClick={() =>
                    onChange({
                      ...section,
                      items: moveAt(section.items, itemIndex, -1),
                    })
                  }
                />
                <Button
                  label={`Move item ${itemIndex + 1} down`}
                  size="sm"
                  variant="ghost"
                  isDisabled={
                    isDisabled || itemIndex === section.items.length - 1
                  }
                  onClick={() =>
                    onChange({
                      ...section,
                      items: moveAt(section.items, itemIndex, 1),
                    })
                  }
                />
                <Button
                  label={`Delete item ${itemIndex + 1}`}
                  size="sm"
                  variant="ghost"
                  isDisabled={isDisabled}
                  onClick={() =>
                    onChange({
                      ...section,
                      items: section.items.filter(
                        (_candidate, index) => index !== itemIndex,
                      ),
                    })
                  }
                />
              </HStack>

              {item.title ? (
                <TextInput
                  htmlName={tailoringFieldId(section.id, itemIndex, 'title')}
                  status={fieldStatus(itemIndex, 'title')}
                  label={`Title ${itemLabel(section, itemIndex)}`}
                  value={item.title.text}
                  isDisabled={isDisabled}
                  onChange={(text) =>
                    updateItem(itemIndex, {
                      ...item,
                      title: withText(item.title!, text),
                    })
                  }
                />
              ) : null}
              {item.subtitle ? (
                <TextInput
                  htmlName={tailoringFieldId(section.id, itemIndex, 'subtitle')}
                  status={fieldStatus(itemIndex, 'subtitle')}
                  label={`Subtitle ${itemLabel(section, itemIndex)}`}
                  value={item.subtitle.text}
                  isDisabled={isDisabled}
                  onChange={(text) =>
                    updateItem(itemIndex, {
                      ...item,
                      subtitle: withText(item.subtitle!, text),
                    })
                  }
                />
              ) : null}
              {item.date_text ? (
                <TextInput
                  htmlName={tailoringFieldId(section.id, itemIndex, 'date')}
                  status={fieldStatus(itemIndex, 'date')}
                  label={`Dates ${itemLabel(section, itemIndex)}`}
                  value={item.date_text.text}
                  isDisabled={isDisabled}
                  onChange={(text) =>
                    updateItem(itemIndex, {
                      ...item,
                      date_text: withText(item.date_text!, text),
                    })
                  }
                />
              ) : null}
              {item.location ? (
                <TextInput
                  htmlName={tailoringFieldId(section.id, itemIndex, 'location')}
                  status={fieldStatus(itemIndex, 'location')}
                  label={`Location ${itemLabel(section, itemIndex)}`}
                  value={item.location.text}
                  isDisabled={isDisabled}
                  onChange={(text) =>
                    updateItem(itemIndex, {
                      ...item,
                      location: withText(item.location!, text),
                    })
                  }
                />
              ) : null}
              <TextArea
                htmlName={tailoringFieldId(section.id, itemIndex, 'body')}
                aria-label={`${section.heading} body`}
                status={fieldStatus(itemIndex, 'body')}
                label={`Body ${itemLabel(section, itemIndex)}`}
                value={item.body.text}
                rows={3}
                maxLength={4_000}
                isDisabled={isDisabled}
                onChange={(text) =>
                  updateItem(itemIndex, {
                    ...item,
                    body: withText(item.body, text),
                  })
                }
              />

              {item.bullets.map((bullet, bulletIndex) => (
                <HStack
                  key={`${item.id}-bullet-${bulletIndex}`}
                  gap={2}
                  vAlign="end"
                  wrap="wrap"
                >
                  <TextArea
                    htmlName={`${tailoringFieldId(section.id, itemIndex, 'bullet')}-${bulletIndex}`}
                    status={fieldStatus(itemIndex, 'bullet')}
                    label={`Bullet ${bulletIndex + 1} · ${itemLabel(section, itemIndex)}`}
                    value={bullet.text}
                    rows={2}
                    maxLength={4_000}
                    isDisabled={isDisabled}
                    onChange={(text) =>
                      updateItem(itemIndex, {
                        ...item,
                        bullets: replaceAt(
                          item.bullets,
                          bulletIndex,
                          withText(bullet, text),
                        ),
                      })
                    }
                  />
                  <Button
                    label={`Move bullet ${bulletIndex + 1} up`}
                    size="sm"
                    variant="ghost"
                    isDisabled={isDisabled || bulletIndex === 0}
                    onClick={() =>
                      updateItem(itemIndex, {
                        ...item,
                        bullets: moveAt(item.bullets, bulletIndex, -1),
                      })
                    }
                  />
                  <Button
                    label={`Move bullet ${bulletIndex + 1} down`}
                    size="sm"
                    variant="ghost"
                    isDisabled={
                      isDisabled || bulletIndex === item.bullets.length - 1
                    }
                    onClick={() =>
                      updateItem(itemIndex, {
                        ...item,
                        bullets: moveAt(item.bullets, bulletIndex, 1),
                      })
                    }
                  />
                  <Button
                    label={`Delete bullet ${bulletIndex + 1}`}
                    size="sm"
                    variant="ghost"
                    isDisabled={isDisabled}
                    onClick={() =>
                      updateItem(itemIndex, {
                        ...item,
                        bullets: item.bullets.filter(
                          (_candidate, index) => index !== bulletIndex,
                        ),
                      })
                    }
                  />
                </HStack>
              ))}

              {item.attributes.map((attribute, attributeIndex) => (
                <Section
                  key={`${item.id}-attribute-${attribute.name}`}
                  variant="transparent"
                  padding={0}
                >
                  <VStack gap={2}>
                    <Text type="label">{attribute.name}</Text>
                    {attribute.values.map((attributeValue, valueIndex) => (
                      <TextInput
                        htmlName={`${tailoringFieldId(section.id, itemIndex, 'attribute')}-${attributeIndex}-${valueIndex}`}
                        status={fieldStatus(itemIndex, 'attribute')}
                        key={`${attribute.name}-${valueIndex}`}
                        label={`${attribute.name} ${valueIndex + 1}`}
                        value={attributeValue.text}
                        isDisabled={isDisabled}
                        onChange={(text) =>
                          updateItem(itemIndex, {
                            ...item,
                            attributes: replaceAt(
                              item.attributes,
                              attributeIndex,
                              {
                                ...attribute,
                                values: replaceAt(
                                  attribute.values,
                                  valueIndex,
                                  withText(attributeValue, text),
                                ),
                              },
                            ),
                          })
                        }
                      />
                    ))}
                  </VStack>
                </Section>
              ))}
            </VStack>
          </Section>
        ))}

        {evidence.length > 0 ? (
          <Collapsible trigger={<Text type="label">Source evidence</Text>} isOpen={evidenceOpen} onOpenChange={setEvidenceOpen}>
            <VStack ref={evidenceRef} tabIndex={-1} role="region" aria-label={`${section.heading} source evidence`} gap={2}>
              {evidence.map((fact) => (
                <Text key={fact.fact_id} type="supporting" as="p">
                  {fact.source_text}
                </Text>
              ))}
            </VStack>
          </Collapsible>
        ) : null}
      </VStack>
    </Section>
  );
}
