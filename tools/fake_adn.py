"""Simulador do ADN para treinar sem certificado.

    python fake_adn.py --xmls C:\\caminho\\notas-exemplo\\notas

Serve GET /contribuintes/DFe/{nsu}?cnpjConsulta=... em http://127.0.0.1:8787, com até 50
documentos por chamada, na ordem alfabética dos arquivos (NSU 1, 2, 3...). Mostra cada pedido.
"""
import argparse
import base64
import gzip
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

TAMANHO_LOTE = 50
DOCUMENTOS = []


def local(tag):
    return tag.rsplit("}", 1)[-1]


def carregar(pasta):
    for i, arq in enumerate(sorted(Path(pasta).rglob("*.xml")), start=1):
        bruto = arq.read_bytes()
        raiz = ET.fromstring(bruto)
        chave, tipo, tipo_evento = "", "NFSE", None
        for el in raiz.iter():
            nome = local(el.tag)
            if nome == "infNFSe" and el.get("Id"):
                chave = re.sub(r"\D", "", el.get("Id") or "")
            elif nome == "chNFSe" and el.text:
                chave, tipo = el.text.strip(), "EVENTO"
            elif re.fullmatch(r"e\d{6}", nome):
                tipo, tipo_evento = "EVENTO", nome[1:]
        DOCUMENTOS.append({
            "NSU": i, "ChaveAcesso": chave, "TipoDocumento": tipo, "TipoEvento": tipo_evento,
            "ArquivoXml": base64.b64encode(gzip.compress(bruto)).decode(),
            "DataHoraGeracao": datetime.now().isoformat(timespec="seconds"),
        })
    return len(DOCUMENTOS)


class Handler(BaseHTTPRequestHandler):
    def responder(self, codigo, corpo):
        dados = json.dumps(corpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        url = urlparse(self.path)
        m = re.fullmatch(r"/contribuintes/DFe/(\d+)", url.path)
        cnpj = parse_qs(url.query).get("cnpjConsulta", [""])[0]
        print(f"[{datetime.now():%H:%M:%S}] GET {self.path}")
        if not m:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            print("   -> 404 (caminho desconhecido; o certo é /contribuintes/DFe/{nsu})")
            return
        nsu = int(m.group(1))
        lote = [d for d in DOCUMENTOS if d["NSU"] > nsu][:TAMANHO_LOTE]
        agora = datetime.now().isoformat(timespec="seconds")
        if not lote:
            print("   -> 404 NENHUM_DOCUMENTO_LOCALIZADO")
            self.responder(404, {"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO", "LoteDFe": [],
                                 "Alertas": [], "Erros": [], "DataHoraProcessamento": agora})
            return
        print(f"   -> 200, {len(lote)} documentos (NSU {lote[0]['NSU']} a {lote[-1]['NSU']}) para o CNPJ {cnpj}")
        self.responder(200, {"StatusProcessamento": "DOCUMENTOS_LOCALIZADOS", "LoteDFe": lote,
                             "Alertas": [], "Erros": [], "DataHoraProcessamento": agora})

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--xmls", required=True, help="pasta com os XMLs de exemplo")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    total = carregar(a.xmls)
    print(f"Simulador do ADN com {total} documentos em http://{a.host}:{a.port}  (Ctrl+C para parar)")
    HTTPServer((a.host, a.port), Handler).serve_forever()
