"""Keine Ticketdaten im Protokoll: Streamlit schreibt jede unbehandelte Ausnahme samt Meldung ins Protokoll der App ("Uncaught app execution"). Bei einer Ausnahme
nach einem Upload kann die Meldung Teile der Daten enthalten (ein Statusname, ein Titel), und das Protokoll liest der Betreiber der App.

`scrub_streamlit_logs` hängt an die Handler aller Streamlit-Logger einen Filter, der bei Protokolleinträgen mit Ausnahme die Meldung durch den
Ausnahmetyp ersetzt und nur die Stationen des Aufrufs (Datei, Zeile, Quelltext) behält. So bleibt ein Fehler auffindbar, ohne dass Daten ins Protokoll geraten."""

import logging
import traceback

SUPPRESSED = "<Meldung unterdrückt, damit keine Daten im Protokoll stehen>"


class ScrubExceptionDetails(logging.Filter):
    """Ersetzt Ausnahmemeldung und Traceback-Text eines Protokolleintrags durch Typ und Aufrufstationen."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and record.exc_info[0] is not None:
            kind, _value, tb = record.exc_info
            frames = "".join(traceback.format_tb(tb)) if tb is not None else ""
            record.msg = f"{record.getMessage()}\n{frames}{kind.__name__}: {SUPPRESSED}"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True


def _streamlit_loggers() -> list[logging.Logger]:
    """Alle bereits angelegten Logger von Streamlit (jeder hat einen eigenen Handler und gibt nichts an den Root-Logger weiter) und der Root-Logger."""
    named = [lg for name, lg in sorted(logging.root.manager.loggerDict.items()) if name.startswith("streamlit") and isinstance(lg, logging.Logger)]
    return named + [logging.getLogger()]


def scrub_streamlit_logs() -> int:
    """Installiert den Filter an allen Handlern der Streamlit-Logger (mehrfaches Aufrufen schadet nicht; Logger, die erst später entstehen, erfasst der nächste Lauf).
    Rückgabe: Zahl der Handler, an denen der Filter hängt."""
    count = 0
    for logger in _streamlit_loggers():
        for handler in logger.handlers:
            if not any(isinstance(f, ScrubExceptionDetails) for f in handler.filters):
                handler.addFilter(ScrubExceptionDetails())
            count += 1
    return count
