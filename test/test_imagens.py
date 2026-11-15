from imagens import assinatura_ok


def test_png_valido():
    assert assinatura_ok(b"\x89PNG\r\n\x1a\n" + b"resto", "png")


def test_jpg_valido():
    assert assinatura_ok(b"\xff\xd8\xff\xe0resto", "jpg")


def test_webp_valido():
    assert assinatura_ok(b"RIFF1234WEBPresto", "webp")


def test_extensao_trocada_e_recusada():
    assert not assinatura_ok(b"\x89PNG\r\n\x1a\n", "jpg")


def test_html_disfarcado_e_recusado():
    assert not assinatura_ok(b"<html><script>", "png")