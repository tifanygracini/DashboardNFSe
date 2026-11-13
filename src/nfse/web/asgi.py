"""Ponto de entrada do servidor:  uvicorn nfse.web.asgi:app"""
from .app import criar_app_do_ambiente

app = criar_app_do_ambiente()
