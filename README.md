# SIGAM — MVP web responsivo

Aplicación local de gestión de activos y mantenimiento, construida con Flask y SQLite.

## Requisitos
- Python 3.10 o superior
- Navegador web moderno

## Instalación y ejecución

1. Descomprime el archivo ZIP.
2. Abre una terminal dentro de la carpeta `SIGAM`.
3. (Recomendado) crea un entorno virtual:

   **Windows**
   ```bash
   py -m venv venv
   venv\Scripts\activate
   ```

   **macOS / Linux**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

4. Instala Flask:
   ```bash
   pip install -r requirements.txt
   ```

5. Inicia la aplicación:
   ```bash
   python app.py
   ```

6. Abre en tu navegador:
   http://127.0.0.1:5000

La base de datos `sigam.db` se crea automáticamente al iniciar por primera vez.

## Uso desde el teléfono en la misma red Wi-Fi
Esta versión está configurada por defecto para uso local en el mismo computador. Para una demostración en una red local, cambia en `app.py`:
`app.run(host="127.0.0.1", port=5000, debug=True)`
por:
`app.run(host="0.0.0.0", port=5000, debug=True)`

Luego, desde el teléfono conectado a la misma Wi-Fi, ingresa a `http://IP-LOCAL-DEL-COMPUTADOR:5000`. La IP se consulta en la configuración de red del computador. No expongas esta versión de desarrollo a Internet.

## Apartado de prueba y suscripción
En el menú **Prueba y planes** puedes iniciar una prueba gratuita demostrativa de 14 días, seleccionar un plan referencial y registrar pruebas de usabilidad. Los planes propuestos son Básico ($19.990 CLP/mes) y Pyme ($39.990 CLP/mes). La selección se almacena localmente; no se realizan cobros, no existe pasarela de pago ni control real de licencias. Los precios son una hipótesis académica y deben validarse.

## Flujo recomendado de prueba
1. Crea un activo desde **Activos**.
2. Registra una falla desde **Avisos**.
3. En la lista de avisos, crea una orden de trabajo.
4. Cambia su estado y registra una intervención con responsable y fecha.
5. Abre la ficha del activo o **Historial** para consultar la trazabilidad.

## Usabilidad
La interfaz incorpora etiquetas más cotidianas, instrucciones breves, botones táctiles amplios y un apartado para registrar pruebas de usabilidad. El objetivo tomado del informe es completar un aviso simple desde móvil en un máximo de 2 minutos.

## Alcance y limitaciones
Es un MVP académico local. No incluye autenticación, roles, operación multiusuario, sincronización, copias de seguridad automáticas, inventario, adjuntos, QR ni mantenimiento preventivo automático. No debe utilizarse como sistema productivo sin implementar controles de seguridad, respaldos y despliegue apropiado.
