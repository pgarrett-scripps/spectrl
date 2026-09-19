# Encoding benchmark measurements

127 spectra from 40 datasets. 36,634 array pipeline comparisons.

Positive savings mean smaller output. Total savings weight by baseline bytes. Median savings weight each spectrum or array equally. Timing totals sum the per-input median wall times and are in milliseconds.

## Complete tokens using the existing API

Adaptive includes candidate search and final re-encoding. Static policies time the normal public encoder. All metadata, descriptors, base64url expansion, and checksums are included in token sizes.

| Mode | Policy | N | Total savings | Median savings | Worst growth | Wins | Encode ms | Decode ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lossless | adaptive | 127 | 37.61% | 12.90% | 0.00% | 120 | 2591.3 | 94.9 |
| lossless | default | 127 | 0.00% | 0.00% | 0.00% | 0 | 2261.0 | 251.1 |
| lossless | shuffle | 127 | 37.11% | 11.89% | 33.50% | 115 | 123.0 | 94.0 |
| lossless | zstd | 127 | 4.32% | 7.56% | 19.98% | 87 | 185.8 | 115.6 |
| lossy | adaptive | 127 | 2.88% | 0.07% | 0.00% | 79 | 1060.3 | 568.7 |
| lossy | default | 127 | 0.00% | 0.00% | 0.00% | 0 | 470.0 | 628.2 |
| lossy | fp-10000 | 127 | 6.07% | 7.71% | 12.87% | 110 | 136.8 | 524.9 |
| lossy | fp-1000000 | 127 | -10.52% | -7.50% | 19.72% | 7 | 146.3 | 560.5 |
| lossy | numpress-zstd | 127 | -3.69% | -0.51% | 15.26% | 42 | 146.6 | 546.9 |

## Lossless array payloads

These sizes exclude descriptors and token framing. Each row uses its own eligible input subset and matching baseline, so check N when comparing transforms. Float32 variants and custom delta/XOR pipelines are experiments, not new spectrl codec identifiers.

| Transform | Compressor | N | Total savings | Median savings | Encode ms | Decode ms |
| --- | --- | --- | --- | --- | --- | --- |
| delta-shuffle | zstd-19 | 257 | 52.81% | 15.45% | 1922.4 | 41.1 |
| delta2-shuffle | zstd-19 | 257 | 51.37% | 13.37% | 2519.6 | 45.5 |
| delta-shuffle | bz2-9 | 257 | 51.33% | 8.84% | 3208.8 | 516.9 |
| delta-shuffle | xz-3 | 257 | 51.29% | 12.63% | 1959.3 | 427.3 |
| delta-shuffle | brotli-5 | 257 | 51.08% | 16.86% | 233.5 | 73.1 |
| delta-shuffle | zstd-9 | 257 | 49.73% | 12.81% | 188.6 | 39.2 |
| delta-shuffle | zlib-9 | 257 | 49.53% | 15.38% | 7719.6 | 146.3 |
| delta2-shuffle | bz2-9 | 257 | 49.23% | 0.45% | 5451.9 | 607.0 |
| delta-shuffle | zlib-6 | 257 | 49.12% | 15.38% | 1186.8 | 148.7 |
| delta-shuffle | gzip-6 | 257 | 49.08% | 10.79% | 1173.4 | 135.7 |
| delta | xz-3 | 257 | 48.44% | 9.08% | 2845.2 | 449.4 |
| delta-shuffle | zstd-3 | 257 | 47.81% | 11.46% | 54.2 | 40.4 |
| delta2-shuffle | xz-3 | 257 | 47.09% | 10.63% | 2285.6 | 456.4 |
| delta | bz2-9 | 257 | 46.86% | 5.15% | 3763.8 | 705.9 |
| delta-shuffle | zstd-1 | 257 | 46.55% | 9.47% | 40.2 | 39.3 |
| delta2-shuffle | brotli-5 | 257 | 46.29% | 14.72% | 302.0 | 80.2 |
| shuffle | zstd-19 | 257 | 45.90% | 17.04% | 2069.5 | 35.3 |
| delta | zstd-19 | 257 | 45.55% | 7.71% | 8192.2 | 27.4 |
| xor-shuffle | zstd-19 | 257 | 45.48% | 17.12% | 2241.9 | 40.4 |
| delta2-shuffle | zlib-9 | 257 | 45.22% | 11.05% | 18677.7 | 157.3 |
| shuffle | xz-3 | 257 | 45.22% | 15.97% | 2057.0 | 432.2 |
| delta2-shuffle | zstd-9 | 257 | 45.21% | 10.50% | 241.4 | 45.4 |
| delta-shuffle | zlib-1 | 257 | 44.91% | 14.17% | 409.3 | 155.2 |
| xor-shuffle | xz-3 | 257 | 43.90% | 14.12% | 2071.7 | 441.8 |
| xor-shuffle | bz2-9 | 257 | 43.73% | 7.55% | 3985.8 | 567.6 |
| delta2-shuffle | zlib-6 | 257 | 43.63% | 10.94% | 1559.8 | 161.2 |
| delta2-shuffle | gzip-6 | 257 | 43.59% | 9.50% | 1550.6 | 149.4 |
| xor-shuffle | brotli-5 | 257 | 43.53% | 19.55% | 242.2 | 72.5 |
| shuffle | bz2-9 | 257 | 43.38% | 7.52% | 3942.0 | 573.2 |
| shuffle | brotli-5 | 257 | 43.33% | 19.04% | 243.8 | 71.1 |
| delta2-shuffle | zstd-3 | 257 | 43.18% | 9.30% | 61.0 | 47.8 |
| xor-shuffle | zstd-9 | 257 | 42.18% | 15.74% | 185.2 | 38.6 |
| xor-shuffle | zlib-9 | 257 | 42.15% | 16.43% | 6197.6 | 149.3 |
| shuffle | zlib-9 | 257 | 42.13% | 16.35% | 6126.9 | 142.9 |
| shuffle | zlib-6 | 257 | 41.66% | 16.02% | 1113.9 | 144.6 |
| shuffle | gzip-6 | 257 | 41.62% | 14.24% | 1093.6 | 131.3 |
| xor-shuffle | zlib-6 | 257 | 41.47% | 16.33% | 1138.9 | 150.4 |
| xor-shuffle | gzip-6 | 257 | 41.43% | 14.33% | 1131.1 | 138.4 |
| delta2-shuffle | zstd-1 | 257 | 41.29% | 7.92% | 48.6 | 47.4 |
| delta | brotli-5 | 257 | 41.12% | 7.36% | 415.9 | 53.6 |
| shuffle | zstd-9 | 257 | 40.51% | 15.53% | 178.2 | 33.1 |
| xor-shuffle | zstd-3 | 257 | 39.65% | 15.03% | 58.4 | 39.7 |
| delta | zlib-9 | 257 | 39.31% | 2.17% | 16475.6 | 143.4 |
| delta | zstd-9 | 257 | 39.09% | 4.25% | 421.0 | 30.2 |
| delta | zlib-6 | 257 | 37.96% | 1.79% | 1494.8 | 142.8 |
| delta | gzip-6 | 257 | 37.92% | -1.58% | 1481.2 | 129.8 |
| shuffle | zstd-3 | 257 | 37.36% | 13.92% | 55.6 | 34.3 |
| xor-shuffle | zstd-1 | 257 | 37.33% | 14.33% | 41.8 | 39.3 |
| delta2-shuffle | zlib-1 | 257 | 36.67% | 7.78% | 458.6 | 171.9 |
| xor-shuffle | zlib-1 | 257 | 36.57% | 15.11% | 439.2 | 157.8 |
| shuffle | zlib-1 | 257 | 36.34% | 15.14% | 429.4 | 151.4 |
| shuffle | zstd-1 | 257 | 34.69% | 13.38% | 37.9 | 33.3 |
| delta | zstd-3 | 257 | 34.02% | 0.83% | 84.0 | 35.0 |
| xor | xz-3 | 257 | 32.68% | 9.24% | 3804.1 | 539.5 |
| xor | bz2-9 | 257 | 32.49% | 2.43% | 2465.0 | 843.0 |
| xor | zstd-19 | 257 | 29.82% | 9.85% | 8908.3 | 31.7 |
| delta-shuffle | lz4-0 | 257 | 28.69% | 0.00% | 29.0 | 34.6 |
| delta | zstd-1 | 257 | 28.48% | -0.46% | 62.6 | 33.2 |
| delta | zlib-1 | 257 | 27.70% | -2.92% | 466.8 | 155.5 |
| raw | xz-3 | 257 | 24.16% | 12.73% | 3532.3 | 664.6 |
| xor | brotli-5 | 257 | 21.90% | 8.28% | 534.4 | 62.3 |
| xor-shuffle | lz4-0 | 257 | 20.38% | 5.10% | 30.0 | 34.3 |
| xor | zlib-9 | 257 | 19.89% | 0.00% | 23126.8 | 159.5 |
| xor | zstd-9 | 257 | 19.87% | 7.11% | 530.9 | 35.1 |
| shuffle | lz4-0 | 257 | 18.44% | 4.65% | 27.9 | 29.1 |
| xor | zlib-6 | 257 | 17.48% | 0.00% | 2038.2 | 160.4 |
| xor | gzip-6 | 257 | 17.45% | -1.92% | 2024.8 | 148.6 |
| raw | zstd-19 | 257 | 15.73% | 12.96% | 7452.8 | 29.5 |
| xor | zstd-1 | 257 | 14.43% | 4.34% | 73.4 | 36.8 |
| raw | brotli-5 | 257 | 12.88% | 10.04% | 534.2 | 62.3 |
| delta2-shuffle | lz4-0 | 257 | 11.62% | -10.96% | 35.1 | 41.7 |
| xor | zstd-3 | 257 | 11.59% | 4.87% | 105.2 | 40.6 |
| raw | zstd-9 | 257 | 7.00% | 8.70% | 459.9 | 30.0 |
| raw | zstd-3 | 257 | 4.35% | 5.88% | 95.6 | 33.0 |
| xor | zlib-1 | 257 | 2.49% | -3.94% | 584.5 | 179.2 |
| raw | zlib-6 | 257 | 0.00% | 0.00% | 2166.2 | 164.8 |
| raw | gzip-6 | 257 | -0.04% | -0.31% | 2158.0 | 152.4 |
| raw | zstd-1 | 257 | -0.70% | 3.44% | 60.4 | 29.6 |
| raw | zlib-9 | 257 | -1.27% | 0.00% | 21578.5 | 164.2 |
| raw | zlib-1 | 257 | -7.26% | -4.04% | 634.9 | 177.1 |
| raw | bz2-9 | 257 | -7.54% | -14.41% | 3579.4 | 1073.3 |
| delta | lz4-0 | 257 | -8.12% | -37.18% | 32.7 | 17.1 |
| xor | lz4-0 | 257 | -42.88% | -41.50% | 38.7 | 17.0 |
| raw | lz4-0 | 257 | -79.96% | -52.17% | 31.7 | 13.4 |
| delta | none | 257 | -232.59% | -114.02% | 5.5 | 9.0 |
| delta-shuffle | none | 257 | -232.59% | -114.02% | 15.7 | 28.0 |
| delta2-shuffle | none | 257 | -232.59% | -114.02% | 17.9 | 33.1 |
| raw | none | 257 | -232.59% | -114.02% | 0.1 | 0.2 |
| shuffle | none | 257 | -232.59% | -114.02% | 13.4 | 23.3 |
| xor | none | 257 | -232.59% | -114.02% | 5.6 | 8.2 |
| xor-shuffle | none | 257 | -232.59% | -114.02% | 16.0 | 27.7 |

## Lossy array payloads

These sizes exclude descriptors and token framing. Each row uses its own eligible input subset and matching baseline, so check N when comparing transforms. Float32 variants and custom delta/XOR pipelines are experiments, not new spectrl codec identifiers.

| Transform | Compressor | N | Total savings | Median savings | Encode ms | Decode ms |
| --- | --- | --- | --- | --- | --- | --- |
| numpress | bz2-9 | 257 | 7.41% | -14.38% | 993.2 | 739.9 |
| numpress | zstd-19 | 257 | 4.83% | 0.10% | 1121.3 | 477.0 |
| numpress | xz-3 | 257 | 4.72% | -2.28% | 1138.0 | 683.4 |
| numpress | zlib-9 | 257 | 0.42% | 0.00% | 1028.3 | 508.5 |
| numpress | zlib-6 | 257 | 0.00% | 0.00% | 396.2 | 523.2 |
| numpress | gzip-6 | 257 | -0.10% | -0.68% | 394.0 | 508.4 |
| numpress | brotli-5 | 257 | -0.38% | 0.88% | 162.2 | 486.3 |
| numpress | zstd-9 | 257 | -1.80% | -0.02% | 145.0 | 472.2 |
| numpress | zlib-1 | 257 | -3.53% | 0.00% | 220.0 | 514.8 |
| numpress | zstd-3 | 257 | -3.76% | -0.14% | 73.5 | 472.1 |
| float32-delta-shuffle | zstd-19 | 254 | -6.63% | 3.56% | 1530.5 | 31.8 |
| float32-delta-shuffle | xz-3 | 254 | -9.97% | -33.40% | 1423.9 | 274.2 |
| float32-delta-shuffle | brotli-5 | 254 | -10.39% | 3.15% | 176.6 | 50.1 |
| numpress | zstd-1 | 257 | -10.87% | -0.27% | 65.0 | 470.1 |
| float32-delta-shuffle | zlib-9 | 254 | -12.45% | 6.07% | 5574.2 | 91.1 |
| float32-delta-shuffle | zlib-6 | 254 | -13.82% | 5.92% | 785.3 | 93.3 |
| float32-delta-shuffle | gzip-6 | 254 | -13.92% | -10.84% | 780.0 | 86.4 |
| float32-delta-shuffle | bz2-9 | 254 | -14.30% | -22.10% | 1789.6 | 381.8 |
| float32-delta-shuffle | zstd-9 | 254 | -15.03% | 1.99% | 140.5 | 30.2 |
| float32-delta-shuffle | zstd-3 | 254 | -18.93% | 0.00% | 38.6 | 30.2 |
| float32-delta-shuffle | zlib-1 | 254 | -22.90% | 0.00% | 260.8 | 96.1 |
| float32-delta-shuffle | zstd-1 | 254 | -22.93% | -1.72% | 29.6 | 30.7 |
| float32-shuffle | xz-3 | 254 | -29.58% | -45.43% | 1600.4 | 330.2 |
| float32-shuffle | zstd-19 | 254 | -32.24% | -7.44% | 1824.4 | 25.8 |
| numpress | lz4-0 | 257 | -32.30% | -7.52% | 57.4 | 468.2 |
| float32-shuffle | bz2-9 | 254 | -34.30% | -46.85% | 1798.1 | 443.8 |
| float32-shuffle | zlib-9 | 254 | -39.12% | -12.18% | 6014.6 | 90.7 |
| float32-shuffle | brotli-5 | 254 | -39.52% | -13.25% | 188.9 | 49.0 |
| float32-shuffle | zlib-6 | 254 | -40.49% | -14.27% | 793.3 | 90.8 |
| float32-shuffle | gzip-6 | 254 | -40.59% | -18.86% | 790.1 | 85.2 |
| float32-shuffle | zstd-9 | 254 | -46.66% | -16.45% | 133.7 | 23.4 |
| float32-shuffle | zlib-1 | 254 | -51.12% | -20.93% | 287.9 | 95.9 |
| float32-shuffle | zstd-3 | 254 | -52.30% | -25.75% | 37.0 | 23.5 |
| float32-delta-shuffle | lz4-0 | 254 | -57.04% | -35.46% | 19.6 | 27.0 |
| float32-shuffle | zstd-1 | 254 | -59.78% | -27.68% | 25.4 | 22.9 |
| float32-raw | xz-3 | 254 | -75.64% | -56.69% | 2542.7 | 514.8 |
| float32-shuffle | lz4-0 | 254 | -86.24% | -78.87% | 18.2 | 20.8 |
| numpress | none | 257 | -90.24% | -2.28% | 50.7 | 467.8 |
| float32-raw | brotli-5 | 254 | -95.70% | -14.16% | 296.0 | 48.5 |
| float32-raw | zstd-19 | 254 | -114.11% | -46.03% | 2920.3 | 20.7 |
| float32-raw | zlib-9 | 254 | -136.42% | -46.47% | 7135.6 | 104.6 |
| float32-raw | zlib-6 | 254 | -140.56% | -46.47% | 1121.3 | 106.8 |
| float32-raw | gzip-6 | 254 | -140.66% | -51.14% | 1097.4 | 101.4 |
| float32-raw | zlib-1 | 254 | -152.77% | -54.38% | 497.9 | 116.8 |
| float32-raw | bz2-9 | 254 | -171.59% | -94.36% | 2764.7 | 780.3 |
| float32-raw | zstd-9 | 254 | -184.70% | -52.38% | 128.7 | 10.9 |
| float32-raw | zstd-3 | 254 | -188.99% | -54.70% | 33.9 | 11.8 |
| float32-raw | zstd-1 | 254 | -194.88% | -55.04% | 25.8 | 11.5 |
| float32-raw | lz4-0 | 254 | -264.13% | -94.84% | 11.4 | 2.9 |
| float32-delta-shuffle | none | 254 | -383.79% | -100.92% | 9.7 | 22.6 |
| float32-raw | none | 254 | -383.79% | -100.92% | 1.6 | 0.2 |
| float32-shuffle | none | 254 | -383.79% | -100.92% | 8.2 | 17.3 |

## Lossy array reconstruction error

Maximum observed error across arrays. Exact counts mean zero numeric error. Lossless transforms also passed separate byte equality checks.

| Transform | Array | N | Exact arrays | Absolute | Relative | Peak normalized |
| --- | --- | --- | --- | --- | --- | --- |
| float32-delta-shuffle | intensity | 127 | 125 | 0.477051 | 5.86462e-08 | 2.69449e-08 |
| float32-delta-shuffle | mz | 127 | 102 | 0.000244136 | 5.95834e-08 | 4.36075e-08 |
| float32-raw | intensity | 127 | 125 | 0.477051 | 5.86462e-08 | 2.69449e-08 |
| float32-raw | mz | 127 | 102 | 0.000244136 | 5.95834e-08 | 4.36075e-08 |
| float32-shuffle | intensity | 127 | 125 | 0.477051 | 5.86462e-08 | 2.69449e-08 |
| float32-shuffle | mz | 127 | 102 | 0.000244136 | 5.95834e-08 | 4.36075e-08 |
| numpress | MS:1003006 | 3 | 0 | 4.99616e-06 | 3.37089e-06 | 3.21138e-06 |
| numpress | intensity | 127 | 0 | 60826.3 | 1 | 0.000141586 |
| numpress | mz | 127 | 0 | 5e-06 | 2.47478e-07 | 2.6919e-08 |

## Rejected precision overrides

0 rejected cases.


## Environment

```json
{
  "python": "3.14.0",
  "platform": "Linux-6.8.0-35-generic-x86_64-with-glibc2.39",
  "numpress_backend": "pynumpress",
  "repeats": 3,
  "packages": {
    "numpy": "2.4.6",
    "zstandard": "0.25.0",
    "mzmlpy": "0.4.0"
  },
  "compressors": [
    "none",
    "zlib-1",
    "zlib-6",
    "zlib-9",
    "gzip-6",
    "zstd-1",
    "zstd-3",
    "zstd-9",
    "zstd-19",
    "bz2-9",
    "xz-3",
    "brotli-5",
    "lz4-0"
  ],
  "zlib": "1.3.1"
}
```
