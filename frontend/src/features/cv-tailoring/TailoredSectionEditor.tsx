import {Button} from '@astryxdesign/core/Button';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Heading} from '@astryxdesign/core/Heading';
import {HStack} from '@astryxdesign/core/HStack';
import {Section} from '@astryxdesign/core/Section';
import {Text} from '@astryxdesign/core/Text';
import {TextArea} from '@astryxdesign/core/TextArea';
import {TextInput} from '@astryxdesign/core/TextInput';
import {VStack} from '@astryxdesign/core/VStack';

import type {
  SourceBoundText,
  TailoredFactEvidence,
  TailoredItem,
  TailoredSection,
} from './types';

export type TailoredSectionEditorProps = {
  readonly section: TailoredSection;
  readonly evidence: readonly TailoredFactEvidence[];
  readonly isDisabled: boolean;
  readonly onChange: (section: TailoredSection) => void;
  readonly onAskAi: (sectionId: string, heading: string) => void;
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
}: TailoredSectionEditorProps) {
  const updateItem = (index: number, item: TailoredItem) => {
    onChange({...section, items: replaceAt(section.items, index, item)});
  };

  return (
    <Section
      variant="transparent"
      dividers={['bottom']}
      data-testid={`jobagent-tailored-section-${section.id}`}
    >
      <VStack gap={4}>
        <HStack gap={3} hAlign="between" vAlign="center" wrap="wrap">
          <Heading level={2}>{section.heading}</Heading>
          <Button
            label="Nhờ AI chỉnh section này"
            size="sm"
            variant="secondary"
            isDisabled={isDisabled}
            onClick={() => onAskAi(section.id, section.heading)}
          />
        </HStack>

        {section.items.length === 0 ? (
          <Text type="supporting">Section này không có mục nội dung.</Text>
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
                  label={`Đưa mục ${itemIndex + 1} lên`}
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
                  label={`Đưa mục ${itemIndex + 1} xuống`}
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
                  label={`Xóa mục ${itemIndex + 1}`}
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
                  label={`Tiêu đề ${itemLabel(section, itemIndex)}`}
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
                  label={`Phụ đề ${itemLabel(section, itemIndex)}`}
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
                  label={`Thời gian ${itemLabel(section, itemIndex)}`}
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
                  label={`Địa điểm ${itemLabel(section, itemIndex)}`}
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
                label={`Nội dung ${itemLabel(section, itemIndex)}`}
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
                    label={`Gạch đầu dòng ${bulletIndex + 1} · ${itemLabel(section, itemIndex)}`}
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
                    label={`Đưa gạch đầu dòng ${bulletIndex + 1} lên`}
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
                    label={`Đưa gạch đầu dòng ${bulletIndex + 1} xuống`}
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
                    label={`Xóa gạch đầu dòng ${bulletIndex + 1}`}
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
          <Collapsible trigger={<Text type="label">Nguồn đối chiếu</Text>} defaultIsOpen={false}>
            <VStack gap={2}>
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
