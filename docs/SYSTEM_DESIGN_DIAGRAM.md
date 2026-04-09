# HighwayVLM System Design Diagram

## High-Level Architecture

```mermaid
flowchart LR
  U[Operator Browser]
  S[FastAPI App<br/>main.py -> highwayvlm.api]
  W[Background Worker Thread<br/>pipeline.run_loop]
  C[Camera Config<br/>config/cameras.yaml]
  I[Ingest Layer<br/>fetcher / stream / motion / vehicle]
  V[VLM Client<br/>highwayvlm.vlm.client]
  O[OpenAI-Compatible Vision API<br/>/chat/completions]
  DB[(SQLite<br/>data/highwayvlm.db)]
  F[(File Storage<br/>data/frames<br/>data/raw_vlm_outputs<br/>logs/incidents.jsonl)]
  UI[Web UI Assets<br/>web/*.html + web/static/*]

  U -->|HTTP| S
  S --> UI
  UI -->|poll JSON APIs| S

  S -->|startup event| W
  W --> C
  W --> I
  I --> V
  V --> O
  O --> V
  V --> W

  W -->|insert_log / archive writes| DB
  W -->|save snapshots / raw output / logs| F

  S -->|read for dashboard/archive APIs| DB
  S -->|serve image/frame files| F
```

## Runtime Tick Flow (Per Camera)

```mermaid
flowchart TD
  A[Tick begins<br/>SYSTEM_INTERVAL_SECONDS]
  B[Load cameras + per-camera state]
  C[Process cameras concurrently<br/>ThreadPoolExecutor]
  D[Fetch frame(s)<br/>HLS path or snapshot path]
  E[Local CV checks<br/>motion + YOLO vehicle count]
  G{Escalate to VLM?}
  H[Skip VLM<br/>persist CV-only result]
  I[Call VLM analyze_comparison]
  J[Validate + normalize JSON result]
  K[Incident confirmation logic<br/>pending/confirmed/filtered]
  L[Persist rows + files<br/>SQLite + snapshots + raw response]
  M[Frontend polls APIs<br/>/api/logs/latest /api/incidents /api/hourly]

  A --> B --> C --> D --> E --> G
  G -- No --> H --> L
  G -- Yes --> I --> J --> K --> L --> M
```

## Main Interfaces

- HTML/UI routes: `/`, `/incidents`, `/hourly`, `/overnight`, `/debug`
- Data APIs: `/api/logs/latest`, `/api/incidents`, `/api/hourly`, `/api/archive/overview`, `/api/debug/stats`
- Health: `/health`, `/api/health`

