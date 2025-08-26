"""
title: Enhanced Image Generation Tool for OpenWebUI
author: FYURI
description: Tool that generates images directly via Tool Calling using the ComfyUI workflow configured in OpenWebUI. Automatically converts local paths to base64, supports multiple emission methods (direct, markdown, html), and allows advanced valve configuration for both administrators and users.
required_open_webui_version: 0.6.0
version: 0.1.5
licence: MIT
"""

import json
import traceback
from pathlib import Path
import base64
from typing import Optional, List, Dict, Any, Literal
import logging
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        """Configuración mediante Valves de OpenWebUI - Solo para Admins"""

        DEBUG_ENABLED: bool = Field(
            default=False,
            description="Habilita logging detallado para debugging de la tool",
        )
        VERBOSE_LOGGING: bool = Field(
            default=False,
            description="Habilita logging extremadamente detallado (incluye contenido completo de respuestas)",
        )
        EMIT_METHOD_PRIORITY: Literal["auto", "direct", "markdown", "html"] = Field(
            default="auto",
            description="Método preferido para emitir imágenes: auto=intenta todos, direct=directo primero, markdown=markdown primero, html=html primero",
        )
        MAX_FILE_SIZE_MB: int = Field(
            default=10,
            description="Tamaño máximo de archivo en MB para conversión a base64",
        )
        SUPPORTED_FORMATS: str = Field(
            default="png,jpg,jpeg,webp,gif,bmp,tiff",
            description="Formatos de imagen soportados (separados por comas)",
        )

    class UserValves(BaseModel):
        """Configuración por usuario - Cada usuario puede cambiar esto"""

        SHOW_PROCESSING_STATUS: bool = Field(
            default=True,
            description="Mostrar estados de procesamiento durante la generación",
        )
        AUTO_ALT_TEXT: bool = Field(
            default=True,
            description="Generar automáticamente texto alternativo descriptivo para las imágenes",
        )
        pass

    def __init__(self):
        # Inicializar valves
        self.valves = self.Valves()

        # Configurar logger específico para esta tool
        self.logger = logging.getLogger("image_gen_tool")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "[%(asctime)s] [IMAGE_GEN] [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self._update_log_level()
        pass

    def _update_log_level(self):
        """Actualiza el nivel de logging según las valves"""
        if self.valves.VERBOSE_LOGGING:
            self.logger.setLevel(logging.DEBUG)
        elif self.valves.DEBUG_ENABLED:
            self.logger.setLevel(logging.INFO)
        else:
            self.logger.setLevel(logging.WARNING)

    def _log_debug(self, message: str):
        """Log debug con control de verbosidad"""
        if self.valves.VERBOSE_LOGGING:
            self.logger.debug(message)

    def _log_info(self, message: str):
        """Log info con control de debug"""
        if self.valves.DEBUG_ENABLED:
            self.logger.info(message)

    def _log_warning(self, message: str):
        """Log warning siempre activo"""
        self.logger.warning(message)

    def _log_error(self, message: str):
        """Log error siempre activo"""
        self.logger.error(message)

    async def generate_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        workflow: Optional[str] = None,
        sampler: Optional[str] = None,
        seed: Optional[int] = None,
        __request__=None,
        __user__=None,
        __event_emitter__=None,
    ) -> Dict[str, Any]:

        # Actualizar nivel de logging al inicio de cada ejecución
        self._update_log_level()

        # Obtener UserValves del usuario (robusto: acepta dicts o objetos con distintas convenciones)
        user_valves = None
        if __user__ and "valves" in __user__:
            user_valves = __user__["valves"]

        # Helper para leer de forma tolerante (dicts o objetos, distintos estilos de nombre)
        def _get_valve(uvalves, *candidates, default=None):
            if uvalves is None:
                return default
            # si es mapping/dict
            try:
                if isinstance(uvalves, dict):
                    for k in candidates:
                        if k in uvalves:
                            return uvalves[k]
                # si es objeto (pydantic model u otro)
                for k in candidates:
                    if hasattr(uvalves, k):
                        return getattr(uvalves, k)
                # chequeo por nombre insensible a mayúsculas/minúsculas en atributos del objeto
                attrs = {a.lower(): a for a in dir(uvalves)}
                for k in candidates:
                    ak = attrs.get(k.lower())
                    if ak:
                        return getattr(uvalves, ak)
            except Exception:
                pass
            return default

        # Leer valores con varias alternativas de nombre (mayúsculas, snake_case, camelCase)
        show_status = _get_valve(
            user_valves,
            "SHOW_PROCESSING_STATUS",
            "show_processing_status",
            "showProcessingStatus",
            default=True,
        )
        auto_alt_text = _get_valve(
            user_valves, "AUTO_ALT_TEXT", "auto_alt_text", "autoAltText", default=True
        )

        self._log_info(f"=== INICIANDO GENERACIÓN DE IMAGEN ===")
        self._log_info(
            f"Configuración Valves - Debug: {self.valves.DEBUG_ENABLED}, Verbose: {self.valves.VERBOSE_LOGGING}"
        )
        self._log_info(
            f"Configuración Usuario - Status: {show_status}, Alt Text: {auto_alt_text}"
        )
        self._log_info(f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
        self._log_info(f"Dimensiones: {width}x{height}, Steps: {steps}")
        self._log_debug(f"Método emisión: {self.valves.EMIT_METHOD_PRIORITY}")
        self._log_debug(f"Formatos soportados: {self.valves.SUPPORTED_FORMATS}")
        self._log_debug(f"Tamaño máximo archivo: {self.valves.MAX_FILE_SIZE_MB}MB")

        def _make_data_uri_from_b64(b64: str, mime: str = "image/png") -> str:
            if b64.startswith("data:"):
                self._log_debug("B64 ya tiene formato data URI")
                return b64
            result = f"data:{mime};base64,{b64}"
            self._log_debug(f"Convertido b64 a data URI: {mime}, longitud: {len(b64)}")
            return result

        def _path_to_data_uri(path: str, mime: str = "image/png") -> str:
            """Convierte un path local en data URI base64."""
            self._log_debug(f"Convirtiendo path a data URI: {path}")
            try:
                p = Path(path)
                if not p.exists():
                    self._log_warning(f"Archivo no encontrado: {path}")
                    return ""

                if not p.is_file():
                    self._log_warning(f"Path no es un archivo válido: {path}")
                    return ""

                # Verificar tamaño de archivo
                file_size = p.stat().st_size
                max_size_bytes = self.valves.MAX_FILE_SIZE_MB * 1024 * 1024
                if file_size > max_size_bytes:
                    self._log_error(
                        f"Archivo muy grande: {file_size/1024/1024:.2f}MB > {self.valves.MAX_FILE_SIZE_MB}MB"
                    )
                    return ""

                # Verificar extensión según configuración
                supported_exts = [
                    f".{ext.strip().lower()}"
                    for ext in self.valves.SUPPORTED_FORMATS.split(",")
                ]
                if not p.suffix.lower() in supported_exts:
                    self._log_warning(
                        f"Extensión no soportada: {p.suffix}. Soportadas: {supported_exts}"
                    )
                    return ""

                self._log_debug(
                    f"Leyendo archivo válido: {path} ({file_size/1024:.1f}KB)"
                )

                with open(p, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")

                # Detectar MIME type correcto
                mime_map = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                    ".bmp": "image/bmp",
                    ".tiff": "image/tiff",
                    ".png": "image/png",
                }
                detected_mime = mime_map.get(p.suffix.lower(), "image/png")

                result = f"data:{detected_mime};base64,{b64}"
                self._log_info(
                    f"✓ Archivo convertido: {detected_mime}, {len(b64)} chars, {file_size/1024:.1f}KB"
                )
                return result

            except Exception as e:
                self._log_error(f"Error convirtiendo path a data URI: {e}")
                if self.valves.VERBOSE_LOGGING:
                    self._log_error(f"Traceback: {traceback.format_exc()}")
                return ""

        async def _emit_status(description: str, done: bool = False):
            """Helper para emitir status con logging"""
            if not show_status:
                return

            try:
                if __event_emitter__:
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {
                                "description": description,
                                "done": done,
                            },
                        }
                    )
                    self._log_debug(f"Status emitido: {description} (done: {done})")
            except Exception as e:
                self._log_error(f"Error emitiendo status '{description}': {e}")

        async def _emit_image_direct(
            url_or_datauri: str, w: Optional[int], h: Optional[int], alt: str
        ):
            """Método directo de emisión"""
            try:
                if __event_emitter__:
                    data = {"url": url_or_datauri}
                    if w and w > 0:
                        data["width"] = w
                    if h and h > 0:
                        data["height"] = h
                    if alt:
                        data["alt"] = alt

                    await __event_emitter__({"type": "image", "data": data})
                    self._log_info("✓ Imagen emitida con método DIRECTO")
                    return True
            except Exception as e:
                self._log_warning(f"Falló método directo: {e}")
            return False

        async def _emit_image_markdown(url_or_datauri: str, alt: str):
            """Método markdown de emisión"""
            try:
                if __event_emitter__:
                    markdown_content = f"![{alt}]({url_or_datauri})"
                    await __event_emitter__(
                        {
                            "type": "message",
                            "data": {"content": markdown_content},
                        }
                    )
                    self._log_info("✓ Imagen emitida con método MARKDOWN")
                    return True
            except Exception as e:
                self._log_warning(f"Falló método markdown: {e}")
            return False

        async def _emit_image_html(
            url_or_datauri: str, w: Optional[int], h: Optional[int], alt: str
        ):
            """Método HTML de emisión"""
            try:
                if __event_emitter__:
                    html_content = f'<img src="{url_or_datauri}" alt="{alt}" style="max-width: {w or 512}px; max-height: {h or 512}px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">'
                    await __event_emitter__(
                        {"type": "message", "data": {"content": html_content}}
                    )
                    self._log_info("✓ Imagen emitida con método HTML")
                    return True
            except Exception as e:
                self._log_warning(f"Falló método HTML: {e}")
            return False

        async def _emit_image(
            url_or_datauri: str,
            w: Optional[int] = None,
            h: Optional[int] = None,
            alt: str = "",
            index: int = 1,
        ):
            """Emite imagen según configuración de prioridad en valves"""
            if not url_or_datauri:
                self._log_warning("URL o data URI vacío, no se puede emitir imagen")
                return False

            # Generar texto alternativo automático si está habilitado
            if auto_alt_text and not alt:
                alt = f"Imagen generada: {prompt[:50]}{'...' if len(prompt) > 50 else ''} - #{index}"

            self._log_info(f"Emitiendo imagen #{index}: {alt}")
            self._log_debug(f"URL length: {len(url_or_datauri)}, Dimensiones: {w}x{h}")
            self._log_debug(f"Método configurado: {self.valves.EMIT_METHOD_PRIORITY}")

            # Determinar orden de métodos según configuración
            if self.valves.EMIT_METHOD_PRIORITY == "direct":
                methods = [
                    ("directo", lambda: _emit_image_direct(url_or_datauri, w, h, alt)),
                    ("markdown", lambda: _emit_image_markdown(url_or_datauri, alt)),
                    ("html", lambda: _emit_image_html(url_or_datauri, w, h, alt)),
                ]
            elif self.valves.EMIT_METHOD_PRIORITY == "markdown":
                methods = [
                    ("markdown", lambda: _emit_image_markdown(url_or_datauri, alt)),
                    ("directo", lambda: _emit_image_direct(url_or_datauri, w, h, alt)),
                    ("html", lambda: _emit_image_html(url_or_datauri, w, h, alt)),
                ]
            elif self.valves.EMIT_METHOD_PRIORITY == "html":
                methods = [
                    ("html", lambda: _emit_image_html(url_or_datauri, w, h, alt)),
                    ("directo", lambda: _emit_image_direct(url_or_datauri, w, h, alt)),
                    ("markdown", lambda: _emit_image_markdown(url_or_datauri, alt)),
                ]
            else:  # auto (por defecto)
                methods = [
                    ("directo", lambda: _emit_image_direct(url_or_datauri, w, h, alt)),
                    ("markdown", lambda: _emit_image_markdown(url_or_datauri, alt)),
                    ("html", lambda: _emit_image_html(url_or_datauri, w, h, alt)),
                ]

            # Intentar métodos en orden
            for method_name, method_func in methods:
                self._log_debug(f"Intentando método: {method_name}")
                if await method_func():
                    return True

            self._log_error("✗ Todos los métodos de emisión fallaron")
            return False

        # Emit status inicial
        await _emit_status("Inicializando generación de imagen...")

        # ===== SOBRESCRIBIR TEMPORALMENTE OPEN WEBUI =====
        original_steps = None
        try:
            # Guardar valor original
            original_steps = __request__.app.state.config.IMAGE_STEPS
            # Sobrescribir con nuestro valor
            __request__.app.state.config.IMAGE_STEPS = steps
            self._log_info(f"🔧 Sobrescribiendo steps de Open WebUI: {steps}")
        except Exception as e:
            self._log_warning(f"No se pudo sobrescribir configuración: {e}")

        try:
            # Construir payload (ahora Open WebUI usará NUESTRO valor)
            payload = {
                "prompt": prompt,
                "size": f"{width}x{height}",
                "width": width,
                "height": height,
                "steps": steps,  # También lo enviamos por si acaso
            }
            if workflow:
                payload["workflow"] = workflow
            if sampler:
                payload["sampler"] = sampler
            if seed is not None:
                payload["seed"] = seed

            self._log_info(
                f"Payload construido (formato híbrido): size={payload['size']}, width={width}, height={height}, steps={steps}"
            )
            self._log_debug(f"Payload completo: {payload}")
            internal_err = None

            # Importaciones con logging
            self._log_debug("Importando módulos de OpenWebUI...")
            from open_webui.routers.images import image_generations, GenerateImageForm

            try:
                from open_webui.models.users import Users

                self._log_debug("Módulo Users importado exitosamente")
            except Exception as e:
                Users = None
                self._log_warning(f"No se pudo importar Users: {e}")

            # Preparar formulario
            try:
                form = GenerateImageForm(**payload)
                self._log_debug("GenerateImageForm creado exitosamente")
            except Exception as e:
                self._log_warning(
                    f"No se pudo crear GenerateImageForm, usando dict: {e}"
                )
                form = payload

            # Preparar usuario
            user_obj = None
            try:
                if __user__ and Users:
                    user_obj = Users.get_user_by_id(__user__.get("id"))
                    self._log_debug(
                        f"Usuario obtenido: {user_obj.id if hasattr(user_obj, 'id') else 'Unknown'}"
                    )
            except Exception as e:
                self._log_warning(f"No se pudo obtener usuario: {e}")

            await _emit_status("Generando imagen...")

            # ===== LLAMADA PRINCIPAL =====
            self._log_info("🎯 Llamando a image_generations...")
            images = await image_generations(
                request=__request__, form_data=form, user=user_obj
            )

            # Log detallado de la respuesta
            self._log_info(f"📋 Respuesta recibida - Tipo: {type(images)}")
            if self.valves.VERBOSE_LOGGING:
                self._log_debug(f"📄 Respuesta completa: {images}")
            else:
                # Log resumido para debug normal
                if isinstance(images, list):
                    self._log_info(f"📝 Lista con {len(images)} elementos")
                elif isinstance(images, dict):
                    self._log_info(
                        f"📘 Dict con claves: {list(images.keys()) if images else 'Vacío'}"
                    )
                else:
                    self._log_info(f"📄 Valor: {str(images)[:200]}...")

            # ===== PROCESAMIENTO DE RESPUESTA =====
            images_out: List[str] = []

            # Normalizar respuesta
            if images is None:
                raw_items = []
                self._log_warning("⚠️ Respuesta es None - no hay imágenes para procesar")
            elif isinstance(images, list):
                raw_items = images
            else:
                raw_items = [images]

            self._log_info(f"🔄 Procesando {len(raw_items)} elementos")

            for idx, it in enumerate(raw_items):
                self._log_info(f"--- 🖼️ Elemento {idx + 1}/{len(raw_items)} ---")
                self._log_debug(f"Tipo: {type(it)}")

                if self.valves.VERBOSE_LOGGING:
                    self._log_debug(f"Contenido completo: {it}")

                processed_url = None

                if isinstance(it, dict):
                    self._log_debug(f"Dict con claves: {list(it.keys())}")

                    # Buscar en campos prioritarios
                    priority_fields = [
                        "url",
                        "b64",
                        "image",
                        "data",
                        "base64",
                        "file_path",
                        "path",
                        "src",
                        "image_url",
                    ]

                    for field in priority_fields:
                        if field in it and it[field]:
                            value = it[field]
                            self._log_debug(
                                f"Procesando campo '{field}': {str(value)[:100]}..."
                            )

                            if field == "url" or field in ["file_path", "path"]:
                                # Tratar como URL o path
                                try:
                                    path_obj = Path(value)
                                    if path_obj.exists() and path_obj.is_file():
                                        self._log_info(
                                            f"🔄 Campo '{field}' es path local"
                                        )
                                        processed_url = _path_to_data_uri(value)
                                    else:
                                        self._log_info(
                                            f"🌐 Campo '{field}' es URL externa"
                                        )
                                        processed_url = value
                                except Exception:
                                    processed_url = value
                                break

                            elif field in ["b64", "base64"]:
                                # Tratar como base64
                                self._log_info(f"🔤 Campo '{field}' es base64")
                                processed_url = _make_data_uri_from_b64(value)
                                break

                            elif isinstance(value, str) and (
                                value.startswith("data:") or value.startswith("http")
                            ):
                                # Es URL o data URI
                                self._log_info(f"🔗 Campo '{field}' es URL/data URI")
                                processed_url = value
                                break

                    if not processed_url:
                        self._log_warning(f"❌ No se encontró imagen válida en dict")
                        processed_url = json.dumps(it)

                elif isinstance(it, str):
                    self._log_info(f"🔤 Procesando string: {it[:100]}...")

                    try:
                        path_obj = Path(it)
                        if path_obj.exists() and path_obj.is_file():
                            self._log_info("📂 String es path local")
                            processed_url = _path_to_data_uri(it)
                        else:
                            self._log_info("🌐 String es URL/URI")
                            processed_url = it
                    except Exception:
                        processed_url = it
                else:
                    self._log_warning(f"❓ Tipo desconocido: {type(it)}")
                    processed_url = str(it)

                if processed_url:
                    images_out.append(processed_url)
                    self._log_info(f"✅ Elemento {idx + 1} procesado exitosamente")
                else:
                    self._log_error(f"❌ No se pudo procesar elemento {idx + 1}")

            # ===== EMISIÓN DE IMÁGENES =====
            self._log_info(f"🚀 Emitiendo {len(images_out)} imágenes")
            success_count = 0

            for idx, url in enumerate(images_out):
                self._log_info(
                    f"--- 📤 Emitiendo imagen {idx + 1}/{len(images_out)} ---"
                )

                success = await _emit_image(
                    url,
                    payload.get("width"),
                    payload.get("height"),
                    f"imagen_generada_{idx+1}",
                    idx + 1,
                )

                if success:
                    success_count += 1

            # Status y resultado final
            final_message = f"✅ Generación completada: {success_count}/{len(images_out)} imágenes mostradas"
            await _emit_status(final_message, True)
            self._log_info(f"🎉 {final_message}")

            return {
                "success": True,
                "images": images_out,
                "images_emitted": success_count,
                "total_processed": len(images_out),
                "raw": (
                    images
                    if self.valves.VERBOSE_LOGGING
                    else "Oculto - activa VERBOSE_LOGGING para ver"
                ),
                "method": "internal",
                "valves_config": {
                    "debug": self.valves.DEBUG_ENABLED,
                    "verbose": self.valves.VERBOSE_LOGGING,
                    "emit_method": self.valves.EMIT_METHOD_PRIORITY,
                    "user_show_status": show_status,
                    "user_auto_alt": auto_alt_text,
                },
            }

        except Exception as e:
            internal_err = traceback.format_exc()
            self._log_error(f"💥 Error crítico: {str(e)}")
            if self.valves.DEBUG_ENABLED:
                self._log_error(f"Traceback:\n{internal_err}")

            await _emit_status(f"❌ Error: {str(e)}", True)

            return {
                "success": False,
                "error": f"Error interno: {str(e) if 'e' in locals() else 'Desconocido'}",
                "internal_trace": (
                    internal_err
                    if self.valves.DEBUG_ENABLED
                    else "Activa DEBUG_ENABLED en Valves para detalles"
                ),
                "valves_config": {
                    "debug": self.valves.DEBUG_ENABLED,
                    "verbose": self.valves.VERBOSE_LOGGING,
                },
            }

        finally:
            # ===== RESTAURAR CONFIGURACIÓN ORIGINAL =====
            try:
                if original_steps is not None:
                    __request__.app.state.config.IMAGE_STEPS = original_steps
                    self._log_info(f"♻️ Configuración restaurada: {original_steps}")
            except Exception as e:
                self._log_error(f"Error restaurando configuración: {e}")
