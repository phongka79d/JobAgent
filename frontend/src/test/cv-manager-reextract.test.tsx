import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {CvManagerDrawer} from '../features/cv-manager/CvManagerDrawer';
import {useCvManagerState, type CvManagerViewState} from '../features/cv-manager/state';
import type {CvManagerApi} from '../features/cv-manager/api';

const PROFILE_ID = 'cccccccc-dddd-4eee-8fff-000000000000';
const REPLACEMENT_PROFILE_ID = 'dddddddd-eeee-4fff-8aaa-111111111111';
const REVISION = '2026-07-28T10:00:00Z';

afterEach(() => cleanup());

function controller(state: CvManagerViewState, overrides: Record<string, unknown> = {}) {
  return {
    state,
    refresh: vi.fn(), select: vi.fn(), openDeleteDialog: vi.fn(), closeDeleteDialog: vi.fn(),
    confirmDelete: vi.fn().mockResolvedValue(true), startReextract: vi.fn().mockResolvedValue(true),
    loadReview: vi.fn().mockResolvedValue(true),
    approveReview: vi.fn().mockResolvedValue(true), discardReview: vi.fn().mockResolvedValue(true),
    closeReview: vi.fn(),
    ...overrides,
  };
}

const base: CvManagerViewState = {
  phase: 'ready', items: [], selectedId: null, pendingByAttachment: {}, errorsByAttachment: {}, deleteTargetId: null,
};

function RecoveryHarness({api, profileId = PROFILE_ID}: {api: Partial<CvManagerApi>; profileId?: string}) {
  const manager = useCvManagerState({api, profileId, profileReady: true});
  return <><button type="button" onClick={() => void manager.open()}>Open manager</button><output data-testid="recovery-state">{JSON.stringify(manager.state.reextract)}</output></>;
}

function ReextractHarness({api}: {api: Partial<CvManagerApi>}) {
  const manager = useCvManagerState({api, profileId: PROFILE_ID, profileReady: true});
  return <button type="button" onClick={() => void manager.startReextract(PROFILE_ID)}>Start re-extraction</button>;
}

type OperationStatusResponse = Awaited<ReturnType<NonNullable<CvManagerApi['getProfileReextractOperation']>>>;

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return {promise, resolve};
}

function runningOperation(operationId: string): OperationStatusResponse {
  return {operation: {profile_id: PROFILE_ID, operation_id: operationId, state: 'running', error_code: null, error_summary: null, review_revision: null, can_review: false, can_retry: false, can_discard: false}};
}

describe('ProfileReextractReview', () => {
  it('renders direct-stream progress without rendering a synthetic chat turn', () => {
    render(<Theme theme={neutralTheme}><CvManagerDrawer isOpen onOpenChange={vi.fn()} controller={controller({...base, reextract: {phase: 'loading', profileId: PROFILE_ID, stage: 'extracting_document', review: null, error: null, draftAvailable: false}})} /></Theme>);
    expect(screen.getByTestId('jobagent-profile-reextract-progress')).toHaveTextContent('extracting document');
    expect(screen.queryByTestId('jobagent-chat-page')).not.toBeInTheDocument();
  });

  it('saves a durable review, runs App invalidation callback, and closes the drawer', async () => {
    const approveReview = vi.fn().mockResolvedValue(true);
    const onProfileApproved = vi.fn();
    const onOpenChange = vi.fn();
    render(<Theme theme={neutralTheme}><CvManagerDrawer isOpen onOpenChange={onOpenChange} onProfileApproved={onProfileApproved} controller={controller({...base, reextract: {phase: 'review', profileId: PROFILE_ID, stage: null, error: null, draftAvailable: true, review: {profile_id: PROFILE_ID, revision: REVISION, current: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: 'Approved', current_title: 'Engineer', skill_labels: ['TypeScript']}, proposed: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: 'Proposed', current_title: 'Senior Engineer', skill_labels: ['TypeScript', 'React']}, changed_fields: [{field: 'current_title', before: 'Engineer', after: 'Senior Engineer'}], preference_changes: [], skills_added: ['React'], skills_removed: [], collection_deltas: {experiences: 0, education: 0, languages: 0, certifications: 0}, extraction_confidence: null, can_approve: true, can_discard: true}}}, {approveReview})} /></Theme>);
    expect(
      screen.getByText(/current title: Engineer.*Senior Engineer/),
    ).toBeInTheDocument();
    screen.getByRole('button', {name: 'Save review'}).focus();
    await userEvent.keyboard('{Enter}');
    await waitFor(() => expect(approveReview).toHaveBeenCalledTimes(1));
    expect(onProfileApproved).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows preference-only review changes before save', () => {
    render(<Theme theme={neutralTheme}><CvManagerDrawer isOpen onOpenChange={vi.fn()} controller={controller({...base, reextract: {phase: 'review', profileId: PROFILE_ID, stage: null, error: null, draftAvailable: true, review: {profile_id: PROFILE_ID, revision: REVISION, current: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: '', current_title: null, skill_labels: []}, proposed: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: '', current_title: null, skill_labels: []}, changed_fields: [], preference_changes: [{field: 'target_roles', before: ['Platform Engineer'], after: ['ML Platform Engineer']}], skills_added: [], skills_removed: [], collection_deltas: {experiences: 0, education: 0, languages: 0, certifications: 0}, extraction_confidence: null, can_approve: true, can_discard: true}}})} /></Theme>);
    expect(screen.getByText(/target roles: Platform Engineer.*ML Platform Engineer/)).toBeInTheDocument();
  });

  it('offers retry only when the server says no draft is available', async () => {
    const startReextract = vi.fn().mockResolvedValue(false);
    const discardReview = vi.fn().mockResolvedValue(true);
    render(<Theme theme={neutralTheme}><CvManagerDrawer isOpen onOpenChange={vi.fn()} controller={controller({...base, reextract: {phase: 'error', profileId: PROFILE_ID, stage: null, error: {code: 'SOURCE_FAILED', summary: 'The source could not be read'}, draftAvailable: false, review: null}}, {startReextract, discardReview})} /></Theme>);
    screen.getByRole('button', {name: 'Retry'}).focus();
    await userEvent.keyboard('{Enter}');
    expect(startReextract).toHaveBeenCalledWith(PROFILE_ID);
    expect(discardReview).not.toHaveBeenCalled();
  });

  it('retries durable GET instead of starting extraction when the server reports a draft', async () => {
    const loadReview = vi.fn().mockResolvedValue(true);
    const startReextract = vi.fn();
    render(<Theme theme={neutralTheme}><CvManagerDrawer isOpen onOpenChange={vi.fn()} controller={controller({...base, reextract: {phase: 'error', profileId: PROFILE_ID, stage: null, error: {code: 'REVIEW_UNAVAILABLE', summary: 'Retry loading the review'}, draftAvailable: true, review: null}}, {loadReview, startReextract})} /></Theme>);
    screen.getByRole('button', {name: 'Retry'}).focus();
    await userEvent.keyboard('{Enter}');
    expect(loadReview).toHaveBeenCalledWith(PROFILE_ID);
    expect(startReextract).not.toHaveBeenCalled();
  });

  it('confirms keyboard discard and restores focus after Escape closes the manager', async () => {
    const discardReview = vi.fn().mockResolvedValue(true);
    const onProfileDiscarded = vi.fn();
    const onOpenChange = vi.fn();
    render(<Theme theme={neutralTheme}><button type="button">Manage CVs</button><CvManagerDrawer isOpen onOpenChange={onOpenChange} onProfileDiscarded={onProfileDiscarded} controller={controller({...base, reextract: {phase: 'review', profileId: PROFILE_ID, stage: null, error: null, draftAvailable: true, review: {profile_id: PROFILE_ID, revision: REVISION, current: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: '', current_title: null, skill_labels: []}, proposed: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: '', current_title: null, skill_labels: []}, changed_fields: [], preference_changes: [], skills_added: [], skills_removed: [], collection_deltas: {experiences: 0, education: 0, languages: 0, certifications: 0}, extraction_confidence: null, can_approve: false, can_discard: true}}}, {discardReview})} /></Theme>);
    screen.getAllByRole('button', {name: 'Discard review'})[0]?.focus();
    await userEvent.keyboard('{Enter}');
    const confirmation = await screen.findByRole('alertdialog', {
      name: 'Discard this profile review?',
    });
    within(confirmation).getByRole('button', {name: 'Discard review'}).focus();
    await userEvent.keyboard('{Enter}');
    await waitFor(() => expect(discardReview).toHaveBeenCalledTimes(1));
    expect(onProfileDiscarded).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(screen.getByRole('dialog', {name: 'CV Manager'}), {key: 'Escape'});
    expect(onOpenChange).toHaveBeenCalledWith(false);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Manage CVs'})).toHaveFocus());
  });

  it('closing the drawer does not abort a running re-extraction', async () => {
    const streamAbort = vi.fn();
    const onOpenChange = vi.fn();
    render(<Theme theme={neutralTheme}><CvManagerDrawer isOpen onOpenChange={onOpenChange} controller={controller({...base, reextract: {phase: 'loading', profileId: PROFILE_ID, stage: 'extracting_document', review: null, error: null, draftAvailable: false}}, {close: streamAbort})} /></Theme>);

    fireEvent.keyDown(screen.getByRole('dialog', {name: 'CV Manager'}), {key: 'Escape'});

    expect(streamAbort).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(screen.getByText('extracting document')).toBeInTheDocument();
  });

  it('keeps a same-profile re-extraction stream active when start is requested again', async () => {
    const streamAbort = vi.fn();
    const streamProfileReextract = vi.fn(async (_profileId: string, _handlers: Parameters<NonNullable<CvManagerApi['streamProfileReextract']>>[1], signal?: AbortSignal) => {
      signal?.addEventListener('abort', streamAbort);
      await new Promise<void>(() => undefined);
    });
    render(<ReextractHarness api={{fetchCvManager: vi.fn().mockResolvedValue({items: []}), deleteCv: vi.fn(), streamProfileReextract}} />);

    await userEvent.click(screen.getByRole('button', {name: 'Start re-extraction'}));
    await waitFor(() => expect(streamProfileReextract).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByRole('button', {name: 'Start re-extraction'}));

    expect(streamAbort).not.toHaveBeenCalled();
    expect(streamProfileReextract).toHaveBeenCalledTimes(1);
  });

  it('recovers a review-ready operation from authoritative status after open', async () => {
    const operationId = '11111111-1111-4111-8111-111111111111';
    const getProfileReextractOperation = vi.fn().mockResolvedValue({operation: {profile_id: PROFILE_ID, operation_id: operationId, state: 'review_ready', error_code: null, error_summary: null, review_revision: REVISION, can_review: true, can_retry: false, can_discard: true}});
    const getProfileReextractReview = vi.fn().mockResolvedValue({profile_id: PROFILE_ID, source: 'reextract', operation_id: operationId, operation_state: 'review_ready', revision: REVISION, current: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: 'Approved', current_title: null, skill_labels: []}, proposed: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: 'Proposed', current_title: null, skill_labels: []}, changed_fields: [], preference_changes: [], skills_added: [], skills_removed: [], collection_deltas: {experiences: 0, education: 0, languages: 0, certifications: 0}, extraction_confidence: null, can_approve: true, can_discard: true});
    render(<RecoveryHarness api={{fetchCvManager: vi.fn().mockResolvedValue({items: []}), deleteCv: vi.fn(), getProfileReextractOperation, getProfileReextractReview}} />);

    await userEvent.click(screen.getByRole('button', {name: 'Open manager'}));

    await waitFor(() => expect(getProfileReextractReview).toHaveBeenCalledWith(PROFILE_ID, expect.any(AbortSignal), operationId));
    expect(getProfileReextractOperation).toHaveBeenCalledWith(PROFILE_ID, expect.any(AbortSignal));
    expect(screen.getByTestId('recovery-state')).toHaveTextContent('"phase":"review"');
  });

  it('keeps a newer same-scope operation status when an older recovery resolves late', async () => {
    const first = deferred<OperationStatusResponse>();
    const second = deferred<OperationStatusResponse>();
    const getProfileReextractOperation = vi.fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    render(<RecoveryHarness api={{fetchCvManager: vi.fn().mockResolvedValue({items: []}), deleteCv: vi.fn(), getProfileReextractOperation}} />);

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByRole('button', {name: 'Open manager'}));
    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalledTimes(2));

    second.resolve(runningOperation('22222222-2222-4222-8222-222222222222'));
    await waitFor(() => expect(screen.getByTestId('recovery-state')).toHaveTextContent('22222222-2222-4222-8222-222222222222'));
    await act(async () => {
      first.resolve(runningOperation('11111111-1111-4111-8111-111111111111'));
      await first.promise;
    });

    expect(screen.getByTestId('recovery-state')).toHaveTextContent('22222222-2222-4222-8222-222222222222');
  });

  it('aborts the effect-owned operation status request on unmount', async () => {
    const pending = deferred<OperationStatusResponse>();
    let requestSignal: AbortSignal | undefined;
    const getProfileReextractOperation = vi.fn((_profileId: string, signal?: AbortSignal) => {
      requestSignal = signal;
      return pending.promise;
    });
    const {unmount} = render(<RecoveryHarness api={{fetchCvManager: vi.fn().mockResolvedValue({items: []}), deleteCv: vi.fn(), getProfileReextractOperation}} />);

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalledTimes(1));
    expect(requestSignal).toBeDefined();
    expect(requestSignal?.aborted).toBe(false);
    unmount();
    expect(requestSignal?.aborted).toBe(true);
  });

  it('aborts the effect-owned operation status request on real profile-scope replacement', async () => {
    const first = deferred<OperationStatusResponse>();
    const second = deferred<OperationStatusResponse>();
    let firstSignal: AbortSignal | undefined;
    const getProfileReextractOperation = vi.fn((_profileId: string, signal?: AbortSignal) => {
      if (getProfileReextractOperation.mock.calls.length === 1) firstSignal = signal;
      return getProfileReextractOperation.mock.calls.length === 1 ? first.promise : second.promise;
    });
    const api = {fetchCvManager: vi.fn().mockResolvedValue({items: []}), deleteCv: vi.fn(), getProfileReextractOperation};
    const {rerender} = render(<RecoveryHarness api={api} />);

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalledTimes(1));
    expect(firstSignal).toBeDefined();
    rerender(<RecoveryHarness api={api} profileId={REPLACEMENT_PROFILE_ID} />);

    await waitFor(() => expect(getProfileReextractOperation).toHaveBeenCalledTimes(2));
    expect(firstSignal?.aborted).toBe(true);
  });
});
