# SIGAM — MVP académico con acceso por red local

Aplicación web responsiva para gestión básica de activos y mantenimiento. Utiliza Python, Flask y SQLite. En esta versión, un computador actúa como servidor y mantiene la única base de datos; los demás dispositivos acceden mediante un navegador a través de la red local (LAN/Wi-Fi).

## Requisitos

- Windows 10/11 para el inicio automático incluido.
- Python 3.10 o superior instalado en el computador servidor.
- Conexión a Internet solo durante la primera instalación de Flask y sus dependencias.
- Los equipos cliente deben estar conectados a la misma red local que el servidor.

## Inicio en Windows

1. Instala Python 3.10 o superior desde https://www.python.org/downloads/ y marca **Add Python to PATH**.
2. Descomprime la carpeta `SIGAM` en el computador que actuará como servidor.
3. Haz doble clic en `INICIAR_SIGAM.bat`.
4. La primera vez se crea el entorno virtual e instalan las dependencias; se necesita Internet.
5. La ventana muestra dos direcciones: `http://127.0.0.1:5000` para el propio servidor y `http://IP-LOCAL:5000` para los demás dispositivos.
6. En los celulares, notebooks y computadores cliente abre la dirección de red local indicada. Todos deben usar la misma Wi-Fi/LAN.
7. Si Windows Firewall pregunta, permite Python en **redes privadas**. No habilites redes públicas.
8. Para cerrar SIGAM, vuelve a la ventana del servidor y presiona **Ctrl + C**.

El computador servidor debe permanecer encendido y conectado a la red mientras los demás usuarios utilicen SIGAM. Si cambia su dirección IP, usa la nueva dirección que muestra el archivo de inicio.

## Base de datos compartida

La base `sigam.db` se crea automáticamente en la carpeta de la aplicación del computador servidor. Todos los dispositivos acceden a los datos a través de Flask; no deben abrir, copiar ni sincronizar el archivo SQLite directamente. **No coloques `sigam.db` en una carpeta de red compartida**: debe permanecer en el disco local del servidor. Realiza copias de seguridad manuales periódicas cerrando SIGAM y copiando el archivo de base de datos.

SQLite está configurado con claves foráneas, espera breve ante escrituras simultáneas y modo WAL para mejorar la convivencia entre lecturas y escrituras. Esto es adecuado para una demostración académica de alcance pequeño, no constituye una garantía de rendimiento para una planta productiva ni para decenas de usuarios concurrentes.

## Uso desde dispositivos cliente

1. Conecta el dispositivo a la misma red Wi-Fi/LAN.
2. Abre Chrome, Edge, Firefox o Safari.
3. Escribe `http://IP-LOCAL-DEL-SERVIDOR:5000`, reemplazando el texto por la IP que muestra la ventana del servidor.
4. Registra o consulta activos, avisos, órdenes e intervenciones. Los cambios se guardan en la base central y quedan disponibles para los demás al actualizar o volver a consultar la página.

## Si no puedes conectarte

- Confirma que el servidor está encendido y que la ventana de SIGAM sigue abierta.
- Verifica que ambos dispositivos estén conectados a la misma red local y no a una red de invitados aislada.
- Revisa la IP mostrada en la ventana; puedes ejecutar `ipconfig` en Windows y buscar la dirección IPv4 del adaptador conectado.
- Comprueba que el Firewall de Windows permita Python en redes privadas.
- Asegúrate de escribir `http://` y el puerto `:5000`.

## Alcance académico y seguridad

Esta versión implementa acceso compartido en red local con una base de datos centralizada. **No implementa modo offline ni sincronización posterior entre bases independientes.** Incluye autenticación y roles desde v4.2, pero su uso sigue limitado a una red privada de confianza. Por ello, úsala solo en una red privada y de confianza, con datos de demostración; no la expongas directamente a Internet ni la consideres lista para producción. Para una operación real se necesitarán autenticación, autorización, HTTPS, respaldos automatizados, auditoría y un servidor de despliegue apropiado.

## Funciones del MVP

- Registro, búsqueda, edición y desactivación de activos.
- Registro y consulta de avisos de falla.
- Creación y seguimiento básico de órdenes de trabajo.
- Registro de intervenciones e historial por activo.
- Panel principal con indicadores básicos.
- Apartado demostrativo de prueba y planes; no procesa pagos ni contrata servicios reales.

## Prueba de usabilidad

El objetivo académico es que una persona pueda registrar un aviso sencillo desde un celular en un máximo de 2 minutos. Este objetivo debe validarse con personas reales; el diseño por sí solo no demuestra que se cumpla.


## Cuentas y niveles de acceso (v4.2)

Al iniciar SIGAM por primera vez, abre `http://127.0.0.1:5000/configurar` y crea la primera cuenta de Administrador. No existe una contraseña predeterminada. Después, cada usuario inicia sesión con su nombre de usuario y contraseña.

Roles:
- **Administrador:** acceso completo y administración de usuarios.
- **Supervisor:** gestiona activos, avisos y órdenes de trabajo.
- **Trabajador:** consulta información, registra avisos y agrega intervenciones. No puede editar activos, crear órdenes ni cambiar estados de órdenes.

El sistema almacena contraseñas como hashes, utiliza protección CSRF en formularios y controla permisos en el servidor. Las cuentas se pueden activar o desactivar desde el menú Usuarios. Las contraseñas deben tener al menos 10 caracteres.

**Seguridad:** esta versión conserva SQLite y el acceso LAN de v4.0. No debe exponerse directamente a Internet. Para un despliegue cloud se requiere HTTPS, configuración segura de secretos, copias de seguridad y una revisión adicional de seguridad; además, se recomienda PostgreSQL para concurrencia y crecimiento.


## Importación de activos desde Excel (v4.3)

- Disponible para Administrador y Supervisor desde el menú “Importar Excel”.
- Descarga la plantilla `.xlsx`, completa código, nombre, categoría y ubicación, y súbela.
- Código, nombre y ubicación son obligatorios.
- Los códigos repetidos en el archivo o ya existentes en SIGAM se omiten y se informan.
- Las filas válidas se guardan en la base central SQLite del servidor.
- Se requiere `openpyxl`, incluido en `requirements.txt`.

## SIGAM v4.4 — Asignaciones y verificación de mantenimiento

- Administradores y supervisores pueden asignar órdenes a trabajadores o supervisores activos, reasignarlas y consultar el historial de cambios.
- Las intervenciones pueden registrar horas de inicio y término, además de un resultado.
- Administradores y supervisores pueden guardar una prueba de retorno: Aprobada, Rechazada o No aplica.
- Las bases de datos existentes de v4.3 se actualizan automáticamente al iniciar v4.4, conservando los registros anteriores.
- Los campos horarios admiten trabajos dentro del mismo día (hora de término posterior a la de inicio).

### Reiniciar la base de datos

1. **Cierra SIGAM** y asegúrate de que nadie esté usando el servidor.
2. En el computador servidor, ejecuta `REINICIAR_BASE_DATOS.bat`.
3. Lee la advertencia y escribe `REINICIAR` para confirmar.
4. Se crea una copia de seguridad SQLite verificada en `respaldos/` antes de retirar la base activa.
5. Ejecuta `INICIAR_SIGAM.bat`: SIGAM creará una base vacía y solicitará configurar el administrador inicial.

El reinicio elimina también las cuentas de usuarios, los activos, los avisos y las órdenes. Los respaldos no se eliminan. **No ejecutes este proceso con el servidor en uso**. Para restaurar una copia, cierra SIGAM, respalda primero la base activa y copia el archivo `.db` del respaldo como `sigam.db`.

### Pruebas

Ejecuta `EJECUTAR_PRUEBAS.bat` en Windows. Incluye las pruebas de importación Excel de v4.3 y las pruebas de mantenimiento v4.4. Usan bases temporales y no modifican `sigam.db`.


## SIGAM v4.5 — Repuestos y control básico de inventario

- **Repuestos:** desde el menú lateral, los administradores y supervisores pueden registrar repuestos con código único, nombre, unidad de medida y stock mínimo. El stock inicial es cero.
- **Entradas:** agregan existencias y registran fecha, cantidad, usuario y observación. Solo las pueden registrar administradores y supervisores.
- **Consumo por orden:** desde el detalle de una orden se registra la cantidad utilizada; el sistema descuenta existencias y relaciona el movimiento con la orden de trabajo.
- **Permisos:** administradores y supervisores pueden consumir en órdenes abiertas; un trabajador solo puede registrar consumos en órdenes que tenga asignadas. No se permite consumo en órdenes finalizadas.
- **Control:** no se permite una cantidad negativa o cero, ni consumir más de lo disponible. Se muestra “Stock bajo” cuando las existencias son menores o iguales al mínimo.
- **Trazabilidad:** el listado “Ver movimientos” presenta los últimos 300 movimientos con su usuario y orden asociada (si corresponde). Los movimientos se conservan al reiniciar la aplicación.
- **Compatibilidad:** SIGAM crea automáticamente las tablas nuevas al abrir una base v4.4; conserva los registros previos. `REINICIAR_BASE_DATOS.bat` sigue siendo una operación **opcional y destructiva** que debe realizarse con SIGAM cerrado, no una actualización necesaria.

### Actualizar desde v4.4 sin perder datos

1. Cierra la aplicación (`Ctrl+C` en la ventana del servidor) y verifica que los demás usuarios estén desconectados.
2. Respalda la carpeta de v4.4, incluido `sigam.db` y, si existe, `.sigam_secret_key`.
3. Descomprime la nueva carpeta `SIGAM` **en una ubicación nueva** y copia en ella los archivos existentes `sigam.db` y `.sigam_secret_key`. Si tienes archivos `sigam.db-wal` o `sigam.db-shm`, vuelve a comprobar que la app esté realmente detenida antes de mover la base.
4. Inicia `INICIAR_SIGAM.bat`. Las tablas de inventario se crearán automáticamente sin borrar las anteriores.
5. Ejecuta `EJECUTAR_PRUEBAS.bat`. Las pruebas utilizan bases temporales y no deben afectar tu base real.

**Límites de v4.5:** inventario simplificado con cantidades enteras; no incluye proveedores, compras, costos, unidades fraccionarias ni reposición automática. El sistema sigue siendo un MVP académico LAN + SQLite.
