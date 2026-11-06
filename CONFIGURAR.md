# Configurar AM-CONNECT

La PC de escritorio es el servidor. Cada sucursal solo recibe un comando. Tú entras desde el panel de esa PC y pulsas **Connect** cuando la tienda aparece **Online**.

El puerto del servidor es **TCP 8000**. Hay un comando distinto por cada sucursal.

## Orden de trabajo

1. Descargar el zip `am-connect-windows` y descomprimirlo.
2. Dejar `AM-CONNECT.exe` en la PC de escritorio.
3. Reenviar el puerto TCP 8000 del módem a esa PC.
4. Crear `Abrir-servidor.bat` con tu IP pública.
5. Abrir el servidor, crear usuario e iniciar sesión.
6. En cada tienda, pegar una vez el comando de PowerShell.
7. Pulsar **Connect** cuando la sucursal diga **Online**.

## 1. Servidor

En tu PC de escritorio descarga el zip `am-connect-windows`.

1. Abre la compilación: https://github.com/aba3bs-arch/remote3b/actions/runs/41586726237
2. Entra a **Summary**.
3. Al final de la página, en **Artifacts**, pulsa **am-connect-windows**.

Enlace directo del zip: https://github.com/aba3bs-arch/remote3b/actions/runs/41586726237/artifacts/13208383977

GitHub pide que tengas la sesión iniciada.

| Archivo | En qué PC | Qué hace |
| --- | --- | --- |
| `AM-CONNECT.exe` | Escritorio, el servidor | Abre el panel y espera a las tiendas |
| `AM-CONNECT-Agent.exe` | Solo las sucursales | Queda junto al zip; el comando de la tienda lo usa si hace falta |

### Primera apertura

1. Descomprime el zip en una carpeta fija, por ejemplo el Escritorio, dentro de una carpeta `AM-CONNECT`.
2. Doble clic en `AM-CONNECT.exe`. Si Windows Firewall pregunta, permite la app en redes privadas.
3. Se abre el navegador en `http://127.0.0.1:8000`. Deja la ventana de AM-CONNECT abierta. Si la cierras, el servidor se apaga.
4. Pulsa la letra de la esquina superior derecha. Crea un usuario y luego inicia sesión. La contraseña lleva 12 caracteres o más, con mayúscula, minúscula, número y símbolo.

Con el exe suelto, las sucursales de otra red todavía no llegan. Sigue con la sección Red antes de pegar comandos en las tiendas.

## 2. Red

Cada tienda llama a tu PC. Para eso el módem de tu casa tiene que entregar el puerto 8000 a la PC de escritorio, y el programa tiene que anunciar tu IP pública.

### En el módem

1. Anota la IP local de la PC de escritorio. En PowerShell escribe `ipconfig`. Busca la IPv4 de tu Wi-Fi o del cable, algo como `192.168.1.20`.
2. En el módem, reserva esa IP para esta PC, para que no cambie.
3. Crea un reenvío de puerto: protocolo TCP, puerto externo 8000, puerto interno 8000, destino la IP local de la PC.
4. En la misma PC, busca en el navegador cuál es tu IP. Esa es la IP pública. Anótala.

### Abrir-servidor.bat

Crea este archivo de texto en la misma carpeta que `AM-CONNECT.exe`. Cambia `TU_IP_PUBLICA` por la IP del paso 4. Guárdalo con el nombre `Abrir-servidor.bat`. Desde entonces abre este archivo con doble clic.

```bat
set PUBLIC_URL=http://TU_IP_PUBLICA:8000
start "" "%~dp0AM-CONNECT.exe"
```

La ventanita de AM-CONNECT puede mostrar una IP `192.168`. La que vale está en el panel del navegador, en la línea de las tiendas, y dentro del comando que copias. Esa dirección tiene que ser `http://TU_IP_PUBLICA:8000`. Si Windows pregunta otra vez, permite la app también en redes públicas.

Un enlace temporal `trycloudflare.com` solo sirve para mirar el panel. Las sucursales se configuran contra la IP pública de tu casa.

## 3. Sucursal

Haz esto una vez por cada tienda, con el servidor ya abierto mediante `Abrir-servidor.bat` y con tu sesión iniciada.

1. En el panel pulsa **Agregar equipo / Descargar**.
2. Escribe el nombre de la sucursal, por ejemplo `3B7 Del Valle`, y pulsa **Registrar y generar**.
3. Copia el comando. Tiene que incluir tu IP pública y el puerto 8000.
4. En la PC de esa tienda abre PowerShell, pega el comando y déjalo terminar. Instala el agente y lo deja iniciar con Windows.
5. Repite con otro nombre para la siguiente sucursal. Cada tienda tiene su propio comando.

El agente queda en la carpeta local `AM-CONNECT\agent` de esa PC y crea un acceso en Inicio de Windows. Instálalo solo en equipos de 3B o con permiso del dueño.

## 4. Conectar

Con las dos computadoras encendidas, la sucursal llama sola al servidor. En la tabla, esa fila pasa de **Offline** a **Online**.

Pulsa **Connect** en esa fila y confirma que tienes autorización. Se abre la pantalla de la tienda, con mouse y teclado.

### Desde otra computadora tuya

Abre `http://TU_IP_PUBLICA:8000` en el navegador, entra con el mismo usuario y pulsa **Connect**. La PC de escritorio tiene que seguir encendida, con la ventana de AM-CONNECT abierta, y sin suspenderse. En Opciones de energía, pon que no se suspenda.

## Si falla

| Lo que ves | Qué revisar |
| --- | --- |
| El navegador no abre `127.0.0.1:8000` | La ventana de AM-CONNECT tiene que estar abierta. La dirección es `http`, con el puerto 8000. |
| La tienda se queda Offline | El comando debe llevar la IP pública. Revisa el reenvío TCP 8000, el firewall en redes públicas y que ambas PCs estén encendidas. |
| Ayer funcionaba y hoy no | Tu IP pública cambió. Actualiza `Abrir-servidor.bat`, vuelve a abrir el servidor y genera de nuevo el comando de cada tienda. |
| El módem no deja entrar | Compara la IP pública del navegador con la WAN del módem. Si el módem muestra `100.64` o una IP distinta, el reenvío de puerto no alcanza y hace falta otra salida a internet. |
