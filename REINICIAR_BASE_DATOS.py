"""Respaldo y reinicio de la base de datos SIGAM. Ejecutar con SIGAM cerrado."""
import os
import socket
from contextlib import closing
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'sigam.db'
RESPALDOS = ROOT / 'respaldos'


def main():
    port = int(os.environ.get('SIGAM_PORT', '5000'))
    # Comprobación de seguridad habitual: evitar reiniciar con el servidor local activo.
    with socket.socket() as sock:
        sock.settimeout(0.4)
        if sock.connect_ex(('127.0.0.1', port)) == 0:
            print(f'ERROR: Hay un servicio activo en el puerto {port}. Cierra SIGAM antes de continuar.')
            return 1

    if not DB.exists():
        print('No hay base de datos activa. Al iniciar SIGAM se creara una nueva.')
        return 0

    RESPALDOS.mkdir(exist_ok=True)
    fecha = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    destino = RESPALDOS / f'sigam_respaldo_{fecha}.db'
    try:
        # API de copia SQLite: incluye transacciones WAL confirmadas.
        with closing(sqlite3.connect(f'file:{DB}?mode=rw', uri=True, timeout=3)) as origen:
            with closing(sqlite3.connect(destino)) as copia:
                origen.backup(copia)
                ok = copia.execute('PRAGMA integrity_check').fetchone()[0]
                if ok != 'ok':
                    raise RuntimeError('El respaldo no supero la verificacion de integridad.')
        # Comprobar que no existen conexiones activas de escritura antes de borrar.
        with closing(sqlite3.connect(f'file:{DB}?mode=rw', uri=True, timeout=1)) as con:
            con.execute('PRAGMA locking_mode=EXCLUSIVE')
            con.execute('BEGIN EXCLUSIVE')
            con.execute('ROLLBACK')
        DB.unlink()
        for suffix in ('-wal', '-shm'):
            archivo = Path(str(DB) + suffix)
            if archivo.exists():
                archivo.unlink()
    except Exception as exc:
        print(f'ERROR: No se pudo reiniciar la base de datos: {exc}')
        print('No intentes continuar con SIGAM abierto. Revisa el respaldo antes de repetir.')
        return 1
    print('Base de datos reiniciada correctamente.')
    print(f'Respaldo guardado en: {destino}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
