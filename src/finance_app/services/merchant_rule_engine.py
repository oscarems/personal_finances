"""
Motor de coincidencia para reglas de categorización automática de comercios.

Funciones puras, sin acceso a base de datos, para poder testear y reutilizar
tanto en la importación de Gmail como en la creación manual de transacciones.
"""
import re


def _text_for_field(rule, payee_name: str | None, memo: str | None) -> str | None:
    if rule.field == "memo":
        return memo
    return payee_name


def match_rule(rule, payee_name: str | None, memo: str | None) -> bool:
    """Evalúa si una regla coincide contra el payee/memo de una transacción."""
    text = _text_for_field(rule, payee_name, memo)
    if not text:
        return False

    value = (rule.merchant_name or "").strip()
    if not value:
        return False

    operator = rule.operator or "contains"

    if operator == "regex":
        try:
            return re.search(value, text, re.IGNORECASE) is not None
        except re.error:
            return False

    text_lower = text.lower()
    value_lower = value.lower()

    if operator == "equals":
        return text_lower == value_lower
    if operator == "starts_with":
        return text_lower.startswith(value_lower)
    # default: contains
    return value_lower in text_lower


def find_matching_rule(rules: list, payee_name: str | None, memo: str | None):
    """Devuelve la regla que coincide con mayor prioridad.

    Desempate: entre reglas con la misma prioridad, gana la que aparezca
    primero en `rules` (se recomienda pasar la lista ya ordenada por id
    ascendente, de modo que la regla más antigua gane el empate).
    """
    best = None
    for rule in rules:
        if not match_rule(rule, payee_name, memo):
            continue
        if best is None or rule.priority > best.priority:
            best = rule
    return best
