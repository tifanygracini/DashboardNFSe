"""Embrulho para valores sensíveis (senha do certificado): nunca aparece em print, log ou traceback."""


class Segredo:
    __slots__ = ("_valor",)

    def __init__(self, valor: str):
        self._valor = valor

    def revelar(self) -> str:
        """Único jeito de obter o valor. Use só no ponto exato em que ele é necessário."""
        return self._valor

    def __bool__(self):
        return bool(self._valor)

    def __repr__(self):
        return "Segredo('***')"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("Segredo não pode ser serializado (pickle).")
