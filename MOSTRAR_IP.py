import socket

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No se envían datos: connect() permite consultar qué interfaz usaría
        # el equipo para salir por su ruta de red predeterminada.
        sock.connect(("192.0.2.1", 80))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            print(ip)
            return
    except OSError:
        pass
    finally:
        sock.close()
    print("No se pudo detectar automáticamente la IP. Ejecuta ipconfig en Windows.")

if __name__ == "__main__":
    main()
