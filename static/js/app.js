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

        body.textContent = mensaje;
        ok.textContent = opciones.textoBoton || 'Confirmar';
        ok.className = 'btn ' + (opciones.peligro === false ? 'btn-primary' : 'btn-danger');

        let confirmado = false;
        const alConfirmar = function () {
            confirmado = true;
            modal.hide();
            if (typeof callback === 'function') callback();
        };
        const alCerrar = function () {
            modalEl.removeEventListener('hidden.bs.modal', alCerrar);
            ok.removeEventListener('click', alConfirmar);
            if (!confirmado) {
                // La cancelación no dispara ninguna acción.
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

    window.pedirConfirmacion = pedirConfirmacion;
    window.mostrarToast = mostrarToast;
    window.formatearFecha = formatearFecha;
    window.formatearNumero = formatearNumero;
})();
