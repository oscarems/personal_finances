"""
Benchmark de modelos Ollama para extracción de transacciones bancarias.
Uso:
    pip install httpx
    python benchmark_ollama.py

Opcional - cambiar URL o modelos:
    OLLAMA_URL=http://192.168.1.10:11434 python benchmark_ollama.py
"""

import json
import logging
import os
import re
import time

import httpx

# ─── Configuración ────────────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")

MODELS = [
    "gemma4:e4b",
    "gemma4:2b",
    "llama3.2:3b",
    "mistral:7b",
    "qwen2.5:3b",
]

PROMPT = """Extrae la transacción del correo bancario y devuelve SOLO JSON válido.

CORREO:
De: alertas@davivienda.com.pa
Asunto: Notificación de Transacción - Tarjeta Internacional
Se ha realizado una transacción con su Tarjeta Mastercard Black terminada en 7834:
Fecha: 25/05/2026 | Hora: 09:15 AM
Comercio: NETFLIX.COM | Monto: USD 15.99
Ciudad: Los Gatos, CA - USA

CUENTAS: id=1: Davivienda Ahorros (COP) | id=2: Davivienda Mastercard (COP) | id=3: Mastercard Black Panamá (USD) | id=4: Wise USD (USD)
CATEGORÍAS: id=10: Mercado | id=11: Restaurantes | id=12: Transporte | id=13: Entretenimiento | id=14: Servicios digitales | id=15: Salud | id=16: Ropa | id=17: Hogar
MAPEO EXACTO: NETFLIX → categoria_id=14 | RAPPI → categoria_id=11 | UBER → categoria_id=12

REGLAS:
- fecha: YYYY-MM-DD
- monto: numérico puro. COP→punto=miles. USD→punto=decimal ($15.99=15.99)
- moneda: "COP" o "USD"
- cuenta_id: por dígitos tarjeta > moneda coincidente > red/banco > null
- categoria_id: mapeo exacto tiene prioridad máxima
- comentario: nombre del comercio

JSON:
{"fecha":"YYYY-MM-DD","monto":0.00,"moneda":"COP o USD","cuenta_id":null,"categoria_id":null,"comentario":""}"""

EXPECTED = {
    "fecha": "2026-05-25",
    "monto": 15.99,
    "moneda": "USD",
    "cuenta_id": 3,
    "categoria_id": 14,
}

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("benchmark")

SEP = "─" * 60


def parse_response(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def run_checks(data: dict) -> dict[str, bool]:
    return {
        "fecha correcta (2026-05-25)": data.get("fecha") == "2026-05-25",
        "monto correcto (15.99)": abs(float(data.get("monto") or 0) - 15.99) < 0.001,
        "moneda USD": data.get("moneda") == "USD",
        "cuenta_id = 3": int(data.get("cuenta_id") or 0) == 3,
        "categoria_id = 14": int(data.get("categoria_id") or 0) == 14,
    }


def benchmark_model(client: httpx.Client, model: str) -> dict:
    log.info("%s  Probando modelo: %s", SEP[:10], model)

    payload = {
        "model": model,
        "prompt": PROMPT,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "num_ctx": 1024,
            "num_predict": 150,
        },
    }

    t0 = time.perf_counter()
    try:
        r = client.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120.0)
        r.raise_for_status()
    except httpx.ConnectError:
        log.error("  ✗ No se pudo conectar a Ollama en %s", OLLAMA_URL)
        return {"model": model, "error": "connection_refused"}
    except httpx.HTTPStatusError as e:
        log.error(
            "  ✗ HTTP %s — el modelo '%s' probablemente no está instalado",
            e.response.status_code,
            model,
        )
        return {"model": model, "error": f"http_{e.response.status_code}"}

    elapsed = time.perf_counter() - t0
    js = r.json()

    raw = js.get("response", "{}").strip()
    eval_count = js.get("eval_count", 0)
    eval_duration = js.get("eval_duration", 1)
    tps = (eval_count / eval_duration * 1e9) if eval_duration else 0

    try:
        data = parse_response(raw)
    except Exception as e:
        log.error("  ✗ No se pudo parsear el JSON: %s", e)
        log.debug("  Raw response: %s", raw[:300])
        return {
            "model": model,
            "elapsed": elapsed,
            "tps": tps,
            "error": "parse_error",
            "raw": raw[:200],
        }

    checks = run_checks(data)
    passed = sum(checks.values())
    total = len(checks)

    log.info("  Tiempo     : %.2f s", elapsed)
    log.info("  Tokens/s   : %.1f", tps)
    log.info("  Precisión  : %d/%d checks", passed, total)
    log.info("  Respuesta  : %s", json.dumps(data, ensure_ascii=False))

    for name, ok in checks.items():
        icon = "✓" if ok else "✗"
        level = logging.INFO if ok else logging.WARNING
        log.log(level, "    %s  %s", icon, name)

    return {
        "model": model,
        "elapsed": elapsed,
        "tps": tps,
        "score": passed,
        "total": total,
        "passed": passed == total,
        "data": data,
        "checks": checks,
    }


def print_summary(results: list[dict]) -> None:
    log.info("")
    log.info("%s", SEP)
    log.info("RESUMEN FINAL")
    log.info("%s", SEP)

    valid = [r for r in results if "error" not in r]
    errored = [r for r in results if "error" in r]

    if errored:
        log.warning("Modelos con error (no instalados o no disponibles):")
        for r in errored:
            log.warning("  ✗  %-30s  %s", r["model"], r["error"])
        log.info("")

    if not valid:
        log.error("Ningún modelo respondió correctamente.")
        return

    # Tabla
    header = f"  {'Modelo':<30}  {'Tiempo':>8}  {'Tok/s':>7}  {'Score':>7}"
    log.info(header)
    log.info("  " + "─" * (len(header) - 2))

    valid_sorted = sorted(valid, key=lambda r: (not r["passed"], r["elapsed"]))
    for r in valid_sorted:
        flag = "✓" if r["passed"] else "✗"
        log.info(
            "  %s %-29s  %7.2fs  %7.1f  %d/%d",
            flag,
            r["model"],
            r["elapsed"],
            r["tps"],
            r["score"],
            r["total"],
        )

    log.info("")
    winners = [r for r in valid_sorted if r["passed"]]
    if winners:
        best = winners[0]
        log.info("🏆  Ganador: %s", best["model"])
        log.info(
            "    %.2f s · %.1f tok/s · %d/%d checks",
            best["elapsed"],
            best["tps"],
            best["score"],
            best["total"],
        )
    else:
        log.warning("Ningún modelo pasó todos los checks.")
        best_partial = max(valid, key=lambda r: (r["score"], -r["elapsed"]))
        log.info(
            "Mejor parcial: %s  (%d/%d checks)",
            best_partial["model"],
            best_partial["score"],
            best_partial["total"],
        )


def list_available_models(client: httpx.Client) -> list[str]:
    try:
        r = client.get(f"{OLLAMA_URL}/api/tags", timeout=10.0)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def main() -> None:
    log.info("%s", SEP)
    log.info("BENCHMARK OLLAMA — extracción de transacciones bancarias")
    log.info("%s", SEP)
    log.info("URL Ollama : %s", OLLAMA_URL)

    client = httpx.Client(timeout=120.0)

    available = list_available_models(client)
    if available:
        log.info("Modelos instalados en Ollama: %s", ", ".join(available))
    else:
        log.warning("No se pudo listar modelos (Ollama no responde o no hay modelos).")

    to_test = available if available else MODELS

    if not to_test:
        log.error("Ningún modelo disponible. Instala alguno con: ollama pull <modelo>")
        return

    log.info("Modelos a probar: %s", ", ".join(to_test))
    log.info("")

    results = []
    for model in to_test:
        result = benchmark_model(client, model)
        results.append(result)
        log.info("")

    print_summary(results)
    client.close()


if __name__ == "__main__":
    main()
