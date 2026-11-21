/* Utilidades comunes de la interfaz: formato, confirmación y avisos. */
(function () {
    'use strict';

    const fmtFecha = new Intl.DateTimeFormat('es-ES', {
        day: '2-digit', month: '2-digit', year: 'numeric'
    });
    const fmtNumero = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 });

    // Fecha ISO (YYYY-MM-DD) -> DD/MM/YYYY
    function formatearFecha(iso) {
        if (!iso) return '';
        const d = new Date(String(iso).slice(0, 10) + 'T00:00:00');
        return isNaN(d.getTime()) ? String(iso) : fmtFecha.format(d);
    }

    // Número con coma decimal española y sin ceros sobrantes
    function formatearNumero(n) {
        const valor = Number(n);
        return Number.isFinite(valor) ? fmtNumero.format(valor) : String(n ?? '');
    }

    /* Cuerpo del modal de confirmación: un texto y, opcionalmente, una lista de
       detalles (por ejemplo las recetas que usan una subreceta). Todo con
       textContent: nunca se inyecta HTML desde los datos. */
    function pintarCuerpoConfirmacion(body, mensaje, lineas) {
        body.textContent = '';

        const parrafo = document.createElement('p');
        parrafo.className = 'confirm-modal-texto';
        parrafo.textContent = mensaje;
        body.appendChild(parrafo);

        if (Array.isArray(lineas) && lineas.length) {
            const lista = document.createElement('ul');
            lista.className = 'confirm-modal-lineas';
            lineas.forEach(function (texto) {
                const li = document.createElement('li');
                li.textContent = texto;
                lista.appendChild(li);
            });
            body.appendChild(lista);
        }
    }

    function pedirConfirmacion(mensaje, callback, opciones) {
        opciones = opciones || {};
        const modalEl = document.getElementById('confirm-modal');
        if (!modalEl || typeof bootstrap === 'undefined') {
            if (window.confirm(mensaje)) callback();
            return;
        }

        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        const body = document.getElementById('confirm-modal-body');
        const ok = document.getElementById('confirm-modal-ok');

        pintarCuerpoConfirmacion(body, mensaje, opciones.lineas);
        ok.textContent = opciones.textoBoton || 'Confirmar';
        ok.className = 'btn ' + (opciones.peligro === false ? 'btn-primary' : 'btn-danger');

        let confirmado = false;
        const alConfirmar = function () {
            confirmado = true;
            modal.hide();
        };
        const alCerrar = function () {
            modalEl.removeEventListener('hidden.bs.modal', alCerrar);
            ok.removeEventListener('click', alConfirmar);
            if (confirmado && typeof callback === 'function') {
                // Se ejecuta con el modal ya cerrado del todo: si la acción vuelve a pedir
                // otra confirmación (p. ej. un 409), el segundo modal no se solapa con el
                // cierre del primero y se ve entero.
                callback();
            }
        };

        ok.addEventListener('click', alConfirmar, { once: true });
        modalEl.addEventListener('hidden.bs.modal', alCerrar, { once: true });
        modal.show();
    }

    function mostrarToast(mensaje, tipo) {
        const contenedor = document.getElementById('toast-container');
        if (!contenedor || typeof bootstrap === 'undefined') return;

        const el = document.createElement('div');
        el.className = 'toast align-items-center text-bg-' + (tipo || 'danger') + ' border-0';
        el.setAttribute('role', 'alert');
        el.setAttribute('aria-live', 'assertive');
        el.setAttribute('aria-atomic', 'true');
        el.innerHTML =
            '<div class="d-flex">' +
            '<div class="toast-body"></div>' +
            '<button type="button" class="btn-close btn-close-white me-2 m-auto" ' +
            'data-bs-dismiss="toast" aria-label="Cerrar"></button>' +
            '</div>';
        el.querySelector('.toast-body').textContent = mensaje;
        contenedor.appendChild(el);

        const toast = new bootstrap.Toast(el, { delay: 5000 });
        el.addEventListener('hidden.bs.toast', function () { el.remove(); });
        toast.show();
    }

    // Flag global: muestra si hay un menú generándose en segundo plano.
    function actualizarFlagGeneracion() {
        const contenedor = document.getElementById('generacion-global');
        if (!contenedor || typeof window.jQuery === 'undefined') return;

        window.jQuery.get('/menus/api/generar/activos', function (data) {
            const activos = (data && data.activos) || [];
            if (activos.length) {
                const texto = contenedor.querySelector('.generacion-global-texto');
                if (texto) {
                    texto.textContent = activos.length === 1
                        ? 'Generando menú en segundo plano…'
                        : 'Generando ' + activos.length + ' menús en segundo plano…';
                }
                contenedor.hidden = false;
            } else {
                contenedor.hidden = true;
            }
        }, 'json');
    }

    window.pedirConfirmacion = pedirConfirmacion;
    window.mostrarToast = mostrarToast;
    window.formatearFecha = formatearFecha;
    window.formatearNumero = formatearNumero;
    window.actualizarFlagGeneracion = actualizarFlagGeneracion;

    // Solo se consulta si existe el flag en la página (todas las páginas lo tienen).
    if (document.getElementById('generacion-global')) {
        actualizarFlagGeneracion();
        setInterval(actualizarFlagGeneracion, 15000);
    }
})();
