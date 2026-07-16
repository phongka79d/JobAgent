/**
 * CV sidebar + shared upload path tests (04A).
 */
import {
  cleanup,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@astryxdesign/core';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {App} from '../app/App';
import {
  ChatApiError,
  getActiveCvUrl,
  SIDEBAR_CV_TURN_MESSAGE,
} from '../features/profile/api';
import {CvSidebar} from '../features/profile/CvSidebar';
import {
  parseAttachmentPublic,
  parseCvUploadResponse,
  parseProfileReadResponse,
  type CvUploadResponse,
  type ProfileReadResponse,
} from '../features/profile/types';
import {getApiBaseUrl} from '../lib/api/chat';

const ATTACHMENT_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';

function emptyProfile(): ProfileReadResponse {
  return {
    present: false,
    profile: null,
    preferences: null,
    active_attachment: null,
    draft_present: false,
    pending_attachment: null,
  };
}

function activeProfile(
  name = 'resume.pdf',
): ProfileReadResponse {
  return {
    present: true,
    profile: {
      summary: 'Engineer',
      current_title: 'Software Engineer',
    },
    preferences: {
      target_roles: [],
      preferred_locations: [],
      acceptable_work_modes: [],
      target_seniority: [],
    },
    active_attachment: {
      id: ATTACHMENT_ID,
      original_name: name,
      mime_type: 'application/pdf',
      size_bytes: 1024,
      page_count: 2,
      state: 'active',
      failure_code: null,
    },
    draft_present: false,
    pending_attachment: null,
  };
}

function uploadResponse(
  name = 'new-cv.pdf',
  id = ATTACHMENT_ID,
): CvUploadResponse {
  return {
    attachment: {
      id,
      original_name: name,
      mime_type: 'application/pdf',
      size_bytes: 2048,
      page_count: 1,
      state: 'staged',
      failure_code: null,
    },
    outcome: 'new',
    profile: null,
    draft: null,
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  // AppShell responsive hooks
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

describe('profile transport parsers', () => {
  it('parses empty and active profile without storage_path', () => {
    expect(parseProfileReadResponse({present: false})).toEqual(emptyProfile());
    const active = parseProfileReadResponse({
      present: true,
      profile: {summary: 'Hi', current_title: 'Dev'},
      preferences: {
        target_roles: ['eng'],
        preferred_locations: [],
        acceptable_work_modes: [],
        target_seniority: [],
      },
      active_attachment: {
        id: ATTACHMENT_ID,
        original_name: 'cv.pdf',
        mime_type: 'application/pdf',
        size_bytes: 10,
        page_count: 1,
        state: 'active',
        failure_code: null,
      },
    });
    expect(active.present).toBe(true);
    expect(active.active_attachment?.original_name).toBe('cv.pdf');
  });

  it('rejects storage_path leakage in attachment and upload payloads', () => {
    expect(() =>
      parseAttachmentPublic({
        id: ATTACHMENT_ID,
        original_name: 'x.pdf',
        mime_type: 'application/pdf',
        size_bytes: 1,
        page_count: 1,
        state: 'staged',
        failure_code: null,
        storage_path: 'secret/path',
      }),
    ).toThrow(/storage_path/);
    expect(() =>
      parseCvUploadResponse({
        attachment: {
          id: ATTACHMENT_ID,
          original_name: 'x.pdf',
          mime_type: 'application/pdf',
          size_bytes: 1,
          page_count: 1,
          state: 'staged',
          failure_code: null,
        },
        outcome: 'new',
        profile: null,
        draft: null,
        storage_path: 'nope',
      }),
    ).toThrow(/storage_path/);
  });

  it('builds active CV URL from VITE_API_BASE_URL only', () => {
    const prev = import.meta.env.VITE_API_BASE_URL;
    try {
      // @ts-expect-error test mutation of import.meta.env
      import.meta.env.VITE_API_BASE_URL = 'http://localhost:8000/';
      expect(getApiBaseUrl()).toBe('http://localhost:8000');
      expect(getActiveCvUrl()).toBe('http://localhost:8000/api/profile/cv');
    } finally {
      // @ts-expect-error restore
      import.meta.env.VITE_API_BASE_URL = prev;
    }
  });
});

describe('CvSidebar empty / active states', () => {
  it('shows empty profile state, upload, and disabled download', async () => {
    const loadProfile = vi.fn().mockResolvedValue(emptyProfile());
    const onSuccess = vi.fn();
    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          isUploadDisabled={false}
          onSidebarUploadSuccess={onSuccess}
          deps={{loadProfile, uploadCv: vi.fn()}}
        />
      </Theme>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('jobagent-profile-state')).toHaveTextContent(
        'No approved profile',
      );
    });
    expect(screen.getByTestId('jobagent-active-cv-filename')).toHaveTextContent(
      'No active CV',
    );
    expect(screen.getByTestId('jobagent-cv-upload')).toBeInTheDocument();
    expect(screen.getByText('Upload CV')).toBeInTheDocument();
    const download = screen.getByTestId('jobagent-cv-download');
    expect(download).toBeDisabled();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('shows active filename, profile state, and enables view/download', async () => {
    const loadProfile = vi.fn().mockResolvedValue(activeProfile('my-cv.pdf'));
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          isUploadDisabled={false}
          onSidebarUploadSuccess={vi.fn()}
          deps={{
            loadProfile,
            uploadCv: vi.fn(),
            getActiveCvUrl: () => 'http://api.test/api/profile/cv',
          }}
        />
      </Theme>,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('jobagent-active-cv-filename'),
      ).toHaveTextContent('my-cv.pdf');
    });
    expect(screen.getByTestId('jobagent-profile-state')).toHaveTextContent(
      /Active/,
    );
    expect(screen.getByText('Replace CV')).toBeInTheDocument();

    const download = screen.getByTestId('jobagent-cv-download');
    expect(download).not.toBeDisabled();
    await userEvent.click(download);
    expect(openSpy).toHaveBeenCalledWith(
      'http://api.test/api/profile/cv',
      '_blank',
      'noopener,noreferrer',
    );
  });

  it('disables upload while interaction is locked', async () => {
    const loadProfile = vi.fn().mockResolvedValue(emptyProfile());
    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          isUploadDisabled
          onSidebarUploadSuccess={vi.fn()}
          deps={{loadProfile, uploadCv: vi.fn()}}
        />
      </Theme>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-cv-upload')).toBeInTheDocument();
    });
    const input = screen.getByTestId('jobagent-cv-upload') as HTMLInputElement;
    // FileInput disables the hidden input and/or marks the trigger aria-disabled.
    const trigger = input.closest('[role="button"]');
    expect(
      input.disabled ||
        input.getAttribute('aria-disabled') === 'true' ||
        trigger?.getAttribute('aria-disabled') === 'true' ||
        trigger?.getAttribute('data-disabled') === 'true',
    ).toBe(true);
  });

  it('surfaces stable upload errors without success callback', async () => {
    const loadProfile = vi.fn().mockResolvedValue(emptyProfile());
    const upload = vi
      .fn()
      .mockRejectedValue(
        new ChatApiError(422, 'PDF_TOO_LARGE', 'PDF exceeds maximum size'),
      );
    const onSuccess = vi.fn();

    render(
      <Theme theme={neutralTheme}>
        <CvSidebar
          isUploadDisabled={false}
          onSidebarUploadSuccess={onSuccess}
          deps={{loadProfile, uploadCv: upload}}
        />
      </Theme>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('jobagent-cv-upload')).toBeInTheDocument();
    });

    const file = new File(['%PDF-1.4 fake'], 'big.pdf', {
      type: 'application/pdf',
    });
    const input = screen.getByTestId('jobagent-cv-upload') as HTMLInputElement;
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(upload).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByText(/PDF exceeds maximum size/)).toBeInTheDocument();
      expect(screen.getByText(/PDF_TOO_LARGE/)).toBeInTheDocument();
    });
    expect(onSuccess).not.toHaveBeenCalled();
  });
});

describe('shared sidebar upload → chat turn', () => {
  it('sidebar and composer share uploadCv; sidebar success starts ID-only turn', async () => {
    const loadHistory = vi.fn().mockResolvedValue({items: [], next_cursor: null});
    const loadProfile = vi
      .fn()
      .mockResolvedValueOnce(emptyProfile())
      .mockResolvedValue(emptyProfile());
    const upload = vi.fn().mockResolvedValue(uploadResponse('side.pdf'));
    const sendTurn = vi.fn().mockResolvedValue(undefined);

    render(
      <Theme theme={neutralTheme}>
        <App
          deps={{
            chat: {loadHistory, sendTurn, uploadCv: upload},
            sidebar: {loadProfile, uploadCv: upload},
          }}
        />
      </Theme>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('jobagent-cv-sidebar')).toBeInTheDocument();
      expect(screen.getByTestId('jobagent-chat-page')).toBeInTheDocument();
    });

    // Target the sidebar file input (first Upload CV).
    const inputs = Array.from(
      document.querySelectorAll('input[type="file"]'),
    ) as HTMLInputElement[];
    expect(inputs.length).toBeGreaterThanOrEqual(1);
    const sidebarInput = inputs[0]!;
    const file = new File(['%PDF-1.4'], 'side.pdf', {type: 'application/pdf'});
    await userEvent.upload(sidebarInput, file);

    await waitFor(() => {
      expect(upload).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(sendTurn).toHaveBeenCalled();
    });

    const body = sendTurn.mock.calls[0]![0] as {
      message: string;
      attachment_ids?: string[];
    };
    expect(body.message).toBe(SIDEBAR_CV_TURN_MESSAGE);
    expect(body.attachment_ids).toEqual([ATTACHMENT_ID]);
    // No File/Blob/PDF body on the turn request.
    expect(JSON.stringify(body)).not.toMatch(/storage_path|%PDF/);
  });
});
