import {act, renderHook} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import {useObservabilityState} from '../features/observability/state';
import type {ChunkListPage, CvHistoryPage} from '../features/observability/types';
import {
  ATTACHMENT_ID,
  chunkListPage,
  cvHistoryPage,
} from './support/observability';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve;
  });
  return {promise, resolve};
}

describe('observability request ordering', () => {
  it('ignores an older initial CV request after a forced refresh succeeds', async () => {
    const initial = deferred<CvHistoryPage>();
    const refresh = deferred<CvHistoryPage>();
    const fetchCvHistory = vi
      .fn()
      .mockReturnValueOnce(initial.promise)
      .mockReturnValueOnce(refresh.promise);
    const {result} = renderHook(() =>
      useObservabilityState({api: {fetchCvHistory}}),
    );
    let initialLoad!: Promise<void>;
    let forcedRefresh!: Promise<void>;

    act(() => {
      initialLoad = result.current.loadCvHistory();
      forcedRefresh = result.current.loadCvHistory({force: true});
    });

    const refreshedPage = cvHistoryPage();
    refreshedPage.items[0].original_name = 'newer.pdf';
    await act(async () => {
      refresh.resolve(refreshedPage);
      await forcedRefresh;
    });

    const initialPage = cvHistoryPage();
    initialPage.items[0].original_name = 'older.pdf';
    await act(async () => {
      initial.resolve(initialPage);
      await initialLoad;
    });

    expect(result.current.state.cvHistory.data?.items[0].original_name).toBe(
      'newer.pdf',
    );
  });

  it('keeps request ordering independent for each chunk-list cache key', async () => {
    const initial = deferred<ChunkListPage>();
    const refresh = deferred<ChunkListPage>();
    const other = deferred<ChunkListPage>();
    const otherAttachmentId = '11111111-2222-4333-8444-555555555555';
    const fetchChunkList = vi
      .fn()
      .mockReturnValueOnce(initial.promise)
      .mockReturnValueOnce(refresh.promise)
      .mockReturnValueOnce(other.promise);
    const {result} = renderHook(() =>
      useObservabilityState({api: {fetchChunkList}}),
    );
    let initialLoad!: Promise<void>;
    let forcedRefresh!: Promise<void>;
    let otherLoad!: Promise<void>;

    act(() => {
      initialLoad = result.current.loadChunkList(ATTACHMENT_ID);
      forcedRefresh = result.current.loadChunkList(ATTACHMENT_ID, {force: true});
      otherLoad = result.current.loadChunkList(otherAttachmentId);
    });

    const refreshedPage = chunkListPage();
    refreshedPage.items[0].preview = 'newer preview';
    const otherPage = chunkListPage();
    otherPage.items[0].attachment_id = otherAttachmentId;
    otherPage.items[0].preview = 'other preview';
    await act(async () => {
      refresh.resolve(refreshedPage);
      other.resolve(otherPage);
      await Promise.all([forcedRefresh, otherLoad]);
    });

    const initialPage = chunkListPage();
    initialPage.items[0].preview = 'older preview';
    await act(async () => {
      initial.resolve(initialPage);
      await initialLoad;
    });

    expect(
      result.current.state.chunkLists[ATTACHMENT_ID]?.data?.items[0].preview,
    ).toBe('newer preview');
    expect(
      result.current.state.chunkLists[otherAttachmentId]?.data?.items[0].preview,
    ).toBe('other preview');
  });
});
