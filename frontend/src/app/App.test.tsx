import {render, screen, waitFor} from '@testing-library/react';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it, vi} from 'vitest';

import {App} from './App';

describe('App foundation shell', () => {
  it('renders AppShell with CV sidebar and chat page', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/api/profile') && !url.includes('/cv')) {
        return new Response(
          JSON.stringify({
            present: false,
            profile: null,
            preferences: null,
            active_attachment: null,
          }),
          {status: 200, headers: {'Content-Type': 'application/json'}},
        );
      }
      return new Response(JSON.stringify({items: [], next_cursor: null}), {
        status: 200,
        headers: {'Content-Type': 'application/json'},
      });
    });

    const {container} = render(
      <Theme theme={neutralTheme}>
        <App />
      </Theme>,
    );

    const shell = container.querySelector('.astryx-app-shell');
    expect(shell).not.toBeNull();
    expect(shell).toHaveAttribute('data-variant', 'surface');
    expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument();
    expect(screen.getByTestId('jobagent-cv-sidebar')).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText(/Start a conversation|History load issue/),
      ).toBeInTheDocument();
    });
  });
});
