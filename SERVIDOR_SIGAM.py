"""Inicia SIGAM v4.3 mediante Waitress; mantiene el alcance funcional del Sprint 1."""
import os

def configuracion_servidor():
    puerto = int(os.environ.get('SIGAM_PORT', '5000'))
    if not 1 <= puerto <= 65535:
        raise ValueError('Puerto no válido')
    host = '0.0.0.0' if os.environ.get('SIGAM_BIND_LAN', '1') == '1' else '127.0.0.1'
    return host, puerto

def main():
    from waitress import serve
    from app import app
    host, puerto = configuracion_servidor()
    print(f'SIGAM v4.3 · escuchando en {host}:{puerto}',flush=True)
    serve(app,host=host,port=puerto,threads=6,connection_limit=80,max_request_body_size=10*1024*1024)

if __name__ == '__main__':
    main()
