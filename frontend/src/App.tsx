import React, { useState, useEffect, useRef } from 'react';
import { BrowserRouter, Routes, Route, Link, useNavigate, useParams, useLocation } from 'react-router-dom';
import { 
  Sparkles, 
  FolderGit2, 
  Layers, 
  Palette, 
  Settings as SettingsIcon, 
  Search, 
  ArrowRight, 
  Plus, 
  Video, 
  FileText, 
  Image as ImageIcon, 
  Globe, 
  Trash2, 
  Upload, 
  Check, 
  ChevronRight,
  Menu,
  X,
  ShieldCheck,
  AlertTriangle,
  ArrowLeftRight,
  Zap,
  Film
} from 'lucide-react';
import { t, getLang, setLang, Lang } from './i18n';
import * as api from './services/api';
import { CampaignSummary } from './services/api';
import { AssetSummary, BrandKit } from './types';
import CampaignFlow from './CampaignFlow';

// Helper for human-readable stage badge mapping
const getStageHumanLabel = (stage: string): string => {
  const stageMap: Record<string, keyof typeof import('./i18n').translations['en']> = {
    'intake': 'stage_intake',
    'intake_clarification': 'stage_intake',
    'brief_review': 'stage_brief_review',
    'research_plan': 'stage_research_plan',
    'research': 'stage_research',
    'verification': 'stage_verification',
    'directions': 'stage_directions',
    'studio': 'stage_studio',
    'production': 'stage_production',
    'reel': 'stage_reel',
    'failed': 'stage_failed'
  };
  const key = stageMap[stage];
  return key ? t(key) : stage.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};

// Helper for human-readable output format label
const getFormatHumanLabel = (format?: string | null): string => {
  if (format === 'campaign_pack') return t('format_campaign_pack');
  if (format === 'static_post') return t('format_static_post');
  if (format === 'carousel_post') return t('format_carousel_post');
  if (format === 'slideshow_reel') return t('format_slideshow_reel');
  if (format === 'full_video_reel') return t('format_full_video_reel');
  return t('format_hybrid_reel');
};

// Helper for brand voice default detection
const isDefaultBrandVoice = (voice: string | undefined): boolean => {
  return !voice || voice === 'Clear, confident, human' || voice === 'Açık, güven veren, samimi';
};

const getBrandProfileContextKey = (kit: BrandKit, assets: AssetSummary[]): string => {
  const orderedContext = assets
    .filter(asset => ['url', 'text', 'pdf', 'docx'].includes(asset.kind) && Boolean(asset.text_preview))
    .sort((left, right) => right.created_at.localeCompare(left.created_at));
  const brandToken = kit.brand_name.trim().toLowerCase();
  const relatedContext = brandToken.length >= 3
    ? orderedContext.filter(asset => `${asset.name} ${asset.source_url || ''} ${asset.text_preview}`.toLowerCase().includes(brandToken))
    : orderedContext.slice(0, 1);
  const contextIds = relatedContext
    .slice(0, 4)
    .map(asset => asset.asset_id)
    .sort()
    .join(',');
  return [
    brandToken,
    kit.logo_asset_id || '',
    kit.primary_product_asset_id || '',
    contextIds,
  ].join('|').slice(0, 600);
};

// ============================================================================
// ASSET THUMBNAIL COMPONENT (Authenticated, Workspace-Safe, Object URL Revoked)
// ============================================================================
const AssetThumbnail: React.FC<{
  asset?: AssetSummary | null;
  className?: string;
  fallbackIconSize?: number;
}> = ({ asset, className = "w-full h-full object-cover", fallbackIconSize = 20 }) => {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;

    if (asset && (asset.kind === 'image' || asset.kind === 'video')) {
      setLoadFailed(false);
      api.fetchAssetBlobUrl(asset.asset_id)
        .then(url => {
          if (active) {
            createdUrl = url;
            setBlobUrl(url);
          } else {
            URL.revokeObjectURL(url);
          }
        })
        .catch(() => {
          if (active) setLoadFailed(true);
        });
    } else {
      setBlobUrl(null);
    }

    return () => {
      active = false;
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl);
      }
    };
  }, [asset?.asset_id, asset?.kind]);

  if (!asset || loadFailed || (!blobUrl && asset.kind !== 'image' && asset.kind !== 'video')) {
    const kind = asset?.kind || 'image';
    return (
      <div className="w-full h-full flex items-center justify-center bg-surfaceRaised text-accent">
        {kind === 'image' ? <ImageIcon size={fallbackIconSize} /> : 
         kind === 'video' ? <Video size={fallbackIconSize} /> : 
         kind === 'url' ? <Globe size={fallbackIconSize} /> : 
         <FileText size={fallbackIconSize} />}
      </div>
    );
  }

  if (blobUrl && asset.kind === 'image') {
    return <img src={blobUrl} alt={asset.name} className={className} />;
  }

  if (blobUrl && asset.kind === 'video') {
    return <video src={blobUrl} muted playsInline className={className} />;
  }

  return (
    <div className="w-full h-full flex items-center justify-center bg-surfaceRaised text-primaryText/40">
      <ImageIcon size={fallbackIconSize} />
    </div>
  );
};

// ============================================================================
// TOP HEADER
// ============================================================================
const TopHeader = ({ onOpenMobileNav }: { onOpenMobileNav: () => void }) => {
  return (
    <header className="h-16 border-b border-white/10 px-4 md:px-8 flex items-center justify-between bg-surface/80 backdrop-blur-md sticky top-0 z-40">
      <div className="flex items-center gap-3">
        {/* Mobile Hamburger Button */}
        <button
          type="button"
          onClick={onOpenMobileNav}
          aria-label={t('menu')}
          className="md:hidden p-2 rounded-xl bg-surfaceRaised hover:bg-white/10 border border-white/10 text-primaryText transition-colors focus-visible:ring-2 focus-visible:ring-accent outline-none"
        >
          <Menu size={18} />
        </button>

        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
          <span className="text-xs font-mono uppercase tracking-widest text-primaryText/70">{t('liveStack')}</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-surfaceRaised/80 border border-white/5 text-xs text-primaryText/70">
          <ShieldCheck size={14} className="text-accent" />
          <span>{t('demoWorkspace')}</span>
        </div>
        <Link 
          to="/campaigns/new" 
          className="bg-accent hover:bg-accentHover text-background font-semibold px-4 py-2 rounded-xl text-xs flex items-center gap-2 transition-all shadow-lg shadow-accent/20 active:scale-95 focus-visible:ring-2 focus-visible:ring-accent outline-none"
        >
          <Plus size={15} />
          <span>{t('newCampaign')}</span>
        </Link>
      </div>
    </header>
  );
};

// ============================================================================
// SIDEBAR (Responsive Desktop + Accessible Mobile Drawer)
// ============================================================================
const Sidebar = ({ mobileOpen, onCloseMobile }: { mobileOpen: boolean; onCloseMobile: () => void }) => {
  const location = useLocation();

  const links = [
    { to: '/campaigns/new', label: t('newCampaign'), icon: Plus, highlight: true },
    { to: '/campaigns', label: t('campaigns'), icon: FolderGit2 },
    { to: '/assets', label: t('assets'), icon: Layers },
    { to: '/brand-kit', label: t('brandKit'), icon: Palette },
    { to: '/settings', label: t('settings'), icon: SettingsIcon },
  ];

  return (
    <>
      {/* Mobile Backdrop Overlay */}
      {mobileOpen && (
        <div 
          onClick={onCloseMobile}
          className="md:hidden fixed inset-0 bg-background/80 backdrop-blur-sm z-50 transition-opacity animate-in fade-in duration-200"
          aria-hidden="true"
        />
      )}

      {/* Sidebar Container */}
      <aside 
        className={`fixed top-0 bottom-0 left-0 z-50 w-64 bg-surface border-r border-white/10 flex flex-col justify-between transition-transform duration-300 ease-out md:translate-x-0 ${
          mobileOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full'
        }`}
      >
        <div className="p-6">
          {/* Logo & Product Title */}
          <div className="flex items-center justify-between mb-8">
            <Link to="/campaigns" onClick={onCloseMobile} className="flex items-center gap-3 group">
              <div className="w-10 h-10 rounded-xl bg-accent flex items-center justify-center text-background font-black text-lg shadow-md group-hover:scale-105 transition-transform">
                RD
              </div>
              <div>
                <h1 className="font-bold text-sm text-primaryText tracking-tight">Reel Director</h1>
                <p className="text-[10px] font-mono uppercase tracking-wider text-accent/90">{t('creativeWorkspaceSubtitle')}</p>
              </div>
            </Link>

            {/* Mobile Close Button */}
            <button 
              type="button"
              onClick={onCloseMobile}
              aria-label={t('close')}
              className="md:hidden p-1.5 rounded-lg text-primaryText/50 hover:text-primaryText hover:bg-white/10 transition-colors"
            >
              <X size={18} />
            </button>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1.5" aria-label={t('primaryNav')}>
            {links.map((link) => {
              const Icon = link.icon;
              const isActive = location.pathname === link.to || (link.to === '/campaigns' && location.pathname === '/');
              return (
                <Link
                  key={link.to}
                  to={link.to}
                  onClick={onCloseMobile}
                  className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all focus-visible:ring-2 focus-visible:ring-accent outline-none ${
                    isActive 
                      ? 'bg-accent/15 text-accent border border-accent/20 shadow-sm' 
                      : link.highlight
                        ? 'bg-white/5 text-primaryText hover:bg-white/10 border border-white/5'
                        : 'text-primaryText/70 hover:text-primaryText hover:bg-white/5'
                  }`}
                >
                  <Icon size={16} />
                  <span>{link.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Footer Brand Info */}
        <div className="p-6 border-t border-white/5">
          <div className="p-3 rounded-xl bg-surfaceRaised border border-white/5">
            <div className="flex items-center gap-2 mb-1">
              <Zap size={14} className="text-accent" />
              <span className="text-[11px] font-semibold text-primaryText">{t('hackathonPreview')}</span>
            </div>
            <p className="text-[10px] text-primaryText/50 leading-relaxed font-mono">
              {t('sidebarFooter')}
            </p>
          </div>
        </div>
      </aside>
    </>
  );
};

// ============================================================================
// CAMPAIGNS LIST (Search, Category Filters, Localized Stage Badges, Keyboard Access)
// ============================================================================
const CampaignsList = () => {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterTab, setFilterTab] = useState<'all' | 'in_progress' | 'completed'>('all');
  const navigate = useNavigate();

  useEffect(() => {
    api.listCampaigns()
      .then(data => {
        setCampaigns(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message || t('campaignsLoadError'));
        setLoading(false);
      });
  }, []);

  const inProgressCount = campaigns.filter(c => c.stage !== 'reel' && c.stage !== 'failed').length;
  const completedCount = campaigns.filter(c => c.stage === 'reel').length;

  const filteredCampaigns = campaigns.filter(c => {
    const matchesSearch = searchQuery === '' || 
      c.title.toLowerCase().includes(searchQuery.toLowerCase());
    
    if (!matchesSearch) return false;
    if (filterTab === 'in_progress') return c.stage !== 'reel' && c.stage !== 'failed';
    if (filterTab === 'completed') return c.stage === 'reel';
    return true;
  });

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto space-y-8 animate-in fade-in duration-300">
      {/* Title & Stats */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-primaryText">{t('campaignLibrary')}</h2>
          <p className="text-xs md:text-sm text-primaryText/60 mt-1">{t('campaignLibrarySubtitle')}</p>
        </div>
        <Link 
          to="/campaigns/new" 
          className="bg-accent hover:bg-accentHover text-background font-semibold px-5 py-2.5 rounded-xl text-xs flex items-center gap-2 transition-all self-start md:self-auto shadow-md shadow-accent/20 focus-visible:ring-2 focus-visible:ring-accent outline-none"
        >
          <Plus size={16} />
          <span>{t('createCampaign')}</span>
        </Link>
      </div>

      {/* Search & Filter Toolbar */}
      {campaigns.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-4 justify-between items-stretch sm:items-center bg-surfaceRaised/60 p-2 rounded-2xl border border-white/5">
          {/* Filter Tabs */}
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setFilterTab('all')}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                filterTab === 'all' ? 'bg-white/10 text-primaryText shadow-sm' : 'text-primaryText/50 hover:text-primaryText'
              }`}
            >
              {t('filterAll')} ({campaigns.length})
            </button>
            <button
              type="button"
              onClick={() => setFilterTab('in_progress')}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                filterTab === 'in_progress' ? 'bg-accent/20 text-accent shadow-sm' : 'text-primaryText/50 hover:text-primaryText'
              }`}
            >
              {t('filterInProgress')} ({inProgressCount})
            </button>
            <button
              type="button"
              onClick={() => setFilterTab('completed')}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                filterTab === 'completed' ? 'bg-success/20 text-success shadow-sm' : 'text-primaryText/50 hover:text-primaryText'
              }`}
            >
              {t('filterCompleted')} ({completedCount})
            </button>
          </div>

          {/* Search Input */}
          <div className="relative min-w-[240px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-primaryText/40" />
            <input
              type="text"
              placeholder={t('searchCampaigns')}
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full bg-background border border-white/10 rounded-xl pl-9 pr-3 py-1.5 text-xs text-primaryText placeholder:text-primaryText/30 focus:border-accent outline-none"
            />
          </div>
        </div>
      )}

      {/* Content Area */}
      {loading ? (
        <div className="p-16 text-center text-primaryText/50 font-mono text-xs animate-pulse">
          {t('loadingCampaign')}
        </div>
      ) : error ? (
        <div className="p-8 text-center bg-error/10 border border-error/20 rounded-2xl text-error text-xs">
          {error}
        </div>
      ) : campaigns.length === 0 ? (
        <div className="text-center py-16 px-6 bg-surfaceRaised/40 border border-dashed border-white/10 rounded-3xl space-y-4">
          <div className="w-14 h-14 bg-surfaceRaised rounded-2xl flex items-center justify-center mx-auto text-accent shadow-inner">
            <Sparkles size={26} />
          </div>
          <div className="max-w-md mx-auto space-y-2">
            <h3 className="font-semibold text-base text-primaryText">{t('emptyCampaignTitle')}</h3>
            <p className="text-xs text-primaryText/50 leading-relaxed">{t('emptyCampaignDesc')}</p>
          </div>
          <Link 
            to="/campaigns/new" 
            className="inline-flex items-center gap-2 bg-accent hover:bg-accentHover text-background font-semibold px-5 py-2.5 rounded-xl text-xs transition-all shadow-md"
          >
            <Plus size={16} />
            <span>{t('createCampaign')}</span>
          </Link>
        </div>
      ) : filteredCampaigns.length === 0 ? (
        <div className="text-center py-12 bg-surfaceRaised/20 border border-white/5 rounded-2xl text-primaryText/40 text-xs">
          <p>{t('noFilterResults')}</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredCampaigns.map((c) => {
            const isCompleted = c.stage === 'reel';
            const stageLabel = getStageHumanLabel(c.stage);
            const formatLabel = getFormatHumanLabel(c.output_format);
            const dateStr = new Date(c.updated_at || Date.now()).toLocaleDateString(getLang() === 'tr' ? 'tr-TR' : 'en-US');

            return (
              <div 
                key={c.id} 
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate(`/campaigns/${c.id}`);
                  }
                }}
                onClick={() => navigate(`/campaigns/${c.id}`)}
                className="group relative bg-surfaceRaised/70 hover:bg-surfaceRaised border border-white/10 hover:border-white/20 rounded-2xl p-5 transition-all flex flex-col justify-between cursor-pointer hover:shadow-xl hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-accent outline-none"
              >
                <div>
                  {/* Card Header & Stage Badge */}
                  <div className="flex items-start justify-between gap-3 mb-4">
                    <span className={`text-[10px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded-full border ${
                      isCompleted 
                        ? 'bg-success/15 border-success/30 text-success' 
                        : c.stage === 'failed'
                          ? 'bg-error/15 border-error/30 text-error'
                          : 'bg-accent/15 border-accent/30 text-accent'
                    }`}>
                      {stageLabel}
                    </span>
                    <span className="text-[11px] font-mono text-primaryText/40">{dateStr}</span>
                  </div>

                  {/* Compact 9:16 Thumbnail Motif */}
                  <div className="w-full h-28 bg-background/80 rounded-xl mb-4 border border-white/5 flex items-center justify-center relative overflow-hidden group-hover:border-accent/30 transition-colors">
                    <div className="w-12 h-20 rounded-md border border-white/10 bg-surfaceRaised flex flex-col items-center justify-center text-primaryText/30 group-hover:text-accent transition-colors">
                      {['static_post', 'carousel_post'].includes(c.output_format || '') ? <ImageIcon size={18} /> : <Film size={18} />}
                      <span className="text-[8px] font-mono mt-1 font-bold">{['static_post', 'carousel_post'].includes(c.output_format || '') ? '4:5' : '9:16'}</span>
                    </div>
                  </div>

                  {/* Subject & Goal */}
                  <h3 className="font-semibold text-sm text-primaryText group-hover:text-accent transition-colors break-words line-clamp-1">
                    {c.title || t('newCampaign')}
                  </h3>
                  <p className="text-xs text-primaryText/50 mt-1 line-clamp-2 leading-relaxed">
                    {formatLabel} · {t('sidebarFooter')}
                  </p>
                </div>

                {/* Card Footer */}
                <div className="mt-5 pt-3 border-t border-white/5 flex items-center justify-between text-xs text-primaryText/60">
                  <span className="text-[10px] font-mono text-primaryText/40">{formatLabel}</span>
                  <span className="text-accent group-hover:translate-x-1 transition-transform flex items-center gap-1 font-semibold text-[11px]">
                    {isCompleted ? t('viewOutput') : t('resume')} <ArrowRight size={13} />
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ============================================================================
// ASSETS PAGE (Unified Intake Surface, Real Authenticated Thumbnails, Cleanup)
// ============================================================================
const AssetsPage = () => {
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [importingUrl, setImportingUrl] = useState(false);

  const load = () => {
    setLoading(true);
    api.listAssets()
      .then(data => { setAssets(data); setLoading(false); })
      .catch(err => { setError(err.message || t('uploadFailed')); setLoading(false); });
  };

  useEffect(() => { load(); }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadAsset(file);
      setSuccessMsg(t('assetAddedSuccess'));
      setTimeout(() => setSuccessMsg(null), 3000);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('uploadFailed'));
    } finally {
      setUploading(false);
    }
  };

  const handleImportUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!urlInput.trim()) return;
    setImportingUrl(true);
    setError(null);
    try {
      await api.importUrlAsset(urlInput.trim());
      setUrlInput('');
      setSuccessMsg(t('assetAddedSuccess'));
      setTimeout(() => setSuccessMsg(null), 3000);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('uploadFailed'));
    } finally {
      setImportingUrl(false);
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto space-y-8 animate-in fade-in duration-300">
      {/* Title */}
      <div>
        <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-primaryText">{t('assetLibraryTitle')}</h2>
        <p className="text-xs md:text-sm text-primaryText/60 mt-1">{t('assetsSubtitle')}</p>
      </div>

      {/* Status Alerts */}
      {error && (
        <div className="p-4 bg-error/10 border border-error/20 rounded-xl text-error text-xs">
          {error}
        </div>
      )}
      {successMsg && (
        <div className="p-4 bg-success/10 border border-success/20 rounded-xl text-success text-xs flex items-center gap-2">
          <Check size={16} />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Unified Intake Container */}
      <div className="bg-surfaceRaised border border-white/10 rounded-2xl p-6 space-y-6">
        <div>
          <h3 className="font-semibold text-sm text-primaryText">{t('unifiedIntakeTitle')}</h3>
          <p className="text-xs text-primaryText/50 mt-1">{t('unifiedIntakeSubtitle')}</p>
        </div>

        <div className="grid md:grid-cols-2 gap-5">
          {/* URL Import */}
          <form onSubmit={handleImportUrl} className="space-y-3 bg-background/60 p-4 rounded-xl border border-white/5">
            <div className="flex items-center gap-2 text-xs font-semibold text-primaryText/80">
              <Globe size={15} className="text-accent" />
              <span>{t('addUrl')}</span>
            </div>
            <div className="flex gap-2">
              <input
                type="url"
                required
                placeholder={t('assetUrlPlaceholder')}
                value={urlInput}
                onChange={e => setUrlInput(e.target.value)}
                className="flex-1 bg-surface border border-white/10 rounded-xl px-3 py-2 text-xs text-primaryText placeholder:text-primaryText/30 focus:border-accent outline-none"
              />
              <button
                type="submit"
                disabled={importingUrl}
                className="bg-accent hover:bg-accentHover disabled:opacity-50 text-background font-semibold px-4 py-2 rounded-xl text-xs transition-all"
              >
                {importingUrl ? '...' : t('addUrl')}
              </button>
            </div>
          </form>

          {/* File Upload Dropzone */}
          <div className="bg-background/60 p-4 rounded-xl border border-white/5 flex flex-col justify-between">
            <div className="flex items-center gap-2 text-xs font-semibold text-primaryText/80 mb-2">
              <Upload size={15} className="text-accent" />
              <span>{t('uploadAsset')}</span>
            </div>
            <label className="cursor-pointer border border-dashed border-white/15 hover:border-accent/40 rounded-xl p-3 text-center transition-all bg-surface/50 hover:bg-white/5 block">
              <input type="file" onChange={handleUpload} disabled={uploading} className="hidden" />
              <span className="text-xs font-semibold text-primaryText/80 block">
                {uploading ? t('loadingAssets') : t('attachFiles')}
              </span>
              <span className="text-[10px] text-primaryText/40 block mt-0.5">{t('fileTypes')}</span>
            </label>
          </div>
        </div>
      </div>

      {/* Asset Cards Grid */}
      {loading ? (
        <div className="p-16 text-center text-primaryText/50 font-mono text-xs animate-pulse">
          {t('loadingAssets')}
        </div>
      ) : assets.length === 0 ? (
        <div className="text-center py-16 bg-surfaceRaised/30 border border-dashed border-white/10 rounded-3xl text-primaryText/50 text-xs">
          {t('assetsEmpty')}
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {assets.map((asset) => {
            const kindKey = `kind_${asset.kind}` as keyof typeof import('./i18n').translations['en'];
            const localizedKind = t(kindKey) || asset.kind;
            const dateStr = new Date(asset.created_at || Date.now()).toLocaleDateString(getLang() === 'tr' ? 'tr-TR' : 'en-US');

            return (
              <article key={asset.asset_id} className="bg-surfaceRaised/60 border border-white/10 rounded-2xl p-5 flex flex-col justify-between hover:border-white/20 transition-all group">
                <div>
                  {/* Card Header & Localized Kind Badge */}
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <span className="text-[9px] font-mono uppercase tracking-widest text-primaryText/60 border border-white/10 rounded-full px-2.5 py-1 bg-surfaceRaised">
                      {localizedKind}
                    </span>
                    <span className="text-[11px] font-mono text-primaryText/40">{formatBytes(asset.size_bytes)}</span>
                  </div>

                  {/* Real Authenticated Thumbnail for image/video assets */}
                  {(asset.kind === 'image' || asset.kind === 'video') && (
                    <div className="w-full h-36 bg-background rounded-xl mb-3.5 border border-white/10 overflow-hidden relative group-hover:border-accent/40 transition-colors">
                      <AssetThumbnail asset={asset} className="w-full h-full object-cover" />
                    </div>
                  )}

                  <h3 className="font-semibold text-sm text-primaryText break-words line-clamp-2">{asset.name}</h3>

                  {asset.text_preview && (
                    <p className="text-xs text-primaryText/60 mt-3 line-clamp-3 leading-relaxed bg-background/50 p-2.5 rounded-xl border border-white/5 font-mono text-[11px]">
                      {asset.text_preview}
                    </p>
                  )}
                </div>

                <div className="mt-4 pt-3 border-t border-white/5 text-[10px] font-mono text-primaryText/40">
                  {dateStr}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ============================================================================
// BRAND KIT PAGE (Color Swatches, Segmented Controls, Real Thumbnails & Live Preview)
// ============================================================================
const BrandKitPage = () => {
  const [kit, setKit] = useState<BrandKit | null>(null);
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [suggestionStatus, setSuggestionStatus] = useState<'idle' | 'analyzing' | 'ready' | 'error'>('idle');
  const [newColorHex, setNewColorHex] = useState('');
  const [extractingPalette, setExtractingPalette] = useState<'logo' | 'product' | null>(null);
  const kitRef = useRef<BrandKit | null>(null);
  const requestedProfileKey = useRef<string | null>(null);

  useEffect(() => {
    kitRef.current = kit;
  }, [kit]);

  const requestBrandSuggestion = async (currentKit: BrandKit, contextKey: string) => {
    requestedProfileKey.current = contextKey;
    setSuggestionStatus('analyzing');
    setError(null);
    try {
      const suggestion = await api.suggestBrandKit(currentKit, getLang());
      const latestKit = kitRef.current;
      if (!latestKit || getBrandProfileContextKey(latestKit, assets) !== contextKey) return;
      const suggestedKit: BrandKit = {
        ...latestKit,
        brand_voice: suggestion.brand_voice,
        brand_colors: suggestion.brand_colors,
        font_family: suggestion.font_family,
        caption_preset: suggestion.caption_preset,
        cta_treatment: suggestion.cta_treatment,
        motion_preset: suggestion.motion_preset,
        default_visual_treatment: suggestion.default_visual_treatment,
        sample_headline: suggestion.sample_headline,
        sample_caption: suggestion.sample_caption,
        sample_cta: suggestion.sample_cta,
        smart_profile_source: suggestion.source,
        smart_profile_context_key: suggestion.context_key,
        smart_profile_rationale: suggestion.rationale,
      };
      setKit(suggestedKit);
      kitRef.current = suggestedKit;
      const persisted = await api.updateBrandKit(suggestedKit);
      if (getBrandProfileContextKey(kitRef.current || persisted, assets) === contextKey) {
        setKit(persisted);
        kitRef.current = persisted;
        setSuggestionStatus('ready');
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      }
    } catch (err) {
      requestedProfileKey.current = null;
      setSuggestionStatus('error');
      setError(err instanceof Error ? err.message : t('brandSuggestionFailed'));
    }
  };

  useEffect(() => {
    Promise.all([api.getBrandKit(), api.listAssets()])
      .then(([loadedKit, loadedAssets]) => { setKit(loadedKit); setAssets(loadedAssets); })
      .catch(err => setError(err.message));
  }, []);

  useEffect(() => {
    if (!kit) return;
    const contextKey = getBrandProfileContextKey(kit, assets);
    const hasContext = Boolean(kit.brand_name.trim() || kit.logo_asset_id || kit.primary_product_asset_id || contextKey.split('|')[3]);
    if (!hasContext) {
      setSuggestionStatus('idle');
      return;
    }
    if (kit.smart_profile_context_key === contextKey && kit.smart_profile_source !== 'default') {
      setSuggestionStatus('ready');
      requestedProfileKey.current = contextKey;
      return;
    }
    if (requestedProfileKey.current === contextKey) return;
    const timer = window.setTimeout(() => requestBrandSuggestion(kit, contextKey), 800);
    return () => window.clearTimeout(timer);
  }, [kit?.brand_name, kit?.logo_asset_id, kit?.primary_product_asset_id, kit?.smart_profile_context_key, kit?.smart_profile_source, assets]);

  if (!kit) return <div className="p-12 text-center text-primaryText/50">{error || t('loadingAssets')}</div>;
  const imageAssets = assets.filter(asset => asset.kind === 'image');
  const selectedLogoAsset = imageAssets.find(a => a.asset_id === kit.logo_asset_id);
  const selectedPrimaryProduct = imageAssets.find(a => a.asset_id === kit.primary_product_asset_id);
  const productRolePattern = /(screenshot|screen[-_ ]?shot|screen|detail|mockup|capture|ekran|detay)/i;
  const logoRolePattern = /(logo|app[-_ ]?icon|appicon|icon|monogram|brand[-_ ]?mark|simge)/i;
  const brandRolesAppearSwapped = Boolean(
    selectedLogoAsset
    && selectedPrimaryProduct
    && selectedLogoAsset.asset_id !== selectedPrimaryProduct.asset_id
    && productRolePattern.test(selectedLogoAsset.name)
    && logoRolePattern.test(selectedPrimaryProduct.name)
  );

  const saveKit = async () => {
    setError(null);
    try {
      const updated = await api.updateBrandKit(kit);
      setKit(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('saveFailed'));
    }
  };

  const refreshBrandSuggestion = () => {
    if (!kit) return;
    const contextKey = getBrandProfileContextKey(kit, assets);
    requestedProfileKey.current = null;
    void requestBrandSuggestion(kit, contextKey);
  };

  const toggleProductAsset = (assetId: string) => {
    if (assetId === kit.primary_product_asset_id) return;
    const selected = kit.product_asset_ids.includes(assetId);
    setKit({ ...kit, product_asset_ids: selected ? kit.product_asset_ids.filter(id => id !== assetId) : [...kit.product_asset_ids, assetId].slice(0, 3) });
  };

  const setPrimaryProduct = (assetId?: string) => {
    setKit({
      ...kit,
      primary_product_asset_id: assetId,
      product_asset_ids: kit.product_asset_ids.filter(id => id !== assetId),
    });
  };

  const swapBrandRoles = () => {
    const currentLogo = kit.logo_asset_id;
    const currentProduct = kit.primary_product_asset_id;
    setKit({
      ...kit,
      logo_asset_id: currentProduct,
      primary_product_asset_id: currentLogo,
      product_asset_ids: kit.product_asset_ids.filter(id => id !== currentLogo && id !== currentProduct),
    });
    setError(null);
  };

  const updateColor = (index: number, color: string) => {
    const updated = [...kit.brand_colors];
    updated[index] = color.toUpperCase();
    setKit({ ...kit, brand_colors: updated });
  };

  const extractPalette = async (source: 'logo' | 'product') => {
    const assetId = source === 'logo' ? kit.logo_asset_id : kit.primary_product_asset_id;
    if (!assetId) return;
    setError(null);
    setExtractingPalette(source);
    try {
      const result = await api.extractBrandPalette(assetId);
      setKit(current => current ? { ...current, brand_colors: result.colors } : current);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('paletteExtractionFailed'));
    } finally {
      setExtractingPalette(null);
    }
  };

  const handleAddColor = () => {
    let hex = newColorHex.trim();
    if (!hex) return;
    if (!hex.startsWith('#')) hex = '#' + hex;
    if (!/^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/.test(hex)) {
      setError(t('hexError'));
      return;
    }
    setError(null);
    setKit({ ...kit, brand_colors: [...kit.brand_colors, hex.toUpperCase()] });
    setNewColorHex('');
  };

  const handleRemoveColor = (idx: number) => {
    const updated = [...kit.brand_colors];
    updated.splice(idx, 1);
    setKit({ ...kit, brand_colors: updated });
  };

  const primaryAccent = kit.brand_colors[0] || '#8B7CFF';
  const paletteRoles = [t('palettePrimary'), t('paletteBackground'), t('paletteAccent')];
  const displayedVoice = isDefaultBrandVoice(kit.brand_voice) ? t('defaultBrandVoice') : kit.brand_voice;

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto space-y-8 animate-in fade-in duration-300">
      {/* Title */}
      <div>
        <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-primaryText">{t('brandKitTitle')}</h2>
        <p className="text-xs md:text-sm text-primaryText/60 mt-1">{t('brandKitSubtitle')}</p>
      </div>

      {error && (
        <div className="p-4 bg-error/10 border border-error/20 rounded-xl text-error text-xs">
          {error}
        </div>
      )}

      <section className={`rounded-3xl border p-5 md:p-6 transition-all ${
        suggestionStatus === 'ready'
          ? 'border-success/30 bg-success/[0.07]'
          : suggestionStatus === 'analyzing'
            ? 'border-accent/35 bg-accent/[0.08]'
            : 'border-white/10 bg-surfaceRaised/70'
      }`} aria-live="polite">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex min-w-0 items-start gap-3.5">
            <div className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${suggestionStatus === 'ready' ? 'bg-success/15 text-success' : 'bg-accent/15 text-accent'}`}>
              <Sparkles size={19} className={suggestionStatus === 'analyzing' ? 'animate-pulse' : ''} />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-bold text-primaryText">{t('aiBrandStarter')}</h3>
              <p className="mt-1 text-xs leading-relaxed text-primaryText/60">
                {suggestionStatus === 'analyzing'
                  ? t('aiBrandAnalyzing')
                  : suggestionStatus === 'ready'
                    ? t('aiBrandReady')
                    : t('aiBrandStarterEmpty')}
              </p>
              {suggestionStatus === 'ready' && kit.smart_profile_rationale && (
                <p className="mt-2 max-w-3xl text-[11px] leading-relaxed text-primaryText/45">{kit.smart_profile_rationale}</p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={refreshBrandSuggestion}
            disabled={suggestionStatus === 'analyzing' || !Boolean(kit.brand_name.trim() || kit.logo_asset_id || kit.primary_product_asset_id)}
            className="shrink-0 rounded-xl border border-white/10 bg-white/[0.06] px-4 py-2.5 text-xs font-semibold text-primaryText transition-all hover:border-accent/40 hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-35"
          >
            {suggestionStatus === 'analyzing' ? t('aiBrandAnalyzingShort') : t('refreshBrandSuggestion')}
          </button>
        </div>
        {suggestionStatus === 'ready' && (
          <div className="mt-4 flex flex-wrap gap-2 border-t border-white/[0.07] pt-4">
            {[
              kit.font_family,
              t(`preset${kit.caption_preset.charAt(0).toUpperCase()}${kit.caption_preset.slice(1)}` as any),
              t(kit.cta_treatment === 'pill' ? 'treatmentPill' : kit.cta_treatment === 'card' ? 'treatmentCard' : 'treatmentMinimal'),
              t(kit.motion_preset === 'subtle' ? 'motionSubtle' : kit.motion_preset === 'dynamic' ? 'motionDynamic' : 'motionNone'),
            ].map((item, index) => <span key={`${item}-${index}`} className="rounded-full border border-white/10 bg-background/45 px-3 py-1 text-[10px] font-semibold text-primaryText/65">{item}</span>)}
            <span className="ml-0 text-[10px] leading-6 text-primaryText/40 md:ml-auto">{t('aiBrandEditable')}</span>
          </div>
        )}
      </section>

      <div className="grid lg:grid-cols-12 gap-8">
        {/* Left Form (7 cols) */}
        <div className="lg:col-span-7 bg-surfaceRaised border border-white/10 rounded-2xl p-6 md:p-8 space-y-6">
          <div className="grid sm:grid-cols-2 gap-4">
            <label className="block space-y-2">
              <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('brandName')}</span>
              <input 
                type="text" 
                value={kit.brand_name} 
                onChange={e => setKit({...kit, brand_name: e.target.value})} 
                className="w-full bg-background border border-white/10 rounded-xl p-3.5 text-sm outline-none focus:border-accent text-primaryText"
              />
            </label>

            <label className="block space-y-2">
              <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('font')}</span>
              <input 
                type="text" 
                value={kit.font_family} 
                onChange={e => setKit({...kit, font_family: e.target.value})} 
                className="w-full bg-background border border-white/10 rounded-xl p-3.5 text-sm outline-none focus:border-accent text-primaryText font-mono"
              />
            </label>
          </div>

          <label className="block space-y-2">
            <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('brandVoice')}</span>
            <textarea 
              rows={2} 
              value={displayedVoice} 
              onChange={e => setKit({...kit, brand_voice: e.target.value})} 
              className="w-full bg-background border border-white/10 rounded-xl p-3.5 text-sm outline-none focus:border-accent text-primaryText leading-relaxed"
            />
          </label>

          {/* Human-readable color roles. Raw values stay in an optional advanced disclosure. */}
          <div className="space-y-4 pt-2">
            <div>
              <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('colorPalette')}</span>
              <p className="mt-1 text-xs leading-relaxed text-primaryText/45">{t('colorPaletteHelp')}</p>
            </div>

            <div className="grid sm:grid-cols-3 gap-3">
              {[0, 1, 2].map(index => {
                const color = kit.brand_colors[index] || ['#F5F5F0', '#111111', '#7CFFB2'][index];
                return (
                  <label key={paletteRoles[index]} className="group rounded-2xl border border-white/10 bg-background/60 p-3 cursor-pointer hover:border-white/25 transition-all">
                    <span className="block text-[10px] font-bold uppercase tracking-wider text-primaryText/45 mb-2">{paletteRoles[index]}</span>
                    <span className="relative block h-16 overflow-hidden rounded-xl border border-white/10 shadow-inner" style={{ backgroundColor: color }}>
                      <input
                        type="color"
                        value={color}
                        onChange={event => updateColor(index, event.target.value)}
                        aria-label={paletteRoles[index]}
                        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                      />
                      <span className="absolute inset-x-2 bottom-2 rounded-full bg-black/45 px-2 py-1 text-center text-[9px] font-bold text-white opacity-0 backdrop-blur-sm transition-opacity group-hover:opacity-100">{t('chooseColor')}</span>
                    </span>
                  </label>
                );
              })}
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!kit.logo_asset_id || Boolean(extractingPalette)}
                onClick={() => extractPalette('logo')}
                className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold text-primaryText transition-all hover:bg-white/10 disabled:opacity-35"
              >
                {extractingPalette === 'logo' ? t('extractingColors') : t('colorsFromLogo')}
              </button>
              <button
                type="button"
                disabled={!kit.primary_product_asset_id || Boolean(extractingPalette)}
                onClick={() => extractPalette('product')}
                className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold text-primaryText transition-all hover:bg-white/10 disabled:opacity-35"
              >
                {extractingPalette === 'product' ? t('extractingColors') : t('colorsFromProduct')}
              </button>
            </div>

            <details className="rounded-xl border border-white/5 bg-background/35 p-3">
              <summary className="cursor-pointer text-[11px] font-semibold text-primaryText/45">{t('advancedColorValues')}</summary>
              <div className="mt-3 space-y-2">
                {kit.brand_colors.map((color, index) => (
                  <div key={`${color}-${index}`} className="flex items-center gap-2">
                    <input
                      value={color}
                      onChange={event => updateColor(index, event.target.value)}
                      className="min-w-0 flex-1 rounded-lg border border-white/10 bg-background px-3 py-2 text-xs font-mono text-primaryText"
                    />
                    {index > 2 && (
                      <button type="button" onClick={() => handleRemoveColor(index)} aria-label={t('removeColor')} className="rounded-lg p-2 text-primaryText/35 hover:text-error"><Trash2 size={14} /></button>
                    )}
                  </div>
                ))}
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="text"
                    placeholder="#8B7CFF"
                    value={newColorHex}
                    onChange={e => setNewColorHex(e.target.value)}
                    className="min-w-0 flex-1 rounded-lg border border-white/10 bg-background px-3 py-2 text-xs font-mono text-primaryText"
                  />
                  <button type="button" onClick={handleAddColor} className="rounded-lg bg-white/10 px-3 py-2 text-xs font-semibold text-primaryText"><Plus size={14} /></button>
                </div>
              </div>
            </details>
          </div>

          <div className="rounded-2xl border border-accent/20 bg-accent/[0.05] p-4">
            <div className="flex items-center gap-2 text-sm font-bold text-primaryText"><ShieldCheck size={17} className="text-accent" />{t('brandIdentityAssets')}</div>
            <p className="mt-1 text-xs leading-relaxed text-primaryText/45">{t('brandIdentityAssetsHelp')}</p>
          </div>

          {brandRolesAppearSwapped && (
            <div className="rounded-2xl border border-amber-400/35 bg-amber-400/[0.08] p-4" role="alert">
              <div className="flex items-start gap-3">
                <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-300" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-bold text-primaryText">{t('brandRolesSwappedTitle')}</p>
                  <p className="mt-1 text-xs leading-relaxed text-primaryText/60">{t('brandRolesSwappedHelp')}</p>
                  <p className="mt-2 text-[11px] text-primaryText/45">
                    {t('brandLogo')}: {selectedLogoAsset?.name} · {t('mainProduct')}: {selectedPrimaryProduct?.name}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={swapBrandRoles}
                  className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-xs font-semibold text-amber-100 hover:bg-amber-300/20"
                >
                  <ArrowLeftRight size={14} />
                  {t('swapBrandRoles')}
                </button>
              </div>
            </div>
          )}

          {/* Logo Asset Selector with Thumbnails */}
          <div className="space-y-3 pt-2">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('brandLogo')}</span>
                <p className="mt-1 text-[11px] text-primaryText/40">{t('brandLogoHelp')}</p>
              </div>
              {/* Native Select Parity for Testing & Accessibility */}
              <select 
                value={kit.logo_asset_id || ''} 
                onChange={e => setKit({...kit, logo_asset_id: e.target.value || undefined})} 
                aria-label={t('brandLogo')}
                className="bg-background border border-white/10 rounded-lg px-2 py-1 text-xs text-primaryText/80 outline-none"
              >
                <option value="">—</option>
                {imageAssets.map(asset => <option key={asset.asset_id} value={asset.asset_id}>{asset.name}</option>)}
              </select>
            </div>

            {imageAssets.length === 0 ? (
              <p className="text-xs text-primaryText/40 bg-background/50 p-3 rounded-xl border border-white/5">{t('assetsEmpty')}</p>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
                <button
                  type="button"
                  onClick={() => setKit({...kit, logo_asset_id: undefined})}
                  className={`p-2.5 rounded-xl border text-center transition-all flex flex-col items-center justify-center gap-1 ${
                    !kit.logo_asset_id ? 'border-accent bg-accent/15 text-accent shadow-sm' : 'border-white/10 bg-background/50 text-primaryText/50 hover:bg-white/5'
                  }`}
                >
                  <span className="text-xs font-bold">—</span>
                  <span className="text-[10px] truncate max-w-full">{t('noAsset')}</span>
                </button>
                {imageAssets.map(asset => {
                  const isSelected = kit.logo_asset_id === asset.asset_id;
                  return (
                    <button
                      key={asset.asset_id}
                      type="button"
                      onClick={() => setKit({...kit, logo_asset_id: asset.asset_id})}
                      className={`p-2 rounded-xl border text-left transition-all relative overflow-hidden group ${
                        isSelected ? 'border-accent bg-accent/15 shadow-sm ring-1 ring-accent' : 'border-white/10 bg-background/50 hover:bg-white/5'
                      }`}
                    >
                      <div className="w-full h-12 rounded-lg overflow-hidden bg-background mb-1.5 border border-white/5">
                        <AssetThumbnail asset={asset} className="w-full h-full object-cover" />
                      </div>
                      <span className="text-[10px] text-primaryText block truncate font-medium">{asset.name}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Main product is a single explicit role, separate from supporting visuals. */}
          <div className="space-y-3 rounded-2xl border border-white/10 bg-background/25 p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('mainProduct')}</span>
                <p className="mt-1 text-[11px] leading-relaxed text-primaryText/40">{t('mainProductHelp')}</p>
              </div>
              <select
                value={kit.primary_product_asset_id || ''}
                onChange={event => setPrimaryProduct(event.target.value || undefined)}
                aria-label={t('mainProduct')}
                className="max-w-[180px] rounded-lg border border-white/10 bg-background px-2 py-1 text-xs text-primaryText/80 outline-none"
              >
                <option value="">—</option>
                {imageAssets.map(asset => <option key={asset.asset_id} value={asset.asset_id}>{asset.name}</option>)}
              </select>
            </div>

            {imageAssets.length === 0 ? (
              <p className="rounded-xl border border-white/5 bg-background/50 p-3 text-xs text-primaryText/40">{t('assetsEmpty')}</p>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
                <button
                  type="button"
                  onClick={() => setPrimaryProduct(undefined)}
                  className={`flex flex-col items-center justify-center gap-1 rounded-xl border p-2.5 text-center transition-all ${!kit.primary_product_asset_id ? 'border-accent bg-accent/15 text-accent' : 'border-white/10 bg-background/50 text-primaryText/50'}`}
                >
                  <span className="text-xs font-bold">—</span>
                  <span className="text-[10px]">{t('noAsset')}</span>
                </button>
                {imageAssets.map(asset => {
                  const selected = kit.primary_product_asset_id === asset.asset_id;
                  return (
                    <button
                      key={asset.asset_id}
                      type="button"
                      onClick={() => setPrimaryProduct(asset.asset_id)}
                      className={`relative overflow-hidden rounded-xl border p-2 text-left transition-all ${selected ? 'border-success bg-success/10 ring-1 ring-success' : 'border-white/10 bg-background/50 hover:bg-white/5'}`}
                    >
                      {selected && <span className="absolute right-1.5 top-1.5 z-10 rounded-full bg-success px-2 py-0.5 text-[8px] font-bold uppercase text-background">{t('mainProductBadge')}</span>}
                      <div className="mb-1.5 h-12 w-full overflow-hidden rounded-lg border border-white/5 bg-background"><AssetThumbnail asset={asset} className="h-full w-full object-cover" /></div>
                      <span className="block truncate text-[10px] font-medium text-primaryText">{asset.name}</span>
                    </button>
                  );
                })}
              </div>
            )}
            {selectedPrimaryProduct && <p className="text-[11px] text-success">{t('mainProductSelected')}: {selectedPrimaryProduct.name}</p>}
          </div>

          {/* Scannable Segmented Presets */}
          <div className="space-y-6 pt-2">
            <div className="space-y-2.5">
              <div>
                <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('defaultVisualDirection')}</span>
                <p className="mt-1 text-[11px] leading-relaxed text-primaryText/40">{t('defaultVisualDirectionHelp')}</p>
              </div>
              <div className="grid sm:grid-cols-3 gap-2.5">
                {[
                  { id: 'brand_safe', title: t('treatmentBrandSafe'), desc: t('treatmentBrandSafeDesc') },
                  { id: 'campaign_mood', title: t('treatmentCampaignMood'), desc: t('treatmentCampaignMoodDesc') },
                  { id: 'high_contrast', title: t('treatmentHighContrast'), desc: t('treatmentHighContrastDesc') },
                ].map(option => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setKit({ ...kit, default_visual_treatment: option.id as BrandKit['default_visual_treatment'] })}
                    className={`rounded-xl border p-3 text-left transition-all ${
                      (kit.default_visual_treatment || 'brand_safe') === option.id
                        ? 'border-accent bg-accent/10 shadow-sm'
                        : 'border-white/10 bg-background/50 hover:bg-white/5'
                    }`}
                  >
                    <div className="mb-1 text-xs font-semibold text-primaryText">{option.title}</div>
                    <div className="text-[10px] leading-relaxed text-primaryText/50">{option.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Caption Preset */}
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('captionStyle')}</span>
                <select 
                  value={kit.caption_preset} 
                  onChange={e => setKit({...kit, caption_preset: e.target.value as any})} 
                  className="bg-background border border-white/10 rounded-lg px-2.5 py-1 text-xs text-primaryText/80 outline-none"
                >
                  <option value="clean">{t('presetClean')}</option>
                  <option value="bold">{t('presetBold')}</option>
                  <option value="editorial">{t('presetEditorial')}</option>
                </select>
              </div>
              <div className="grid sm:grid-cols-3 gap-2.5">
                {[
                  { id: 'clean', title: t('presetClean'), desc: t('presetCleanDesc') },
                  { id: 'bold', title: t('presetBold'), desc: t('presetBoldDesc') },
                  { id: 'editorial', title: t('presetEditorial'), desc: t('presetEditorialDesc') },
                ].map(p => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setKit({...kit, caption_preset: p.id as any})}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      kit.caption_preset === p.id 
                        ? 'border-accent bg-accent/10 shadow-sm' 
                        : 'border-white/10 bg-background/50 hover:bg-white/5'
                    }`}
                  >
                    <div className="font-semibold text-xs text-primaryText mb-1">{p.title}</div>
                    <div className="text-[10px] text-primaryText/50 leading-relaxed">{p.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* CTA Treatment */}
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('ctaStyle')}</span>
                <select 
                  value={kit.cta_treatment} 
                  onChange={e => setKit({...kit, cta_treatment: e.target.value as any})} 
                  className="bg-background border border-white/10 rounded-lg px-2.5 py-1 text-xs text-primaryText/80 outline-none"
                >
                  <option value="pill">{t('treatmentPill')}</option>
                  <option value="card">{t('treatmentCard')}</option>
                  <option value="minimal">{t('treatmentMinimal')}</option>
                </select>
              </div>
              <div className="grid sm:grid-cols-3 gap-2.5">
                {[
                  { id: 'pill', title: t('treatmentPill'), desc: t('treatmentPillDesc') },
                  { id: 'card', title: t('treatmentCard'), desc: t('treatmentCardDesc') },
                  { id: 'minimal', title: t('treatmentMinimal'), desc: t('treatmentMinimalDesc') },
                ].map(p => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setKit({...kit, cta_treatment: p.id as any})}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      kit.cta_treatment === p.id 
                        ? 'border-accent bg-accent/10 shadow-sm' 
                        : 'border-white/10 bg-background/50 hover:bg-white/5'
                    }`}
                  >
                    <div className="font-semibold text-xs text-primaryText mb-1">{p.title}</div>
                    <div className="text-[10px] text-primaryText/50 leading-relaxed">{p.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Motion Preset */}
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('motion')}</span>
                <select 
                  value={kit.motion_preset} 
                  onChange={e => setKit({...kit, motion_preset: e.target.value as any})} 
                  className="bg-background border border-white/10 rounded-lg px-2.5 py-1 text-xs text-primaryText/80 outline-none"
                >
                  <option value="subtle">{t('motionSubtle')}</option>
                  <option value="dynamic">{t('motionDynamic')}</option>
                  <option value="none">{t('motionNone')}</option>
                </select>
              </div>
              <div className="grid sm:grid-cols-3 gap-2.5">
                {[
                  { id: 'subtle', title: t('motionSubtle') },
                  { id: 'dynamic', title: t('motionDynamic') },
                  { id: 'none', title: t('motionNone') },
                ].map(p => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setKit({...kit, motion_preset: p.id as any})}
                    className={`p-3 rounded-xl border text-center transition-all ${
                      kit.motion_preset === p.id 
                        ? 'border-accent bg-accent/10 text-primaryText font-semibold' 
                        : 'border-white/10 bg-background/50 text-primaryText/60 hover:bg-white/5'
                    }`}
                  >
                    <span className="text-xs">{p.title}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Product Assets Selector with Real Thumbnails */}
          <div className="space-y-3 pt-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('supportingVisuals')}</span>
                <p className="mt-1 text-[11px] text-primaryText/40">{t('supportingVisualsHelp')}</p>
              </div>
              <span className="text-[10px] font-mono text-primaryText/35">{kit.product_asset_ids.length}/3</span>
            </div>
            {imageAssets.length === 0 ? (
              <p className="text-xs text-primaryText/40 bg-background/50 p-3 rounded-xl border border-white/5">{t('assetsEmpty')}</p>
            ) : (
              <div className="grid sm:grid-cols-2 gap-3">
                {imageAssets.filter(asset => asset.asset_id !== kit.primary_product_asset_id).map(asset => {
                  const isSelected = kit.product_asset_ids.includes(asset.asset_id);
                  return (
                    <button 
                      type="button" 
                      onClick={() => toggleProductAsset(asset.asset_id)} 
                      key={asset.asset_id} 
                      className={`p-2.5 rounded-xl border text-left flex items-center gap-3 transition-all ${
                        isSelected 
                          ? 'border-success bg-success/15 shadow-sm text-primaryText' 
                          : 'border-white/10 bg-background/50 hover:bg-white/5 text-primaryText/70'
                      }`}
                    >
                      <div className="w-12 h-12 rounded-lg overflow-hidden bg-background shrink-0 border border-white/10">
                        <AssetThumbnail asset={asset} className="w-full h-full object-cover" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <span className="text-xs font-semibold block truncate">{asset.name}</span>
                        <span className="text-[10px] text-primaryText/40 block mt-0.5 font-mono">{asset.kind}</span>
                      </div>
                      <div className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 border ${
                        isSelected ? 'bg-success border-success text-background' : 'border-white/20 bg-background/60'
                      }`}>
                        {isSelected && <Check size={12} strokeWidth={3} />}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <button 
            type="button"
            onClick={saveKit} 
            disabled={brandRolesAppearSwapped}
            className="w-full bg-accent hover:bg-accentHover text-background font-semibold py-3.5 rounded-xl text-xs flex items-center justify-center gap-2 transition-all shadow-lg shadow-accent/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {saved ? (
              <>
                <Check size={16} />
                <span>{t('brandSaved')}</span>
              </>
            ) : (
              <span>{t('saveBrandKit')}</span>
            )}
          </button>
        </div>

        {/* Right: Live Deterministic Brand Preview Panel (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <div>
            <span className="text-xs uppercase font-mono tracking-widest text-accent font-semibold">{t('livePreviewTitle')}</span>
            <p className="text-xs text-primaryText/50 mt-0.5">{t('livePreviewSubtitle')}</p>
          </div>

          {/* 9:16 Canvas Simulator */}
          <div className="w-full max-w-[320px] mx-auto aspect-[9/16] bg-surfaceRaised border border-white/15 rounded-3xl p-6 flex flex-col justify-between shadow-2xl relative overflow-hidden backdrop-blur-xl">
            {/* Top Brand Header in Preview */}
            <div className="flex items-center justify-between z-10">
              <div className="flex items-center gap-2.5">
                {selectedLogoAsset ? (
                  <div className="w-7 h-7 rounded-lg overflow-hidden border border-white/20 bg-background">
                    <AssetThumbnail asset={selectedLogoAsset} className="w-full h-full object-cover" />
                  </div>
                ) : (
                  <div 
                    className="w-7 h-7 rounded-lg flex items-center justify-center font-black text-xs text-background shadow-md"
                    style={{ backgroundColor: primaryAccent }}
                  >
                    {(kit.brand_name || 'R').charAt(0).toUpperCase()}
                  </div>
                )}
                <span className="font-bold text-xs text-white tracking-wide truncate max-w-[140px]" style={{ fontFamily: kit.font_family || 'inherit' }}>
                  {kit.brand_name || t('previewBrandDefault')}
                </span>
              </div>

              <span className="text-[9px] font-mono uppercase tracking-wider text-white/60 bg-white/10 px-2 py-0.5 rounded-full border border-white/10">
                {kit.motion_preset}
              </span>
            </div>

            {/* Middle Product / Headline Simulator */}
            <div className="my-auto text-center space-y-3 z-10">
              <div
                className="w-20 h-24 rounded-2xl mx-auto flex items-center justify-center border shadow-xl transition-all overflow-hidden"
                style={{ borderColor: `${primaryAccent}40`, backgroundColor: `${primaryAccent}15` }}
              >
                {selectedPrimaryProduct
                  ? <AssetThumbnail asset={selectedPrimaryProduct} className="w-full h-full object-contain" />
                  : <Sparkles size={24} style={{ color: primaryAccent }} />}
              </div>
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-white tracking-tight leading-snug" style={{ fontFamily: kit.font_family || 'inherit' }}>
                  {kit.sample_headline || t('previewHeadline')}
                </h4>
                <p className="text-[11px] text-white/60 leading-relaxed max-w-[220px] mx-auto">
                  {kit.sample_caption || t('previewCaption')}
                </p>
              </div>
            </div>

            {/* Bottom Caption & CTA Simulator */}
            <div className="space-y-3 z-10">
              {/* Caption Preview Pill */}
              <div className={`text-center p-2 rounded-xl text-[11px] backdrop-blur-md transition-all ${
                kit.caption_preset === 'bold' 
                  ? 'bg-black/90 text-white font-bold border border-white/20 shadow-lg' 
                  : kit.caption_preset === 'editorial'
                    ? 'bg-gradient-to-r from-white/10 via-white/20 to-white/10 text-white italic border border-white/10'
                    : 'bg-black/60 text-white/90 border border-white/10'
              }`}>
                {kit.sample_caption || t('previewCaption')}
              </div>

              {/* CTA Preview */}
              {kit.cta_treatment === 'pill' && (
                <div 
                  className="w-full py-2.5 rounded-full text-center text-xs font-bold text-background shadow-lg transition-transform"
                  style={{ backgroundColor: primaryAccent }}
                >
                  {kit.sample_cta || t('previewCtaPill')}
                </div>
              )}
              {kit.cta_treatment === 'card' && (
                <div className="w-full p-2.5 rounded-xl bg-surfaceRaised border border-white/15 text-center text-xs font-bold text-white shadow-lg">
                  <span style={{ color: primaryAccent }}>{kit.sample_cta || t('previewCtaCardOffer')}</span>{!kit.sample_cta && <> · {t('previewCtaCardAccess')}</>}
                </div>
              )}
              {kit.cta_treatment === 'minimal' && (
                <div className="w-full py-1 text-center text-xs font-bold underline tracking-wider text-white">
                  {kit.sample_cta || t('previewCtaMinimal')}
                </div>
              )}
            </div>

            {/* Subtle Gradient Backdrops */}
            <div 
              className="absolute inset-0 opacity-15 pointer-events-none"
              style={{
                background: `radial-gradient(circle at 50% 30%, ${primaryAccent}, transparent 60%)`
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// SETTINGS PAGE
// ============================================================================
const Settings = () => {
  const [lang, setLocalLang] = useState<Lang>(getLang());
  const [saved, setSaved] = useState(false);
  const currentWs = api.getWorkspaceId();

  const handleSave = () => {
    setLang(lang);
    setSaved(true);
    setTimeout(() => {
      setSaved(false);
      window.location.reload();
    }, 500);
  };

  return (
    <div className="p-6 md:p-10 max-w-3xl mx-auto space-y-8 animate-in fade-in duration-300">
      <div>
        <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-primaryText">{t('settings')}</h2>
        <p className="text-xs md:text-sm text-primaryText/60 mt-1">{t('settingsSubtitle')}</p>
      </div>

      <div className="space-y-6">
        {/* Language Selection Card */}
        <div className="bg-surfaceRaised border border-white/10 rounded-2xl p-6 space-y-5">
          <label className="block space-y-2">
            <span className="text-xs uppercase font-mono tracking-widest text-primaryText/50">{t('uiLanguage')}</span>
            <select 
              value={lang} 
              onChange={e => setLocalLang(e.target.value as Lang)} 
              className="w-full bg-background border border-white/10 rounded-xl p-3 text-sm outline-none focus:border-accent text-primaryText"
            >
              <option value="en">{t('langEnglish')}</option>
              <option value="tr">{t('langTurkish')}</option>
            </select>
          </label>

          {/* UI Language vs Campaign Output Language Explanation */}
          <div className="p-3.5 rounded-xl bg-accent/10 border border-accent/20 text-accent text-xs leading-relaxed">
            {t('languageExplanation')}
          </div>

          <button 
            type="button"
            onClick={handleSave} 
            className="w-full bg-accent hover:bg-accentHover text-background font-semibold py-3 rounded-xl text-xs transition-all shadow-md"
          >
            {saved ? t('languageUpdated') : t('save')}
          </button>
        </div>

        {/* Shared Demo User workspace card */}
        <div className="bg-surfaceRaised border border-white/10 rounded-2xl p-6 space-y-4">
          <div className="flex items-center gap-2">
            <ShieldCheck size={18} className="text-success" />
            <h3 className="font-semibold text-sm text-primaryText">{t('workspaceIsolationTitle')}</h3>
          </div>
          <p className="text-xs text-primaryText/60 leading-relaxed">
            {t('workspaceIsolationDesc')}
          </p>
          <div className="bg-background/80 p-3 rounded-xl border border-white/5 flex items-center justify-between text-xs font-mono">
            <span className="text-primaryText/50">{t('workspaceIdLabel')}:</span>
            <span className="text-accent font-semibold">{currentWs}</span>
          </div>
          <p className="text-[10px] font-mono text-primaryText/30">
            {t('sessionPersistence')}
          </p>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// MAIN APP ROUTER
// ============================================================================
export default function App() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background text-primaryText flex">
        <Sidebar mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} />
        
        <div className="flex-1 md:pl-64 flex flex-col min-w-0">
          <TopHeader onOpenMobileNav={() => setMobileOpen(true)} />
          <main className="flex-1 pb-16">
            <Routes>
              <Route path="/" element={<CampaignsList />} />
              <Route path="/campaigns" element={<CampaignsList />} />
              <Route path="/campaigns/new" element={<CampaignFlow />} />
              <Route path="/campaigns/:id" element={<CampaignFlow />} />
              <Route path="/assets" element={<AssetsPage />} />
              <Route path="/brand-kit" element={<BrandKitPage />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  );
}
