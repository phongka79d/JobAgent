import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {CvManagerDrawer} from '../features/cv-manager/CvManagerDrawer';
import type {CvManagerViewState} from '../features/cv-manager/state';

const PROFILE_ID = 'cccccccc-dddd-4eee-8fff-000000000000';
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
    render(<Theme theme={neutralTheme}><CvManagerDrawer isOpen onOpenChange={onOpenChange} onProfileApproved={onProfileApproved} controller={controller({...base, reextract: {phase: 'review', profileId: PROFILE_ID, stage: null, error: null, draftAvailable: true, review: {profile_id: PROFILE_ID, revision: REVISION, current: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: 'Approved', current_title: 'Engineer', skill_labels: ['TypeScript']}, proposed: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: 'Proposed', current_title: 'Senior Engineer', skill_labels: ['TypeScript', 'React']}, changed_fields: [{field: 'current_title', before: 'Engineer', after: 'Senior Engineer'}], skills_added: ['React'], skills_removed: [], collection_deltas: {experiences: 0, education: 0, languages: 0, certifications: 0}, extraction_confidence: null, can_approve: true, can_discard: true}}}, {approveReview})} /></Theme>);
    screen.getByRole('button', {name: 'Save review'}).focus();
    await userEvent.keyboard('{Enter}');
    await waitFor(() => expect(approveReview).toHaveBeenCalledTimes(1));
    expect(onProfileApproved).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(screen.getByText('Senior Engineer')).toBeInTheDocument();
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
    const onOpenChange = vi.fn();
    render(<Theme theme={neutralTheme}><button type="button">Manage CVs</button><CvManagerDrawer isOpen onOpenChange={onOpenChange} controller={controller({...base, reextract: {phase: 'review', profileId: PROFILE_ID, stage: null, error: null, draftAvailable: true, review: {profile_id: PROFILE_ID, revision: REVISION, current: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: '', current_title: null, skill_labels: []}, proposed: {full_name: null, location: null, phone: null, email: null, github_url: null, summary: '', current_title: null, skill_labels: []}, changed_fields: [], skills_added: [], skills_removed: [], collection_deltas: {experiences: 0, education: 0, languages: 0, certifications: 0}, extraction_confidence: null, can_approve: false, can_discard: true}}}, {discardReview})} /></Theme>);
    screen.getAllByRole('button', {name: 'Discard review'})[0]?.focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.tab();
    await userEvent.keyboard('{Enter}');
    await waitFor(() => expect(discardReview).toHaveBeenCalledTimes(1));
    fireEvent.keyDown(screen.getByRole('dialog', {name: 'CV Manager'}), {key: 'Escape'});
    expect(onOpenChange).toHaveBeenCalledWith(false);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Manage CVs'})).toHaveFocus());
  });
});
