"""Helpers de XML que comparam só o nome local da tag (ignoram namespace)."""


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def filho(el, *caminho):
    """Desce por filhos diretos, comparando só o nome local."""
    for nome in caminho:
        if el is None:
            return None
        el = next((c for c in el if local(c.tag) == nome), None)
    return el


def texto(el, *caminho) -> str:
    e = filho(el, *caminho)
    return (e.text or "").strip() if e is not None and e.text else ""


def achar(raiz, nome):
    """Primeiro elemento com esse nome em qualquer profundidade."""
    for el in raiz.iter():
        if local(el.tag) == nome:
            return el
    return None


def achar_texto(raiz, nome) -> str:
    """Texto do primeiro elemento com esse nome que tenha conteúdo."""
    for el in raiz.iter():
        if local(el.tag) == nome and el.text and el.text.strip():
            return el.text.strip()
    return ""


def numero(s: str) -> float:
    try:
        return float(s.replace(",", ".")) if s else 0.0
    except ValueError:
        return 0.0
