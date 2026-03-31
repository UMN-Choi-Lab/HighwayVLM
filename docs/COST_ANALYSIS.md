# Cost Analysis

This document starts with the workload that was actually run overnight, then separates that from the later `30` second projection.

## Baseline Facts

- Overnight window used: `12:00 AM` to `6:00 AM` Central Time on `March 3, 2026`
- Cameras in the run: `4`
- Model actually used: `gpt-4o-mini`
- Runtime setup used for that run:
  - `SYSTEM_INTERVAL_SECONDS=30`
  - legacy VLM minimum-interval gate was `300` seconds
- Stored results in that window:
  - `288` saved live frames
  - `288` raw VLM output files
  - `288` successful analyses by `captured_at`
  - `72` analyses per camera

Important interpretation:

- Over the full `6` hour window, the run averaged `1` analysis every `5` minutes per camera.
- It was not a clean steady 5-minute schedule.
- It was also not a continuous 30-second schedule.
- During active periods, each camera was usually analyzed about every `43` to `45` seconds.

For reference, if the system had truly analyzed all `4` cameras every `30` seconds for the full 6-hour window, it would have produced `2,880` analyses, not `288`.

## Chart 1: Actual Overnight Run

This is the top chart because it is the workload that actually happened.

| Item | Value |
|---|---:|
| Time window | 6 hours |
| Cameras | 4 |
| Model used | gpt-4o-mini |
| Run interval | 30 seconds |
| Minimum VLM interval | 300 seconds |
| Total analyses | 288 |
| Analyses per camera | 72 |
| Full-window average cadence | 1 analysis every 5 minutes per camera |
| Active-window cadence | about 43 to 45 seconds per camera |
| Observed spend delta | $0.60 |
| Effective observed cost per analysis | $0.002083 |

## Chart 2: Actual Overnight Cluster Pattern

| Cluster | Time range | Analyses |
|---|---|---:|
| 1 | 12:00:09 AM to 12:01:06 AM | 8 |
| 2 | 12:20:10 AM to 1:02:58 AM | 232 |
| 3 | 1:49:49 AM to 1:52:13 AM | 16 |
| 4 | 3:28:49 AM | 1 |
| 5 | 5:22:51 AM to 5:28:00 AM | 31 |

## Request Profile Used For Estimates

Measured from the current app:

- Text input per request: about `1,459` tokens
- Text output per request: about `95` tokens
- Snapshot size: `720x480`

High-detail tile math for `720x480`:

- shortest side is scaled to `768`
- resized image becomes `1152x768`
- tile grid becomes `3 x 2 = 6` tiles

## Chart 3: Same Overnight Workload, Different Models

This chart answers: if the exact same `288` analysis workload had been run on other supported vision-capable models, what would the estimated cost have been?

| Model | Estimated cost for the 288-analysis overnight workload, low detail | Estimated cost for the 288-analysis overnight workload, high detail |
|---|---:|---:|
| gpt-5-nano | $0.03 | $0.05 |
| gpt-5-mini | $0.16 | $0.23 |
| gpt-4o-mini | $0.20 | $1.67 |
| o3 | $1.10 | $1.62 |
| gpt-4.1 | $1.11 | $1.70 |
| gpt-4o | $1.39 | $2.12 |

The real observed run cost was `$0.60` on `gpt-4o-mini`, which sits between the low-detail and high-detail theoretical bounds for that model.

## Chart 4: If The Current Overnight Average Were Sustained

This chart keeps the same effective workload as the overnight run: `1 analysis every 5 minutes per camera` on average over time.

### Using the real observed overnight cost

| Scope | Analyses / day | Analyses / 30-day month | Cost / day | Cost / 30-day month |
|---|---:|---:|---:|---:|
| 4 cameras | 1,152 | 34,560 | $2.40 | $72.00 |
| 1,929 cameras | 555,552 | 16,666,560 | $1,157.40 | $34,722.00 |

## Chart 5: If The System Is Changed To Consistent 30-Second Analysis

This is the later projection. It is not the workload that produced the observed overnight spend.

### Using the same observed `gpt-4o-mini` per-analysis cost

| Scope | Analyses / day | Analyses / 30-day month | Cost / day | Cost / 30-day month |
|---|---:|---:|---:|---:|
| 4 cameras | 11,520 | 345,600 | $24.00 | $720.00 |
| 1,929 cameras | 5,555,520 | 166,665,600 | $11,574.00 | $347,220.00 |

### Using theoretical `gpt-4o-mini` low-detail and high-detail bounds

| Scope | Low-detail cost / day | Low-detail cost / 30-day month | High-detail cost / day | High-detail cost / 30-day month |
|---|---:|---:|---:|---:|
| 4 cameras | $8.07 | $242.20 | $66.83 | $2,004.86 |
| 1,929 cameras | $3,893.31 | $116,799.25 | $32,228.13 | $966,843.81 |

## Chart 6: Consistent 30-Second Analysis, Different Models

### 4 cameras

| Model | Low-detail cost / day | Low-detail cost / 30-day month | High-detail cost / day | High-detail cost / 30-day month |
|---|---:|---:|---:|---:|
| gpt-5-nano | $1.32 | $39.55 | $1.80 | $54.07 |
| gpt-5-mini | $6.59 | $197.77 | $9.01 | $270.35 |
| gpt-4o-mini | $8.07 | $242.20 | $66.83 | $2,004.86 |
| o3 | $44.10 | $1,322.96 | $64.83 | $1,945.04 |
| gpt-4.1 | $44.33 | $1,329.87 | $67.83 | $2,034.89 |
| gpt-4o | $55.41 | $1,662.34 | $84.79 | $2,543.62 |

### 1,929 cameras

| Model | Low-detail cost / day | Low-detail cost / 30-day month | High-detail cost / day | High-detail cost / 30-day month |
|---|---:|---:|---:|---:|
| gpt-5-nano | $635.83 | $19,074.88 | $869.16 | $26,074.83 |
| gpt-5-mini | $3,179.15 | $95,374.39 | $4,345.81 | $130,374.17 |
| gpt-4o-mini | $3,893.31 | $116,799.25 | $32,228.13 | $966,843.81 |
| o3 | $21,266.53 | $637,995.92 | $31,266.47 | $937,994.00 |
| gpt-4.1 | $21,377.64 | $641,329.23 | $32,710.90 | $981,327.05 |
| gpt-4o | $26,722.05 | $801,661.54 | $40,888.63 | $1,226,658.82 |

## Model Assumptions

- `gpt-4o-mini` uses the `4o-mini` image-token schedule from the OpenAI vision guide:
  - low detail: `2,833` image tokens
  - high detail: `2,833 + 5,667 * tile_count`
- `gpt-5-mini` and `gpt-5-nano` use the GPT-5 image-token schedule from the same guide:
  - low detail: `70` image tokens
  - high detail: `70 + 140 * tile_count`
- `gpt-4.1` and `gpt-4o` use the `4.1 / 4o` image-token schedule from the guide:
  - low detail: `85` image tokens
  - high detail: `85 + 170 * tile_count`
- `o3` uses the o-series image-token schedule from the guide:
  - low detail: `75` image tokens
  - high detail: `75 + 150 * tile_count`

## Bottom Line

- The actual overnight run was a `300`-second-minimum-interval run with clustered activity.
- The real observed spend for that run was `$0.60`.
- A future consistent `30` second design is a separate projection and is much more expensive.
- At `1,929` cameras, the consistent `30` second design ranges from roughly `$19k/month` on `gpt-5-nano` low-detail to more than `$1.2M/month` on `gpt-4o` high-detail.
- The current model, `gpt-4o-mini`, lands around `$117k/month` low-detail or `$967k/month` high-detail at `1,929` cameras every `30` seconds.

These are cost comparisons only. They do not imply equal traffic-analysis quality across models.

## Sources

- OpenAI pricing: https://platform.openai.com/docs/pricing/
- OpenAI images and vision guide: https://developers.openai.com/docs/guides/images-vision
