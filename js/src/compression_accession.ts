/** Generated CompressionAccession values. Do not edit by hand. */

export const CompressionAccession = {
  NUMPRESS_LINEAR_ZLIB: "MS:1002746",
  NUMPRESS_SLOF_ZLIB: "MS:1002748",
  NUMPRESS_PIC_ZLIB: "MS:1002747",
  ZLIB: "MS:1000574",
  ZSTD: "MS:1003780",
  BYTE_SHUFFLED_ZSTD: "MS:1003781",
  NUMPRESS_LINEAR_ZSTD: "MS:1003783",
  NUMPRESS_PIC_ZSTD: "MS:1003784",
  NUMPRESS_SLOF_ZSTD: "MS:1003785",
} as const;

export type CompressionAccession = (typeof CompressionAccession)[keyof typeof CompressionAccession];
