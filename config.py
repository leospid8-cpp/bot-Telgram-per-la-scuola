import os
from dataclasses import dataclass


# racchiude le impostazioni minime per avviare il bot
@dataclass(frozen=True)
class Configurazione:
    token_bot: str
    url_indice: str
    secondi_cache: int = 6 * 60 * 60


# carica e valida le variabili richieste
def carica_configurazione() -> Configurazione:
    # legge le variabili d'ambiente richieste e fallisce subito se mancano
    # così l'errore è evidente all'avvio e non durante una richiesta utente
    token = os.getenv("BOT_TOKEN")
    url_indice = os.getenv("URL_INDICE")

    missing = []
    if not token:
        missing.append("BOT_TOKEN")
    if not url_indice:
        missing.append("URL_INDICE")

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Variabili mancanti: {joined}. Impostale nell'ambiente.")

    return Configurazione(token_bot=token, url_indice=url_indice)
