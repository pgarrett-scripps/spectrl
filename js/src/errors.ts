/** spectrl error types. */

/** Base class for all spectrl errors. */
export class SpectrlError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/** A token could not be decoded: malformed, corrupted, or unsupported. */
export class SpectrlDecodeError extends SpectrlError {}
