import { AssetSummary, BrandKit, BrandKitSuggestion, Campaign, CampaignBrief, Job, OutputFormat, ProductionSettings } from '../types';
import { getWorkspaceId, WORKSPACE_STORAGE_KEY } from '../workspace';

const API_BASE = import.meta.env.VITE_API_BASE || (import.meta.env.DEV ? 'http://localhost:8000/api' : '/api');
export const GUEST_WORKSPACE_KEY = WORKSPACE_STORAGE_KEY;
export { getWorkspaceId };

const request = async (endpoint: string, options: RequestInit = {}) => {
  const headers = new Headers(options.headers || {});
  headers.set('X-Workspace-ID', getWorkspaceId());
  
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers, credentials: 'include' });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API Error ${res.status}: ${text}`);
  }
  
  if (res.headers.get('content-type')?.includes('application/json')) {
    return res.json();
  }
  return res;
};

export interface CampaignSummary {
  id: string;
  title: string;
  stage: string;
  updated_at: string;
  output_exists: boolean;
  output_format?: OutputFormat | null;
}

export const listCampaigns = (): Promise<CampaignSummary[]> => request('/campaigns');
export const getHealth = (options: RequestInit = {}): Promise<{status: string, environment: string, demo_mode: boolean}> => request('/health', options);
export const extractBrief = (raw_text: string, source_urls: string[] = [], asset_ids: string[] = []): Promise<{job_id: string, campaign_id: string}> =>
  request('/campaigns/extract-brief', { method: 'POST', body: JSON.stringify({ raw_text, source_urls, asset_ids }) });
export const answerClarification = (id: string, answer: string): Promise<{job_id: string}> => 
  request(`/campaigns/${id}/answer-clarification`, { method: 'POST', body: JSON.stringify({ answer }) });
export const skipClarification = (id: string): Promise<{job_id: string}> => 
  request(`/campaigns/${id}/skip-clarification`, { method: 'POST' });
export const confirmBrief = (id: string, brief: CampaignBrief): Promise<{job_id: string}> => 
  request(`/campaigns/${id}/confirm-brief`, { method: 'POST', body: JSON.stringify(brief) });
export const createCampaign = (brief: CampaignBrief): Promise<Campaign> => 
  request('/campaigns', { method: 'POST', body: JSON.stringify(brief) });
export const getCampaign = (id: string): Promise<Campaign> => request(`/campaigns/${id}`);
export const startResearch = (id: string): Promise<{job_id: string}> => request(`/campaigns/${id}/research`, { method: 'POST' });
export const excludeEvidence = (id: string, evidenceId: string): Promise<Campaign> => request(`/campaigns/${id}/research/evidence/${evidenceId}/exclude`, { method: 'POST' });
export const generateDirections = (id: string): Promise<{job_id: string}> => request(`/campaigns/${id}/directions`, { method: 'POST' });
export const selectDirection = (id: string, directionId: string): Promise<Campaign> => request(`/campaigns/${id}/directions/${directionId}/select`, { method: 'POST' });
export const generateShotPlan = (id: string): Promise<{job_id: string}> => request(`/campaigns/${id}/shot-plan`, { method: 'POST' });
export const generatePreviews = (id: string): Promise<{job_id: string}> => request(`/campaigns/${id}/generate-previews`, { method: 'POST' });
export const selectShot = (id: string, shotId: string): Promise<Campaign> => request(`/campaigns/${id}/shots/${shotId}/select`, { method: 'POST' });
export const selectOutputFormat = (id: string, output_format: OutputFormat): Promise<Campaign> =>
  request(`/campaigns/${id}/output-format`, { method: 'POST', body: JSON.stringify({ output_format }) });
export const updateProductionSettings = (id: string, settings: ProductionSettings): Promise<Campaign> =>
  request(`/campaigns/${id}/production-settings`, { method: 'PUT', body: JSON.stringify(settings) });
export const startProduction = (id: string): Promise<{job_id: string}> => request(`/campaigns/${id}/produce`, { method: 'POST' });
export const retryShot = (id: string, shotId: string): Promise<{job_id: string}> => request(`/campaigns/${id}/shots/${shotId}/retry`, { method: 'POST' });
export const pollJob = (jobId: string): Promise<Job> => request(`/jobs/${jobId}`);
// Live research and Veo production can legitimately take several minutes.
// Explicit provider failures still return immediately; this window only avoids
// misreporting a healthy long-running job as failed.
export const waitForJob = async (jobId: string, maxAttempts = 450): Promise<Job> => {
  let lastError: unknown = null;
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const job: Job = await pollJob(jobId);
      if (job.stage === 'complete' || job.stage === 'failed') {
        return job;
      }
      lastError = null;
    } catch (error) {
      // A single transient proxy/network failure must not strand the UI in a
      // permanent "Analyzing" state while the backend job continues normally.
      lastError = error;
    }
    await new Promise(resolve => setTimeout(resolve, 800));
  }
  if (lastError instanceof Error) {
    throw new Error(`Job ${jobId} could not be refreshed: ${lastError.message}`);
  }
  throw new Error(`Job ${jobId} timed out`);
};

export const listAssets = (): Promise<AssetSummary[]> => request('/assets');
export const uploadAsset = (file: File): Promise<AssetSummary> => {
  const body = new FormData();
  body.append('file', file);
  return request('/assets', { method: 'POST', body });
};
export const importUrlAsset = (url: string, name = 'Website context'): Promise<AssetSummary> =>
  request('/assets/url', { method: 'POST', body: JSON.stringify({ url, name }) });
export const getBrandKit = (): Promise<BrandKit> => request('/brand-kit');
export const updateBrandKit = (kit: BrandKit): Promise<BrandKit> =>
  request('/brand-kit', { method: 'PUT', body: JSON.stringify(kit) });
export const extractBrandPalette = (assetId: string): Promise<{ colors: string[] }> =>
  request('/brand-kit/extract-palette', { method: 'POST', body: JSON.stringify({ asset_id: assetId }) });
export const suggestBrandKit = (kit: BrandKit, uiLanguage: 'en' | 'tr'): Promise<BrandKitSuggestion> =>
  request('/brand-kit/suggest', { method: 'POST', body: JSON.stringify({ kit, ui_language: uiLanguage }) });

export const fetchMediaBlob = async (mediaPathOrUrl: string): Promise<string> => {
  let target = mediaPathOrUrl;
  if (target.startsWith('/api/media/')) {
    target = import.meta.env.DEV ? `http://localhost:8000${target}` : target;
  }
  
  const headers = new Headers();
  headers.set('X-Workspace-ID', getWorkspaceId());

  const res = await fetch(target, {
    headers,
    credentials: 'include',
  });

  if (!res.ok) {
    throw new Error(`Media fetch failed: ${res.status}`);
  }

  const blob = await res.blob();
  return URL.createObjectURL(blob);
};

export const prepareMediaUrl = async (url: string): Promise<string> => {
  if (url.startsWith('/api/media/') || url.startsWith('http://localhost:8000/api/media/')) {
    return fetchMediaBlob(url);
  }

  const parsed = new URL(url);
  const trustedPrivateGcs = parsed.protocol === 'https:' && (parsed.hostname === 'storage.googleapis.com' || parsed.hostname.endsWith('.storage.googleapis.com'));
  if (!trustedPrivateGcs) throw new Error(`prepareMediaUrl rejected untrusted origin for URL: ${url}`);
  return url;
};

export const fetchAssetBlobUrl = async (assetId: string): Promise<string> => {
  return fetchMediaBlob(`${API_BASE}/assets/${assetId}/content`);
};
