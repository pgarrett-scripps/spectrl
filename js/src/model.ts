/** Data models for spectrl encode input and decode output. Mirrors the Python reference impl. */

/** A CV parameter, mirroring mzML cvParam semantics.
 * `accession`/`unitAccession` use `ONTOLOGY:NNNNNNN` form (e.g. `MS:1000511`).
 * A `null`/`undefined` value indicates a flag parameter (presence is the meaning). */
export interface CvParam {
  accession: string;
  value?: number | string | null;
  unitAccession?: string | null;
}

/** A free-text user parameter (mzML userParam) with no CV accession. */
export interface UserParam {
  name: string;
  value?: string | number | null;
  /** XSD type annotation, e.g. "xsd:float". */
  type?: string | null;
  unitAccession?: string | null;
}

export interface ScanWindow {
  params: CvParam[];
}

export interface Scan {
  params: CvParam[];
  windows?: ScanWindow[];
  userParams?: UserParam[];
}

export interface IsolationWindow {
  params: CvParam[];
}

export interface SelectedIon {
  params: CvParam[];
}

export interface Activation {
  params: CvParam[];
}

export interface Precursor {
  isolationWindow?: IsolationWindow | null;
  selectedIons?: SelectedIon[];
  activation?: Activation | null;
}

export interface Product {
  isolationWindow?: IsolationWindow | null;
}

export type ArrayCodec =
  | "auto"
  | "zlib"
  | "zstd"
  | "byte-shuffled-zstd"
  | "numlin-zlib"
  | "numlin-zstd"
  | "numslof-zlib"
  | "numslof-zstd"
  | "numpic-zlib"
  | "numpic-zstd"
  | `MS:${string}`;

export interface ArrayEncoding {
  codec?: ArrayCodec | number;
  fixedPoint?: number;
}

export type ArrayEncodingOption = ArrayCodec | number | ArrayEncoding;

/** Input to {@link encodeSpectrum}. Mirrors an mzML <spectrum>. */
export interface InlineSpectrum {
  defaultArrayLength: number;
  mz?: Float64Array | number[] | null;
  intensity?: Float64Array | number[] | null;
  charge?: Float64Array | number[] | null;
  id?: string | null;
  params?: CvParam[];
  scans?: Scan[];
  scanCombination?: CvParam | null;
  precursors?: Precursor[];
  products?: Product[];
  interp?: string | null;
  /** Spectrum-level free-text user parameters (mzML userParam). */
  userParams?: UserParam[];
  /** Additional per-peak arrays, including every ion-mobility variant, keyed by
   * PSI-MS accession or a free-text name for non-standard arrays.
   * Int32Array/Float32Array preserve their declared mzML data type; anything
   * else is encoded as float64. */
  extraArrays?: Record<string, Float64Array | Float32Array | Int32Array | number[]>;
  /** Optional CV units keyed like core or extra arrays. */
  arrayUnits?: Record<string, string>;
}

/** Output from {@link decodeToken}. */
export interface DecodedSpectrum {
  defaultArrayLength: number;
  mz: Float64Array | null;
  intensity: Float64Array | null;
  charge: Float64Array | null;
  id: string | null;
  params: CvParam[];
  scans: Scan[];
  scanCombination: CvParam | null;
  precursors: Precursor[];
  products: Product[];
  interp: string | null;
  /** Decoded spectrum-level free-text user parameters. */
  userParams: UserParam[];
  /** Decoded additional per-peak arrays, keyed by CV accession or non-standard name. */
  extraArrays: Record<string, Float64Array | Float32Array | Int32Array>;
  arrayUnits: Record<string, string>;
  checksum: string;
  formatVersion: number;
}
