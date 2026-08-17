/** Generated UnitAccession values. Do not edit by hand. */

export const UnitAccession = {
  MZ: "MS:1000040",
  NUMBER_OF_DETECTOR_COUNTS: "MS:1000131",
  PERCENT_OF_BASE_PEAK: "MS:1000132",
  COUNTS_PER_SECOND: "MS:1000814",
  SECOND: "UO:0000010",
  MILLISECOND: "UO:0000028",
  MINUTE: "UO:0000031",
  VOLT_SECOND_PER_SQUARE_CENTIMETER: "MS:1002814",
} as const;

export type UnitAccession = (typeof UnitAccession)[keyof typeof UnitAccession];
