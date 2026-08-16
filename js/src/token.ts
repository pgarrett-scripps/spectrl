/** spectrl magic + format version.
 *
 * A spectrl2 token is `spectrl2.<base64url(cbor_document)>[.<hash>]`: a single
 * CBOR document (header + array blobs embedded as byte strings) with an
 * optional trailing integrity hash; see cbor_format.
 */

export { FORMAT_VERSION, MAGIC } from "./format.js";
