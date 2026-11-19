"""Aplicação web do NFS-e (FastAPI). Rodar:  uvicorn nfse.web.asgi:app

Telas:
  /                         todas as empresas do escritório (filtros por regime, busca, situação, período)
  /empresa/{cnpj}           dashboard de NFS-e de uma empresa
  /exportar.csv             a lista de empresas filtrada (nfse:exportar)
  /empresa/{cnpj}/exportar.csv   as notas da empresa filtradas (nfse:exportar)

Variáveis de ambiente (App Settings no Azure):
  NFSE_DATABASE_URL     papel nfse_leitura (lê nfse.notas, nfse.empresas e as views de acesso do schema iam)
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
from nfse.domain.documentos import cnpj_valido, so_digitos
from nfse.ui.dashboard.marca import Marca, carregar_marca

from . import carteira, evolucao, painel

PASTA = Path(__file__).resolve().parent
PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
log = logging.getLogger("nfse.web")

# o Plotly injeta um <style> próprio; só as páginas com gráfico liberam estilo inline (scripts continuam só 'self')
CSP_PAINEL = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
              "form-action 'self'; frame-ancestors 'none'; base-uri 'self'")


def criar_app(settings: Settings | None = None, identidade: Identidade | None = None,
              marca: Marca | None = None, abrir_banco_acesso: bool = True) -> FastAPI:
    settings = settings or get_settings()
    if identidade is None:
        if not os.environ.get("DATABASE_URL") and settings.database_url:
            os.environ["DATABASE_URL"] = settings.database_url.revelar()
        config = carregar_config("nfse")
        identidade = Identidade(config, Banco(config.database_url, max_size=3), pasta_templates=PASTA / "templates")
    marca = marca or carregar_marca()
    destino = DestinoBanco(settings.banco, settings.database_url)
    cache_notas = painel.CacheNotas(destino)
    cache_carteira = carteira.CacheCarteira(destino)

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

    def ler(funcao):
        """(dados, None) ou (None, mensagem para a tela)."""
        try:
            return funcao(), None
        except BancoIndisponivel as e:
            return None, str(e)
        except ERROS_BANCO as e:
            log.exception("erro ao ler o banco de notas")
            return None, f"Erro ao ler o banco de notas: {str(e).strip().splitlines()[0]}"

    def pagina(request, template, ctx, erro=None):
        resp = identidade.render(request, template, ctx, status_code=503 if erro else 200)
        resp.headers["Content-Security-Policy"] = CSP_PAINEL
        return resp

    def empresa_do_cadastro(cnpj: str) -> dict | None:
        dados, erro = ler(cache_carteira.obter)
        if erro or dados is None:
            return None
        linha = dados.empresas[dados.empresas["cnpj"] == cnpj]
        if not len(linha):
            return None
        return {k: (None if v is None or (isinstance(v, float) and v != v) else v)  # NaN -> None
                for k, v in linha.iloc[0].to_dict().items()}

    @app.get("/saude", include_in_schema=False)
    def saude():
        return {"ok": True}

    @app.get("/_vendor/plotly.min.js", include_in_schema=False)
    def plotly_js():
        return FileResponse(PLOTLY_JS, media_type="text/javascript",
                            headers={"Cache-Control": "public, max-age=604800"})

    # ------------------------------------------------------------ carteira
    @app.get("/", response_class=HTMLResponse)
    def inicio(request: Request, usuario: Usuario = Depends(ver), de: str = "", ate: str = "", regime: str = "",
               busca: str = "", situacao: str = "", ordem: str = "", inativas: str = "", empresa: str = "",
               pagina_: int = Query(1, alias="pagina")):
        ctx = {"titulo": "NFS-e", "pode_exportar": usuario.pode("nfse:exportar")}
        dados, erro = ler(cache_carteira.obter)
        if not erro and dados.empresas.empty:
            erro = ("Nenhuma empresa cadastrada ainda. No computador do robô, rode: nfse-empresas sincronizar "
                    "(cadastro do Acessórias) e nfse-empresas certificados.")
        if erro:
            ctx["erro"] = erro
        else:
            f = carteira.ler_filtros(dados, de, ate, regime, busca, situacao, ordem, inativas, pagina_,
                                     so_digitos(empresa))
            ctx.update(carteira.montar(dados, f, marca), filtros=f)
        return pagina(request, "carteira.html", ctx, erro)

    @app.get("/exportar.csv")
    def exportar_carteira(request: Request, usuario: Usuario = Depends(exportar), de: str = "", ate: str = "",
                          regime: str = "", busca: str = "", situacao: str = "", ordem: str = "", inativas: str = "",
                          empresa: str = ""):
        dados, erro = ler(cache_carteira.obter)
        if erro or dados.empresas.empty:
            return Response(erro or "Sem empresas.", status_code=503, media_type="text/plain; charset=utf-8")
        f = carteira.ler_filtros(dados, de, ate, regime, busca, situacao, ordem, inativas, 1, so_digitos(empresa))
        conteudo = carteira.csv_carteira(dados, f)
        _auditar(request, usuario, "nfse_exportou_carteira", f"{f.de}..{f.ate}",
                 {"regime": f.regime, "busca": f.busca, "situacao": f.situacao})
        return _csv(conteudo, f"nfse_empresas_{f.de}_a_{f.ate}.csv")

    # ------------------------------------------------------------ empresa
    @app.get("/empresa/{cnpj}", response_class=HTMLResponse)
    def empresa(request: Request, cnpj: str, usuario: Usuario = Depends(ver), de: str = "", ate: str = "",
                tipo: list[str] | None = Query(None), busca: str = "", pagina_: int = Query(1, alias="pagina"),
                volta: str = ""):
        cnpj = so_digitos(cnpj)
        cadastro = empresa_do_cadastro(cnpj) if cnpj_valido(cnpj) else None
        if cadastro is None:
            return pagina(request, "empresa.html", {"titulo": "NFS-e", "nao_encontrada": True}, None)
        ctx = {"titulo": f"NFS-e · {cadastro.get('razao_social') or carteira.formatar_cnpj(cnpj)}",
               "empresa": carteira.ficha(cadastro), "pode_exportar": usuario.pode("nfse:exportar"),
               "volta": volta if volta.startswith("/") and not volta.startswith("//") else "/"}
        dados, erro = ler(lambda: cache_notas.obter(cnpj))
        if erro:
            ctx["erro"] = erro
        elif dados.empty:
            ctx["sem_notas"] = True
        else:
            f = painel.ler_filtros(dados, de, ate, tipo, busca, pagina_)
            ctx.update(painel.montar(dados, f, marca), filtros=f)
            resumo, _ = ler(cache_carteira.obter)
            if resumo is not None:  # mesmos gráficos de evolução da visão de empresa única
                ctx["evolucao"] = evolucao.montar(resumo.resumo, cnpj, f.de, f.ate, marca)
        return pagina(request, "empresa.html", ctx, erro)

    @app.get("/empresa/{cnpj}/exportar.csv")
    def exportar_empresa(request: Request, cnpj: str, usuario: Usuario = Depends(exportar), de: str = "",
                         ate: str = "", tipo: list[str] | None = Query(None), busca: str = ""):
        cnpj = so_digitos(cnpj)
        if not cnpj_valido(cnpj):
            return Response("CNPJ inválido.", status_code=404, media_type="text/plain; charset=utf-8")
        dados, erro = ler(lambda: cache_notas.obter(cnpj))
        if erro or dados.empty:
            return Response(erro or "Sem notas.", status_code=503, media_type="text/plain; charset=utf-8")
        f = painel.ler_filtros(dados, de, ate, tipo, busca)
        conteudo = painel.csv_exportacao(dados, f)
        _auditar(request, usuario, "nfse_exportou", f"{cnpj} {f.de}..{f.ate}", {"tipos": f.tipos, "busca": f.busca})
        return _csv(conteudo, f"nfse_{cnpj}_{f.de}_a_{f.ate}.csv")

    def _auditar(request, usuario, acao, alvo, detalhe):
        try:
            identidade.registrar(request, usuario, acao, alvo=alvo, detalhe=detalhe)
        except Exception:  # auditoria não pode impedir o download
            log.exception("falha ao registrar exportação")

    return app


def _csv(conteudo: bytes, nome: str) -> Response:
    return Response(conteudo, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome.replace("/", "-")}"'})


def criar_app_do_ambiente() -> FastAPI:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    try:
        return criar_app()
    except ConfigError as e:
        raise SystemExit(f"Configuração inválida: {e}") from e
