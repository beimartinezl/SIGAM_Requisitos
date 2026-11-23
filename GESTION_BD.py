"""Funciones seguras de respaldo y reinicio para el panel gráfico v4.3."""
from pathlib import Path
from datetime import datetime
import sqlite3

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'sigam.db'
BACKUPS = ROOT / 'respaldos'

def respaldar(db=DB, backups=BACKUPS):
    db, backups = Path(db), Path(backups)
    if not db.exists():
        raise FileNotFoundError('Aún no existe una base de datos para respaldar.')
    backups.mkdir(parents=True, exist_ok=True)
    archivo = backups / f'sigam_respaldo_{datetime.now():%Y%m%d_%H%M%S_%f}.db'
    try:
        # sqlite3.backup toma una instantánea consistente, incluso en modo WAL.
        with sqlite3.connect(f'file:{db.resolve().as_posix()}?mode=ro', uri=True, timeout=15) as origen:
            with sqlite3.connect(archivo, timeout=15) as copia:
                origen.backup(copia)
                if copia.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('La copia de seguridad no pasó el control de integridad.')
    except Exception:
        archivo.unlink(missing_ok=True)
        raise
    return archivo

def reiniciar(db=DB, backups=BACKUPS):
    """Solo ejecutar sin el servidor activo. Crea copia antes de retirar BD y WAL."""
    db = Path(db)
    if not db.exists():
        return None
    copia = respaldar(db, backups)
    # Cada archivo WAL/SHM pertenece a esta BD. Se eliminan solo tras cerrar SIGAM.
    db.unlink()
    for sufijo in ('-wal', '-shm'):
        archivo = Path(str(db) + sufijo)
        if archivo.exists():
            archivo.unlink()
    return copia
