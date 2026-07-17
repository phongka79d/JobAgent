import {cleanup, render, screen, waitFor} from '@testing-library/react';
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
  const strip = tablist.querySelector<HTMLElement>(
    ':scope > [role="presentation"]',
  );
  expect(strip).not.toBeNull();
  expect(window.getComputedStyle(strip!).flexDirection).toBe('column');
  expect(window.getComputedStyle(strip!).width).toBe('100%');

  for (const tab of strip!.querySelectorAll<HTMLElement>(
    '[data-testid^="jobagent-obs-tab-"]',
  )) {
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
    expect(tablist.firstElementChild).toHaveAttribute('role', 'presentation');
    expectVerticalTabsToFit(tablist);
    expect(
      screen.getByRole('separator', {name: 'Resize sidebar'}),
    ).toBeInTheDocument();
  });

  it('does not expose the presentational tab strip as navigation', async () => {
    renderObservabilitySidebar();
    const tablist = await screen.findByRole('tablist', {
      name: 'Observability inspector',
    });
    expect(tablist).toHaveAttribute('aria-orientation', 'vertical');
    expect(screen.getAllByRole('tab')).toHaveLength(5);
    expect(tablist.firstElementChild).toHaveAttribute('role', 'presentation');
    expect(tablist.firstElementChild).not.toHaveAttribute('aria-label');
    expect(
      screen.queryByRole('navigation', {name: 'Tabs'}),
    ).not.toBeInTheDocument();
  });

  it('keeps tabs in the collapsed rail and expands the selected view', async () => {
    renderObservabilitySidebar();
    await userEvent.click(
      await screen.findByTestId('jobagent-sidebar-collapse'),
    );
    const graphTab = screen.getByRole('tab', {name: 'Neo4j graph'});
    expect(graphTab).not.toHaveAttribute('aria-controls');
    expectVerticalTabsToFit(
      screen.getByRole('tablist', {name: 'Observability inspector'}),
    );
    await userEvent.click(graphTab);
    expect(await screen.findByTestId('jobagent-obs-graph')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-sidebar-collapse')).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('lets AppShell expose the same inspector through automatic mobile navigation', async () => {
    installMatchMedia(true);
    const api = mockObservabilityApi();
    const loadProfile = vi.fn().mockResolvedValue(emptyProfile());
    render(
      <Theme theme={neutralTheme}>
        <AppShell
          sideNav={
            <CvSidebar
              isUploadDisabled={false}
              onSidebarUploadSuccess={vi.fn()}
              deps={{
                loadProfile,
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
    const tablist = await screen.findByRole('tablist', {
      name: 'Observability inspector',
    });
    expect(loadProfile).toHaveBeenCalledTimes(1);
    expect(tablist.firstElementChild).toHaveAttribute('role', 'presentation');
    expectVerticalTabsToFit(tablist);
    expect(await screen.findByRole('tab', {name: 'Overview'})).toBeInTheDocument();
    expect(screen.getByTestId('mobile-chat-content')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', {name: 'Neo4j graph'}));
    expect(await screen.findByTestId('jobagent-obs-graph')).toBeInTheDocument();
    await waitFor(() => {
      expect(api.fetchGraphSnapshot).toHaveBeenCalledTimes(1);
    });
    await userEvent.click(
      screen.getByRole('button', {name: 'Close navigation'}),
    );
    await userEvent.click(
      await screen.findByRole('button', {name: 'Open navigation'}),
    );

    expect(
      await screen.findByRole('tab', {name: 'Neo4j graph'}),
    ).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByTestId('jobagent-obs-graph')).toBeInTheDocument();
    expect(api.fetchGraphSnapshot).toHaveBeenCalledTimes(1);
    expect(loadProfile).toHaveBeenCalledTimes(1);
  });
});
