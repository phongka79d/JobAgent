import {render, screen} from '@testing-library/react';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {describe, expect, it} from 'vitest';

import {App} from './App';

describe('App foundation shell', () => {
  it('renders AppShell under the neutral theme provider', () => {
    const {container} = render(
      <Theme theme={neutralTheme}>
        <App />
      </Theme>,
    );

    const shell = container.querySelector('.astryx-app-shell');
    expect(shell).not.toBeNull();
    expect(shell).toHaveAttribute('data-variant', 'surface');
    expect(
      screen.getByRole('heading', {level: 1, name: 'JobAgent'}),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Astryx-neutral application foundation'),
    ).toBeInTheDocument();
  });
});
