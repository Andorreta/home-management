"""
Generación de menús en segundo plano.

El POST de /menus/api/generar ya no espera a la IA: crea un trabajo persistido
en data/generacion/<job_id>.json, lanza un hilo y responde 202 al instante.
La UI consulta el estado con GET /menus/api/generar/<job_id> y muestra el
resultado cuando el trabajo termina.

Se guarda en ficheros (no en memoria) porque gunicorn tiene dos workers: el
POST y las consultas de estado pueden caer en procesos distintos. Cada fichero
se escribe de forma atómica (tmp + os.replace) para que un GET nunca lea JSON
a medias.
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime

from . import generation

ACTIVOS = ('pendiente', 'en_proceso')
log = logging.getLogger(__name__)


def _ahora():
    return datetime.now().isoformat(timespec='seconds')


def _proceso_vivo(pid):
    """True si el proceso existe. Sirve para detectar trabajos huérfanos tras
    un reinicio del servidor sin penalizar a los que siguen generando."""
    if not pid:
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


class GeneracionJobs:
    def __init__(self, data_dir, logger=None):
        self.directory = os.path.join(data_dir, 'generacion')
        os.makedirs(self.directory, exist_ok=True)
        self.logger = logger or log

    # --- Persistencia ---

    def _ruta(self, job_id):
        return os.path.join(self.directory, job_id + '.json')

    @staticmethod
    def _id_valido(job_id):
        return bool(job_id) and all(c.isalnum() or c in '_-' for c in job_id)

    def _escribir(self, job):
        ruta = self._ruta(job['id'])
        tmp = ruta + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(job, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(tmp, ruta)

    def _leer(self, job_id):
        if not self._id_valido(job_id):
            return None
        try:
            with open(self._ruta(job_id), 'r', encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _marcar_si_huerfano(self, job):
        """Si el proceso que generaba ya no existe, convierte el trabajo en error."""
        if job.get('estado') in ACTIVOS and not _proceso_vivo(job.get('pid')):
            job['estado'] = 'error'
            job['error'] = 'La generación se interrumpió (el servidor cambió de proceso). Vuelve a intentarlo.'
            job['actualizado'] = _ahora()
            job['pid'] = None
            self._escribir(job)
        return job

    # --- API interna ---

    def obtener(self, job_id):
        job = self._leer(job_id)
        if not job:
            return None
        return self._marcar_si_huerfano(job)

    def activos(self):
        """Trabajos pendientes o en proceso, el más reciente primero."""
        jobs = []
        try:
            nombres = os.listdir(self.directory)
        except OSError:
            return jobs
        for nombre in nombres:
            if not nombre.endswith('.json'):
                continue
            job = self._leer(nombre[:-5])
            if not job:
                continue
            job = self._marcar_si_huerfano(job)
            if job.get('estado') in ACTIVOS:
                jobs.append(job)
        jobs.sort(key=lambda j: j.get('creado', ''), reverse=True)
        return jobs

    def crear(self, store, cfg, fecha_inicio, fecha_fin, feedback=''):
        """Registra el trabajo y lanza la generación en un hilo daemon."""
        feedback = str(feedback or '')[:1000]

        # Si ya hay una generación idéntica en curso, se reutiliza: así una
        # recarga de la página no crea dos trabajos para lo mismo.
        for job in self.activos():
            if (job.get('fecha_inicio') == fecha_inicio and
                    job.get('fecha_fin') == fecha_fin and
                    job.get('feedback', '') == feedback):
                return job

        job_id = datetime.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
        job = {
            'id': job_id,
            'estado': 'pendiente',
            'creado': _ahora(),
            'actualizado': _ahora(),
            'pid': os.getpid(),
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'feedback': feedback,
        }
        self._escribir(job)

        hilo = threading.Thread(
            target=self._ejecutar,
            args=(job_id, store, cfg, fecha_inicio, fecha_fin, feedback),
            name='generacion-' + job_id,
            daemon=True,
        )
        hilo.start()
        return job

    def _ejecutar(self, job_id, store, cfg, fecha_inicio, fecha_fin, feedback):
        job = self._leer(job_id)
        if not job:
            return

        job['estado'] = 'en_proceso'
        job['actualizado'] = _ahora()
        job['pid'] = os.getpid()
        self._escribir(job)

        try:
            respuesta, status = generation.generar_menu(
                store, cfg, fecha_inicio, fecha_fin, feedback=feedback)
            if status == 200:
                job['estado'] = 'terminado'
                job['resultado'] = respuesta
                job.pop('error', None)
            else:
                job['estado'] = 'error'
                job['error'] = respuesta.get('error', 'Error al generar el menú')
        except Exception as exc:
            job['estado'] = 'error'
            job['error'] = f'Error inesperado al generar el menú: {exc}'
            self.logger.exception('Fallo generando menú %s', job_id)
        finally:
            job['actualizado'] = _ahora()
            self._escribir(job)
