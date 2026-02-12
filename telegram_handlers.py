import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from orario import (
    ServizioOrario,
    formatta_giorno,
    formatta_slot,
    giorno_oggi_sigla,
    ora_corrente_numero,
)


def registra_handler(app: Application, servizio: ServizioOrario) -> None:
    """Collega gli handler Telegram all'applicazione."""

    # saluta e mostra esempi
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # messaggio di benvenuto con esempi di utilizzo
        await update.message.reply_text(
            "Ciao! Sono il bot dell'orario.\n\n"
            "Usa:\n"
            "/oggi 4F\n"
            "/oggi ROSSI\n"
            "/oggi AULA 69\n\n"
            "Oppure scrivi: orario 4F (orario giornaliero)\n\n"
            "Ti rispondo con la lezione dell'ora attuale."
        )

    # elenca i comandi
    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # lista rapida dei comandi disponibili
        await update.message.reply_text(
            "Comandi:\n"
            "/oggi <classe|prof|aula>\n"
            "Esempi: /oggi 4F - /oggi Burgio - /oggi AULA 69\n"
            "Testo libero: orario 4F (orario giornaliero)\n"
        )

    # risponde con la lezione dell'ora corrente
    async def oggi(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # restituisce lo slot corrente per la classe o il prof o l'aula indicati
        if not context.args:
            await update.message.reply_text("Scrivi cosi: /oggi 4F (oppure prof/aula)")
            return

        nome = " ".join(context.args).strip()

        giorno = giorno_oggi_sigla()
        if giorno is None:
            await update.message.reply_text("Oggi e domenica: non c'e orario.")
            return

        ora = ora_corrente_numero()
        if ora is None:
            await update.message.reply_text("Fuori fascia orario lezioni (07:00-13:25).")
            return

        try:
            indice = servizio.ottieni_indice()
            categoria = servizio.categoriaricerca(nome, indice)

            url = None
            trovati = []
            res = servizio.scegli_url(indice[categoria], nome)
            if isinstance(res, tuple):
                url, trovati = res
            else:
                url = res

            if not url:
                if trovati:
                    await update.message.reply_text(
                        "Ho trovato piu risultati, sii piu preciso:\n" + "\n".join(trovati[:30])
                    )
                else:
                    await update.message.reply_text("Non trovato. Scrivi un nome piu simile a quello sul sito.")
                return

            orari, griglia = servizio.carica_orario(url)
            msg = formatta_slot(orari, griglia, giorno, ora)
            await update.message.reply_text(msg)

        except Exception:  # pragma: no cover - handler livello i/o
            logging.exception("Errore comando /oggi")
            await update.message.reply_text("Si e' verificato un errore temporaneo. Riprova.")

    # gestisce richieste libere o comando "orario"
    async def testo_libero(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # gestisce input libero: se inizia con la parola orario mostra il giorno intero, altrimenti solo l'ora corrente
        testo = (update.message.text or "").strip()

        mappa_url = {
            "manerbio": os.getenv("URL_MANERBIO"),
            "verolanuova": os.getenv("URL_VEROLANUOVA"),
        }
        
        if not testo:
            return

        if len(testo) > 60:
            await update.message.reply_text("Scrivi solo classe/prof/aula, es: 4F oppure ROSSI oppure AULA 69.")
            return

        parole = testo.split()
        solo_oggi = True

        testo_key = testo.lower()
        if testo_key in mappa_url:
            url = mappa_url[testo_key]
            if not url:
                await update.message.reply_text("URL per questa scuola non configurato.")
                return
            servizio.url_indice = url
            servizio._cache.ts = None
            servizio._cache.data = None
            await update.message.reply_text(f"Impostato: {testo_key}")
            return
        
        if parole and parole[0].lower() == "orario":
            solo_oggi = False
            nome = " ".join(parole[1:]).strip()
            if not nome:
                await update.message.reply_text("Scrivi cosi: orario 4F (oppure prof/aula)")
                return
        else:
            nome = testo

        giorno = giorno_oggi_sigla()
        if giorno is None:
            await update.message.reply_text("Oggi e domenica: non c'e orario.")
            return

        try:
            indice = servizio.ottieni_indice()
            categoria = servizio.categoriaricerca(nome, indice)

            res = servizio.scegli_url(indice[categoria], nome)
            if isinstance(res, tuple):
                url, trovati = res
            else:
                url, trovati = res, []

            if not url:
                if trovati:
                    await update.message.reply_text(
                        "Ho trovato piu risultati, sii piu preciso:\n" + "\n".join(trovati[:30])
                    )
                else:
                    await update.message.reply_text("Non trovato. Scrivi un nome piu simile a quello sul sito.")
                return

            orari, griglia = servizio.carica_orario(url)
            if solo_oggi:
                ora = ora_corrente_numero()
                if ora is None:
                    await update.message.reply_text("Fuori fascia orario lezioni (07:00-13:25).")
                    return
                msg = formatta_slot(orari, griglia, giorno, ora)
            else:
                msg = formatta_giorno(orari, griglia, giorno)
            await update.message.reply_text(msg)

        except Exception:  # pragma: no cover - handler livello i/o
            logging.exception("Errore nel testo libero")
            await update.message.reply_text("Si e' verificato un errore temporaneo. Riprova.")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("oggi", oggi))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, testo_libero))
