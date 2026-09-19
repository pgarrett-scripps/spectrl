import type { OperationOption } from "./pipeline.js"
import type { NumArray } from "./codecs.js"
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
  userParams?: UserParam[];
}

export interface Scan extends ContextFields {
  params: CvParam[];
  userParams?: UserParam[];
  windows?: ScanWindow[];
}

export interface IsolationWindow {
  params: CvParam[];
  userParams?: UserParam[];
}

export interface SelectedIon {
  params: CvParam[];
  userParams?: UserParam[];
}

export interface Activation {
  params: CvParam[];
  userParams?: UserParam[];
}

export interface Precursor extends ContextFields {
  isolationWindow?: IsolationWindow | null;
  selectedIons?: SelectedIon[];
  activation?: Activation | null;
}

export interface Product {
  isolationWindow?: IsolationWindow | null;
}

export interface ArrayEncoding {
  encoding?: OperationOption
}
export type ArrayEncodingOption = OperationOption | ArrayEncoding

/** Input to {@link encodeSpectrum}. Mirrors an mzML <spectrum>. */
export interface InlineSpectrum extends ContextFields, ArrayMetadata {
  defaultArrayLength: number;
  mz?: NumArray | number[] | null;
  intensity?: NumArray | number[] | null;
  charge?: NumArray | number[] | null;
  id?: string | null;
  params?: CvParam[];
  scans?: Scan[];
  scanCombination?: CvParam | null;
  precursors?: Precursor[];
  products?: Product[];
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
export interface DecodedSpectrum extends ContextFields, ArrayMetadata {
  defaultArrayLength: number;
  mz: NumArray | null;
  intensity: NumArray | null;
  charge: NumArray | null;
  id: string | null;
  params: CvParam[];
  scans: Scan[];
  scanCombination: CvParam | null;
  precursors: Precursor[];
  products: Product[];
  /** Decoded spectrum-level free-text user parameters. */
  userParams: UserParam[];
  /** Decoded additional per-peak arrays, keyed by CV accession or non-standard name. */
  extraArrays: Record<string, Float64Array | Float32Array | Int32Array>;
  arrayUnits: Record<string, string>;
  checksum: string;
  formatVersion: number;
}

export interface ContextRecord {
  params?: CvParam[]
  userParams?: UserParam[]
  id?: string
  name?: string
  version?: string
  location?: string
  externalIds?: string[]
  spectrumRef?: string
  instrument?: ContextRecord
  components?: ContextRecord[]
  kind?: "source" | "analyzer" | "detector"
  order?: number
  software?: ContextRecord
  operation?: string
  revision?: number
  parameters?: Record<string, unknown>
  sourceParams?: CvParam[]
}
export type Extensions = Record<string, { revision: number, required: boolean, data: unknown }>
export interface ContextFields {
  source?: ContextRecord | null
  acquisition?: ContextRecord | null
  processing?: ContextRecord[]
}
export interface ArrayMetadata {
  /** Optional array names, keyed by the canonical array key. */
  arrayNames?: Record<string, string>
  arrayParams?: Record<string, CvParam[]>
  arrayUserParams?: Record<string, UserParam[]>
  arrayProcessing?: Record<string, ContextRecord[]>
  arrayExtensions?: Record<string, Extensions>
  extensions?: Extensions
}
