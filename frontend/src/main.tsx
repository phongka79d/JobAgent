import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';

import '@astryxdesign/core/reset.css';
import '@astryxdesign/core/astryx.css';
import '@astryxdesign/theme-neutral/theme.css';

import {AppShell} from '@astryxdesign/core/AppShell';
import {Button} from '@astryxdesign/core/Button';
import {ButtonGroup} from '@astryxdesign/core/ButtonGroup';
import {Card} from '@astryxdesign/core/Card';
import {
  ChatComposer,
  ChatLayout,
  ChatMessage,
  ChatMessageBubble,
  ChatMessageList,
  ChatToolCalls,
} from '@astryxdesign/core/Chat';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {ProgressBar} from '@astryxdesign/core/ProgressBar';

/**
 * Phase 0 only: prove public imports and required props from the pinned Astryx
 * package. No production chat behavior, SSE, or undocumented props.
 */
function Phase0AstryxProof() {
  return (
    <AppShell contentPadding={4} height="fill" variant="surface">
      <ChatLayout
        composer={
          <ChatComposer
            onSubmit={() => {
              /* diagnostic no-op */
            }}
            placeholder="Phase 0 diagnostic composer"
          />
        }
      >
        <ChatMessageList>
          <ChatMessage sender="assistant" name="JobAgent">
            <ChatMessageBubble>
              Phase 0 Astryx public-import proof
            </ChatMessageBubble>
            <ChatToolCalls
              calls={[
                {
                  name: 'astryx_feasibility',
                  status: 'complete',
                  target: 'public_api',
                  duration: '0ms',
                },
              ]}
            />
          </ChatMessage>
          <ChatMessage sender="user">
            <ChatMessageBubble>Minimal documented render</ChatMessageBubble>
          </ChatMessage>
        </ChatMessageList>
        <Card padding={4}>
          <Collapsible trigger="Score details" defaultIsOpen>
            <ProgressBar
              label="Match score"
              value={72}
              max={100}
              hasValueLabel
            />
          </Collapsible>
          <ButtonGroup label="Approval actions">
            <Button label="Save Profile" />
            <Button label="Request Changes" />
          </ButtonGroup>
        </Card>
      </ChatLayout>
    </AppShell>
  );
}

const root = document.getElementById('root');
if (!root) {
  throw new Error('Missing #root element');
}

createRoot(root).render(
  <StrictMode>
    <Phase0AstryxProof />
  </StrictMode>,
);
