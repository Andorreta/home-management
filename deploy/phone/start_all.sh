#!/data/data/com.termux/files/usr/bin/bash

# Script Maestro de Control para la Infraestructura del OnePlus 7 Pro
# Ubicación: ~/web-server/start_all.sh
# (Copia versionada en el repo: home-management/deploy/phone/start_all.sh)

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE}")" && pwd)"

# Colores para la salida
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

show_help() {
    echo "Uso: ./start_all.sh [opción]"
    echo ""
    echo "Opciones:"
    echo "  start     Arrancar SELinux, cortafuegos, Flask y Caddy"
    echo "  stop      Detener Flask, Caddy, liberar puertos y wake-lock"
    echo "  help      Mostrar esta ayuda"
}

run_app() {
    echo -e "${BLUE}=== Iniciando Infraestructura del Servidor ===${NC}"

    # 1. Asegurar modo Permissive de SELinux
    su -c "setenforce 0"
    echo -e "-> SELinux configurado en ${GREEN}Permissive${NC}."

    # 2. Configurar redirección de puertos a nivel de Kernel (Puerto 80 -> 8080 de Caddy)
    # Limpiamos reglas previas idénticas para evitar duplicados en el firewall
    su -c "iptables -t nat -D PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 8080" &> /dev/null
    su -c "iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 8080"
    echo -e "-> Cortafuegos: Redirección del ${GREEN}Puerto 80 al 8080 (Caddy HTTP)${NC} activada."

    # 3. Activar Wake-Lock de Termux para que Android 15 no congele la CPU
    if command -v termux-wake-lock &> /dev/null; then
        termux-wake-lock
        echo -e "-> Wake-lock de Termux: ${GREEN}Activado${NC}."
    fi

    # 4. Arrancar la aplicación Flask (Gunicorn)
    if [ -d "$BASE_DIR/home-management" ]; then
        echo -e "-> Iniciando aplicación Flask con Gunicorn..."
        cd "$BASE_DIR/home-management"
        pkill -f "gunicorn.*5000" &> /dev/null
        HM_CONFIG=ServerConfig ./venv/bin/gunicorn -w 2 -b 0.0.0.0:5000 app:app --daemon --timeout 300
        echo -e "   [${GREEN}OK${NC}] Flask escuchando de fondo en el puerto 5000."
    else
        echo -e "   [${RED}Error${NC}] No se encontró la carpeta de la app en $BASE_DIR/home-management"
    fi

    # 5. Arrancar el Proxy Inverso Caddy Global
    if [ -d "$BASE_DIR/caddy-proxy" ]; then
        echo -e "-> Iniciando Proxy Caddy..."
        cd "$BASE_DIR/caddy-proxy"
        pkill -f caddy &> /dev/null
        sleep 1 # Damos un segundo de margen al kernel para liberar el puerto
        caddy start --config Caddyfile
        echo -e "   [${GREEN}OK${NC}] Caddy escuchando de fondo en los puertos 8080 y 8443."
    else
        echo -e "   [${RED}Error${NC}] No se encontró el archivo del proxy en $BASE_DIR/caddy-proxy"
    fi

    echo -e "${GREEN}=== ¡Todo el sistema se ha iniciado correctamente! ===${NC}"
    echo -e "Acceso desde la red local: ${BLUE}http://192.168.1.4${NC}"
}

stop_all() {
    echo -e "${BLUE}=== Deteniendo Infraestructura del Servidor ===${NC}"

    # 1. Detener el Proxy Caddy
    if [ -d "$BASE_DIR/caddy-proxy" ]; then
        cd "$BASE_DIR/caddy-proxy"
        caddy stop &> /dev/null
        echo -e "-> Caddy Server: ${GREEN}Detenido${NC}."
    fi

    # 2. Detener Gunicorn / Flask
    pkill -f "gunicorn.*5000" &> /dev/null
    echo -e "-> Gunicorn/Flask: ${GREEN}Detenido${NC}."

    # 3. Limpiar las reglas de redirección del cortafuegos (iptables)
    su -c "iptables -t nat -D PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 8080" &> /dev/null
    echo -e "-> Cortafuegos: Regla del puerto 80 ${GREEN}Eliminada${NC}."

    # 4. Liberar el Wake-Lock para permitir que el teléfono ahorre energía si no se usa
    if command -v termux-wake-unlock &> /dev/null; then
        termux-wake-unlock
        echo -e "-> Wake-lock de Termux: ${GREEN}Liberado${NC}."
    fi

    echo -e "${GREEN}=== Todos los servicios se han cerrado correctamente ===${NC}"
}

# Control de argumentos
if [ $# -eq 0 ]; then
    # Por defecto, si no pasas parámetros, arranca el sistema
    run_app
    exit 0
fi

case $1 in
    start)   run_app ;;
    stop)    stop_all ;;
    help)    show_help ;;
    *)       echo -e "${RED}Opción no válida: $1${NC}"; show_help; exit 1 ;;
esac
