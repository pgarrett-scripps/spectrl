/** CRC-32/ISO-HDLC transport checksum. */

const TABLE = new Uint32Array(256);
for (let n = 0; n < TABLE.length; n++) {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  TABLE[n] = c >>> 0;
}

/** CRC-32 of the ASCII token body as eight lowercase hexadecimal characters. */
export function tokenChecksum(body: string): string {
  let crc = 0xffffffff;
  for (let i = 0; i < body.length; i++) crc = TABLE[(crc ^ body.charCodeAt(i)) & 0xff]! ^ (crc >>> 8);
  return ((crc ^ 0xffffffff) >>> 0).toString(16).padStart(8, "0");
}
