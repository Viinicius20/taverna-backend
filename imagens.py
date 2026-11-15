TIPOS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
LIMITE_BYTES = 3 * 1024 * 1024


def assinatura_ok(dados: bytes, ext: str) -> bool:
    if ext == "jpg":
        return dados[:3] == b"\xff\xd8\xff"
    if ext == "png":
        return dados[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == "webp":
        return dados[:4] == b"RIFF" and dados[8:12] == b"WEBP"
    return False