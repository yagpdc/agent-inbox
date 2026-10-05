"""Como está o tempo em Curitiba (Open-Meteo, sem chave e sem cadastro)."""

import json
import urllib.request

CURITIBA = {"latitude": -25.4284, "longitude": -49.2733}
API = "https://api.open-meteo.com/v1/forecast"

# Código do Open-Meteo -> o que dizer. Agrupado: o que muda a decisão é chuva, não a nuance.
CEU = {
    0: "céu limpo", 1: "quase limpo", 2: "parcialmente nublado", 3: "nublado",
    45: "névoa", 48: "névoa com geada", 51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    56: "garoa congelante", 57: "garoa congelante forte", 61: "chuva fraca", 63: "chuva",
    65: "chuva forte", 66: "chuva congelante", 67: "chuva congelante forte",
    71: "neve fraca", 73: "neve", 75: "neve forte", 77: "grãos de neve",
    80: "pancadas de chuva", 81: "pancadas de chuva", 82: "pancadas fortes de chuva",
    85: "pancadas de neve", 86: "pancadas fortes de neve",
    95: "tempestade", 96: "tempestade com granizo", 99: "tempestade com granizo",
}


def agora() -> dict:
    url = (f"{API}?latitude={CURITIBA['latitude']}&longitude={CURITIBA['longitude']}"
           "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
           "&daily=temperature_2m_min,temperature_2m_max,precipitation_probability_max"
           "&timezone=America%2FSao_Paulo&forecast_days=1")
    with urllib.request.urlopen(url, timeout=15) as r:
        d = json.loads(r.read())
    c, dia = d["current"], d["daily"]
    return {
        "cidade": "Curitiba",
        "temperatura": round(c["temperature_2m"]),
        "sensacao": round(c["apparent_temperature"]),
        "umidade": c["relative_humidity_2m"],
        "vento": round(c["wind_speed_10m"]),
        "ceu": CEU.get(c["weather_code"], "tempo indefinido"),
        "minima": round(dia["temperature_2m_min"][0]),
        "maxima": round(dia["temperature_2m_max"][0]),
        "chuva": dia["precipitation_probability_max"][0],
    }
