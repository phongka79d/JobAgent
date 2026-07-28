import {apiUrl, ChatApiError, parseErrorBody} from '../../lib/api/chat';
import {parseCvManagerListResponse, type CvManagerListResponse} from './types';

export async function fetchCvManager(signal?: AbortSignal): Promise<CvManagerListResponse> {
  const response = await fetch(apiUrl('/api/cvs'), {method: 'GET', headers: {Accept: 'application/json'}, signal});
  const body = await response.text();
  if (!response.ok) throw parseErrorBody(response.status, body);
  try {
    return parseCvManagerListResponse(JSON.parse(body) as unknown);
  } catch {
    throw new ChatApiError(200, 'INVALID_CV_MANAGER_PAYLOAD', 'CV manager data is unavailable');
  }
}

export async function deleteCv(id: string, signal?: AbortSignal): Promise<void> {
  const response = await fetch(apiUrl(`/api/cvs/${encodeURIComponent(id)}`), {method: 'DELETE', headers: {Accept: 'application/json'}, signal});
  if (response.status === 204) return;
  throw parseErrorBody(response.status, await response.text());
}

export function cvFileUrl(id: string, disposition: 'inline' | 'attachment'): string {
  return apiUrl(`/api/cvs/${encodeURIComponent(id)}/file?disposition=${disposition}`);
}

export type CvManagerApi = {fetchCvManager: typeof fetchCvManager; deleteCv: typeof deleteCv};
export const defaultCvManagerApi: CvManagerApi = {fetchCvManager, deleteCv};
