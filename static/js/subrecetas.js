/* Subrecetas: un paso puede enlazar a otra receta con  [subreceta](id) .
   Aquí se pinta el enlace (con estilo propio para distinguirlo del texto normal)
   y se abre la receta enlazada en un modal. Lo usan las dos vistas que muestran
   pasos: el plan semanal (/menus) y la ficha de receta (/menus/recetas). */
(function () {
    'use strict';

    // Gemela de SUBRECETA_RE en services/menus_helpers.py
    const MARCADOR = /\[subreceta\]\(\s*([^)]*?)\s*\)/g;

    let catalogoPromise = null;   // {id: nombre}, se pide una vez por página
    let catalogoCache = {};       // {id: nombre} una vez resuelto
    let catalogoListo = false;
    const recetasCache = {};      // {id: receta normalizada}
    let pilaAbierta = [];         // cadena de subrecetas abiertas (evita bucles visuales)
    let ultimaTrigger = null;     // enlace que abrió el modal, para devolverle el foco

    function esc(s) {
        return String(s).replace(/[&<>"']/g, c => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    // --- Resolución de enlaces (espejo del lado del servidor) ---

    const TRADUCCION = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u', 'ñ': 'n',
        'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u'
    };

    function slug(texto) {
        const s = String(texto || '').toLowerCase().split('')
            .map(c => TRADUCCION[c] || c).join('')
            .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
        return s.slice(0, 60);
    }

    function norma(texto) {
        return String(texto || '').toLowerCase().split('')
            .map(c => TRADUCCION[c] || c).join('')
            .replace(/[^a-z0-9]+/g, ' ').trim();
    }

    function catalogo() {
        if (!catalogoPromise) {
            catalogoPromise = new Promise(function (resolver) {
                $.getJSON('/menus/api/recetas')
                    .done(function (datos) {
                        const mapa = {};
                        (datos || []).forEach(function (r) { mapa[r.id] = r.nombre; });
                        resolver(mapa);
                    })
                    .fail(function () { resolver({}); });
            });
        }
        return catalogoPromise;
    }

    // id exacto → slug → nombre. Devuelve el id o null si ya no existe.
    function resolverEnCatalogo(texto, mapa) {
        const t = String(texto || '').trim();
        if (!t) return null;
        if (mapa[t] !== undefined) return t;
        const s = slug(t);
        if (mapa[s] !== undefined) return s;
        const clave = norma(t);
        const gemelas = Object.keys(mapa).filter(id => norma(mapa[id]) === clave);
        return gemelas.length === 1 ? gemelas[0] : null;
    }

    // --- Pintado de pasos ---

    function chipHtml(crudo, cadena) {
        const id = crudo.match(/^[a-z0-9_]+$/) ? crudo : slug(crudo);
        const anidada = id && cadena.indexOf(id) !== -1;
        const clases = 'subreceta-chip' + (anidada ? ' subreceta-chip-anidada' : ' subreceta-rota');
        const atributo = anidada
            ? ' title="Esta subreceta ya está abierta en esta cadena"'
            : ' title="Subreceta no encontrada: ' + esc(crudo) + '"';
        return '<span class="' + clases + '" role="button" tabindex="0" aria-disabled="true"' + atributo + '>' +
               '<i class="fas fa-diagram-project" aria-hidden="true"></i>' +
               '<span class="subreceta-chip-nombre">' + esc(crudo) + '</span>' +
               '<i class="fas fa-question-circle subreceta-chip-aviso" aria-hidden="true"></i></span>';
    }

    function chipEnlace(id, nombre) {
        return '<button type="button" class="subreceta-chip" data-subreceta="' + esc(id) + '"' +
               ' aria-haspopup="dialog">' +
               '<i class="fas fa-diagram-project" aria-hidden="true"></i>' +
               '<span class="subreceta-chip-nombre">' + esc(nombre || id) + '</span></button>';
    }

    // Etiqueta de un enlace, con el nombre resuelto si la receta existe.
    // `cadena` son los ids ya abiertos por encima (dentro del modal).
    function chipPara(crudo, cadena) {
        const id = resolverEnCatalogo(crudo, catalogoCache) ||
                   (/^[a-z0-9_]+$/.test(crudo) ? crudo : null);
        if (id && catalogoCache[id] !== undefined) {
            if (cadena.indexOf(id) !== -1) {
                return '<span class="subreceta-chip subreceta-chip-anidada" aria-disabled="true"' +
                       ' title="Ya la has abierto más arriba en esta cadena">' +
                       '<i class="fas fa-diagram-project" aria-hidden="true"></i>' +
                       '<span class="subreceta-chip-nombre">' + esc(catalogoCache[id]) + '</span></span>';
            }
            return chipEnlace(id, catalogoCache[id]);
        }
        if (id && !catalogoListo) {
            // El catálogo aún no ha llegado: chip provisional que se refresca luego.
            return chipEnlace(id, crudo);
        }
        return chipHtml(crudo, cadena);
    }

    /* HTML de un paso: texto normal con los enlaces a subreceta como chips. */
    function pasoHtml(paso, cadena) {
        cadena = cadena || [];
        const texto = String(paso === null || paso === undefined ? '' : paso);
        const re = new RegExp(MARCADOR.source, 'g');
        let html = '';
        let ultimo = 0;
        let m;
        while ((m = re.exec(texto)) !== null) {
            html += esc(texto.slice(ultimo, m.index));
            html += chipPara((m[1] || '').trim(), cadena);
            ultimo = m.index + m[0].length;
        }
        html += esc(texto.slice(ultimo));
        return html;
    }

    function pasosHtml(pasos, cadena) {
        return (pasos || []).map(function (p) { return '<li>' + pasoHtml(p, cadena) + '</li>'; }).join('');
    }

    // --- Pasos ya pintados por otras vistas (ficha de receta, plan semanal) ---
    // Esas vistas escriben el paso como texto plano; aquí se sustituyen sus enlaces
    // por la etiqueta clicable. Cada <li> se marca para no repasarlo dos veces.

    function pintarLista(ol) {
        Array.prototype.forEach.call(ol.children, function (li) {
            if (li.dataset.subrecetaPintado) return;
            li.dataset.subrecetaPintado = '1';
            const texto = li.textContent;
            if (texto.indexOf('[subreceta]') === -1) return;
            // split con grupo: [texto, id, texto, id, ...]
            const partes = texto.split(MARCADOR);
            let trozos = [];
            partes.forEach(function (parte, i) {
                const trozo = i % 2 === 1 ? chipPara(String(parte).trim(), texto) : esc(parte);
                if (trozo) trozos.push(trozo);
            });
            if (trozos.length) li.innerHTML = trozos.join(' ');
        });
    }

    function listasDentro(nodo) {
        const hay = [];
        if (!nodo || nodo.nodeType !== 1) return hay;
        if (nodo.classList && nodo.classList.contains('pasos-lista')) hay.push(nodo);
        if (nodo.querySelectorAll) Array.prototype.push.apply(hay, nodo.querySelectorAll('.pasos-lista'));
        return hay;
    }

    function pintarEnlacesEn(raiz) { listasDentro(raiz).forEach(pintarLista); }

    function vigilarCambiosDOM() {
        const cuerpo = document.body;
        if (!cuerpo || typeof MutationObserver === 'undefined') return;
        let pendiente = null;
        const observador = new MutationObserver(function (mutaciones) {
            let tocado = false;
            mutaciones.forEach(function (m) {
                if (tocado) return;
                tocado = listasDentro(m.target).length > 0;
                if (!tocado) {
                    Array.prototype.forEach.call(m.addedNodes || [], function (n) {
                        if (!tocado) tocado = listasDentro(n).length > 0;
                    });
                }
            });
            if (!tocado) return;
            // Un solo repaso por turno del lazo: pintar un paso modifica el DOM y el
            // propio observador lo vería volver a cambiar.
            if (pendiente) return;
            pendiente = Promise.resolve().then(function () {
                pendiente = null;
                pintarEnlacesEn(document);
            });
        });
        observador.observe(cuerpo, { childList: true, subtree: true });
    }

    // --- Detalle de receta (se usa dentro del modal) ---

    function valorIngrediente(data) {
        if (typeof data === 'string' || typeof data === 'number') return String(data);
        if (data && typeof data === 'object') {
            const partes = [];
            if (data.val !== undefined && data.val !== null) {
                partes.push(window.formatearNumero(data.val) + (data.unit ? ' ' + data.unit : ''));
            } else if (data.unit) {
                partes.push(data.unit);
            }
            return partes.join(' ');
        }
        return '';
    }

    function detalleHtml(receta) {
        let html = '<div class="recipe-detail">';

        if (receta.ingredientes && Object.keys(receta.ingredientes).length) {
            html += '<div class="section-title"><i class="fas fa-leaf"></i> Ingredientes</div><ul class="ingredient-list">';
            Object.keys(receta.ingredientes).forEach(function (clave) {
                const dato = receta.ingredientes[clave];
                const opcional = !!(dato && typeof dato === 'object' && dato.opcional === true);
                const cantidad = valorIngrediente(dato);
                html += '<li class="' + (opcional ? 'optional-ingredient' : '') + '"><strong>' + esc(clave) + '</strong>' +
                        (cantidad ? ': ' + esc(cantidad) : '') +
                        (opcional ? ' <span class="badge bg-warning text-dark">(Opcional)</span>' : '') + '</li>';
            });
            html += '</ul>';
        } else {
            html += '<p class="text-muted"><i class="fas fa-info-circle"></i> Sin ingredientes propios.</p>';
        }

        if (receta.utensilios && receta.utensilios.length) {
            html += '<div class="section-title"><i class="fas fa-blender"></i> Utensilios</div>' +
                    '<ul class="ingredient-list">' +
                    receta.utensilios.map(function (u) { return '<li>' + esc(u) + '</li>'; }).join('') + '</ul>';
        }

        html += '<div class="section-title"><i class="fas fa-clipboard-list"></i> Preparación</div>';
        if (receta.pasos && receta.pasos.length) {
            html += '<ol class="recipe-steps pasos-lista">' + pasosHtml(receta.pasos, pilaAbierta) + '</ol>';
        } else {
            html += '<p class="text-muted"><i class="fas fa-info-circle"></i> Esta receta no tiene pasos indicados.</p>';
        }

        if (receta.notas) {
            html += '<div class="section-title"><i class="fas fa-sticky-note"></i> Notas</div><p>' +
                    esc(receta.notas) + '</p>';
        }

        html += '</div>';
        return html;
    }

    function rutaHtml() {
        if (pilaAbierta.length < 2) return '';
        const ultimo = pilaAbierta.length - 1;
        return '<p class="subreceta-ruta small"><i class="fas fa-sitemap" aria-hidden="true"></i> ' +
               pilaAbierta.map(function (id, i) {
                   const nombre = esc(catalogoCache[id] || id);
                   // La última es la receta abierta; las de antes son saltos de vuelta.
                   if (i === ultimo) {
                       return '<span class="subreceta-ruta-actual" aria-current="step">' + nombre + '</span>';
                   }
                   return '<button type="button" class="subreceta-ruta-enlace" data-subreceta="' + esc(id) + '"' +
                          ' title="Volver a ' + nombre + '">' + nombre + '</button>';
               }).join(' <i class="fas fa-angle-right" aria-hidden="true"></i> ') + '</p>';
    }

    function cargarReceta(id) {
        if (recetasCache[id]) return Promise.resolve(recetasCache[id]);
        return new Promise(function (resolver) {
            $.getJSON('/menus/api/receta/' + encodeURIComponent(id))
                .done(function (receta) { recetasCache[id] = receta; resolver(receta); })
                .fail(function () { resolver(null); });
        });
    }

    function pintarModal() {
        const modalEl = document.getElementById('subreceta-modal');
        if (!modalEl) return;
        const id = pilaAbierta[pilaAbierta.length - 1];
        const titulo = catalogoCache[id] || id;
        document.getElementById('subreceta-modal-titulo-texto').textContent = titulo;

        const cuerpo = document.getElementById('subreceta-modal-body');
        // Al cambiar el contenido se destruye el botón que se pulsó; si el foco estaba
        // dentro del modal, se pasa al propio diálogo (si no, Esc dejaría de cerrar).
        const focoDentro = modalEl.classList.contains('show') && modalEl.contains(document.activeElement);
        cargarReceta(id).then(function (receta) {
            if (!receta) {
                cuerpo.innerHTML = '<div class="alert alert-warning"><i class="fas fa-exclamation-triangle"></i> ' +
                                   'No se pudo cargar la subreceta ' + esc(id) + '.</div>';
                return;
            }
            cuerpo.innerHTML = rutaHtml() + detalleHtml(receta);
            if (focoDentro) modalEl.focus();
            cuerpo.scrollTop = 0;
            const dialog = modalEl.querySelector('.modal-content');
            if (dialog) dialog.scrollTop = 0;
        });
    }

    function abrirModal() {
        const modalEl = document.getElementById('subreceta-modal');
        if (!modalEl || typeof bootstrap === 'undefined') return;
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    // --- Catálogo: cuando llega, se refrescan las etiquetas de los chips ya pintados ---

    function aplicarCatalogo(mapa) {
        catalogoCache = mapa;
        catalogoListo = true;
        // Los chips pintados antes de tener el catálogo muestran el id en crudo.
        $('.subreceta-chip[data-subreceta]').each(function () {
            const id = String($(this).data('subreceta'));
            if (mapa[id] === undefined) return;
            const etiqueta = $(this).find('.subreceta-chip-nombre');
            if (etiqueta.length && (!etiqueta.text() || etiqueta.text() === id)) etiqueta.text(mapa[id]);
        });
    }

    function refrescarEtiquetas() {
        catalogo().then(aplicarCatalogo);
    }

    // --- Apertura desde cualquier vista ---

    $(document).on('click', '.subreceta-chip[data-subreceta]', function () {
        // Solo se recuerda el salto que abre el modal desde la página: al cerrar, el foco
        // tiene que volver a ese elemento (los chips de dentro del modal se destruyen).
        if (!pilaAbierta.length) ultimaTrigger = this;
        const id = String($(this).data('subreceta'));
        const base = pilaAbierta.length ? pilaAbierta.slice() : [];
        pilaAbierta = base.concat([id]);
        pintarModal();
        abrirModal();
    });

    // Volver por donde se vino: el breadcrumb recorta la cadena en lugar de alargarla.
    $(document).on('click', '.subreceta-ruta-enlace', function () {
        const id = String($(this).data('subreceta'));
        const posicion = pilaAbierta.indexOf(id);
        if (posicion === -1) return;
        pilaAbierta = pilaAbierta.slice(0, posicion + 1);
        pintarModal();
    });

    $(document).on('keydown', '.subreceta-chip[role="button"]', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            mostrarToast('Esa subreceta ya no existe: ' + $(this).find('.subreceta-chip-nombre').text(), 'warning');
        }
    });

    $(document).ready(function () {
        const modalEl = document.getElementById('subreceta-modal');
        if (modalEl) {
            modalEl.addEventListener('hidden.bs.modal', function () {
                pilaAbierta = [];
                if (ultimaTrigger && document.contains(ultimaTrigger)) {
                    ultimaTrigger.focus();
                }
                ultimaTrigger = null;
            });
        }
        refrescarEtiquetas();
        pintarEnlacesEn(document);
        vigilarCambiosDOM();
    });

    window.pasoHtml = pasoHtml;
    window.pasosHtml = pasosHtml;
    window.pintarEnlacesSubrecetas = pintarEnlacesEn;
    // Para el editor de recetas: resolver un texto escrito a mano y pintar sus avisos.
    window.resolverSubrecetaTexto = function (texto, mapa) {
        return resolverEnCatalogo(texto, mapa || catalogoCache);
    };
    window.verSubreceta = function (id) {
        pilaAbierta = [String(id)];
        pintarModal();
        abrirModal();
    };
    window.refrescarEtiquetasSubrecetas = refrescarEtiquetas;
})();
