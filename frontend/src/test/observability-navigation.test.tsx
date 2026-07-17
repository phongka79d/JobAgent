import {cleanup, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {AppShell} from '@astryxdesign/core/AppShell';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, beforeAll, beforeEach, describe, expect, it, vi} from 'vitest';

import {CvSidebar} from '../features/profile/CvSidebar';
import {
  emptyProfile,
  installMatchMedia,
  mockObservabilityApi,
  renderObservabilitySidebar,
} from './support/observability';

function expectVerticalTabsToFit(tablist: HTMLElement) {
  const strip = tablist.querySelector<HTMLElement>('.astryx-tab-list');
  expect(strip).not.toBeNull();
  expect(window.getComputedStyle(strip!).flexDirection).toBe('column');
  expect(window.getComputedStyle(strip!).width).toBe('100%');

  for (const tab of strip!.querySelectorAll<HTMLElement>('[data-tab-value]')) {
    expect(window.getComputedStyle(tab).width).toBe('100%');
    expect(window.getComputedStyle(tab).maxWidth).toBe('100%');
  }
}

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute('open', '');
  };
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute('open');
  };
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  installMatchMedia(false);
});

describe('observability navigation', () => {
  it('uses a vertical tab list and Astryx resize handle', async () => {
    renderObservabilitySidebar();
    const tablist = await screen.findByRole('tablist', {
      name: 'Observability inspector',
    });
    expect(tablist).toHaveAttribute('aria-orientation', 'vertical');
    expectVerticalTabsToFit(tablist);
    expect(
      screen.getByRole('separator', {name: 'Resize sidebar'}),
    ).toBeInTheDocument();
  });

  it('keeps tabs in the collapsed rail and expands the selected view', async () => {
    renderObservabilitySidebar();
    await userEvent.click(
      await screen.findByTestId('jobagent-sidebar-collapse'),
    );
    expectVerticalTabsToFit(
      screen.getByRole('tablist', {name: 'Observability inspector'}),
    );
    expect(screen.getByRole('tab', {name: 'Neo4j graph'})).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', {name: 'Neo4j graph'}));
    expect(await screen.findByTestId('jobagent-obs-graph')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-sidebar-collapse')).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('lets AppShell expose the same inspector through automatic mobile navigation', async () => {
    installMatchMedia(true);
    const api = mockObservabilityApi();
    render(
      <Theme theme={neutralTheme}>
        <AppShell
          sideNav={
            <CvSidebar
              isUploadDisabled={false}
              onSidebarUploadSuccess={vi.fn()}
              deps={{
                loadProfile: vi.fn().mockResolvedValue(emptyProfile()),
                uploadCv: vi.fn(),
                observability: api,
              }}
            />
          }
        >
          <div data-testid="mobile-chat-content">Chat</div>
        </AppShell>
      </Theme>,
    );
    const open = await screen.findByRole('button', {name: 'Open navigation'});
    await userEvent.click(open);
    expectVerticalTabsToFit(
      await screen.findByRole('tablist', {name: 'Observability inspector'}),
    );
    expect(await screen.findByRole('tab', {name: 'Overview'})).toBeInTheDocument();
    expect(screen.getByTestId('mobile-chat-content')).toBeInTheDocument();
  });
});
