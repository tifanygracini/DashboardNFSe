from datetime import datetime

import pytest

from src.nfse.data import EstadoAdn, EstadoCorrompido, EstadoRepository, XmlStorage
from src.nfse.ui.dashboard.formatters import brl, percentual


def test_estado_ida_e_volta(tmp_path):
    repo = EstadoRepository(tmp_path / "sub" / "estado.json")
    assert repo.ler() == EstadoAdn()
    est = EstadoAdn(42, datetime(2026, 11, 3, 8, 0, 0))
    repo.gravar(est)
    assert repo.ler() == est


def test_estado_corrompido(tmp_path):
    arq = tmp_path / "estado.json"
    arq.write_text("{", encoding="utf-8")
    with pytest.raises(EstadoCorrompido):
        EstadoRepository(arq).ler()


def test_storage_nao_sobrescreve_e_bloqueia_caminho(tmp_path):
    st = XmlStorage(tmp_path)
    assert st.gravar("2026-07", "a-nfse.xml", b"<a/>") is True
    assert st.gravar("2026-07", "a-nfse.xml", b"<b/>") is False
    assert (tmp_path / "2026-07" / "a-nfse.xml").read_bytes() == b"<a/>"
    with pytest.raises(ValueError):
        st.gravar("..", "x.xml", b"")
    with pytest.raises(ValueError):
        st.gravar("2026-07", "../x.xml", b"")


def test_formatters():
    assert brl(1234.5) == "R$ 1.234,50"
    assert percentual(3) == "3,00%"
