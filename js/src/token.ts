/** spectrl magic + format version.
 *
 * A spectrl.v3 token is `spectrl.v3.<mode>.<payload>.<checksum>`: a single
 * raw or zlib-compressed CBOR document with a
 * required trailing CRC-32 checksum. See cbor_format.
 */

export { FORMAT_VERSION, MAGIC } from "./format.js";
