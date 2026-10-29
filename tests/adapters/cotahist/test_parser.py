"""Parser do COTAHIST — layout de largura fixa, fator de cotação e erros com número da linha."""

import zipfile
from datetime import date
from pathlib import Path

import pytest

from options_engine.adapters.outbound.cotahist.errors import CotahistFormatError
from options_engine.adapters.outbound.cotahist.parser import (
    MARKET_CALL,
    MARKET_SPOT,
    RECORD_LENGTH,
    cotahist_sessions,
    iter_cotahist,
    parse_cotahist,
)
from tests._tolerances import ABS_SELF_FLOOR, REL_SELF, assert_close
from tests.adapters.cotahist._layout import arquivo, header, registro, trailer

PREGAO = date(2026, 10, 23)


def _spot(**overrides: object) -> str:
    campos: dict[str, object] = {
        "pregao": PREGAO,
        "simbolo": "PETR4",
        "mercado": MARKET_SPOT,
        "especificacao": "PN N2",
        "ultimo": 30.00,
        "oferta_compra": 29.99,
        "oferta_venda": 30.01,
        "negocios": 5000,
        "quantidade": 1_000_000,
        "volume": 30_000_000.00,
    }
    campos.update(overrides)
    return registro(**campos)  # type: ignore[arg-type]  # justificativa: kwargs de teste montados à mão


def _call(**overrides: object) -> str:
    campos: dict[str, object] = {
        "pregao": PREGAO,
        "simbolo": "PETRK300",
        "mercado": MARKET_CALL,
        "especificacao": "PN",
        "ultimo": 0.85,
        "oferta_compra": 0.84,
        "oferta_venda": 0.86,
        "negocios": 37,
        "quantidade": 3700,
        "volume": 3145.00,
        "strike": 30.00,
        "vencimento": date(2026, 11, 19),
    }
    campos.update(overrides)
    return registro(**campos)  # type: ignore[arg-type]  # justificativa: idem


def _gravar(tmp_path: Path, conteudo: str, nome: str = "COTAHIST.TXT") -> Path:
    caminho = tmp_path / nome
    caminho.write_bytes(conteudo.encode("cp1252"))
    return caminho


def test_registros_de_spot_e_opcao_em_unidades_finais(tmp_path: Path) -> None:
    caminho = _gravar(tmp_path, arquivo([_spot(), _call()], geracao=PREGAO, ano=2026))
    spot, call = parse_cotahist(caminho)
    assert (spot.symbol, spot.market, spot.session) == ("PETR4", MARKET_SPOT, PREGAO)
    assert spot.specification == "PN N2"
    assert_close(spot.last, 30.00, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="PREULT")
    assert_close(spot.best_bid, 29.99, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="PREOFC")
    assert_close(spot.volume, 30_000_000.0, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="VOLTOT")
    assert spot.expiry == date(9999, 12, 31)
    assert (call.symbol, call.market, call.trades, call.quantity) == ("PETRK300", 70, 37, 3700)
    assert_close(call.strike, 30.00, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="PREEXE")
    assert call.expiry == date(2026, 11, 19)
    assert call.strike_correction == 0


def test_fator_de_cotacao_divide_todos_os_precos_mas_nao_o_volume(tmp_path: Path) -> None:
    """FATCOT = 1000: a B3 grava o preço de 1000 unidades; o parser devolve o unitário."""
    linha = _call(fator=1000, ultimo=0.85, oferta_compra=0.84, strike=30.0, volume=3145.0)
    assert linha[110:121] == "00000085000"  # 0,85 x 1000 = 850,00 gravado
    (call,) = parse_cotahist(_gravar(tmp_path, arquivo([linha], geracao=PREGAO, ano=2026)))
    assert call.quote_factor == 1000
    assert_close(call.last, 0.85, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="PREULT/FATCOT")
    assert_close(call.best_bid, 0.84, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="PREOFC/FATCOT")
    assert_close(call.strike, 30.0, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="PREEXE/FATCOT")
    assert_close(call.volume, 3145.0, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="VOLTOT intacto")


def test_zero_da_fonte_segue_zero_no_parser(tmp_path: Path) -> None:
    """A tradução zero -> None é da montagem da cadeia (ADR-0003), não do parser."""
    linha = _call(oferta_compra=0.0, oferta_venda=0.0, ultimo=0.0)
    (call,) = parse_cotahist(_gravar(tmp_path, arquivo([linha], geracao=PREGAO, ano=2026)))
    assert (call.best_bid, call.best_ask, call.last) == (0.0, 0.0, 0.0)


def test_mercados_fora_do_painel_sao_descartados(tmp_path: Path) -> None:
    termo = registro(pregao=PREGAO, simbolo="PETR4T", mercado=30, ultimo=30.5)
    caminho = _gravar(tmp_path, arquivo([termo, _spot()], geracao=PREGAO, ano=2026))
    assert [r.symbol for r in parse_cotahist(caminho)] == ["PETR4"]


@pytest.mark.parametrize("fim_de_linha", ["\r\n", "\n"], ids=["crlf", "lf"])
def test_aceita_crlf_e_lf(tmp_path: Path, fim_de_linha: str) -> None:
    conteudo = arquivo([_spot()], geracao=PREGAO, ano=2026, fim_de_linha=fim_de_linha)
    assert len(parse_cotahist(_gravar(tmp_path, conteudo))) == 1


def test_le_zip_com_um_membro_txt(tmp_path: Path) -> None:
    zip_path = tmp_path / "COTAHIST_D23102026.ZIP"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("COTAHIST_D23102026.TXT", arquivo([_spot()], geracao=PREGAO, ano=2026))
    assert [r.symbol for r in parse_cotahist(zip_path)] == ["PETR4"]


def test_em_fluxo_so_o_escolhido_vira_registro_mas_o_arquivo_todo_e_validado(
    tmp_path: Path,
) -> None:
    outro = date(2026, 10, 22)
    linhas = [_spot(pregao=outro), _call(pregao=outro), _spot(), _call()]
    caminho = _gravar(tmp_path, arquivo(linhas, geracao=PREGAO, ano=2026))
    escolhidos = list(iter_cotahist(caminho, lambda pregao, _mercado: pregao == PREGAO))
    assert [(r.symbol, r.session) for r in escolhidos] == [("PETR4", PREGAO), ("PETRK300", PREGAO)]
    ruim = _call(pregao=outro)
    ruim = ruim[:147] + "00X37" + ruim[152:]
    caminho = _gravar(tmp_path, arquivo([ruim, _spot()], geracao=PREGAO, ano=2026))
    with pytest.raises(CotahistFormatError, match=r"linha 2: campo TOTNEG"):
        list(iter_cotahist(caminho, lambda pregao, _mercado: pregao == PREGAO))


def test_pregoes_do_arquivo_saem_sem_guardar_registros(tmp_path: Path) -> None:
    outro = date(2026, 10, 22)
    caminho = _gravar(tmp_path, arquivo([_spot(pregao=outro), _call()], geracao=PREGAO, ano=2026))
    assert cotahist_sessions(caminho) == frozenset({outro, PREGAO})
    termo = registro(pregao=PREGAO, simbolo="PETR4T", mercado=30, ultimo=30.5)
    assert cotahist_sessions(_gravar(tmp_path, arquivo([termo], geracao=PREGAO, ano=2026))) == (
        frozenset()
    )


def test_zip_com_dado_corrompido_vira_erro_de_formato(tmp_path: Path) -> None:
    zip_path = tmp_path / "COTAHIST_D23102026.ZIP"
    conteudo = arquivo([_spot(), _call()] * 50, geracao=PREGAO, ano=2026)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("COTAHIST_D23102026.TXT", conteudo)
    bruto = bytearray(zip_path.read_bytes())
    bruto[len(bruto) // 2] ^= 0xFF
    zip_path.write_bytes(bytes(bruto))
    with pytest.raises(CotahistFormatError):
        parse_cotahist(zip_path)


def test_zip_com_mais_de_um_txt_e_rejeitado(tmp_path: Path) -> None:
    zip_path = tmp_path / "dois.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("A.TXT", arquivo([_spot()], geracao=PREGAO, ano=2026))
        zf.writestr("B.TXT", arquivo([_spot()], geracao=PREGAO, ano=2026))
    with pytest.raises(CotahistFormatError, match="exatamente um membro"):
        parse_cotahist(zip_path)


# ---------------------------------------------------------------------------
# Erros de layout: sempre com caminho e número da linha
# ---------------------------------------------------------------------------


def test_linha_com_tamanho_errado_aponta_a_linha(tmp_path: Path) -> None:
    curta = _call()[:-1]
    conteudo = "\r\n".join([header(PREGAO, 2026), _spot(), curta, trailer(PREGAO, 2026, 2)])
    caminho = _gravar(tmp_path, conteudo + "\r\n")
    with pytest.raises(CotahistFormatError, match=r"linha 3: registro com 244") as erro:
        parse_cotahist(caminho)
    assert erro.value.line == 3
    assert erro.value.path == caminho
    assert str(caminho) in str(erro.value)


def test_arquivo_truncado_sem_trailer(tmp_path: Path) -> None:
    conteudo = "\r\n".join([header(PREGAO, 2026), _spot(), _call()]) + "\r\n"
    with pytest.raises(CotahistFormatError, match=r"linha 3: arquivo truncado"):
        parse_cotahist(_gravar(tmp_path, conteudo))


def test_trailer_com_total_divergente(tmp_path: Path) -> None:
    conteudo = "\r\n".join([header(PREGAO, 2026), _spot(), trailer(PREGAO, 2026, 5)]) + "\r\n"
    with pytest.raises(CotahistFormatError, match=r"linha 3: trailer declara 5 registros"):
        parse_cotahist(_gravar(tmp_path, conteudo))


def test_totreg_conta_so_os_registros_01_como_no_arquivo_real(tmp_path: Path) -> None:
    """O layout escrito diz que o TOTREG conta header e trailer; os arquivos reais não contam."""
    so_os_01 = "\r\n".join([header(PREGAO, 2026), _spot(), _call(), trailer(PREGAO, 2026, 2)])
    assert len(parse_cotahist(_gravar(tmp_path, so_os_01 + "\r\n"))) == 2
    como_no_layout = so_os_01[:-RECORD_LENGTH] + trailer(PREGAO, 2026, 4)
    with pytest.raises(CotahistFormatError, match=r"declara 4 registros; o arquivo tem 2"):
        parse_cotahist(_gravar(tmp_path, como_no_layout + "\r\n"))


def test_header_ausente(tmp_path: Path) -> None:
    conteudo = "\r\n".join([_spot(), trailer(PREGAO, 2026, 2)]) + "\r\n"
    with pytest.raises(CotahistFormatError, match=r"linha 1: header ausente"):
        parse_cotahist(_gravar(tmp_path, conteudo))


def test_campo_numerico_invalido_aponta_campo_e_linha(tmp_path: Path) -> None:
    linha = _call()
    corrompida = linha[:147] + "00X37" + linha[152:]  # TOTNEG 148-152
    assert len(corrompida) == RECORD_LENGTH
    conteudo = arquivo([_spot(), corrompida], geracao=PREGAO, ano=2026)
    with pytest.raises(CotahistFormatError, match=r"linha 3: campo TOTNEG"):
        parse_cotahist(_gravar(tmp_path, conteudo))


def test_digito_unicode_nao_passa_por_numero(tmp_path: Path) -> None:
    """``"²".isdigit()`` é True, mas ``int("²")`` falha: o parser tem de recusar antes."""
    linha = _call()
    corrompida = linha[:147] + "0003²" + linha[152:]
    conteudo = arquivo([corrompida], geracao=PREGAO, ano=2026)
    with pytest.raises(CotahistFormatError, match="TOTNEG"):
        parse_cotahist(_gravar(tmp_path, conteudo))


def test_data_invalida(tmp_path: Path) -> None:
    linha = _call()
    corrompida = linha[:202] + "20261332" + linha[210:]  # DATVEN 203-210, mês 13
    conteudo = arquivo([corrompida], geracao=PREGAO, ano=2026)
    with pytest.raises(CotahistFormatError, match=r"linha 2: campo DATVEN"):
        parse_cotahist(_gravar(tmp_path, conteudo))


def test_fatcot_zero(tmp_path: Path) -> None:
    linha = _call()
    corrompida = linha[:210] + "0000000" + linha[217:]
    with pytest.raises(CotahistFormatError, match="FATCOT zero"):
        parse_cotahist(_gravar(tmp_path, arquivo([corrompida], geracao=PREGAO, ano=2026)))


def test_tipo_de_registro_inesperado(tmp_path: Path) -> None:
    estranho = "02" + _spot()[2:]
    with pytest.raises(CotahistFormatError, match=r"linha 2: tipo de registro inesperado"):
        parse_cotahist(_gravar(tmp_path, arquivo([estranho], geracao=PREGAO, ano=2026)))


def test_arquivo_vazio(tmp_path: Path) -> None:
    with pytest.raises(CotahistFormatError, match="vazio"):
        parse_cotahist(_gravar(tmp_path, ""))


def test_bytes_fora_do_cp1252(tmp_path: Path) -> None:
    caminho = tmp_path / "ruim.TXT"
    caminho.write_bytes(b"\x81" * RECORD_LENGTH)
    with pytest.raises(CotahistFormatError, match=r"linha 1: bytes fora do cp1252"):
        parse_cotahist(caminho)


def _com_nome_em_utf8(tmp_path: Path, nome: str) -> Path:
    """Como no anual de 2026 real: um nome gravado em UTF-8 no meio do arquivo cp1252."""
    em_utf8 = _spot(nome=nome).encode("utf-8")
    partes = [header(PREGAO, 2026).encode("cp1252"), _call().encode("cp1252"), em_utf8]
    partes.append(trailer(PREGAO, 2026, 2).encode("cp1252"))
    caminho = tmp_path / "COTAHIST_A2026.TXT"
    caminho.write_bytes(b"\r\n".join(partes) + b"\r\n")
    return caminho


@pytest.mark.parametrize("nome", ["FROTA OCEÂNI", "ÁGUAS CLARAS"])
def test_nome_em_utf8_no_arquivo_cp1252_e_lido(tmp_path: Path, nome: str) -> None:
    # "Á" em UTF-8 tem o byte 0x81, que nem existe no cp1252.
    _, spot = parse_cotahist(_com_nome_em_utf8(tmp_path, nome))
    assert (spot.symbol, spot.short_name) == ("PETR4", nome)


def test_linha_que_nem_em_utf8_fecha_o_layout_segue_recusada(tmp_path: Path) -> None:
    caminho = tmp_path / "COTAHIST.TXT"
    longa = _spot().encode("cp1252") + "Â".encode()
    corpo = [header(PREGAO, 2026).encode("cp1252"), longa, trailer(PREGAO, 2026, 1).encode()]
    caminho.write_bytes(b"\r\n".join(corpo) + b"\r\n")
    with pytest.raises(CotahistFormatError, match=r"linha 2: registro com 247 caracteres"):
        parse_cotahist(caminho)


def test_zip_corrompido(tmp_path: Path) -> None:
    caminho = tmp_path / "corrompido.zip"
    caminho.write_bytes(b"PK\x03\x04" + b"\x00" * 40)
    with pytest.raises(CotahistFormatError):
        parse_cotahist(caminho)
