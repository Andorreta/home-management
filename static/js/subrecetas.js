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

    /* HTML de un paso: texto normal con los enlaces a subreceta como chips.
       El marcador «[opcional]» del final se quita del texto y se muestra como
       etiqueta discreta. */
    const OPCIONAL = /\s*\[opcional\]\s*$/;

    function etiquetaOpcional() {
        return ' <span class="paso-opcional"><i class="fas fa-circle-half-stroke" ' +
               'aria-hidden="true"></i> opcional</span>';
    }

    function pasoHtml(paso, cadena) {
        cadena = cadena || [];
        let texto = String(paso === null || paso === undefined ? '' : paso);
        const opcional = OPCIONAL.test(texto);
        if (opcional) texto = texto.replace(OPCIONAL, '');
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
        if (opcional) html += etiquetaOpcional();
        return html;
    }

    function pasosHtml(pasos, cadena) {
        return (pasos || []).map(function (p) {
            const texto = String(p == null ? '' : p);
            const re = new RegExp(MARCADOR.source, 'g');
            const crudos = [];
            let m;
            while ((m = re.exec(texto)) !== null) crudos.push((m[1] || '').trim());
            const atributo = crudos.length
                ? ' data-subcrudos="' + esc(crudos.join('\u0001')) + '"' : '';
            return '<li' + atributo + '>' + pasoHtml(p, cadena) + '</li>';
        }).join('');
    }

    // --- Pasos ya pintados por otras vistas (ficha de receta, plan semanal) ---
    // Esas vistas escriben el paso como texto plano; aquí se sustituyen sus enlaces
    // por la etiqueta clicable. Cada <li> se marca para no repasarlo dos veces.

    function pintarLista(ol) {
        Array.prototype.forEach.call(ol.children, function (li) {
            if (!li.dataset.subrecetaPintado) {
                li.dataset.subrecetaPintado = '1';
                let texto = li.textContent;
                const opcional = OPCIONAL.test(texto);
                if (opcional) texto = texto.replace(OPCIONAL, '');
                if (texto.indexOf('[subreceta]') !== -1 || opcional) {
                    // split con grupo: [texto, id, texto, id, ...]
                    const partes = texto.split(MARCADOR);
                    let trozos = [];
                    const crudos = [];
                    partes.forEach(function (parte, i) {
                        if (i % 2 === 1) {
                            const crudo = String(parte).trim();
                            trozos.push(chipPara(crudo, texto));
                            crudos.push(crudo);
                        } else {
                            const trozo = esc(parte);
                            if (trozo) trozos.push(trozo);
                        }
                    });
                    if (opcional) trozos.push(etiquetaOpcional());
                    if (trozos.length) li.innerHTML = trozos.join(' ');
                    if (crudos.length) li.dataset.subcrudos = crudos.join('\u0001');
                }
            }
            // Y los pasos de cada subreceta se pegan justo debajo, como pasos más
            // de esta lista: así no hace falta abrir modales anidados para verlos.
            // Vale tanto para los pasos recién pintados como para los que ya llegaron
            // con el chip puesto (ficha y plan usan pasosHtml al construirse).
            desplegarEnlaces(li, [], 0);
        });
    }

    // Despliega todos los enlaces que un <li> anuncia en data-subcrudos.
    function desplegarEnlaces(li, cadena, nivel) {
        String(li.dataset.subcrudos || '').split('\u0001').forEach(function (crudo) {
            if (!crudo) return;
            const id = resolverEnCatalogo(crudo, catalogoCache) ||
                       (/^[a-z0-9_]+$/.test(crudo) ? crudo : null);
            if (id && catalogoCache[id] !== undefined) expandirSubpasos(li, id, cadena, nivel);
        });
    }

    // Pega los pasos de la subreceta `id` debajo del <li> que la enlaza. Son <li>
    // normales (solo sigue la numeración); el título ya lo lleva el chip del paso.
    // `cadena` = recetas ya desplegadas por encima: ni se repiten ni se buclea.
    function expandirSubpasos(li, id, cadena, nivel) {
        const hechas = (li.dataset.subpasos || '').split(',').filter(Boolean);
        if (hechas.indexOf(id) !== -1) return;
        hechas.push(id);
        li.dataset.subpasos = hechas.join(',');
        if (cadena.indexOf(id) !== -1 || nivel >= 4) return;
        if (pilaAbierta.indexOf(id) !== -1) return;   // ya es la receta abierta en el modal
        cargarReceta(id).then(function (receta) {
            if (!receta || !(receta.pasos || []).length) return;
            const lista = li.parentNode;
            if (!lista) return;
            const cadenaHija = cadena.concat([id]);
            let despuesDe = li;
            receta.pasos.forEach(function (paso) {
                // Si el paso de la subreceta es SOLO un enlace a otra subreceta, no
                // gasta un número propio: su chip se pega al de arriba («A → B») y los
                // pasos de B se pegan aquí mismo, antes de lo que quede de A. Así
                // «Pasta con atún y tomate → Pasta cocida» ocupa un solo paso.
                if (despuesDe === li) {
                    const encajado = resolverCrudo(enlaceSolitario(paso));
                    if (encajado && encajado !== id && cadenaHija.indexOf(encajado) === -1 &&
                        pilaAbierta.indexOf(encajado) === -1 && nivel + 1 < 5) {
                        encadenarChip(li, id, catalogoCache[encajado] || encajado);
                        expandirSubpasos(li, encajado, cadenaHija, nivel + 1);
                        return;
                    }
                }
                const re = new RegExp(MARCADOR.source, 'g');
                const crudos = [];
                let m;
                while ((m = re.exec(String(paso == null ? '' : paso))) !== null) {
                    crudos.push((m[1] || '').trim());
                }
                const sub = document.createElement('li');
                sub.innerHTML = pasoHtml(paso, cadenaHija);
                sub.dataset.subrecetaPintado = '1';
                if (crudos.length) sub.dataset.subcrudos = crudos.join('\u0001');
                lista.insertBefore(sub, despuesDe.nextSibling);
                despuesDe = sub;
                desplegarEnlaces(sub, cadenaHija, nivel + 1);
            });
        });
    }

    // ¿El paso es únicamente un enlace a otra subreceta (sin texto alrededor)?
    function enlaceSolitario(paso) {
        const s = String(paso == null ? '' : paso).trim();
        if (OPCIONAL.test(s)) return null;
        const m = s.match(/^\[subreceta\]\(\s*([^)]*?)\s*\)$/);
        return m ? String(m[1] || '').trim() : null;
    }

    // id resuelto del catálogo, o null si la receta no existe.
    function resolverCrudo(crudo) {
        if (!crudo) return null;
        const id = resolverEnCatalogo(crudo, catalogoCache) ||
                   (/^[a-z0-9_]+$/.test(crudo) ? crudo : null);
        return id && catalogoCache[id] !== undefined ? id : null;
    }

    // Añade «→ Título» al chip del paso que enlaza la subreceta `id`.
    function encadenarChip(li, id, etiqueta) {
        let chip = null;
        if (/^[a-z0-9_]+$/.test(id)) {
            chip = li.querySelector('.subreceta-chip[data-subreceta="' + id + '"]');
        }
        if (!chip) {
            const chips = li.querySelectorAll('.subreceta-chip');
            chip = chips.length === 1 ? chips[0] : null;   // con varios, no adivinamos
        }
        if (!chip || chip.querySelector('.subreceta-chip-flecha')) return;
        chip.insertAdjacentHTML('beforeend',
            '<span class="subreceta-chip-flecha" aria-hidden="true">→</span>' +
            '<span class="subreceta-chip-nombre">' + esc(etiqueta) + '</span>');
        chip.setAttribute('title', 'Subrecetas: ' + chip.textContent.trim());
    }

    // Si los pasos se pintaron antes de que el catálogo estuviera listo, al
    // llegar éste hay que desplegar lo que entonces no se pudo resolver.
    function repasarExpansiones() {
        document.querySelectorAll('.pasos-lista li[data-subcrudos]').forEach(function (li) {
            if (li.dataset.subpasos) return;
            String(li.dataset.subcrudos).split('\u0001').forEach(function (crudo) {
                if (!crudo) return;
                const id = resolverEnCatalogo(crudo, catalogoCache) ||
                           (/^[a-z0-9_]+$/.test(crudo) ? crudo : null);
                if (id && catalogoCache[id] !== undefined) expandirSubpasos(li, id, [], 0);
            });
        });
    }

    function listasDentro(nodo) {
        const hay = [];
        // document y los fragmentos también valen como raíz (nodeType 9 y 11).
        if (!nodo || (nodo.nodeType !== 1 && nodo.nodeType !== 9 && nodo.nodeType !== 11)) return hay;
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
            const aportesIng = receta.aportes_subrecetas && receta.aportes_subrecetas.ingredientes;
            html += '<div class="section-title"><i class="fas fa-leaf"></i> Ingredientes</div><ul class="ingredient-list">';
            Object.keys(receta.ingredientes).forEach(function (clave) {
                const dato = receta.ingredientes[clave];
                const opcional = !!(dato && typeof dato === 'object' && dato.opcional === true);
                const cantidad = valorIngrediente(dato);
                const aporte = aportesEtiqueta(aportesDe(aportesIng, clave));
                html += '<li class="' + (opcional ? 'optional-ingredient' : '') + (aporte ? ' item-aportado' : '') +
                        '">' + nombreIngredienteHtml(clave) +
                        (cantidad ? ': ' + esc(cantidad) : '') +
                        (opcional ? ' <span class="badge bg-warning text-dark">(Opcional)</span>' : '') +
                        (aporte ? ' ' + aporte : '') + '</li>';
            });
            html += '</ul>';
        } else {
            html += '<p class="text-muted"><i class="fas fa-info-circle"></i> Sin ingredientes propios.</p>';
        }

        if (receta.utensilios && receta.utensilios.length) {
            const aportesUt = receta.aportes_subrecetas && receta.aportes_subrecetas.utensilios;
            html += '<div class="section-title"><i class="fas fa-blender"></i> Utensilios</div>' +
                    '<ul class="ingredient-list">' +
                    receta.utensilios.map(function (u) {
                        const aporte = aportesEtiqueta(aportesDe(aportesUt, u));
                        return '<li class="' + (aporte ? 'item-aportado' : '') + '">' + esc(u) +
                               (aporte ? ' ' + aporte : '') + '</li>';
                    }).join('') + '</ul>';
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
            // Los pasos de las subrecetas se despliegan debajo de su enlace, igual
            // que en la ficha y el plan (la pila abierta evita desplegar un ancestro).
            repasarExpansiones();
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
        repasarExpansiones();
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
    window.nombreIngredienteHtml = nombreIngredienteHtml;

    // --- Lo que aporta cada subreceta, para distinguirlo en las listas ---
    //
    // La API manda en `aportes_subrecetas` los ingredientes y utensilios que llegan
    // de recetas enlazadas (a cualquier nivel). Aquí se buscan y se pintan con su
    // etiqueta, avisando de que no hay que repetirlos en la receta de arriba.

    // --- Ingredientes con sustitutos: «pasta[altern("pasta fresca", "ñoquis")]» ---
    // Se muestra «pasta / pasta fresca / ñoquis»: el base va igual que siempre y
    // los sustitutos, en gris, detrás con barras. Cada sustituto puede llevar su
    // propia cantidad tras una barra vertical: «"mantequilla|30 g"».
    // Espejo de ALTERN_RE del servidor.

    const ALTERN = /\s*\[altern\(([^\]]*)\)\]/;

    function alternativaNombres(clave) {
        const s = String(clave == null ? '' : clave);
        const m = s.match(ALTERN);
        const alts = m ? m[1].split(',').map(function (a) {
            a = a.trim().replace(/^"|"$/g, '');
            const i = a.indexOf('|');
            if (i === -1) return { nombre: a.trim(), cantidad: '' };
            return { nombre: a.slice(0, i).trim(), cantidad: a.slice(i + 1).trim() };
        }).filter(function (a) { return a.nombre; }) : [];
        return { base: s.replace(ALTERN, '').trim(), alts: alts };
    }

    function nombreIngredienteHtml(clave) {
        const p = alternativaNombres(clave);
        let html = '<strong>' + esc(p.base) + '</strong>';
        if (p.alts.length) {
            html += '<span class="ing-alternativos"> / ' + p.alts.map(function (a) {
                return esc(a.nombre) +
                       (a.cantidad ? ' <span class="ing-altern-cantidad">' + esc(a.cantidad) + '</span>' : '');
            }).join(' / ') + '</span>';
        }
        return html;
    }

    function claveNormal(texto) {
        return String(texto == null ? '' : texto).replace(ALTERN, '').trim().toLowerCase().normalize('NFC');
    }

    // Busca en {clave: [nombres]} sin depender de mayúsculas ni tildes
    function aportesDe(mapa, clave) {
        if (!mapa) return [];
        if (Object.prototype.hasOwnProperty.call(mapa, clave)) return mapa[clave] || [];
        const k = claveNormal(clave);
        for (const punto in mapa) {
            if (claveNormal(punto) === k) return mapa[punto] || [];
        }
        return [];
    }

    // Etiqueta discreta: «de «Salsa de tomate»»
    function aportesEtiqueta(nombres) {
        if (!nombres || !nombres.length) return '';
        const primeros = nombres.slice(0, 2);
        let texto = 'de ' + primeros.map(function (n) { return '«' + n + '»'; }).join(' y ');
        if (nombres.length > primeros.length) texto += ' +' + (nombres.length - primeros.length) + ' más';
        return '<span class="aportes-sub" title="' +
               escapeHtml('Lo aportan las recetas enlazadas: ' + nombres.join(', ')) + '">' +
               '<i class="fas fa-diagram-project" aria-hidden="true"></i> ' + escapeHtml(texto) + '</span>';
    }

    // Lo que aporta una subreceta y la receta de arriba NO tiene escrito: también hace
    // falta, así que se añade a su misma lista, marcado con el nombre de su origen.
    function aportesExtras(mapa, propios) {
        if (!mapa) return [];
        const vistas = {};
        (propios || []).forEach(function (p) { vistas[claveNormal(p)] = true; });
        const extras = [];
        for (const clave in mapa) {
            if (!vistas[claveNormal(clave)]) extras.push({ clave: clave, nombres: mapa[clave] || [] });
        }
        extras.sort(function (a, b) { return a.clave.localeCompare(b.clave, 'es'); });
        return extras;
    }

    // Resumen de las recetas enlazadas y lo que cada una trae a la de arriba
    function aportesResumen(aportes) {
        const arbol = (aportes && aportes.arbol) || [];
        if (!arbol.length) return '';
        let html = '<div class="aportes-resumen"><div class="section-title">' +
                   '<i class="fas fa-diagram-project"></i> Usa estas recetas</div>';
        arbol.forEach(function (rama) {
            html += '<div class="aportes-rama">';
            html += '<span class="aportes-nombre">' + escapeHtml(rama.nombre) + '</span>';
            if (!rama.directa) {
                html += ' <span class="aportes-anidada" title="La enlaza otra receta enlazada">(enlazada por otra)</span>';
            }
            if (rama.ingredientes.length) {
                html += '<div class="aportes-detalle"><i class="fas fa-leaf"></i> ' +
                        escapeHtml(rama.ingredientes.join(', ')) + '</div>';
            }
            if (rama.utensilios.length) {
                html += '<div class="aportes-detalle"><i class="fas fa-blender"></i> ' +
                        escapeHtml(rama.utensilios.join(', ')) + '</div>';
            }
            html += '</div>';
        });
        html += '<p class="text-muted small mb-0 mt-1"><i class="fas fa-info-circle"></i> ' +
                'Lo que traen esas recetas ya cuenta para la lista de la compra: ' +
                'no lo repitas aquí.</p></div>';
        return html;
    }

    window.aportesDe = aportesDe;
    window.aportesEtiqueta = aportesEtiqueta;
    window.aportesExtras = aportesExtras;
    window.aportesResumen = aportesResumen;
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
