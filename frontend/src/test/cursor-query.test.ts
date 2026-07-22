import {describe, expect, it} from 'vitest';

import {buildCursorQuery} from '../lib/api/cursorQuery';

describe('buildCursorQuery', () => {
  it('omits absent values', () => {
    expect(buildCursorQuery()).toBe('');
    expect(buildCursorQuery({before: null})).toBe('');
    expect(buildCursorQuery({before: ''})).toBe('');
  });

  it('preserves limit-before ordering and URLSearchParams encoding', () => {
    expect(buildCursorQuery({limit: 10, before: 'cursor value'})).toBe(
      '?limit=10&before=cursor+value',
    );
  });
});
