import logging

from telegram.ext import Application

from config import carica_configurazione
from orario import ServizioOrario
from telegram_handlers import registra_handler


# entrypoint del bot
def main():
    # imposta logging base per vedere errori e info del bot su stdout
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    # carica le variabili richieste e costruisce il servizio di orario
    config = carica_configurazione()
    servizio = ServizioOrario(config.url_indice, secondi_cache=config.secondi_cache)

    # crea l'app telegram e registra tutti gli handler
    app = Application.builder().token(config.token_bot).build()
    registra_handler(app, servizio)

    print("BOT AVVIATO: sto ascoltando Telegram...")
    app.run_polling()


if __name__ == "__main__":
    main()
