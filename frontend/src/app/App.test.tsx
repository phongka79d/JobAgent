import {render, screen, waitFor} from '@testing-library/react';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it, vi} from 'vitest';

import {App} from './App';

describe('App foundation shell', () => {
  it('renders AppShell with the Plan 3 chat page', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({items: [], next_cursor: null}), {
        status: 200,
        headers: {'Content-Type': 'application/json'},
      }),
    );

    const {container} = render(
      <Theme theme={neutralTheme}>
        <App />
      </Theme>,
    );

    const shell = container.querySelector('.astryx-app-shell');
    expect(shell).not.toBeNull();
    expect(shell).toHaveAttribute('data-variant', 'surface');
    expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText(/Start a conversation|History load issue/),
      ).toBeInTheDocument();
    });
  });
});
