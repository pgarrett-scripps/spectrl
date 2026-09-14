/** spectrl magic + format version.
 *
 * A spectrl.v2 token is `spectrl.v2.<base64url(cbor_document)>.<checksum>`: a single
 * CBOR document (header + array blobs embedded as byte strings) with an
 * required trailing CRC-32 checksum; see cbor_format.
 */

export { FORMAT_VERSION, MAGIC } from "./format.js";
