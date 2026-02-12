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
    url_manerbio = os.getenv("URL_MANERBIO")
    url_verolanuova = os.getenv("URL_VEROLANUOVA")

    missing = []
    if not token:
        missing.append("BOT_TOKEN")
    if not url_manerbio and not url_verolanuova:
        missing.append("URL_MANERBIO o URL_VEROLANUOVA")

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Variabili mancanti: {joined}. Impostale nell'ambiente.")

    url_indice = url_manerbio or url_verolanuova
    return Configurazione(token_bot=token, url_indice=url_indice)
