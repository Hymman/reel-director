import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AssetSummary, BrandKit, Campaign, Job, OutputFormat, ProductionSettings } from './types';
import * as api from './services/api';
import { t } from './i18n';
import { Camera, ChevronRight, PlayCircle, Loader2, ShieldCheck, Film, Download, ArrowRight, Sparkles, Upload, Link2, FileText, Image as ImageIcon, Volume2, VolumeX, WandSparkles, Save, CheckCircle2 } from 'lucide-react';

const TextWithEvidenceChips = ({ text }: { text: string }) => {
  const parts = text.split(/(\[E\d+\])/g);
  return (
    <span>
      {parts.map((part, i) => {
        if (part.match(/^\[E\d+\]$/)) {
          const eid = part.slice(1, -1);
          return (
            <button 
              key={i} 
              onClick={(e) => {
                e.preventDefault();
                document.getElementById(`evidence-${eid}`)?.scrollIntoView({behavior: 'smooth', block: 'center'});
              }}
              className="inline-flex items-center justify-center mx-1 px-1.5 py-0.5 bg-white/10 text-primaryText hover:bg-white/20 border border-white/5 font-mono text-[10px] rounded transition-all"
            >
              {eid}
            </button>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
};

const Stepper = ({ currentStage, isProducing }: { currentStage: Campaign['stage'], isProducing: boolean }) => {
  const visualStages = [
    t('stepBrief'),
    t('stepResearch'),
    t('stepDirections'),
    t('stepDirector'),
    t('stepProduction'),
    t('stepFinal')
  ];
  
  let currentIndex = 0;
  if (['intake', 'brief_review'].includes(currentStage)) currentIndex = 0;
  else if (['research_plan', 'research', 'verification'].includes(currentStage)) currentIndex = 1;
  else if (currentStage === 'directions') currentIndex = 2;
  else if (currentStage === 'studio') {
    currentIndex = isProducing ? 4 : 3;
  }
  else if (currentStage === 'reel') currentIndex = 5;

  return (
    <div className="overflow-x-auto border-b border-hairline bg-background/70 relative z-30">
      <div className="min-w-max flex items-center justify-start md:justify-center px-6 py-6 md:py-8">
      {visualStages.map((stage, i) => (
        <div key={stage} className="flex items-center">
          <div className={`flex flex-col items-center transition-all ${
            i < currentIndex ? 'text-primaryText/50' :
            i === currentIndex ? 'text-primaryText drop-shadow-md' :
            'text-primaryText/20'
          }`}>
            <span className="text-[10px] font-bold tracking-[0.2em] uppercase">{stage}</span>
          </div>
          {i < visualStages.length - 1 && (
            <div className="w-8 mx-4 flex items-center">
                <div className={`h-[1px] w-full ${i < currentIndex ? 'bg-primaryText/30' : 'bg-primaryText/10'}`} />
            </div>
          )}
        </div>
      ))}
      </div>
    </div>
  );
};

export default function CampaignFlow() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNewCampaignRoute = !id || id === 'new';

  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [loadingCampaign, setLoadingCampaign] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [serverStatus, setServerStatus] = useState<'connecting' | 'live' | 'mock' | 'offline'>('connecting');
  const [mediaUrls, setMediaUrls] = useState<{ video?: string; slideshow?: string; image?: string; cover?: string; carousel: string[] }>({ carousel: [] });
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const [previewStatus, setPreviewStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const previewRequestCampaign = useRef<string | null>(null);
  const [availableAssets, setAvailableAssets] = useState<AssetSummary[]>([]);
  const [brandKit, setBrandKit] = useState<BrandKit | null>(null);
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([]);
  const [sourceUrls, setSourceUrls] = useState('');
  const [contextError, setContextError] = useState<string | null>(null);
  const [uploadingContext, setUploadingContext] = useState(false);
  const [formatUpdating, setFormatUpdating] = useState(false);
  const [productionDraft, setProductionDraft] = useState<ProductionSettings | null>(null);
  const [productionSettingsSaved, setProductionSettingsSaved] = useState(true);
  const [productionSettingsError, setProductionSettingsError] = useState<string | null>(null);

  useEffect(() => {
    const ws = api.getWorkspaceId();
    if (isNewCampaignRoute) {
      setCampaign(null);
      setActiveJob(null);
      setLoadError(null);
      setLoadingCampaign(false);
      setClarificationAnswer('');
      setContextError(null);
      localStorage.removeItem(`active_campaign_id:${ws}`);
    } else if (id) {
      if (!campaign || campaign.id !== id) {
        setLoadingCampaign(true);
        setLoadError(null);
        api.getCampaign(id).then(c => {
          setCampaign(c);
          setLoadingCampaign(false);
          localStorage.setItem(`active_campaign_id:${ws}`, c.id);
          navigate(`/campaigns/${c.id}`);
          if (c.stage === 'failed') {
            console.error("Campaign failed or was invalid.");
          }
        }).catch(err => {
          setCampaign(null);
          setLoadingCampaign(false);
          setLoadError(err.message || 'Campaign not found');
        });
      }
    } else {
      setCampaign(null);
      setLoadError(null);
      setLoadingCampaign(false);
    }
  }, [id]);

  useEffect(() => {
    if (!isNewCampaignRoute && campaign?.stage !== 'studio') return;
    Promise.all([api.listAssets(), api.getBrandKit()])
      .then(([assets, kit]) => { setAvailableAssets(assets); setBrandKit(kit); })
      .catch(() => { setAvailableAssets([]); setBrandKit(null); });
  }, [id, isNewCampaignRoute, campaign?.stage]);

  useEffect(() => {
    if (!campaign || campaign.stage !== 'studio') return;
    const selectedShot = campaign.shot_plan?.shots.find(shot => shot.shot_id === campaign.selected_shot_id);
    const selectedDirection = campaign.direction_set?.directions.find(direction => direction.direction_id === campaign.selected_direction_id);
    setProductionDraft(campaign.production_settings ? {
      ...campaign.production_settings,
      visual_treatment: campaign.production_settings.visual_treatment || 'brand_safe',
    } : {
      headline: (selectedDirection?.hook || campaign.brief?.subject_name || '').slice(0, 90),
      caption: (selectedShot?.caption || '').slice(0, 110),
      cta: (campaign.brief?.cta || (campaign.brief?.output_language === 'tr' ? 'Daha fazla bilgi' : 'Learn more')).slice(0, 48),
      audio_mode: 'native_ambient',
      product_asset_ids: [],
      visual_treatment: brandKit?.default_visual_treatment || 'brand_safe',
    });
    setProductionSettingsSaved(true);
    setProductionSettingsError(null);
  }, [campaign?.id, campaign?.stage, campaign?.selected_shot_id, campaign?.production_settings, brandKit?.default_visual_treatment]);

  useEffect(() => {
    let active = true;
    const objectUrls: string[] = [];
    const sources = {
      video: campaign?.final_video_url,
      slideshow: campaign?.final_slideshow_url,
      image: campaign?.final_image_url,
      cover: campaign?.final_thumbnail_url,
    } as const;

    Promise.all([
      Promise.all(Object.entries(sources)
        .filter((entry): entry is [keyof typeof sources, string] => Boolean(entry[1]))
        .map(async ([kind, source]) => {
          const prepared = await api.prepareMediaUrl(source);
          if (prepared.startsWith('blob:')) objectUrls.push(prepared);
          return [kind, prepared] as const;
        })),
      Promise.all((campaign?.final_carousel_urls || []).map(async source => {
        const prepared = await api.prepareMediaUrl(source);
        if (prepared.startsWith('blob:')) objectUrls.push(prepared);
        return prepared;
      })),
    ])
      .then(([entries, carousel]) => active && setMediaUrls({ ...Object.fromEntries(entries), carousel }))
      .catch(error => {
        console.error('Media load failed', error);
        if (active) setMediaUrls({ carousel: [] });
      });

    return () => {
      active = false;
      objectUrls.forEach(url => URL.revokeObjectURL(url));
    };
  }, [
    campaign?.final_video_url,
    campaign?.final_slideshow_url,
    campaign?.final_image_url,
    campaign?.final_thumbnail_url,
    campaign?.final_carousel_urls?.join('|'),
  ]);

  useEffect(() => {
    if (!campaign || campaign.stage !== 'studio' || !campaign.shot_plan?.shots.length) return;
    let active = true;
    const objectUrls: string[] = [];

    const loadPreviews = async (current: Campaign) => {
      const entries = await Promise.all(
        (current.shot_plan?.shots || [])
          .filter(shot => Boolean(shot.preview_image_url))
          .map(async shot => {
            const prepared = await api.prepareMediaUrl(shot.preview_image_url!);
            if (prepared.startsWith('blob:')) objectUrls.push(prepared);
            return [shot.shot_id, prepared] as const;
          }),
      );
      if (active) {
        setPreviewUrls(Object.fromEntries(entries));
        setPreviewStatus(entries.length === (current.shot_plan?.shots.length || 0) ? 'ready' : 'error');
      }
    };

    const run = async () => {
      try {
        setPreviewStatus('loading');
        let current = campaign;
        const missing = current.shot_plan?.shots.some(shot => !shot.preview_image_url);
        if (missing && previewRequestCampaign.current !== current.id) {
          previewRequestCampaign.current = current.id;
          const { job_id } = await api.generatePreviews(current.id);
          const job = await api.waitForJob(job_id, 80);
          if (job.stage === 'failed') throw new Error(job.message);
          current = await api.getCampaign(current.id);
          if (active) setCampaign(current);
        }
        await loadPreviews(current);
      } catch (error) {
        console.error('Candidate preview load failed', error);
        if (active) setPreviewStatus('error');
      }
    };

    run();
    return () => {
      active = false;
      objectUrls.forEach(url => URL.revokeObjectURL(url));
    };
  }, [
    campaign?.id,
    campaign?.stage,
    campaign?.shot_plan?.shots.map(shot => shot.preview_image_url || '').join('|'),
  ]);

  useEffect(() => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    api.getHealth({ signal: controller.signal })
      .then(data => {
        setServerStatus(data.demo_mode ? 'mock' : 'live');
        clearTimeout(timeoutId);
      })
      .catch(() => setServerStatus('offline'));
      
    return () => clearTimeout(timeoutId);
  }, []);

  const [briefInput, setBriefInput] = useState("");
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  
  const executeAction = async (actionFn: (id: string) => Promise<{job_id: string}>) => {
    if (!campaign) return;
    try {
      const { job_id } = await actionFn(campaign.id);
      setActiveJob({ job_id, campaign_id: campaign.id, stage: 'running', progress: 20, message: t('analyzingRequest') } as Job);
      const job = await api.waitForJob(job_id);
      setActiveJob(job);
      if (job.stage === 'complete') {
        const c = await api.getCampaign(campaign.id);
        setCampaign(c);
        navigate(`/campaigns/${c.id}`);
      }
    } catch (err) {
      console.error(err);
      setActiveJob(current => ({
        ...(current || ({ job_id: 'unknown', campaign_id: campaign.id, progress: 0 } as Job)),
        stage: 'failed',
        message: err instanceof Error ? err.message : t('failed'),
      } as Job));
    }
  };

  const handleExtractBrief = async () => {
    if (!briefInput) return;
    setContextError(null);
    try {
      const urls = sourceUrls.split(/[\n,]+/).map(value => value.trim()).filter(Boolean).slice(0, 3);
      const { job_id, campaign_id } = await api.extractBrief(briefInput, urls, selectedAssetIds);
      setCampaign({ id: campaign_id, stage: 'intake' } as Campaign);
      setActiveJob({ job_id, campaign_id, stage: 'extracting', progress: 15, message: t('analyzingRequest') } as Job);
      const job = await api.waitForJob(job_id);
      setActiveJob(job);
      const c = await api.getCampaign(campaign_id);
      setCampaign(c);
      navigate(`/campaigns/${c.id}`);
    } catch (error) {
      setContextError(error instanceof Error ? error.message : t('intakeFailed'));
    }
  };

  const handleContextUpload = async (file?: File) => {
    if (!file) return;
    setUploadingContext(true);
    setContextError(null);
    try {
      const asset = await api.uploadAsset(file);
      setAvailableAssets(current => [asset, ...current]);
      setSelectedAssetIds(current => [...current, asset.asset_id]);
    } catch (error) {
      setContextError(error instanceof Error ? error.message : t('uploadFailed'));
    } finally {
      setUploadingContext(false);
    }
  };

  const handleAnswerClarification = async () => {
    if (!campaign || !clarificationAnswer) return;
    await executeAction(id => api.answerClarification(id, clarificationAnswer));
  };

  const handleSkipClarification = async () => {
    if (!campaign) return;
    await executeAction(id => api.skipClarification(id));
  };

  const handleConfirmBrief = async () => {
    if (!campaign || !campaign.brief) return;
    await executeAction(id => api.confirmBrief(id, campaign.brief!));
  };

  const isWorking = activeJob ? (activeJob.stage !== 'complete' && activeJob.stage !== 'failed') : false;

  const updateOutputFormat = async (outputFormat: OutputFormat) => {
    if (!campaign || isWorking || formatUpdating) return;
    setFormatUpdating(true);
    try {
      setCampaign(await api.selectOutputFormat(campaign.id, outputFormat));
    } finally {
      setFormatUpdating(false);
    }
  };

  const retryCandidatePreviews = async () => {
    if (!campaign || previewStatus === 'loading') return;
    previewRequestCampaign.current = null;
    setPreviewStatus('loading');
    try {
      const { job_id } = await api.generatePreviews(campaign.id);
      const job = await api.waitForJob(job_id, 80);
      if (job.stage === 'failed') throw new Error(job.message);
      setCampaign(await api.getCampaign(campaign.id));
    } catch (error) {
      console.error('Candidate preview retry failed', error);
      setPreviewStatus('error');
    }
  };

  const changeProductionDraft = (updates: Partial<ProductionSettings>) => {
    if (!productionDraft) return;
    setProductionDraft({ ...productionDraft, ...updates });
    setProductionSettingsSaved(false);
    setProductionSettingsError(null);
  };

  const toggleProductionAsset = (assetId: string) => {
    if (!productionDraft) return;
    const selected = productionDraft.product_asset_ids.includes(assetId);
    const next = selected
      ? productionDraft.product_asset_ids.filter(id => id !== assetId)
      : [...productionDraft.product_asset_ids, assetId].slice(0, 3);
    changeProductionDraft({ product_asset_ids: next });
  };

  const saveProductionSettings = async () => {
    if (!campaign || !productionDraft) return;
    setProductionSettingsError(null);
    try {
      const updated = await api.updateProductionSettings(campaign.id, productionDraft);
      setCampaign(updated);
      setProductionDraft(updated.production_settings || productionDraft);
      setProductionSettingsSaved(true);
    } catch (error) {
      setProductionSettingsError(error instanceof Error ? error.message : t('saveFailed'));
    }
  };

  const renderActiveJob = () => {
    if (!activeJob) return null;
    if (activeJob.stage === 'failed') {
      return (
        <div className="fixed bottom-8 right-8 bg-surface border border-error p-5 rounded-2xl shadow-2xl w-80 z-50 animate-in slide-in-from-bottom-10 fade-in duration-300">
          <div className="flex items-center space-x-3 mb-4 text-error">
            <ShieldCheck className="w-4 h-4" />
            <span className="font-mono text-xs uppercase tracking-wider">{activeJob.message}</span>
          </div>
          <button onClick={() => setActiveJob(null)} className="text-error/80 text-[10px] font-bold uppercase tracking-widest hover:text-error transition-colors">{t('dismiss')}</button>
        </div>
      );
    }
    if (!isWorking) return null;
    return (
      <div className="fixed bottom-8 right-8 bg-surface border border-hairline p-5 rounded-2xl shadow-2xl w-80 z-50 animate-in slide-in-from-bottom-10 fade-in duration-300">
        <div className="flex items-center space-x-3 mb-4">
          <Loader2 className="w-4 h-4 text-primaryText animate-spin" />
          <span className="font-mono text-xs uppercase tracking-wider text-primaryText/80">{activeJob.message}</span>
        </div>
        <div className="w-full h-1 bg-background rounded-full overflow-hidden">
          <div className="h-full bg-primaryText transition-all duration-500 ease-out" style={{ width: `${activeJob.progress}%` }} />
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen flex flex-col font-sans selection:bg-white/20">
      {campaign && <Stepper currentStage={campaign.stage} isProducing={isWorking} />}
      
      <main className="flex-1 p-5 md:p-8 max-w-7xl mx-auto w-full mb-20">
        {loadingCampaign && (
          <div className="flex flex-col items-center justify-center h-[50vh] space-y-6 opacity-60">
            <Loader2 className="w-10 h-10 animate-spin text-primaryText" />
            <div className="font-mono text-xs tracking-widest uppercase">{t('loadingCampaign')}</div>
          </div>
        )}

        {loadError && (
          <div className="flex flex-col items-center justify-center h-[60vh] space-y-6 text-center animate-in fade-in">
            <div className="w-16 h-16 bg-surface border border-error/30 rounded-2xl flex items-center justify-center text-error">
              <ShieldCheck className="w-8 h-8" />
            </div>
            <div className="space-y-2">
              <h2 className="text-2xl font-bold text-primaryText">{t('campaignNotFound')}</h2>
              <p className="text-sm text-primaryText/60 max-w-md">{t('campaignNotFoundDesc')}</p>
            </div>
            <button 
              onClick={() => navigate('/campaigns')}
              className="px-6 py-2.5 bg-primaryText text-background font-bold text-sm rounded-xl hover:opacity-90 transition-all"
            >
              {t('backToCampaigns')}
            </button>
          </div>
        )}

        {!loadingCampaign && !loadError && !campaign && (
          <div className="flex flex-col items-center justify-center min-h-[65vh] space-y-8 animate-in fade-in duration-700 mt-6 md:mt-8">
            <div className="text-center space-y-4 w-full max-w-2xl mx-auto">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 bg-surface text-[11px] font-mono uppercase tracking-widest text-accent">
                <Sparkles size={13} />
                <span>{t('intakeTitle')}</span>
              </div>
              <h1 className="text-3xl md:text-5xl font-bold tracking-tight text-primaryText leading-tight">
                {t('intakeHeroTitle')}
              </h1>
              <p className="text-sm md:text-base text-primaryText/60 font-light leading-relaxed">
                {t('intakeSubtitle')}
              </p>
            </div>
            
            <div className="w-full max-w-3xl space-y-6">
              {/* Section 1: Creative Brief */}
              <div className="bg-surface border border-white/5 rounded-3xl p-6 md:p-8 space-y-4 shadow-xl">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm md:text-base font-bold text-primaryText flex items-center gap-2">
                    <span className="w-6 h-6 rounded-lg bg-white/10 text-xs flex items-center justify-center font-mono">1</span>
                    {t('stepBriefHeader')}
                  </h3>
                  <span className="text-[10px] font-mono uppercase tracking-wider text-primaryText/40">{t('intakeHeroSubtitle')}</span>
                </div>
                <div className="relative group">
                  <textarea 
                    value={briefInput}
                    onChange={(e) => setBriefInput(e.target.value)}
                    placeholder={t('enterBrief')}
                    className="w-full p-5 md:p-6 h-44 bg-background border border-white/10 rounded-2xl resize-none text-primaryText focus:border-accent outline-none transition-all font-light text-sm md:text-base leading-relaxed placeholder:text-primaryText/30"
                  />
                  <div className="mt-3 flex justify-end">
                    <button 
                      onClick={handleExtractBrief}
                      disabled={!briefInput.trim() || isWorking}
                      className="w-full sm:w-auto px-7 py-3 bg-primaryText text-background font-bold tracking-wide rounded-xl hover:bg-white hover:scale-[1.01] transition-all flex items-center justify-center disabled:opacity-40 shadow-xl cursor-pointer"
                    >
                      {t('sendToDirector')} <ArrowRight className="w-4 h-4 ml-2" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Section 2: Optional Context Sources */}
              <div className="bg-surface border border-white/5 rounded-3xl p-6 md:p-8 space-y-5 shadow-xl">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div className="space-y-1">
                    <h3 className="text-sm md:text-base font-bold text-primaryText flex items-center gap-2">
                      <span className="w-6 h-6 rounded-lg bg-white/10 text-xs flex items-center justify-center font-mono">2</span>
                      {t('stepContextHeader')}
                    </h3>
                    <p className="text-xs text-primaryText/50">{t('stepContextHint')}</p>
                  </div>
                  <label className={`text-xs font-bold px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/15 cursor-pointer flex items-center justify-center gap-2 transition-all shrink-0 ${uploadingContext ? 'opacity-50 pointer-events-none' : ''}`}>
                    <Upload size={14} /> {t('attachFiles')}
                    <input type="file" className="hidden" accept=".png,.jpg,.jpeg,.webp,.mp4,.mov,.pdf,.docx,.txt,.md" onChange={event => handleContextUpload(event.target.files?.[0])} />
                  </label>
                </div>

                <input 
                  value={sourceUrls} 
                  onChange={event => setSourceUrls(event.target.value)} 
                  placeholder={t('sourceUrl')} 
                  className="w-full bg-background border border-white/10 rounded-xl px-4 py-3 text-xs md:text-sm outline-none focus:border-accent transition-colors" 
                />

                <div className="flex items-center gap-2 text-[10px] font-mono text-primaryText/40 border-t border-white/5 pt-3">
                  <span className="text-accent">•</span>
                  <span>{t('supportedChipsText')}</span>
                </div>

                {availableAssets.length > 0 && (
                  <div className="pt-1">
                    <span className="text-[10px] uppercase font-mono tracking-widest text-primaryText/40 block mb-2">{t('selectAssets')}</span>
                    <div className="flex flex-wrap gap-2">
                      {availableAssets.map(asset => {
                        const selected = selectedAssetIds.includes(asset.asset_id);
                        return (
                          <button 
                            type="button" 
                            key={asset.asset_id} 
                            onClick={() => setSelectedAssetIds(current => selected ? current.filter(id => id !== asset.asset_id) : [...current, asset.asset_id])} 
                            className={`px-3 py-1.5 rounded-lg border text-xs flex items-center gap-1.5 transition-all ${selected ? 'border-success bg-success/15 text-primaryText font-medium' : 'border-white/10 bg-background text-primaryText/60 hover:bg-white/5'}`}
                          >
                            <FileText size={12} /> {asset.name}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {contextError && <div className="p-3.5 rounded-xl border border-error/30 bg-error/10 text-error text-xs">{contextError}</div>}

              {/* Workspace Privacy Note */}
              <div className="flex items-center gap-2.5 px-4 py-3 rounded-2xl bg-surface/60 border border-white/5 text-[11px] text-primaryText/50 leading-relaxed">
                <ShieldCheck size={16} className="text-accent shrink-0" />
                <span>{t('workspacePrivacyNote')}</span>
              </div>
            </div>
          </div>
        )}

        {!loadingCampaign && !loadError && campaign && campaign.stage === 'intake' && (
          <div className="flex flex-col items-center justify-center h-[50vh] space-y-6 opacity-60">
            <Loader2 className="w-10 h-10 animate-spin text-primaryText" />
            <div className="font-mono text-xs tracking-widest uppercase">{t('analyzingRequest')}</div>
          </div>
        )}

        {!loadingCampaign && !loadError && campaign && campaign.stage === 'intake_clarification' && campaign.intake_state && (
          <div className="max-w-3xl mx-auto mt-10 animate-in fade-in slide-in-from-bottom-8 duration-700">
            <div className="space-y-6">
              <div className="flex justify-end">
                <div className="bg-surface border border-white/5 p-6 rounded-2xl rounded-tr-none max-w-[85%] shadow-lg">
                  <p className="text-primaryText/80 font-light text-lg whitespace-pre-wrap">{campaign.intake_state.original_brief}</p>
                </div>
              </div>
              
              <div className="flex justify-start">
                <div className="bg-surfaceRaised border border-white/10 p-6 rounded-2xl rounded-tl-none max-w-[85%] shadow-xl">
                  <div className="flex items-center space-x-2 mb-3">
                    <Camera className="w-4 h-4 text-primaryText/60" />
                    <span className="text-[10px] uppercase tracking-widest font-bold text-primaryText/60">Reel Director</span>
                  </div>
                  <p className="text-primaryText font-medium text-xl leading-relaxed">{campaign.intake_state.clarification_question}</p>
                </div>
              </div>

              <div className="flex justify-end mt-8 relative">
                 <textarea 
                  value={clarificationAnswer}
                  onChange={(e) => setClarificationAnswer(e.target.value)}
                  placeholder={t('answerPlaceholder')}
                  className="w-[85%] p-6 h-32 bg-surface border border-white/5 rounded-2xl resize-none text-primaryText focus:border-white/20 focus:ring-1 focus:ring-white/20 outline-none transition-all shadow-2xl font-light text-lg leading-relaxed placeholder:text-primaryText/30"
                />
                <div className="absolute bottom-4 right-4 flex space-x-3">
                  <button 
                    onClick={handleSkipClarification}
                    disabled={isWorking}
                    className="px-6 py-2 bg-transparent text-primaryText/60 font-bold text-sm tracking-wide rounded-xl hover:text-primaryText transition-all disabled:opacity-50"
                  >
                    {t('skipDraftBrief')}
                  </button>
                  <button 
                    onClick={handleAnswerClarification}
                    disabled={!clarificationAnswer.trim() || isWorking}
                    className="px-6 py-2 bg-primaryText text-background font-bold text-sm tracking-wide rounded-xl hover:bg-white hover:scale-[1.02] transition-all flex items-center disabled:opacity-50 disabled:hover:scale-100 shadow-xl"
                  >
                    {t('sendAnswer')}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {!loadingCampaign && !loadError && campaign && campaign.stage === 'brief_review' && campaign.brief && (
          <div className="max-w-3xl mx-auto bg-surface p-10 rounded-2xl border border-white/5 shadow-2xl animate-in fade-in slide-in-from-bottom-8 duration-700">
            <h2 className="text-3xl font-bold tracking-tight mb-3">{t('campaignBlueprint')}</h2>
            <p className="text-primaryText/60 font-light mb-10 text-lg">{t('blueprintSubtitle')}</p>
            
            <div className="space-y-6">
              {[
                { label: t('productSubject'), key: 'subject_name' as const },
                { label: t('description'), key: 'subject_description' as const },
                { label: t('targetAud'), key: 'audience' as const },
                { label: t('goal'), key: 'goal' as const }
              ].map((field) => (
                <div key={field.key} className="group">
                  <label className="block text-primaryText/50 text-[10px] font-bold uppercase tracking-widest mb-2 group-focus-within:text-primaryText/80 transition-colors">{field.label}</label>
                  <input 
                    type="text" 
                    className="w-full bg-background/50 border border-white/5 p-4 rounded-xl text-primaryText focus:border-white/20 focus:outline-none transition-all font-light" 
                    value={campaign.brief![field.key]} 
                    onChange={(e) => setCampaign({...campaign, brief: {...campaign.brief!, [field.key]: e.target.value}})} 
                  />
                </div>
              ))}
              <div className="group mt-6">
                <label className="block text-primaryText/50 text-[10px] font-bold uppercase tracking-widest mb-2 group-focus-within:text-primaryText/80 transition-colors">{t('outputLanguage')}</label>
                <select 
                  className="w-full bg-background/50 border border-white/5 p-4 rounded-xl text-primaryText focus:border-white/20 focus:outline-none transition-all font-light"
                  value={campaign.brief?.output_language || 'en'}
                  onChange={(e) => setCampaign({...campaign, brief: {...campaign.brief!, output_language: e.target.value as 'en' | 'tr'}})}
                >
                  <option value="en">{t('langEnglish')}</option>
                  <option value="tr">{t('langTurkish')}</option>
                </select>
              </div>
            </div>
            
            <div className="mt-12 flex justify-end">
              <button 
                onClick={handleConfirmBrief}
                disabled={isWorking}
                className="px-8 py-3 bg-primaryText text-background font-bold tracking-wide rounded-xl hover:bg-white hover:scale-[1.02] transition-all disabled:opacity-50 disabled:hover:scale-100"
              >
                {t('confirmBrief')}
              </button>
            </div>
          </div>
        )}

        {!loadingCampaign && !loadError && campaign && campaign.stage === 'research_plan' && (
          <div className="max-w-4xl mx-auto bg-surface p-8 rounded-2xl border border-white/5 mb-8 shadow-lg animate-in fade-in">
            <h2 className="text-xs font-bold uppercase tracking-widest text-primaryText/50 mb-6">{t('researchDirective')}</h2>
            {campaign.research_plan ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8 text-sm font-light leading-relaxed">
                <div>
                  <span className="text-primaryText/50 font-bold block mb-1 text-[10px] uppercase tracking-wider">{t('objective')}</span> 
                  {campaign.research_plan.research_objective}
                </div>
                <div>
                  <span className="text-primaryText/50 font-bold block mb-1 text-[10px] uppercase tracking-wider">{t('targeting')}</span> 
                  {campaign.research_plan.target_audience}
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center p-8 space-x-3 text-primaryText/60">
                <Loader2 className="w-5 h-5 animate-spin text-primaryText" />
                <span className="text-sm">{t('creatingResearchPlan')}</span>
              </div>
            )}
            <div className="mt-8 pt-6 border-t border-white/5 flex justify-end">
              <button
                onClick={() => executeAction(api.startResearch)}
                disabled={isWorking}
                className="px-8 py-3 bg-primaryText text-background font-bold tracking-wide rounded-xl hover:bg-white hover:scale-[1.02] transition-all flex items-center disabled:opacity-50 shadow-xl cursor-pointer"
              >
                {isWorking ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {activeJob?.message || t('startResearchBtn')}
                  </>
                ) : (
                  <>
                    {t('startResearchBtn')} <ArrowRight className="w-4 h-4 ml-2" />
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {!loadingCampaign && !loadError && campaign && (campaign.stage === 'research' || campaign.stage === 'verification') && campaign.research_plan && (
          <div className="max-w-4xl mx-auto bg-surface p-8 rounded-2xl border border-white/5 mb-8 shadow-lg">
            <h2 className="text-xs font-bold uppercase tracking-widest text-primaryText/50 mb-6">{t('researchDirective')}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 text-sm font-light leading-relaxed">
              <div>
                <span className="text-primaryText/50 font-bold block mb-1 text-[10px] uppercase tracking-wider">{t('objective')}</span> 
                {campaign.research_plan.research_objective}
              </div>
              <div>
                <span className="text-primaryText/50 font-bold block mb-1 text-[10px] uppercase tracking-wider">{t('targeting')}</span> 
                {campaign.research_plan.target_audience}
              </div>
            </div>
          </div>
        )}

        {!loadingCampaign && !loadError && campaign && campaign.stage === 'research' && !campaign.research_pack && (
          <div className="max-w-3xl mx-auto bg-surface p-12 rounded-2xl border border-white/5 shadow-xl text-center space-y-6 animate-in fade-in">
            <Loader2 className="w-12 h-12 animate-spin text-primaryText mx-auto" />
            <div className="space-y-2">
              <h3 className="text-2xl font-bold text-primaryText">{t('researchInProgress')}</h3>
              <p className="text-sm text-primaryText/60 max-w-md mx-auto">{t('parallelQueryingProgress')}</p>
            </div>
            {!isWorking && (
              <button
                onClick={() => executeAction(api.startResearch)}
                className="px-6 py-2.5 bg-primaryText text-background font-bold text-sm rounded-xl hover:opacity-90 transition-all"
              >
                {t('startResearchBtn')}
              </button>
            )}
          </div>
        )}

        {!loadingCampaign && !loadError && campaign && campaign.stage === 'research' && campaign.research_pack && (
          <div className="animate-in fade-in slide-in-from-bottom-8 duration-700">
            <div className="flex justify-between items-end mb-8">
              <h2 className="text-4xl font-bold tracking-tight">{t('researchIntelligence')}</h2>
              <div className="flex items-center space-x-4">
                <div className="px-4 py-1.5 bg-surface border border-white/5 rounded-full text-[10px] font-mono text-primaryText/60 flex items-center shadow-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-success mr-2 animate-pulse shadow-[0_0_8px_rgba(59,201,138,0.5)]"></span>
                  Parallel Search &bull; {campaign.research_pack.evidence.length} {t('sourcesCount')}
                  {campaign.research_pack.latency_seconds && ` • ${campaign.research_pack.latency_seconds.toFixed(2)}s`}
                </div>
              </div>
            </div>
            
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-8">
              <div className="space-y-8">
                {campaign.claim_verification && campaign.claim_verification.unsupported_claims_found && (
                  <div className="p-6 bg-surfaceRaised border-l-4 border-l-primaryText rounded-r-2xl shadow-lg">
                    <h3 className="text-xs font-bold text-primaryText uppercase tracking-widest mb-5 flex items-center">
                      <ShieldCheck className="w-4 h-4 mr-2" />
                      {t('trustSafetyVerification')}
                    </h3>
                    <div className="space-y-5">
                      {campaign.claim_verification.flags.map((flag, i) => (
                        <div key={i} className="text-sm border-b border-white/5 pb-4 last:border-0 last:pb-0">
                          <div className="font-medium text-lg leading-snug mb-2">"{flag.claim}"</div>
                          <div className="text-primaryText/60 font-light mb-3">{flag.reason}</div>
                          <div className="bg-background/50 p-3 rounded-lg border border-white/5">
                            <span className="text-[10px] uppercase tracking-widest text-primaryText/50 block mb-1">{t('approvedWording')}</span>
                            <span className="font-medium">{flag.safer_wording_suggestion}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {campaign.research_pack.creative_opportunity && (
                  <div className="p-8 bg-gradient-to-br from-surface to-surfaceRaised border border-white/5 rounded-2xl shadow-xl relative overflow-hidden">
                    <Sparkles className="w-32 h-32 absolute -top-10 -right-10 text-white/5" />
                    <h3 className="text-[10px] font-bold text-primaryText/50 uppercase tracking-widest mb-4">{t('creativeOpportunity')}</h3>
                    <p className="text-2xl font-light leading-snug"><TextWithEvidenceChips text={campaign.research_pack.creative_opportunity} /></p>
                  </div>
                )}
                
                <div className="grid grid-cols-2 gap-6">
                  <div className="bg-surface p-6 rounded-2xl border border-white/5">
                    <h3 className="text-[10px] font-bold text-primaryText/50 uppercase tracking-widest mb-4">{t('audienceTensions')}</h3>
                    <ul className="space-y-4">
                      {campaign.research_pack.audience_tensions.map((t, i) => (
                        <li key={i} className="text-sm font-light leading-relaxed"><TextWithEvidenceChips text={t} /></li>
                      ))}
                    </ul>
                  </div>
                  <div className="bg-surface p-6 rounded-2xl border border-white/5">
                    <h3 className="text-[10px] font-bold text-primaryText/50 uppercase tracking-widest mb-4">{t('formatPatterns')}</h3>
                    <ul className="space-y-4">
                      {campaign.research_pack.format_patterns.map((t, i) => (
                        <li key={i} className="text-sm font-light leading-relaxed"><TextWithEvidenceChips text={t} /></li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
              
              <div className="flex flex-col h-[700px] bg-surface rounded-2xl border border-white/5 overflow-hidden">
                <div className="p-5 border-b border-white/5 bg-surface/50 backdrop-blur-md">
                  <h3 className="text-[10px] font-bold text-primaryText/50 uppercase tracking-widest">{t('evidenceStack')}</h3>
                </div>
                <div className="p-4 space-y-3 overflow-y-auto custom-scrollbar flex-1">
                  {campaign.research_pack.evidence.map((e, i) => {
                    if (e.excluded) return null;
                    const rawDomain = e.source_url.match(/^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:\/\n?]+)/img)?.[0] || 'Web';
                    const demoMask = (str: string) => serverStatus === 'mock' ? str.replace(/[a-zA-Z]/g, '█') : str;
                    const domain = serverStatus === 'mock' ? '██████.com' : rawDomain;
                    
                    return (
                      <div key={i} id={`evidence-${e.evidence_id}`} className="p-4 bg-background/50 rounded-xl border border-white/5 hover:border-white/20 transition-all group">
                        <div className="flex items-center justify-between mb-3">
                          <span className="px-2 py-0.5 bg-white/10 text-primaryText font-mono text-[10px] rounded">{e.evidence_id}</span>
                          <span className="text-[10px] text-primaryText/40 truncate max-w-[150px] font-mono">{domain}</span>
                        </div>
                        <h4 className="text-sm font-medium mb-2 truncate text-primaryText/90">{demoMask(e.source_title)}</h4>
                        <p className="text-xs text-primaryText/60 mb-4 line-clamp-3 font-light">{demoMask(e.claim)}</p>
                        <div className="flex justify-between items-center pt-3 border-t border-white/5">
                          {serverStatus === 'mock' ? (
                             <span className="text-[10px] font-medium text-primaryText/40 uppercase tracking-wider">{t('urlRedacted')}</span>
                          ) : (
                             <a href={e.source_url} target="_blank" rel="noopener noreferrer" className="text-[10px] font-bold uppercase tracking-wider text-primaryText/60 hover:text-primaryText transition-colors">{t('viewSource')}</a>
                          )}
                          <button 
                            onClick={() => api.excludeEvidence(campaign.id, e.evidence_id).then(setCampaign)}
                            className="text-[10px] font-bold uppercase tracking-wider text-primaryText/40 hover:text-error transition-colors opacity-0 group-hover:opacity-100"
                          >
                            {t('excludeEvidence')}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
            
            <div className="mt-12 flex justify-between items-center">
              <span className="text-sm text-primaryText/40 font-light italic">{t('geminiSynthesisNotice')}</span>
              <button 
                onClick={() => executeAction(api.generateDirections)}
                disabled={isWorking}
                className="px-8 py-3 bg-primaryText text-background font-bold tracking-wide rounded-xl hover:bg-white hover:scale-[1.02] transition-all flex items-center disabled:opacity-50 disabled:hover:scale-100 shadow-xl"
              >
                {t('generateDirections')} <ArrowRight className="w-4 h-4 ml-2" />
              </button>
            </div>
          </div>
        )}

        {!loadingCampaign && !loadError && campaign && campaign.stage === 'directions' && campaign.direction_set && (
          <div className="animate-in fade-in slide-in-from-bottom-8 duration-700">
            <div className="mb-10 text-center max-w-2xl mx-auto">
              <h2 className="text-4xl font-bold tracking-tight mb-4">{t('creativeDirectionsTitle')}</h2>
              <p className="text-primaryText/60 font-light text-lg">{t('creativeDirectionsSubtitle')}</p>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {campaign.direction_set.directions.map(dir => {
                const isSelected = campaign.selected_direction_id === dir.direction_id;
                const isPick = campaign.direction_set?.director_pick_direction_id === dir.direction_id;
                
                return (
                  <div 
                    key={dir.direction_id} 
                    className={`relative p-8 rounded-3xl border flex flex-col transition-all duration-300 ${
                      isSelected 
                        ? 'bg-surfaceRaised border-primaryText shadow-2xl scale-[1.02]' 
                        : isPick 
                          ? 'bg-surface border-white/20 shadow-xl' 
                          : 'bg-surface border-white/5 hover:border-white/20'
                    }`}
                  >
                    {isPick && (
                      <div className="absolute -top-3 inset-x-0 flex justify-center">
                        <div className="px-3 py-1 bg-primaryText text-background text-[10px] font-bold tracking-widest uppercase rounded-full shadow-lg">
                          {t('directorPick')}
                        </div>
                      </div>
                    )}
                    
                    <h3 className="text-2xl font-bold mb-8 mt-2">{dir.name}</h3>
                    
                    <div className="space-y-6 flex-1 text-sm font-light">
                      <div><span className="block text-[10px] text-primaryText/40 uppercase tracking-widest mb-1.5 font-bold">{t('hook')}</span> <span className="italic text-primaryText/90">"{dir.hook}"</span></div>
                      <div><span className="block text-[10px] text-primaryText/40 uppercase tracking-widest mb-1.5 font-bold">{t('tension')}</span> <span className="text-primaryText/80">{dir.core_tension}</span></div>
                      <div><span className="block text-[10px] text-primaryText/40 uppercase tracking-widest mb-1.5 font-bold">{t('visualConcept')}</span> <span className="text-primaryText/80">{dir.visual_idea}</span></div>
                      <div>
                        <span className="block text-[10px] text-primaryText/40 uppercase tracking-widest mb-2 font-bold">{t('evidenceGrounding')}</span>
                        <div className="flex flex-wrap gap-2">
                          {dir.evidence_ids.map(eid => (
                            <span key={eid} className="px-2 py-1 bg-background/50 border border-white/5 text-[10px] font-mono rounded text-primaryText/60">{eid}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                    
                    <div className="mt-10">
                      <button 
                        onClick={() => api.selectDirection(campaign.id, dir.direction_id).then(setCampaign)}
                        className={`w-full py-3 rounded-xl font-bold tracking-wide transition-all ${
                          isSelected 
                            ? 'bg-primaryText text-background shadow-lg' 
                            : 'bg-white/5 text-primaryText hover:bg-white/10'
                        }`}
                      >
                        {isSelected ? t('selected') : t('selectDirection')}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            
            {campaign.direction_set.director_pick_reason && (
              <div className="mt-12 max-w-3xl mx-auto p-6 bg-surface border border-white/5 rounded-2xl text-center">
                <span className="text-[10px] font-bold uppercase tracking-widest text-primaryText/50 block mb-2">{t('directorPickRationale')}</span>
                <p className="text-sm font-light text-primaryText/80">{campaign.direction_set.director_pick_reason}</p>
              </div>
            )}
            
            <div className="mt-12 flex justify-center">
              <button 
                onClick={() => executeAction(api.generateShotPlan)}
                disabled={!campaign.selected_direction_id || isWorking}
                className="px-10 py-4 bg-primaryText text-background font-bold tracking-widest uppercase rounded-xl hover:bg-white hover:scale-[1.02] transition-all disabled:opacity-50 disabled:hover:scale-100 shadow-2xl flex items-center"
              >
                {t('directorStudio')} <ArrowRight className="w-4 h-4 ml-3" />
              </button>
            </div>
          </div>
        )}

        {!loadingCampaign && !loadError && campaign && campaign.stage === 'studio' && campaign.shot_plan && (
          <div className="animate-in fade-in slide-in-from-bottom-8 duration-700">
            {(() => {
              const outputFormat = campaign.output_format || 'hybrid_reel';
              const outputOptions = [
                {
                  id: 'campaign_pack' as const,
                  title: t('campaignPack'),
                  description: t('campaignPackDesc'),
                  cost: t('campaignPackCost'),
                  icon: Sparkles,
                  badges: [t('recommended'), t('brandedFinishing')],
                },
                {
                  id: 'hybrid_reel' as const,
                  title: t('hybridReel'),
                  description: t('hybridDesc'),
                  cost: t('hybridCost'),
                  icon: WandSparkles,
                  badges: [t('nativeAudio'), t('brandedFinishing')],
                },
                {
                  id: 'static_post' as const,
                  title: t('staticPost'),
                  description: t('staticDesc'),
                  cost: t('noCostStaticPost'),
                  icon: ImageIcon,
                  badges: [t('brandedFinishing')],
                },
                {
                  id: 'carousel_post' as const,
                  title: t('carouselPost'),
                  description: t('carouselDesc'),
                  cost: t('carouselCost'),
                  icon: FileText,
                  badges: [t('brandedFinishing')],
                },
                {
                  id: 'slideshow_reel' as const,
                  title: t('slideshowReel'),
                  description: t('slideshowDesc'),
                  cost: t('slideshowCost'),
                  icon: PlayCircle,
                  badges: [t('brandedFinishing')],
                },
                {
                  id: 'full_video_reel' as const,
                  title: t('fullVideoReel'),
                  description: t('fullDesc'),
                  cost: t('fullReelCost'),
                  icon: Volume2,
                  badges: [t('higherCost'), t('nativeAudio')],
                },
              ];
              const displayShots = outputFormat === 'full_video_reel'
                ? (campaign.shot_plan.full_reel_shots?.length ? campaign.shot_plan.full_reel_shots : campaign.shot_plan.shots)
                : campaign.shot_plan.shots;
              const imageAssets = availableAssets.filter(asset => asset.kind === 'image');
              const showShotPlan = ['campaign_pack', 'hybrid_reel', 'full_video_reel'].includes(outputFormat);
              const brandColors = brandKit?.brand_colors?.length ? brandKit.brand_colors : ['#F5F5F0', '#141210', '#8B7CFF'];
              const foreground = brandColors[0] || '#F5F5F0';
              const background = brandColors[1] || '#141210';
              const accent = brandColors[2] || brandColors[0] || '#8B7CFF';
              const visualTreatments = [
                {
                  id: 'brand_safe' as const,
                  title: t('treatmentBrandSafe'),
                  description: t('treatmentBrandSafeDesc'),
                  swatches: [foreground, background, accent],
                  preview: `linear-gradient(135deg, ${background} 0 66%, ${accent} 66% 78%, ${foreground} 78%)`,
                },
                {
                  id: 'campaign_mood' as const,
                  title: t('treatmentCampaignMood'),
                  description: t('treatmentCampaignMoodDesc'),
                  swatches: [background, accent, foreground],
                  preview: `radial-gradient(circle at 72% 20%, ${accent} 0 18%, transparent 19%), linear-gradient(145deg, ${background}, ${accent})`,
                },
                {
                  id: 'high_contrast' as const,
                  title: t('treatmentHighContrast'),
                  description: t('treatmentHighContrastDesc'),
                  swatches: ['#FFFFFF', '#05070B', accent],
                  preview: `linear-gradient(135deg, #05070B 0 58%, ${accent} 58% 74%, #FFFFFF 74%)`,
                },
              ];
              const showVisualDirection = ['campaign_pack', 'static_post', 'carousel_post', 'slideshow_reel'].includes(outputFormat);

              return (
                <>
                  <section className="mb-12" aria-labelledby="output-type-title">
                    <div className="flex items-center justify-between mb-5">
                      <h2 id="output-type-title" className="text-xs font-bold uppercase tracking-[0.22em] text-primaryText/50">{t('outputType')}</h2>
                      <span className="text-[10px] font-mono uppercase tracking-widest text-primaryText/35">{t('sharedCampaignIntelligence')}</span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                      {outputOptions.map(option => {
                        const Icon = option.icon;
                        const selected = outputFormat === option.id;
                        return (
                          <button
                            key={option.id}
                            type="button"
                            aria-pressed={selected}
                            onClick={() => updateOutputFormat(option.id)}
                            disabled={isWorking || formatUpdating}
                            className={`text-left rounded-2xl border p-6 transition-all disabled:opacity-60 ${selected ? 'border-primaryText bg-white/[0.08] shadow-xl' : 'border-white/10 bg-surface hover:border-white/25 hover:bg-white/[0.04]'}`}
                          >
                            <div className="flex items-start justify-between gap-4 mb-5">
                              <Icon className={`w-6 h-6 ${selected ? 'text-primaryText' : 'text-primaryText/45'}`} />
                              <div className="flex flex-wrap justify-end gap-1.5">
                                {option.badges.map((badge, index) => (
                                  <span key={badge} className={`px-2 py-1 rounded-full text-[9px] font-bold uppercase tracking-wider ${index === 0 && option.id === 'campaign_pack' ? 'bg-success/15 text-success' : option.id === 'full_video_reel' && index === 0 ? 'bg-warning/15 text-warning' : 'bg-white/10 text-primaryText/60'}`}>{badge}</span>
                                ))}
                              </div>
                            </div>
                            <h3 className="text-xl font-bold mb-2">{option.title}</h3>
                            <p className="text-sm font-light leading-relaxed text-primaryText/55">{option.description}</p>
                            <p className="mt-4 text-[10px] font-mono uppercase tracking-wider text-primaryText/40">{option.cost}</p>
                          </button>
                        );
                      })}
                    </div>
                  </section>

                  {productionDraft && (
                    <section className="mb-12 rounded-3xl border border-white/10 bg-surface p-6 md:p-8" aria-labelledby="production-approval-title">
                      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 mb-7">
                        <div>
                          <h2 id="production-approval-title" className="text-xl font-bold mb-2">{t('productionApproval')}</h2>
                          <p className="text-sm text-primaryText/50 max-w-2xl">{t('productionApprovalDesc')}</p>
                        </div>
                        <span className={`self-start px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest ${productionSettingsSaved ? 'bg-success/15 text-success' : 'bg-warning/15 text-warning'}`}>
                          {productionSettingsSaved ? t('approved') : t('unsavedChanges')}
                        </span>
                      </div>

                      {productionSettingsError && <div className="mb-5 rounded-xl border border-error/30 bg-error/10 p-3 text-sm text-error">{productionSettingsError}</div>}

                      {showVisualDirection && (
                        <div className="mb-7 rounded-2xl border border-white/10 bg-background/40 p-4 md:p-5" aria-labelledby="visual-direction-title">
                          <div className="mb-4">
                            <h3 id="visual-direction-title" className="text-sm font-bold text-primaryText">{t('visualDirection')}</h3>
                            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-primaryText/45">{t('visualDirectionHelp')}</p>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            {visualTreatments.map(treatment => {
                              const selected = productionDraft.visual_treatment === treatment.id;
                              return (
                                <button
                                  key={treatment.id}
                                  type="button"
                                  aria-pressed={selected}
                                  data-visual-treatment={treatment.id}
                                  onClick={() => changeProductionDraft({ visual_treatment: treatment.id })}
                                  className={`overflow-hidden rounded-2xl border text-left transition-all ${selected ? 'border-primaryText bg-white/[0.08] ring-1 ring-primaryText' : 'border-white/10 bg-surface hover:border-white/25'}`}
                                >
                                  <span className="block h-20 border-b border-white/10" style={{ background: treatment.preview }} />
                                  <span className="block p-3.5">
                                    <span className="flex items-center justify-between gap-2">
                                      <span className="text-sm font-bold text-primaryText">{treatment.title}</span>
                                      <span className="flex -space-x-1">
                                        {treatment.swatches.map(color => <span key={color} className="h-4 w-4 rounded-full border border-black/30" style={{ backgroundColor: color }} />)}
                                      </span>
                                    </span>
                                    <span className="mt-1.5 block text-[11px] leading-relaxed text-primaryText/45">{treatment.description}</span>
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                        <label className="space-y-2">
                          <span className="text-[10px] font-bold uppercase tracking-widest text-primaryText/45">{t('campaignHeadline')}</span>
                          <input
                            value={productionDraft.headline}
                            maxLength={90}
                            onChange={event => changeProductionDraft({ headline: event.target.value })}
                            className="w-full rounded-xl border border-white/10 bg-background p-3.5"
                          />
                          <span className="block text-right text-[10px] font-mono text-primaryText/30">{productionDraft.headline.length}/90</span>
                        </label>
                        <label className="space-y-2">
                          <span className="text-[10px] font-bold uppercase tracking-widest text-primaryText/45">{t('finalCta')}</span>
                          <input
                            value={productionDraft.cta}
                            maxLength={48}
                            onChange={event => changeProductionDraft({ cta: event.target.value })}
                            className="w-full rounded-xl border border-white/10 bg-background p-3.5"
                          />
                          <span className="block text-right text-[10px] font-mono text-primaryText/30">{productionDraft.cta.length}/48</span>
                        </label>

                        {(outputFormat === 'hybrid_reel' || outputFormat === 'campaign_pack') && (
                          <label className="space-y-2 md:col-span-2">
                            <span className="text-[10px] font-bold uppercase tracking-widest text-primaryText/45">{t('heroCaption')}</span>
                            <input
                              value={productionDraft.caption}
                              maxLength={110}
                              onChange={event => changeProductionDraft({ caption: event.target.value })}
                              placeholder={t('selectShotForCaption')}
                              className="w-full rounded-xl border border-white/10 bg-background p-3.5"
                            />
                            <span className="block text-right text-[10px] font-mono text-primaryText/30">{productionDraft.caption.length}/110</span>
                          </label>
                        )}

                        {!['static_post', 'carousel_post'].includes(outputFormat) && (
                          <div className="space-y-3">
                            <span className="text-[10px] font-bold uppercase tracking-widest text-primaryText/45">{t('audioMode')}</span>
                            <div className="grid grid-cols-2 gap-3">
                              <button
                                type="button"
                                onClick={() => changeProductionDraft({ audio_mode: 'native_ambient' })}
                                className={`rounded-xl border p-3 text-left transition-all ${productionDraft.audio_mode === 'native_ambient' ? 'border-primaryText bg-white/10' : 'border-white/10 bg-background'}`}
                              >
                                <Volume2 size={17} className="mb-2" />
                                <span className="block text-sm font-bold">{t('nativeAmbience')}</span>
                                <span className="text-[11px] text-primaryText/40">{t('nativeAmbienceDesc')}</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => changeProductionDraft({ audio_mode: 'silent' })}
                                className={`rounded-xl border p-3 text-left transition-all ${productionDraft.audio_mode === 'silent' ? 'border-primaryText bg-white/10' : 'border-white/10 bg-background'}`}
                              >
                                <VolumeX size={17} className="mb-2" />
                                <span className="block text-sm font-bold">{t('silent')}</span>
                                <span className="text-[11px] text-primaryText/40">{t('silentDesc')}</span>
                              </button>
                            </div>
                          </div>
                        )}

                        <div className={`space-y-3 ${['static_post', 'carousel_post'].includes(outputFormat) ? 'md:col-span-2' : ''}`}>
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-[10px] font-bold uppercase tracking-widest text-primaryText/45">{t('productProofAssets')}</span>
                            <span className="text-[10px] font-mono text-primaryText/30">{productionDraft.product_asset_ids.length}/3</span>
                          </div>
                          {imageAssets.length === 0 ? (
                            <p className="text-sm text-primaryText/40">{t('productProofEmpty')}</p>
                          ) : (
                            <div className="flex flex-wrap gap-2">
                              {imageAssets.map(asset => {
                                const selected = productionDraft.product_asset_ids.includes(asset.asset_id);
                                return (
                                  <button
                                    key={asset.asset_id}
                                    type="button"
                                    onClick={() => toggleProductionAsset(asset.asset_id)}
                                    className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm ${selected ? 'border-success/50 bg-success/10' : 'border-white/10 bg-background'}`}
                                  >
                                    {selected && <CheckCircle2 size={15} />}{asset.name}
                                  </button>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="mt-7 flex justify-end">
                        <button
                          type="button"
                          onClick={saveProductionSettings}
                          disabled={productionSettingsSaved || !productionDraft.headline.trim() || !productionDraft.cta.trim()}
                          className="flex items-center gap-2 rounded-xl bg-primaryText px-5 py-3 text-sm font-bold text-background disabled:opacity-35"
                        >
                          <Save size={16} /> {productionSettingsSaved ? t('productionApproved') : t('saveProductionSetup')}
                        </button>
                      </div>
                    </section>
                  )}

            {showShotPlan && <div className="flex flex-col gap-4 md:flex-row md:justify-between md:items-end mb-10">
              <div>
                <h2 className="text-4xl font-bold tracking-tight mb-2">{t('directorStudio')}</h2>
                <p className="text-primaryText/50 font-light">{t('candidateShots')}</p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <div className="px-4 py-2 bg-surface border border-white/5 rounded-lg text-xs font-mono text-primaryText/60">
                  {t('target9sNotice')}
                </div>
                <div className="px-4 py-2 bg-surface border border-white/5 rounded-lg text-xs font-mono text-primaryText/60">
                  {t('formatLabel')}: {campaign.shot_plan.aspect_ratio}
                </div>
              </div>
            </div>}
             
            {showShotPlan && <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {displayShots.map(shot => {
                const isSelected = campaign.selected_shot_id === shot.shot_id;
                
                return (
                  <div 
                    key={shot.shot_id} 
                    className={`bg-surface border rounded-2xl overflow-hidden flex flex-col group transition-all duration-300 shadow-lg ${
                      isSelected ? 'border-primaryText shadow-2xl scale-[1.02]' : 'border-white/5 hover:border-white/20'
                    }`}
                  >
                    <div className="aspect-[9/16] bg-[#171B2C] flex flex-col relative overflow-hidden">
                      {previewUrls[shot.shot_id] ? (
                        <img
                          src={previewUrls[shot.shot_id]}
                          alt={`${t('candidatePreview')} ${shot.order}: ${shot.visual}`}
                          className="absolute inset-0 h-full w-full object-cover"
                        />
                      ) : (
                        <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(111,88,255,0.42),transparent_38%),radial-gradient(circle_at_75%_70%,rgba(255,177,71,0.24),transparent_40%),linear-gradient(155deg,#202846,#11131f)]">
                          <div className="absolute inset-6 rounded-[2rem] border border-white/15" />
                          <div className="absolute inset-x-8 top-1/3 text-center">
                            <Camera className="mx-auto mb-4 h-9 w-9 text-white/55" aria-hidden="true" />
                            <span className="text-[10px] font-bold uppercase tracking-[0.22em] text-white/55">{t('previewFallbackTitle')}</span>
                          </div>
                        </div>
                      )}
                      <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-transparent to-black/90 z-10" />
                      
                      <div className="relative z-20 p-5 flex justify-between items-start">
                        <span className="px-2 py-1 bg-white/10 backdrop-blur-md rounded text-[10px] font-bold tracking-widest uppercase border border-white/10">{outputFormat === 'full_video_reel' ? t('scene') : t('option')} {shot.order}</span>
                        <span className="text-[10px] font-mono text-white/70">{shot.duration_seconds}s</span>
                      </div>

                      <div className="relative z-20 mt-auto p-5 text-center">
                        <span className="text-sm font-light italic text-white/90 drop-shadow-md">"{shot.visual}"</span>
                      </div>
                      {previewStatus === 'loading' && !previewUrls[shot.shot_id] && (
                        <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/35 backdrop-blur-[2px]">
                          <span className="flex items-center rounded-full bg-black/65 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-white">
                            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> {t('previewLoadingShot')}
                          </span>
                        </div>
                      )}
                    </div>
                    
                    <div className="p-6 flex-1 flex flex-col text-sm border-t border-white/5 bg-surfaceRaised">
                      <div className="space-y-5 flex-1">
                        <div>
                          <span className="block text-[10px] font-bold text-primaryText/40 uppercase tracking-widest mb-1.5">{t('actionCamera')}</span>
                          <span className="font-medium text-primaryText/90">{shot.action} • {shot.camera}</span>
                        </div>
                        
                        <div>
                          <span className="block text-[10px] font-bold text-primaryText/40 uppercase tracking-widest mb-1.5">{t('onScreenCaption')}</span>
                          <span className="font-light italic text-primaryText/80 text-base">"{shot.caption}"</span>
                        </div>
                      </div>
                      
                      {isSelected && shot.status !== 'planned' && (
                        <div className="mt-6 pt-5 border-t border-white/5 flex items-center justify-between">
                          <span className="text-[10px] font-bold uppercase tracking-widest text-primaryText/40">{t('stage')}</span>
                          <span className="flex items-center text-xs uppercase font-bold tracking-wider">
                            <div className={`w-1.5 h-1.5 rounded-full mr-2 shadow-sm ${
                              shot.status === 'ready' ? 'bg-success shadow-success/50' : 
                              shot.status === 'generating' ? 'bg-warning animate-pulse shadow-warning/50' : 
                              shot.status === 'failed' ? 'bg-error shadow-error/50' : 
                              'bg-primaryText/20'
                            }`} />
                            <span className={
                              shot.status === 'ready' ? 'text-success' : 
                              shot.status === 'generating' ? 'text-warning' : 
                              shot.status === 'failed' ? 'text-error' : 
                              'text-primaryText/40'
                            }>{shot.status}</span>
                          </span>
                        </div>
                      )}
                      
                      <div className="mt-6">
                        <button 
                          onClick={() => api.selectShot(campaign.id, shot.shot_id).then(setCampaign)}
                          disabled={isWorking || formatUpdating || !['hybrid_reel', 'campaign_pack'].includes(outputFormat)}
                          className={`w-full py-3 rounded-xl font-bold tracking-wide transition-all ${
                            isSelected 
                              ? 'bg-primaryText text-background shadow-lg' 
                              : 'bg-white/5 text-primaryText hover:bg-white/10'
                          }`}
                        >
                          {isSelected ? t('selectedForProduction') : t('selectShot')}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>}

            {showShotPlan && previewStatus === 'error' && (
              <div className="mt-5 flex justify-center">
                <button
                  type="button"
                  onClick={retryCandidatePreviews}
                  className="rounded-xl border border-white/15 bg-surface px-4 py-2 text-xs font-bold uppercase tracking-wider text-primaryText hover:border-white/30"
                >
                  {t('previewRetry')}
                </button>
              </div>
            )}

            <div className="mt-12 flex justify-center">
              <div className="text-center">
                <button 
                  onClick={() => executeAction(api.startProduction)}
                  disabled={isWorking || formatUpdating || !productionSettingsSaved || (['hybrid_reel', 'campaign_pack'].includes(outputFormat) && !campaign.selected_shot_id)}
                  className="px-12 py-4 bg-primaryText text-background font-bold tracking-widest uppercase rounded-xl hover:bg-white hover:scale-[1.02] transition-all disabled:opacity-50 disabled:hover:scale-100 shadow-2xl flex items-center"
                >
                  {isWorking
                    ? (outputFormat === 'campaign_pack' ? t('generatingPack') : t('producingReel'))
                    : outputFormat === 'campaign_pack'
                      ? t('produceCampaignPack')
                      : outputFormat === 'static_post'
                        ? t('generateStaticPost')
                        : outputFormat === 'carousel_post'
                          ? t('generateCarouselPost')
                          : outputFormat === 'slideshow_reel'
                            ? t('produceSlideshowReel')
                        : outputFormat === 'full_video_reel'
                          ? t('produceFullReel')
                          : t('produceReel')}
                </button>
                {['hybrid_reel', 'campaign_pack'].includes(outputFormat) && !campaign.selected_shot_id && (
                  <p className="mt-3 text-xs text-primaryText/45">{t(outputFormat === 'campaign_pack' ? 'selectedShotPackRequired' : 'selectedShotRequired')}</p>
                )}
                {!productionSettingsSaved && (
                  <p className="mt-3 text-xs text-warning">{t('saveProductionBeforeGenerate')}</p>
                )}
              </div>
            </div>
                </>
              );
            })()}
          </div>
        )}

        {!loadingCampaign && !loadError && campaign && campaign.stage === 'reel' && (
          <div className="animate-in fade-in slide-in-from-bottom-8 duration-1000 max-w-6xl mx-auto">
            {(() => {
              const isPack = campaign.output_format === 'campaign_pack';
              const deliverables = [
                campaign.final_video_url && {
                  key: 'video' as const,
                  title: campaign.output_format === 'slideshow_reel' ? t('slideshowAsset') : t('reelAsset'),
                  dimensions: t('reelDimensions'),
                  action: campaign.output_format === 'slideshow_reel' ? t('downloadSlideshowMp4') : t('downloadReelMp4'),
                  source: mediaUrls.video,
                  aspect: 'aspect-[9/16]',
                },
                campaign.final_slideshow_url && {
                  key: 'slideshow' as const,
                  title: t('slideshowAsset'),
                  dimensions: t('slideshowDimensions'),
                  action: t('downloadSlideshowMp4'),
                  source: mediaUrls.slideshow,
                  aspect: 'aspect-[9/16]',
                },
                campaign.final_image_url && {
                  key: 'image' as const,
                  title: t('postAsset'),
                  dimensions: t('postDimensions'),
                  action: t('downloadPost'),
                  source: mediaUrls.image,
                  aspect: 'aspect-[4/5]',
                },
                campaign.final_thumbnail_url && {
                  key: 'cover' as const,
                  title: t('coverAsset'),
                  dimensions: t('coverDimensions'),
                  action: t('downloadCover'),
                  source: mediaUrls.cover,
                  aspect: 'aspect-[9/16]',
                },
              ].filter(Boolean) as Array<{
                key: 'video' | 'slideshow' | 'image' | 'cover';
                title: string;
                dimensions: string;
                action: string;
                source?: string;
                aspect: string;
              }>;

              return (
                <>
                  <div className="text-center mb-12">
                    <span className="mb-4 inline-flex rounded-full bg-success/15 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-success">{t('readyToShare')}</span>
                    <h2 className="text-4xl md:text-5xl font-bold tracking-tight mb-4">
                      {isPack
                        ? t('campaignPackIsReady')
                        : campaign.output_format === 'carousel_post'
                          ? t('yourCarouselIsReady')
                          : campaign.final_image_url
                            ? t('yourPostIsReady')
                            : t('yourReelIsReady')}
                    </h2>
                    <p className="text-lg md:text-xl text-primaryText/50 font-light">
                      {isPack ? t('campaignPackReadySubtitle') : t('reelReadySubtitle')}
                    </p>
                  </div>

                  <div className={`grid grid-cols-1 gap-6 ${deliverables.length > 1 ? 'md:grid-cols-2 xl:grid-cols-4' : 'max-w-sm mx-auto'}`}>
                    {deliverables.map(item => (
                      <article key={item.key} className="rounded-3xl border border-white/10 bg-surface p-4 shadow-xl">
                        <div className={`${item.aspect} relative overflow-hidden rounded-2xl bg-[#171B2C]`}>
                          {item.source ? (
                            item.key === 'video' || item.key === 'slideshow' ? (
                              <video src={item.source} controls playsInline className="h-full w-full object-cover" />
                            ) : (
                              <img src={item.source} alt={item.title} className="h-full w-full object-cover" />
                            )
                          ) : (
                            <div className="absolute inset-0 flex items-center justify-center text-primaryText/45">
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> {t('previewLoadingShot')}
                            </div>
                          )}
                        </div>
                        <div className="flex items-start justify-between gap-3 px-1 pb-2 pt-4">
                          <div className="min-w-0">
                            <h3 className="font-bold">{item.title}</h3>
                            <p className="mt-1 text-[10px] font-mono uppercase tracking-wider text-primaryText/40">{item.dimensions}</p>
                          </div>
                          <CheckCircle2 className="h-5 w-5 shrink-0 text-success" aria-hidden="true" />
                        </div>
                        <a
                          href={item.source || '#'}
                          download
                          aria-disabled={!item.source}
                          className={`mt-2 flex w-full items-center justify-center rounded-xl py-3 text-xs font-bold uppercase tracking-widest transition-all ${item.source ? 'bg-primaryText text-background hover:bg-white' : 'pointer-events-none bg-white/5 text-primaryText/25'}`}
                        >
                          <Download className="mr-2 h-4 w-4" /> {item.action}
                        </a>
                      </article>
                    ))}
                  </div>

                  {(campaign.final_carousel_urls?.length || 0) > 0 && (
                    <section className="mt-8 rounded-3xl border border-white/10 bg-surface p-5 md:p-7" aria-labelledby="carousel-output-title">
                      <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                        <div>
                          <h3 id="carousel-output-title" className="text-xl font-bold">{t('carouselAsset')}</h3>
                          <p className="mt-1 text-xs font-mono uppercase tracking-wider text-primaryText/40">{t('carouselDimensions')}</p>
                        </div>
                        <span className="text-xs text-primaryText/50">{campaign.final_carousel_urls?.length || 0} cards · {t('readyToShare')}</span>
                      </div>
                      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                        {(campaign.final_carousel_urls || []).map((_, index) => {
                          const source = mediaUrls.carousel[index];
                          return (
                            <article key={`carousel-${index}`} className="rounded-2xl border border-white/10 bg-background/55 p-3">
                              <div className="aspect-[4/5] overflow-hidden rounded-xl bg-[#171B2C]">
                                {source ? (
                                  <img src={source} alt={`${t('carouselAsset')} ${index + 1}`} className="h-full w-full object-cover" />
                                ) : (
                                  <div className="flex h-full items-center justify-center text-primaryText/40">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  </div>
                                )}
                              </div>
                              <div className="mt-3 flex items-center justify-between text-xs">
                                <span className="font-bold">{String(index + 1).padStart(2, '0')}</span>
                                <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />
                              </div>
                              <a
                                href={source || '#'}
                                download
                                aria-disabled={!source}
                                className={`mt-3 flex items-center justify-center rounded-lg py-2.5 text-[10px] font-bold uppercase tracking-wider ${source ? 'bg-primaryText text-background' : 'pointer-events-none bg-white/5 text-primaryText/25'}`}
                              >
                                <Download className="mr-1.5 h-3.5 w-3.5" /> {t('downloadCarouselSlide')}
                              </a>
                            </article>
                          );
                        })}
                      </div>
                    </section>
                  )}

                  <div className="mt-10 bg-surface p-6 md:p-10 rounded-3xl border border-white/5 shadow-xl">
                <h3 className="text-xs font-bold text-primaryText/40 uppercase tracking-widest mb-8">{t('productionSummary')}</h3>
                
                <div className="relative pl-8 border-l border-white/10 space-y-10">
                  {[
                    { title: t('intelligenceGathering'), desc: t('intelligenceGatheringDesc') },
                    { title: t('strategicDirection'), desc: t('strategicDirectionDesc') },
                    {
                      title: campaign.output_format === 'slideshow_reel' ? t('cardOrchestration') : t('shotOrchestration'),
                      desc: campaign.output_format === 'slideshow_reel' ? t('cardOrchestrationDesc') : t('shotOrchestrationDesc'),
                    },
                    {
                      title: t('generativeProduction'),
                      desc: campaign.output_format === 'slideshow_reel'
                        ? t('generativeProductionDescSlideshow')
                        : campaign.final_video_url ? t('generativeProductionDescVideo') : t('generativeProductionDescImage'),
                    },
                    {
                      title: t('finalAssembly'),
                      desc: campaign.output_format === 'slideshow_reel'
                        ? t('finalAssemblySlideshowDesc')
                        : campaign.final_video_url ? t('finalAssemblyVideoDesc') : t('finalAssemblyStaticDesc'),
                    }
                  ].map((step, i) => (
                    <div key={i} className="relative">
                      <div className="absolute -left-[37px] w-4 h-4 bg-background border-2 border-primaryText/20 rounded-full flex items-center justify-center">
                        <div className="w-1.5 h-1.5 bg-primaryText rounded-full" />
                      </div>
                      <h4 className="text-lg font-bold text-primaryText/90">{step.title}</h4>
                      <p className="text-sm text-primaryText/60 font-light mt-2 leading-relaxed">{step.desc}</p>
                    </div>
                  ))}
                </div>
                  </div>
                </>
              );
            })()}
          </div>
        )}
      </main>

      {renderActiveJob()}
    </div>
  );
}
