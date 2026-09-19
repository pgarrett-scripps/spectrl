/** Bit-preserving modular delta and byte shuffle for v3 encoding 3. */


function validate(data: Uint8Array, itemSize: number): void {
  if (itemSize !== 4 && itemSize !== 8) throw new Error("delta shuffle requires 4-byte or 8-byte words")
  if (data.length % itemSize !== 0) throw new Error("delta shuffle data length must be a multiple of the word size")
}

/** Bytewise subtraction preserves all 64 bits without converting words to Number. */
export function deltaShuffle(raw: Uint8Array, itemSize: number): Uint8Array {
  validate(raw, itemSize)
  return deltaShuffleWords(raw, itemSize)
}

export function deltaShuffleWords(raw: Uint8Array, itemSize: number): Uint8Array {
  if (![1, 2, 4, 8].includes(itemSize) || raw.length % itemSize) throw Error("invalid word dimensions")
  const n = raw.length / itemSize
  const out = new Uint8Array(raw.length)
  let i = 0
  while (i < n) {
    let borrow = 0
    let byte = 0
    while (byte < itemSize) {
      const previous = i === 0 ? 0 : raw[(i - 1) * itemSize + byte]!
      const difference = raw[i * itemSize + byte]! - previous - borrow
      out[byte * n + i] = difference & 255
      borrow = difference < 0 ? 1 : 0
      byte += 1
    }
    i += 1
  }
  return out
}

export function deltaUnshuffle(data: Uint8Array, itemSize: number): Uint8Array {
  validate(data, itemSize)
  return deltaUnshuffleWords(data, itemSize)
}

export function deltaUnshuffleWords(data: Uint8Array, itemSize: number): Uint8Array {
  if (![1, 2, 4, 8].includes(itemSize) || data.length % itemSize) throw Error("invalid word dimensions")
  const n = data.length / itemSize
  const out = new Uint8Array(data.length)
  let i = 0
  while (i < n) {
    let carry = 0
    let byte = 0
    while (byte < itemSize) {
      const previous = i === 0 ? 0 : out[(i - 1) * itemSize + byte]!
      const sum = data[byte * n + i]! + previous + carry
      out[i * itemSize + byte] = sum & 255
      carry = sum >>> 8
      byte += 1
    }
    i += 1
  }
  return out
}
