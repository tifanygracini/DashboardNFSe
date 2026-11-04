"""Erros do cliente do ADN. As mensagens são para o usuário final e nunca contêm segredos."""


class AdnError(Exception):
    """Base de todos os erros de comunicação com o ADN."""


class AdnCertificadoInvalido(AdnError):
    pass


class AdnTlsError(AdnError):
    pass


class AdnConexaoError(AdnError):
    pass


class AdnTimeout(AdnError):
    pass


class AdnLimiteChamadas(AdnError):
    """HTTP 429 depois de todas as tentativas."""


class AdnInstavel(AdnError):
    """HTTP 5xx depois de todas as tentativas."""


class AdnAcessoNegado(AdnError):
    """HTTP 403: certificado de outro CNPJ raiz."""


class AdnCertificadoPessoaFisica(AdnError):
    """HTTP 400 com E2242."""


class AdnRequisicaoInvalida(AdnError):
    pass


class AdnUrlInvalida(AdnError):
    """HTTP 404 sem o JSON do ADN."""


class AdnRespostaInesperada(AdnError):
    pass
