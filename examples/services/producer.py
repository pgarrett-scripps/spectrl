"""Run with: uvicorn producer:app --host 127.0.0.1 --port 8000."""

from fastapi import FastAPI, HTTPException

from spectrl import InlineSpectrum, SpectrlCvParam, encode_spectrum

app = FastAPI()
MAX_TOKEN_BYTES = 256 * 1024


@app.get("/spectra/{spectrum_id}")
def spectrum(spectrum_id: str) -> dict[str, str]:
    """Replace this example lookup with the service's spectrum store."""
    if spectrum_id != "example":
        raise HTTPException(status_code=404, detail="Spectrum not found")
    source = InlineSpectrum(
        default_array_length=3,
        mz=[300.123456, 100.123456, 200.123456],
        intensity=[30, 10, 20],
        id=spectrum_id,
        params=[SpectrlCvParam(accession="MS:1000511", value=2)],
    )
    try:
        token = encode_spectrum(source, lossless=True, max_len=MAX_TOKEN_BYTES)
    except OverflowError as exc:
        raise HTTPException(status_code=422, detail="Spectrum exceeds the token budget") from exc
    return {"token": token, "precision": "lossless"}
