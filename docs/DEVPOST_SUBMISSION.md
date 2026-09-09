# Devpost Submission Draft

## Project name

Reel Director

## One-line pitch

An agentic creative director that researches what is worth making, lets the creator choose production cost before generation, and turns one brief into a branded social campaign pack.

## Track

Parallel

## Inspiration

Impressive generated footage is not automatically a useful campaign. Creators still need audience research, a defensible hook, cost control, product truth, brand consistency, captions, and adjacent social formats. Reel Director moves research and creative direction in front of generation, then finishes every output as a campaign asset.

## What it does

The creator starts with natural language and can attach live URLs, product images or video, PDF, DOCX, TXT, or Markdown. Reel Director asks at most one clarification and always offers Skip. It creates a reviewable Content Blueprint, performs live Parallel research, and uses Gemini to produce an evidence-grounded research synthesis, three creative directions, and a structured production plan.

Director Studio shows three candidate shots before video generation. The creator can produce a complete Campaign Pack or choose Hybrid Reel, Static Post, Carousel Post, Slideshow Reel, or Full Video Reel individually. The default Hybrid Reel sends only the selected candidate to Veo 3.1 Fast. Deterministic finishing then adds the real logo and product visuals, controlled motion copy, pixel-safe captions, and CTA while preserving Veo's native audio.

## How it was built

- React, TypeScript, Vite, and Tailwind for the responsive studio
- FastAPI for orchestration and controlled state transitions
- Parallel Search API through the official `parallel-web` SDK for live evidence
- Gemini through `google-genai` for brief analysis, research synthesis, directions, shot plans, brand suggestions, and still-image generation
- Veo 3.1 Fast through `google-genai` for native-audio vertical footage
- Pillow and FFmpeg for deterministic brand layout, motion, captions, CTA, audio preservation, and assembly
- Private Google Cloud Storage with a local Range proxy and production signed delivery

## Challenges

The difficult part was enforcing production economics and reliability rather than merely invoking models. The project moved from automatic three-shot generation to explicit single-shot selection, added production locking and retry guards, removed OAuth query-string delivery, implemented HTTP Range playback, separated interface language from campaign language, treated uploaded content as untrusted context, and made brand placement and captions deterministic.

## Accomplishments

- The live research path calls Parallel Search and rejects irrelevant or excerpt-free evidence.
- The default Hybrid path generates exactly one selected Veo shot.
- Static and Carousel formats reuse the same intelligence without a Veo call.
- Campaign Pack produces a Hybrid Reel, Static Post, five Carousel cards, Slideshow Reel, and cover.
- URL, image/video, PDF, DOCX, TXT, and Markdown intake are supported.
- Veo native audio is requested and preserved during FFmpeg assembly.
- Media playback supports seeking and avoids credentials or workspace identity in the URL.
- The same container serves the API, production React bundle, and SPA deep links.

## What we learned

Agentic creative production works best when generative models make bounded creative decisions and deterministic systems own exactness. Research, synthesis, and cinematic intent benefit from Gemini and Parallel; typography, brand placement, CTA geometry, security boundaries, and cost limits benefit from strict software contracts.

## What's next

Move state to Firestore or Cloud SQL, add authentication and quotas, run production jobs in durable workers, add collaboration and approval workflows, and connect optional scheduling and publishing services.

## Submission URLs

- Hosted project: `https://reel-director-949736914984.us-central1.run.app`
- Public source repository: `TO_BE_ADDED`
- Public demo video: `TO_BE_ADDED`
