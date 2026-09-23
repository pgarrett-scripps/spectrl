/** Example spectra for the demo and the downloadable example files.
 *
 * Masses are illustrative (monoisotopic residue sums), so they demonstrate
 * the format rather than reproduce a specific acquisition. */
import { ArrayAccession, type InlineSpectrum, type CvParam } from "../../js/dist/index.js";

// ---------------------------------------------------------------------------
// Tiny mass calculator (monoisotopic) for chemically real fragment ions.
// ---------------------------------------------------------------------------
const PROTON = 1.0072764665;
const WATER = 18.0105646863;
const RESIDUE: Record<string, number> = {
  G: 57.02146, A: 71.03711, S: 87.03203, P: 97.05276, V: 99.06841,
  T: 101.04768, C: 103.00919, L: 113.08406, I: 113.08406, N: 114.04293,
  D: 115.02694, Q: 128.05858, K: 128.09496, E: 129.04259, M: 131.04049,
  H: 137.05891, F: 147.06841, R: 156.10111, Y: 163.06333, W: 186.07931,
};

interface Peak { mz: number; intensity: number }

/** Singly-charged b and y ion series for a bare peptide sequence. */
function fragmentIons(peptide: string): Peak[] {
  const res = [...peptide].map((a) => RESIDUE[a] ?? 0);
  const n = res.length;
  const peaks: Peak[] = [];
  let bSum = 0;
  for (let i = 0; i < n - 1; i++) {
    bSum += res[i]!;
    peaks.push({ mz: bSum + PROTON, intensity: 0 });
  }
  let ySum = 0;
  for (let i = n - 1; i > 0; i--) {
    ySum += res[i]!;
    peaks.push({ mz: ySum + WATER + PROTON, intensity: 0 });
  }
  // Deterministic pseudo-random intensities so the plot looks like real data.
  let seed = 1337;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  for (const p of peaks) p.intensity = 1000 + rnd() * rnd() * 9e4;
  peaks.sort((a, b) => a.mz - b.mz);
  return peaks;
}

function precursorMz(peptide: string, charge: number): number {
  const mass = [...peptide].reduce((s, a) => s + (RESIDUE[a] ?? 0), 0) + WATER;
  return (mass + charge * PROTON) / charge;
}

/** A simple decaying isotope envelope around a base m/z (1 Da spacing / charge). */
function isotopeEnvelope(baseMz: number, charge: number, n: number, base = 1e5): Peak[] {
  const peaks: Peak[] = [];
  for (let i = 0; i < n; i++) {
    peaks.push({ mz: baseMz + (i * 1.00335) / charge, intensity: base * Math.exp(-0.55 * i) });
  }
  return peaks;
}

// ---------------------------------------------------------------------------
// Example spectra → InlineSpectrum
// ---------------------------------------------------------------------------
const flag = (acc: string): CvParam => ({ accession: acc });
const val = (acc: string, value: number | string, unit?: string): CvParam => ({
  accession: acc,
  value,
  ...(unit ? { unitAccession: unit } : {}),
});

const round2 = (x: number) => Math.round(x * 100) / 100;

function fromPeaks(peaks: Peak[]): { mz: number[]; intensity: number[] } {
  return { mz: peaks.map((p) => p.mz), intensity: peaks.map((p) => p.intensity) };
}

export function peptideMs2(peptide: string, scan = 1042): InlineSpectrum {
  const peaks = fragmentIons(peptide);
  const { mz, intensity } = fromPeaks(peaks);
  const preMz = precursorMz(peptide, 2);
  return {
    defaultArrayLength: mz.length,
    mz,
    intensity,
    id: `scan=${scan} (${peptide}, 2+)`,
    params: [
      val("MS:1000511", 2), // ms level
      flag("MS:1000130"), // positive scan
      flag("MS:1000127"), // centroid spectrum
    ],
    scans: [{ params: [val("MS:1000016", round2(24.71 + (scan - 1042) * 0.37), "UO:0000031")] }], // scan start time (min)
    precursors: [
      {
        isolationWindow: { params: [val("MS:1000827", preMz), val("MS:1000828", 1.0), val("MS:1000829", 1.0)] },
        selectedIons: [{ params: [val("MS:1000744", preMz), val("MS:1000041", 2)] }],
        activation: { params: [flag("MS:1000422"), val("MS:1000045", 28, "UO:0000266")] }, // HCD, 28 eV
      },
    ],
  };
}

export function smallMoleculeMs1(): InlineSpectrum {
  const peaks = [
    ...isotopeEnvelope(522.3558, 1, 5, 1e5),
    ...isotopeEnvelope(746.1234, 1, 4, 4.2e4),
    ...isotopeEnvelope(301.1411, 1, 3, 2.6e4),
  ].sort((a, b) => a.mz - b.mz);
  const { mz, intensity } = fromPeaks(peaks);
  return {
    defaultArrayLength: mz.length,
    mz,
    intensity,
    id: "scan=88",
    params: [val("MS:1000511", 1), flag("MS:1000130"), flag("MS:1000127")],
    scans: [{ params: [val("MS:1000016", 3.42, "UO:0000031")] }],
  };
}

/** A synthetic profile-style MS¹ scan with `n` peaks (seeded → deterministic). */
function randomSpectrum(n: number): InlineSpectrum {
  let seed = (0x2545f491 ^ (n * 2654435761)) & 0x7fffffff;
  const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const peaks: Peak[] = [];
  for (let i = 0; i < n; i++) {
    const mz = 150 + rnd() * 1850;
    const intensity = Math.pow(rnd(), 3) * 1e6 + 100; // skewed: many small, few tall
    peaks.push({ mz, intensity });
  }
  peaks.sort((a, b) => a.mz - b.mz);
  const { mz, intensity } = fromPeaks(peaks);
  return {
    defaultArrayLength: n,
    mz,
    intensity,
    id: `scan=${n}`,
    params: [val("MS:1000511", 1), flag("MS:1000130"), flag("MS:1000127")],
    scans: [{ params: [val("MS:1000016", 12.5, "UO:0000031")] }],
  };
}

/** A dense centroided top-down MS² scan with an intact, highly charged precursor. */
function topDownMs2(): InlineSpectrum {
  const base = randomSpectrum(320);
  const mz = Array.from(base.mz as number[]);
  const intensity = Array.from(base.intensity as number[]);
  const precursor = 1029.5832;
  const charge = mz.map((m, i) => 1 + ((Math.floor(m) + i * 3) % 8));
  return {
    ...base,
    mz,
    intensity,
    charge,
    id: "scan=2201 (intact protein, 12+)",
    params: [val("MS:1000511", 2), flag("MS:1000130"), flag("MS:1000127")],
    scans: [{ params: [val("MS:1000016", 45.18, "UO:0000031")] }],
    precursors: [
      {
        isolationWindow: { params: [val("MS:1000827", precursor), val("MS:1000828", 2), val("MS:1000829", 2)] },
        selectedIons: [{ params: [val("MS:1000744", precursor), val("MS:1000041", 12)] }],
        activation: { params: [flag("MS:1000422"), val("MS:1000045", 35, "UO:0000266")] },
      },
    ],
  };
}

/** Per-peak inverse reduced ion mobility alongside a centroided MS² scan. */
function ionMobilityMs2(): InlineSpectrum {
  const base = randomSpectrum(180);
  const mz = Array.from(base.mz as number[]);
  const intensity = Array.from(base.intensity as number[]);
  const ionMobility = mz.map((m, i) => 0.68 + ((m - 150) / 1850) * 0.55 + Math.sin(i * 0.71) * 0.012);
  const precursor = 687.8421;
  return {
    ...base,
    mz,
    intensity,
    extraArrays: {
      [ArrayAccession.RAW_INVERSE_REDUCED_ION_MOBILITY]: ionMobility,
    },
    id: "frame=412 scan=37",
    params: [val("MS:1000511", 2), flag("MS:1000130"), flag("MS:1000127")],
    scans: [{ params: [val("MS:1000016", 18.73, "UO:0000031")] }],
    precursors: [
      {
        isolationWindow: { params: [val("MS:1000827", precursor), val("MS:1000828", 0.7), val("MS:1000829", 0.7)] },
        selectedIons: [{ params: [val("MS:1000744", precursor), val("MS:1000041", 2)] }],
        activation: { params: [flag("MS:1000422"), val("MS:1000045", 30, "UO:0000266")] },
      },
    ],
  };
}

/** A spectrum carrying standard and free-text auxiliary arrays for every peak. */
function auxiliaryArraySpectrum(): InlineSpectrum {
  const base = randomSpectrum(120);
  const intensity = Array.from(base.intensity as number[]);
  return {
    ...base,
    id: "scan=731 (auxiliary arrays)",
    extraArrays: {
      "MS:1000517": new Float64Array(intensity.map((v, i) => v / (900 + (i % 11) * 85))),
      local_baseline: new Float32Array(intensity.map((_, i) => 600 + 240 * Math.sin(i * 0.19) ** 2)),
      peak_flags: new Int32Array(intensity.map((v, i) => (v > 500000 ? 2 : i % 9 === 0 ? 1 : 0))),
    },
  };
}

export const EXAMPLES: Record<string, () => InlineSpectrum> = {
  ms2: () => peptideMs2("PEPTIDER"),
  ms1: smallMoleculeMs1,
  topdown: topDownMs2,
  mobility: ionMobilityMs2,
  aux: auxiliaryArraySpectrum,
  r100: () => randomSpectrum(100),
  r500: () => randomSpectrum(500),
};
