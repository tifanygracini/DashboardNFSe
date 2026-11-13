"""Aplicação web do NFS-e (FastAPI). Rodar:  uvicorn nfse.web.asgi:app

Variáveis de ambiente (App Settings no Azure):
  NFSE_DATABASE_URL     papel nfse_leitura (lê nfse.notas e as views de acesso do schema iam)
  CNPJ_EMPRESA          como no robô
  SESSION_SECRET        assina o CSRF deste sistema (32+ caracteres)
  PORTAL_URL            https://portal.informecontabil.com
  INFORME_COOKIE_DOMAIN .informecontabil.com
  DATABASE_URL          opcional: banco do schema iam, se for outro (padrão: NFSE_DATABASE_URL)
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import plotly
from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from informe_auth import Banco, Identidade, Usuario, carregar_config
from nfse.config.settings import ConfigError, Settings, get_settings
from nfse.data.database import ERROS_BANCO, BancoIndisponivel, DestinoBanco
from nfse.ui.dashboard.marca import Marca, carregar_marca

from . import painel

PASTA = Path(__file__).resolve().parent
PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
log = logging.getLogger("nfse.web")

# o Plotly injeta um <style> próprio; só a página do painel libera estilo inline (scripts continuam só 'self')
CSP_PAINEL = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
              "form-action 'self'; frame-ancestors 'none'; base-uri 'self'")


def _cnpj(c: str) -> str:
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else c


def criar_app(settings: Settings | None = None, identidade: Identidade | None = None,
              marca: Marca | None = None, abrir_banco_acesso: bool = True) -> FastAPI:
    settings = settings or get_settings()
    if identidade is None:
        if not os.environ.get("DATABASE_URL") and settings.database_url:
            os.environ["DATABASE_URL"] = settings.database_url.revelar()
        config = carregar_config("nfse")
        identidade = Identidade(config, Banco(config.database_url, max_size=3), pasta_templates=PASTA / "templates")
    marca = marca or carregar_marca()
    cache = painel.CacheNotas(DestinoBanco(settings.banco, settings.database_url))

    @asynccontextmanager
    async def ciclo(app: FastAPI):
        if abrir_banco_acesso:
            identidade.banco.abrir()
        yield
        if abrir_banco_acesso:
            identidade.banco.fechar()

    app = FastAPI(title="NFS-e · Informe", lifespan=ciclo, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.identidade = identidade
    identidade.montar(app)
    app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")
    ver = identidade.exige("nfse:ver")
    exportar = identidade.exige("nfse:exportar")

    def carregar(request: Request) -> tuple:
        try:
            return cache.obter(), None
        except BancoIndisponivel as e:
            return None, str(e)
        except ERROS_BANCO as e:
            log.exception("erro ao ler o banco de notas")
            return None, f"Erro ao ler o banco de notas: {str(e).strip().splitlines()[0]}"

    @app.get("/saude", include_in_schema=False)
    def saude():
        return {"ok": True}

    @app.get("/_vendor/plotly.min.js", include_in_schema=False)
    def plotly_js():
        return FileResponse(PLOTLY_JS, media_type="text/javascript",
                            headers={"Cache-Control": "public, max-age=604800"})

    @app.get("/", response_class=HTMLResponse)
    def inicio(request: Request, usuario: Usuario = Depends(ver),
               de: str = "", ate: str = "", tipo: list[str] | None = Query(None),
               busca: str = "", pagina: int = 1):
        ctx = {"titulo": "NFS-e", "subtitulo": f"Notas fiscais de serviço · CNPJ {_cnpj(settings.cnpj_empresa)}",
               "pode_exportar": usuario.pode("nfse:exportar")}
        dados, erro = carregar(request)
        if erro:
            ctx["erro"] = erro
        elif dados.empty:
            ctx["erro"] = "O banco está vazio. Rode nfse-baixar ou nfse-importar no computador do escritório."
        else:
            f = painel.ler_filtros(dados, de, ate, tipo, busca, pagina)
            ctx.update(painel.montar(dados, f, marca), filtros=f)
        resp = identidade.render(request, "painel.html", ctx, status_code=503 if erro else 200)
        resp.headers["Content-Security-Policy"] = CSP_PAINEL
        return resp

    @app.get("/exportar.csv")
    def exportar_csv(request: Request, usuario: Usuario = Depends(exportar),
                     de: str = "", ate: str = "", tipo: list[str] | None = Query(None),
                     busca: str = ""):
        dados, erro = carregar(request)
        if erro or dados.empty:
            return Response(erro or "Sem notas.", status_code=503, media_type="text/plain; charset=utf-8")
        f = painel.ler_filtros(dados, de, ate, tipo, busca)
        conteudo = painel.csv_exportacao(dados, f)
        try:
            identidade.registrar(request, usuario, "nfse_exportou", alvo=f"{f.de}..{f.ate}",
                                 detalhe={"tipos": f.tipos, "busca": f.busca})
        except Exception:  # auditoria não pode impedir o download
            log.exception("falha ao registrar exportação")
        nome = f"nfse_{f.de}_a_{f.ate}.csv".replace("/", "-")
        return Response(conteudo, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    return app


def criar_app_do_ambiente() -> FastAPI:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    try:
        return criar_app()
    except ConfigError as e:
        raise SystemExit(f"Configuração inválida: {e}") from e
